using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.FileProviders;

using VideoStudio.Server;

var root = StudioPaths.FindRoot();
var configPath = Path.Combine(root, "config", "appsettings.json");
var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile(configPath, optional: true, reloadOnChange: false);
var settings = StudioPaths.Load(builder.Configuration, root);

Directory.CreateDirectory(settings.RootPath);
Directory.CreateDirectory(Path.Combine(settings.RootPath, "logs"));
Directory.CreateDirectory(settings.DataPath);
foreach (var folder in new[] { "Projects", "Characters", "Scenes", "Images", "Videos", "Audio", "Output", "Temp", "Thumbnails" }) Directory.CreateDirectory(Path.Combine(settings.DataPath, folder));

builder.WebHost.UseUrls("http://127.0.0.1:18080");
builder.WebHost.ConfigureKestrel(options => options.Limits.MaxRequestBodySize = 512L * 1024 * 1024);
builder.Logging.AddProvider(new FileLoggerProvider(Path.Combine(settings.RootPath, "logs")));
builder.Services.AddSingleton(settings);
builder.Services.AddSingleton<StudioDb>();
builder.Services.AddSingleton<StudioRepository>();
builder.Services.AddSingleton<DatabaseInitializer>();
builder.Services.AddSingleton<FfmpegService>();
builder.Services.AddSingleton<WorkflowCatalog>();
builder.Services.AddSingleton<LlmProviderFactory>();
builder.Services.AddSingleton<ScriptAnalyzer>();
builder.Services.AddSingleton<PromptEngine>();
builder.Services.AddSingleton<QualityControlService>();
builder.Services.AddSingleton<VideoQaService>();
builder.Services.AddSingleton<LocalTtsService>();
builder.Services.AddSingleton<SubtitleService>();
builder.Services.AddHttpClient<ComfyUiClient>((_, client) =>
{
    client.BaseAddress = new Uri(settings.ComfyUrl);
    client.Timeout = TimeSpan.FromMinutes(30);
});
builder.Services.AddHttpClient("llm", client => { client.Timeout = TimeSpan.FromMinutes(5); });
builder.Services.AddSingleton<GenerationQueue>();
builder.Services.AddHostedService(sp => sp.GetRequiredService<GenerationQueue>());
builder.Services.AddCors(options => options.AddPolicy("local", policy => policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod()));

var app = builder.Build();
var logger = app.Services.GetRequiredService<ILoggerFactory>().CreateLogger("Startup");
var initializer = app.Services.GetRequiredService<DatabaseInitializer>();
var databaseReady = await initializer.TryInitializeAsync();
if (databaseReady)
{
    try { await app.Services.GetRequiredService<WorkflowCatalog>().ScanAsync(); }
    catch (Exception ex) { logger.LogWarning("初始工作流/模型扫描失败: {Message}", ex.Message); }
}

app.UseCors("local");
app.Use(async (context, next) =>
{
    try { await next(); }
    catch (Exception ex)
    {
        logger.LogError(ex, "请求失败 {Method} {Path}", context.Request.Method, context.Request.Path);
        if (!context.Response.HasStarted)
        {
            context.Response.StatusCode = ex is MySqlConnector.MySqlException ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status500InternalServerError;
            context.Response.ContentType = "application/json; charset=utf-8";
            await context.Response.WriteAsJsonAsync(new { error = ex.Message, database = ex is MySqlConnector.MySqlException });
        }
    }
});

var webDist = Path.Combine(settings.RootPath, "web", "dist");
if (Directory.Exists(webDist))
{
    app.UseDefaultFiles(new DefaultFilesOptions { FileProvider = new PhysicalFileProvider(webDist) });
    app.UseStaticFiles(new StaticFileOptions { FileProvider = new PhysicalFileProvider(webDist) });
}

app.MapGet("/api/health", async (StudioDb db, ComfyUiClient comfy, FfmpegService ffmpeg, CancellationToken ct) =>
{
    var dbOk = await db.CanConnectAsync(ct);
    var comfyStatus = await comfy.CheckAsync(ct);
    return Results.Ok(new { app = "AI Video Studio", version = "1.0.0", now = DateTimeOffset.Now, database = new { online = dbOk }, comfy = comfyStatus, ffmpeg = new { available = ffmpeg.IsAvailable } });
});

app.MapGet("/api/dashboard", async (StudioRepository repo, ComfyUiClient comfy, CancellationToken ct) =>
{
    var counts = await repo.DashboardCountsAsync(ct);
    return Results.Ok(new { counts, comfy = await comfy.CheckAsync(ct), recentTasks = await repo.TasksAsync(12, ct) });
});

app.MapGet("/api/projects", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ProjectsAsync(ct)));
app.MapPost("/api/projects", async (ProjectInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "项目名称不能为空" });
    var id = await repo.CreateProjectAsync(input, ct);
    return Results.Created($"/api/projects/{id}", new { id });
});
app.MapPut("/api/projects/{id:long}", async (long id, ProjectInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateProjectAsync(id, input, ct) }));
app.MapDelete("/api/projects/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteProjectAsync(id, ct) }));

app.MapGet("/api/projects/{projectId:long}/episodes", async (long projectId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.EpisodesAsync(projectId, ct)));
app.MapPost("/api/episodes", async (EpisodeInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (input.ProjectId <= 0 || string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "项目和集名称不能为空" });
    var id = await repo.CreateEpisodeAsync(input, ct);
    return Results.Created($"/api/episodes/{id}", new { id });
});
app.MapGet("/api/episodes/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault(), shots = await repo.ShotsAsync(id, ct) }));
app.MapPut("/api/episodes/{id:long}", async (long id, EpisodeInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateEpisodeAsync(id, input, ct) }));

app.MapGet("/api/characters", async (long? projectId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.CharactersAsync(projectId, ct)));
app.MapPost("/api/characters", async (CharacterInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "角色名称不能为空" });
    var id = await repo.CreateCharacterAsync(input, ct);
    return Results.Created($"/api/characters/{id}", new { id });
});
app.MapPut("/api/characters/{id:long}", async (long id, CharacterInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateCharacterAsync(id, input, ct) }));
app.MapDelete("/api/characters/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteCharacterAsync(id, ct) }));

app.MapPost("/api/characters/{id:long}/references", async (long id, HttpRequest request, StudioSettings studio, StudioRepository repo, CancellationToken ct) =>
{
    var form = await request.ReadFormAsync(ct);
    var file = form.Files.GetFile("file");
    if (file is null || file.Length == 0) return Results.BadRequest(new { error = "请选择参考图" });
    var dir = Path.Combine(studio.DataPath, "Characters", id.ToString()); Directory.CreateDirectory(dir);
    var path = Path.Combine(dir, $"ref_{DateTime.Now:yyyyMMdd_HHmmss}_{Guid.NewGuid().ToString("N")[..8]}{Path.GetExtension(file.FileName).ToLowerInvariant()}");
    await using (var stream = File.Create(path)) await file.CopyToAsync(stream, ct);
    var reference = new ReferenceInput { Kind = form["kind"].FirstOrDefault() ?? "identity", IsAnchor = string.Equals(form["isAnchor"].FirstOrDefault(), "true", StringComparison.OrdinalIgnoreCase) };
    var refId = await repo.AddCharacterReferenceAsync(id, path, reference, ct);
    return Results.Ok(new { id = refId, path });
});

app.MapGet("/api/scenes", async (long? projectId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ScenesAsync(projectId, ct)));
app.MapPost("/api/scenes", async (SceneInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "场景名称不能为空" });
    var id = await repo.CreateSceneAsync(input, ct);
    return Results.Created($"/api/scenes/{id}", new { id });
});
app.MapPut("/api/scenes/{id:long}", async (long id, SceneInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateSceneAsync(id, input, ct) }));
app.MapDelete("/api/scenes/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteSceneAsync(id, ct) }));
app.MapPost("/api/scenes/{id:long}/references", async (long id, HttpRequest request, StudioSettings studio, StudioRepository repo, CancellationToken ct) =>
{
    var form = await request.ReadFormAsync(ct); var file = form.Files.GetFile("file");
    if (file is null || file.Length == 0) return Results.BadRequest(new { error = "请选择场景参考图" });
    var dir = Path.Combine(studio.DataPath, "Scenes", id.ToString()); Directory.CreateDirectory(dir);
    var path = Path.Combine(dir, $"ref_{DateTime.Now:yyyyMMdd_HHmmss}_{Guid.NewGuid().ToString("N")[..8]}{Path.GetExtension(file.FileName).ToLowerInvariant()}");
    await using (var stream = File.Create(path)) await file.CopyToAsync(stream, ct);
    var refId = await repo.AddSceneReferenceAsync(id, path, new ReferenceInput { Kind = form["kind"].FirstOrDefault() ?? "master", IsAnchor = string.Equals(form["isAnchor"].FirstOrDefault(), "true", StringComparison.OrdinalIgnoreCase) }, ct);
    return Results.Ok(new { id = refId, path });
});

app.MapGet("/api/episodes/{episodeId:long}/shots", async (long episodeId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ShotsAsync(episodeId, ct)));
app.MapPost("/api/shots", async (ShotInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (input.ProjectId <= 0 || input.EpisodeId <= 0 || string.IsNullOrWhiteSpace(input.Title)) return Results.BadRequest(new { error = "镜头项目、集和标题不能为空" });
    var id = await repo.CreateShotAsync(input, ct);
    return Results.Created($"/api/shots/{id}", new { id });
});
app.MapPut("/api/shots/{id:long}", async (long id, ShotInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateShotAsync(id, input, ct) }));
app.MapDelete("/api/shots/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteShotAsync(id, ct) }));
app.MapPost("/api/episodes/{episodeId:long}/shots/reorder", async (long episodeId, ReorderInput input, StudioRepository repo, CancellationToken ct) => { await repo.ReorderShotsAsync(episodeId, input.ShotIds, ct); return Results.Ok(new { reordered = input.ShotIds.Count }); });

app.MapGet("/api/workflows", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.WorkflowsAsync(ct)));
app.MapPost("/api/workflows/scan", async (WorkflowCatalog catalog, CancellationToken ct) => Results.Ok(new { scanned = await catalog.ScanAsync(ct) }));
app.MapGet("/api/models", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ModelsAsync(ct)));
app.MapGet("/api/loras", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.LorasAsync(ct)));

app.MapGet("/api/assets", async (long? projectId, string? type, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.AssetsAsync(projectId, type, ct)));
app.MapGet("/api/media", (string path, StudioSettings studio) =>
{
    var full = Path.GetFullPath(path);
    var allowed = Path.GetFullPath(@"C:\install\AI");
    if (!full.StartsWith(allowed, StringComparison.OrdinalIgnoreCase) || !File.Exists(full)) return Results.NotFound();
    return Results.File(full, ContentTypeFor(full), enableRangeProcessing: true);
});

app.MapGet("/api/tasks", async (int? limit, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.TasksAsync(limit ?? 100, ct)));
app.MapGet("/api/tasks/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { task = (await repo.TaskAsync(id, ct)).FirstOrDefault(), results = await repo.ResultsAsync(id, ct) }));
app.MapPost("/api/tasks", async (TaskInput input, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.TaskType)) return Results.BadRequest(new { error = "任务类型不能为空" });
    var id = await repo.CreateTaskAsync(input, ct); queue.Enqueue(id);
    return Results.Accepted($"/api/tasks/{id}", new { id, status = "Pending" });
});
app.MapPost("/api/tasks/{id:long}/cancel", async (long id, GenerationQueue queue, CancellationToken ct) => { await queue.CancelAsync(id, ct); return Results.Ok(new { id, status = "Cancelled" }); });
app.MapPost("/api/tasks/{id:long}/retry", async (long id, StudioRepository repo, GenerationQueue queue, CancellationToken ct) => { await repo.ResetTaskForRetryAsync(id, ct); queue.Enqueue(id); return Results.Ok(new { id, status = "Pending" }); });
app.MapPost("/api/tasks/{id:long}/rerun", async (long id, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
{
    var old = (await repo.TaskAsync(id, ct)).FirstOrDefault(); if (old is null) return Results.NotFound();
    using var original = old.Json("inputJson");
    var parameters = original.RootElement.TryGetProperty("parameters", out var p) ? p.Clone() : JsonDocument.Parse("{}").RootElement.Clone();
    var newId = await repo.CreateTaskAsync(new TaskInput { ProjectId = old.LongOrNull("projectId"), EpisodeId = old.LongOrNull("episodeId"), ShotId = old.LongOrNull("shotId"), TaskType = old.Text("taskType") ?? "Image", Priority = old.Int("priority"), MaxRetries = old.Int("maxRetries", 2), WorkflowId = old.LongOrNull("workflowId"), InputImagePath = original.RootElement.TryGetProperty("inputImagePath", out var inputPath) ? inputPath.GetString() : null, Parameters = parameters }, ct);
    queue.Enqueue(newId); return Results.Accepted($"/api/tasks/{newId}", new { id = newId, status = "Pending", sourceTaskId = id });
});
app.MapPost("/api/shots/{shotId:long}/ab", async (long shotId, AbInput input, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
{
    if (input.Variants.Count < 2) return Results.BadRequest(new { error = "A/B 至少需要两个参数变体" });
    var ids = new List<long>();
    foreach (var variant in input.Variants)
    {
        var id = await repo.CreateTaskAsync(new TaskInput { ProjectId = input.ProjectId, EpisodeId = input.EpisodeId, ShotId = shotId, TaskType = input.TaskType, WorkflowId = input.WorkflowId, InputImagePath = input.InputImagePath, Parameters = variant }, ct);
        queue.Enqueue(id); ids.Add(id);
    }
    return Results.Accepted("/api/tasks", new { ids, count = ids.Count });
});
app.MapPost("/api/episodes/{episodeId:long}/concat", async (long episodeId, StudioRepository repo, GenerationQueue queue, StudioSettings studio, CancellationToken ct) =>
{
    var shots = await repo.ShotsAsync(episodeId, ct);
    var files = shots.Select(x => x.Text("resultPath")).Where(x => !string.IsNullOrWhiteSpace(x) && File.Exists(x)).ToArray();
    if (files.Length == 0) return Results.BadRequest(new { error = "本集没有可拼接的镜头结果" });
    using var parametersDoc = JsonDocument.Parse(JsonSerializer.Serialize(new { files, outputName = $"episode_{episodeId}_{DateTime.Now:yyyyMMdd_HHmmss}.mp4" }));
    var taskId = await repo.CreateTaskAsync(new TaskInput { EpisodeId = episodeId, TaskType = "Concat", Parameters = parametersDoc.RootElement.Clone() }, ct); queue.Enqueue(taskId);
    return Results.Accepted($"/api/tasks/{taskId}", new { id = taskId, files = files.Length });
});

ProductionEndpoints.Map(app);
VideoQaEndpoints.Map(app);

app.MapGet("/api/system/settings", (StudioSettings studio) => Results.Ok(new { root = studio.RootPath, data = studio.DataPath, models = studio.ModelsPath, workflows = studio.WorkflowsPath, comfyUrl = studio.ComfyUrl, comfyRoot = studio.ComfyRoot, ffmpeg = studio.FfmpegPath, database = new { host = studio.DatabaseHost, port = studio.DatabasePort, name = studio.DatabaseName, user = studio.DatabaseUser }, queue = new { concurrency = 1, minFreeVramMiB = studio.MinFreeVramMiB } }));

if (Directory.Exists(webDist))
{
    app.MapFallback(async context =>
    {
        if (context.Request.Path.StartsWithSegments("/api") || context.Request.Path.StartsWithSegments("/media")) { context.Response.StatusCode = 404; return; }
        var index = Path.Combine(webDist, "index.html");
        if (File.Exists(index)) await context.Response.SendFileAsync(index);
        else context.Response.StatusCode = 404;
    });
}

await app.RunAsync();

static string ContentTypeFor(string path) => Path.GetExtension(path).ToLowerInvariant() switch
{
    ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp", ".mp4" => "video/mp4", ".mov" => "video/quicktime", ".wav" => "audio/wav", ".mp3" => "audio/mpeg", _ => "application/octet-stream"
};

public sealed class AbInput
{
    public long? ProjectId { get; set; }
    public long? EpisodeId { get; set; }
    public string TaskType { get; set; } = "ImageToVideo";
    public long? WorkflowId { get; set; }
    public string? InputImagePath { get; set; }
    public List<JsonElement> Variants { get; set; } = [];
}
