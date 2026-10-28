using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.FileProviders;

using VideoStudio.Server;

if(args.Length>0&&args[0]=="--character-story-legacy-headshot-self-test")
{
    Environment.ExitCode=await CharacterStoryLegacyHeadshotSelfTest.RunAsync();return;
}

if(args.Length>0&&args[0]=="--character-prompt-self-test")
{
    Environment.ExitCode=CharacterReferencePrompts.SelfTest();return;
}

if(args.Length>0&&args[0]=="--character-scene-self-test")
{
    Environment.ExitCode=await CharacterSceneSelfTest.RunAsync();return;
}
if(args.Length>0&&args[0]=="--character-story-reference-self-test")
{
    Environment.ExitCode=await CharacterStorySelfTest.ReferencesAsync();return;
}
if(args.Length>0&&args[0]=="--character-story-contract-self-test")
{
    Environment.ExitCode=await CharacterStorySelfTest.ContractsAsync();return;
}
if(args.Length>0&&args[0]=="--character-story-self-test")
{
    Environment.ExitCode=await CharacterStorySelfTest.RunAsync();return;
}
if (args.Length > 0 && args[0] == "--character-library-self-test")
{
    Environment.ExitCode = CharacterLibrarySelfTest.Run();
    return;
}

if (args.Length > 0 && string.Equals(args[0], "--stage12-self-test", StringComparison.Ordinal))
{
    Environment.ExitCode = await Stage12SelfTest.RunAsync();
    return;
}
if (args.Length >= 3 && string.Equals(args[0], "--stage12-gpu-probe", StringComparison.Ordinal))
{
    await Stage12GpuProbe.RunAsync(args[1], args[2], args.ElementAtOrDefault(3));
    return;
}
if (args.Length > 0 && args[0].StartsWith("--stage3b-", StringComparison.Ordinal))
{
    Environment.ExitCode = await Stage3BFormalHarness.RunAsync(args);
    return;
}
if (args.Length >= 2 && args[0].StartsWith("--stage25-", StringComparison.Ordinal))
{
    Environment.ExitCode = await Stage25DatabaseHarness.RunAsync(args);
    return;
}
if (args.Length > 0 && string.Equals(args[0], "--workflow-contract-self-test", StringComparison.Ordinal))
{
    Environment.ExitCode = await WorkflowContractSelfTest.RunAsync();
    return;
}
if (args.Length > 0 && string.Equals(args[0], "--reference-metadata-self-test", StringComparison.Ordinal))
{
    Environment.ExitCode = ReferenceMetadataSelfTest.Run();
    return;
}

var root = StudioPaths.FindRoot();
var configPath = Path.Combine(root, "config", "appsettings.json");
var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile(configPath, optional: true, reloadOnChange: false);
var settings = StudioPaths.Load(builder.Configuration, root);
if (args.Contains("--reset-local-admin", StringComparer.Ordinal))
{
    if (!Console.IsInputRedirected) throw new InvalidOperationException("Password must be supplied through standard input");
    var maintenanceDb = new StudioDb(settings, Microsoft.Extensions.Logging.Abstractions.NullLogger<StudioDb>.Instance);
    if (Convert.ToInt32(await maintenanceDb.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running')")) > 0)
        throw new InvalidOperationException("Active tasks block password maintenance; wait for the queue to become idle");
    var maintenanceAuth = new LocalAuthService(settings, new StudioRepository(maintenanceDb, Microsoft.Extensions.Logging.Abstractions.NullLogger<StudioRepository>.Instance), Microsoft.Extensions.Logging.Abstractions.NullLogger<LocalAuthService>.Instance);
    var maintenancePassword = await Console.In.ReadLineAsync() ?? "";
    await maintenanceAuth.ResetLocalPasswordAsync("admin", maintenancePassword);
    await maintenanceDb.ExecuteAsync("UPDATE admin_sessions SET revoked_at=NOW(3) WHERE revoked_at IS NULL");
    Console.WriteLine("Administrator password reset; existing sessions revoked. Restart the service to apply.");
    return;
}
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.PropertyNameCaseInsensitive = true);

Directory.CreateDirectory(settings.RootPath);
Directory.CreateDirectory(Path.Combine(settings.RootPath, "logs"));
Directory.CreateDirectory(settings.DataPath);
foreach (var folder in new[] { "Projects", "Characters", "Scenes", "Images", "Videos", "Audio", "Output", "Temp", "Thumbnails" }) Directory.CreateDirectory(Path.Combine(settings.DataPath, folder));

var listenUrl = Environment.GetEnvironmentVariable("AI_VIDEO_STUDIO_LISTEN_URL");
if (!settings.RequireLocalLogin)
    foreach (var address in (string.IsNullOrWhiteSpace(listenUrl) ? "http://127.0.0.1:18080" : listenUrl).Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        _ = StudioPaths.NormalizeLoopbackHttpUrl(address);
builder.WebHost.UseUrls(string.IsNullOrWhiteSpace(listenUrl) ? "http://127.0.0.1:18080" : listenUrl);
builder.WebHost.ConfigureKestrel(options => options.Limits.MaxRequestBodySize = 512L * 1024 * 1024);
var logDirectory = Path.Combine(settings.RootPath, "logs");
var isolatedLogDirectory = Environment.GetEnvironmentVariable("AI_VIDEO_STUDIO_LOG_DIRECTORY");
if (!string.IsNullOrWhiteSpace(isolatedLogDirectory))
{
    var candidate = Path.GetFullPath(isolatedLogDirectory);
    var dataPrefix = Path.GetFullPath(settings.DataPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
    if (!candidate.StartsWith(dataPrefix, StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("Isolated service logs must remain under the governed Data root");
    logDirectory = candidate;
}
builder.Logging.AddProvider(new FileLoggerProvider(logDirectory));
builder.Services.AddSingleton(settings);
builder.Services.AddSingleton<StudioDb>();
builder.Services.AddSingleton<StudioRepository>();
builder.Services.AddSingleton<ProductionCoreRepository>();
builder.Services.AddSingleton<TaskLeaseRepository>();
builder.Services.AddSingleton<DatabaseInitializer>();
builder.Services.AddSingleton<LocalAuthService>();
builder.Services.AddSingleton<FfmpegService>();
builder.Services.AddSingleton<AssetPathPolicy>();
builder.Services.AddSingleton<AssetReferenceResolver>();
builder.Services.AddSingleton<DiskSpaceGuard>();
builder.Services.AddSingleton<CacheCleanupService>();
builder.Services.AddSingleton<TaskArtifactService>();
builder.Services.AddSingleton<GpuGlobalGate>();
builder.Services.AddSingleton<WorkflowContractService>();
builder.Services.AddSingleton<CharacterReferenceGateService>();
builder.Services.AddSingleton<CharacterLibraryService>();
builder.Services.AddSingleton<CharacterStoryStore>();
builder.Services.AddSingleton<CharacterSceneService>();
builder.Services.AddSingleton<CharacterStoryService>();
builder.Services.AddSingleton<CharacterWorkshopService>();
builder.Services.AddSingleton<ReleaseEligibilityService>();
builder.Services.AddSingleton<ReleaseCandidateRepository>();
builder.Services.AddSingleton<FormalTaskSubmissionService>();
builder.Services.AddSingleton<WorkflowCatalog>();
builder.Services.AddSingleton<LlmEndpointPolicy>();
builder.Services.AddSingleton<LlmEgressAuditService>();
builder.Services.AddSingleton<LlmProviderFactory>();
builder.Services.AddSingleton<ScriptAnalyzer>();
builder.Services.AddSingleton<PromptEngine>();
builder.Services.AddSingleton<QualityControlService>();
builder.Services.AddSingleton<FaceQualityService>();
builder.Services.AddSingleton<QualityPreflightService>();
builder.Services.AddSingleton<CharacterQualityService>();
builder.Services.AddSingleton<ModelRouter>();
builder.Services.AddSingleton<TaskSubmissionPreflightService>();
builder.Services.AddSingleton<VideoQaService>();
builder.Services.AddSingleton<LocalTtsService>();
builder.Services.AddSingleton<MiniMaxLocalService>();
builder.Services.AddSingleton<SeedVr2Service>();
builder.Services.AddSingleton<SubtitleService>();
builder.Services.AddHttpClient<ComfyUiClient>((_, client) =>
{
    client.BaseAddress = new Uri(settings.ComfyUrl);
    client.Timeout = TimeSpan.FromMinutes(30);
    client.MaxResponseContentBufferSize = 32 * 1024 * 1024;
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
{
    AllowAutoRedirect = false,
    MaxResponseHeadersLength = 32
});
builder.Services.AddHttpClient("llm", client =>
{
    client.Timeout = TimeSpan.FromMinutes(5);
    client.MaxResponseContentBufferSize = 2 * 1024 * 1024;
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
{
    AllowAutoRedirect = false,
    MaxResponseHeadersLength = 32
});
builder.Services.AddSingleton<GenerationQueue>();
if (settings.WorkerEnabled) builder.Services.AddHostedService(sp => sp.GetRequiredService<GenerationQueue>());
builder.Services.AddCors(options => options.AddPolicy("local", policy => policy
    .WithOrigins("http://127.0.0.1:18080", "http://localhost:18080", "http://127.0.0.1:18081", "http://localhost:18081")
    .AllowAnyHeader()
    .AllowAnyMethod()
    .AllowCredentials()));

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
            var isDatabaseError = ex is MySqlConnector.MySqlException;
            var isIdempotencyConflict = ex is IdempotencyConflictException;
            var requestId = context.TraceIdentifier;
            context.Response.StatusCode = isIdempotencyConflict ? StatusCodes.Status409Conflict : isDatabaseError ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status500InternalServerError;
            context.Response.ContentType = "application/json; charset=utf-8";
            await context.Response.WriteAsJsonAsync(new { error = isIdempotencyConflict ? ex.Message : isDatabaseError ? "数据库服务暂不可用" : "服务器内部错误", database = isDatabaseError, requestId });
        }
    }
});

app.MapStage12Endpoints();
app.MapLlmEndpoints();
app.MapMiniMaxLocalEndpoints();

app.Use(async (context, next) =>
{
    var path = context.Request.Path;
    if (!path.StartsWithSegments("/api") || HttpMethods.IsOptions(context.Request.Method) || LocalAuthService.IsAnonymousApiPath(path))
    {
        await next();
        return;
    }

    var auth = context.RequestServices.GetRequiredService<LocalAuthService>();
    var requiresCsrf = !HttpMethods.IsGet(context.Request.Method) && !HttpMethods.IsHead(context.Request.Method);
    var decision = await auth.AuthenticateAsync(context, requiresCsrf, context.RequestAborted);
    if (!decision.Allowed)
    {
        await auth.RejectAsync(context, decision, context.RequestAborted);
        return;
    }

    context.Items[LocalAuthService.PrincipalItemKey] = decision.Principal!;
    try
    {
        await next();
        if (requiresCsrf)
            await auth.AuditRequestAsync(context, decision.Principal, context.Response.StatusCode is >= 200 and < 400 ? "Succeeded" : "Rejected", new { statusCode = context.Response.StatusCode }, context.RequestAborted);
    }
    catch
    {
        if (requiresCsrf)
            await auth.AuditRequestAsync(context, decision.Principal, "Failed", new { statusCode = StatusCodes.Status500InternalServerError }, CancellationToken.None);
        throw;
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
app.MapGet("/api/maintenance/cache-cleanup/preview", async (CacheCleanupService cleanup, CancellationToken ct)
    => Results.Ok(await cleanup.PreviewAsync(ct: ct)));

app.MapGet("/api/auth/status", async (HttpContext context, LocalAuthService auth, CancellationToken ct) =>
{
    var status = await auth.StatusAsync(context, ct);
    if ((status.Authenticated || !status.LoginRequired) && !string.IsNullOrWhiteSpace(status.CsrfToken) && status.ExpiresAt is { } expiresAt)
        auth.SetCsrfCookie(context, status.CsrfToken, expiresAt);
    return Results.Ok(status);
});
app.MapPost("/api/auth/setup", async (HttpContext context, LocalAdminSetupInput input, LocalAuthService auth, CancellationToken ct) =>
{
    var result = await auth.SetupAsync(context, input, ct);
    if (!result.Succeeded) return Results.Json(new { error = result.Error, code = result.Outcome, requestId = context.TraceIdentifier }, statusCode: result.StatusCode);
    auth.SetSessionCookies(context, result.SessionToken!, result.CsrfToken!, result.Principal!.ExpiresAt);
    return Results.Ok(new { username = result.Principal.Username, role = result.Principal.Role, csrfToken = result.CsrfToken, expiresAt = result.Principal.ExpiresAt });
});
app.MapPost("/api/auth/login", async (HttpContext context, LocalLoginInput input, LocalAuthService auth, CancellationToken ct) =>
{
    var result = await auth.LoginAsync(context, input, ct);
    if (!result.Succeeded) return Results.Json(new { error = result.Error, code = result.Outcome, requestId = context.TraceIdentifier }, statusCode: result.StatusCode);
    auth.SetSessionCookies(context, result.SessionToken!, result.CsrfToken!, result.Principal!.ExpiresAt);
    return Results.Ok(new { username = result.Principal.Username, role = result.Principal.Role, csrfToken = result.CsrfToken, expiresAt = result.Principal.ExpiresAt });
});
app.MapPost("/api/auth/logout", async (HttpContext context, LocalAuthService auth, CancellationToken ct) =>
{
    var principal = auth.CurrentPrincipal(context);
    if (principal is null) return Results.Unauthorized();
    await auth.LogoutAsync(context, principal, ct);
    return Results.Ok(new { signedOut = true });
});
app.MapGet("/api/auth/audit", async (int? limit, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.SecurityAuditEventsAsync(limit ?? 50, ct)));

app.MapGet("/api/dashboard", async (StudioRepository repo, ComfyUiClient comfy, AssetPathPolicy paths, CancellationToken ct) =>
{
    var counts = await repo.DashboardCountsAsync(ct);
    return Results.Ok(new { counts, comfy = await comfy.CheckAsync(ct), recentTasks = (await repo.TasksAsync(12, ct, recentFirst: true)).Select(task => ToPublicTask(task, paths)) });
});

app.MapGet("/api/projects", async (StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => Results.Ok((await repo.ProjectsAsync(ct)).Select(project => ToPublicProject(project, paths))));
app.MapPost("/api/projects", async (ProjectInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "项目名称不能为空" });
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    if (!TryNormalizeOptionalAssetPath(input.BgmPath, paths, out var bgmPath)) return Results.BadRequest(new { error = "项目 BGM 必须是受控数据目录中的媒体" });
    input.BgmPath = bgmPath;
    var id = await repo.CreateProjectAsync(input, ct);
    return Results.Created($"/api/projects/{id}", new { id });
});
app.MapPut("/api/projects/{id:long}", async (long id, ProjectInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    if (!TryNormalizeOptionalAssetPath(input.BgmPath, paths, out var bgmPath)) return Results.BadRequest(new { error = "项目 BGM 必须是受控数据目录中的媒体" });
    input.BgmPath = bgmPath;
    return Results.Ok(new { updated = await repo.UpdateProjectAsync(id, input, ct) });
});
app.MapDelete("/api/projects/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteProjectAsync(id, ct) }));

app.MapGet("/api/projects/{projectId:long}/episodes", async (long projectId, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => Results.Ok((await repo.EpisodesAsync(projectId, ct)).Select(episode => ToPublicEpisode(episode, paths))));
app.MapPost("/api/episodes", async (EpisodeInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (input.ProjectId <= 0 || string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "项目和集名称不能为空" });
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    var id = await repo.CreateEpisodeAsync(input, ct);
    return Results.Created($"/api/episodes/{id}", new { id });
});
app.MapGet("/api/episodes/{id:long}", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
    if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
    return Results.Ok(new { episode = ToPublicEpisode(episode, paths), shots = (await repo.ShotsAsync(id, ct)).Select(shot => ToPublicShot(shot, paths)) });
});
app.MapGet("/api/episodes/{id:long}/output", async (long id, StudioRepository repo, FfmpegService ffmpeg, AssetPathPolicy paths, ReleaseEligibilityService release, CancellationToken ct) =>
{
    var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
    if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });

    var shots = (await repo.ShotsAsync(id, ct)).OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))).ToArray();
    var qualityGate = await EpisodeQualityGateEvaluator.EvaluateAsync(episode, shots, repo, ffmpeg, paths, ct);
    var releaseEligibility = await release.EvaluateAsync(episode, shots, repo, ffmpeg, paths, null, ct);
    var currentSources = shots.Select(shot =>
    {
        var path = ResolveEpisodeSourceVideoPath(shot, paths);
        return new { shotId = shot.Long("id"), shotNumber = shot.Int("shotNumber"), title = shot.Text("title") ?? $"镜头 {shot.Int("shotNumber")}", status = shot.Text("status") ?? "Draft", path, ready = path is not null };
    }).ToArray();
    var currentFiles = currentSources.Where(x => x.ready && x.path is not null).Select(x => x.path!).ToArray();
    var missingSources = currentSources.Where(x => !x.ready).ToArray();
    var shotStarts = new Dictionary<long, double>();
    var shotCursor = 0d;
    foreach (var shot in shots)
    {
        shotStarts[shot.Long("id")] = shotCursor;
        shotCursor += Math.Max(1, Convert.ToDouble(shot.Decimal("durationSeconds", 5)));
    }
    var currentAudioTracks = new List<string>();
    var voiceVolume = (double)episode.Decimal("voiceVolume", 1);
    var bgmVolume = (double)episode.Decimal("bgmVolume", .18m);
    var sfxVolume = (double)episode.Decimal("sfxVolume", .6m);
    foreach (var audio in await repo.EpisodeAudioResultsAsync(id, ct))
    {
        var path = audio.Text("path");
        if (!paths.TryResolveExisting(path, out var fullPath, out _)) continue;
        var start = audio.LongOrNull("shotId") is { } shotId && shotStarts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
        currentAudioTracks.Add(EpisodeRenderAudioTrackKey(fullPath, voiceVolume, start));
    }
    foreach (var effect in await repo.EpisodeSoundEffectsAsync(id, ct))
    {
        var path = effect.Text("path");
        if (!paths.TryResolveExisting(path, out var fullPath, out _)) continue;
        var start = effect.LongOrNull("shotId") is { } shotId && shotStarts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
        currentAudioTracks.Add(EpisodeRenderAudioTrackKey(fullPath, Math.Clamp((double)effect.Decimal("volume", .6m) * sfxVolume, .05, 2), start + (double)effect.Decimal("startSeconds", 0)));
    }
    foreach (var bgm in await repo.EpisodeBgmAsync(id, ct))
    {
        var path = bgm.Text("path");
        if (!paths.TryResolveExisting(path, out var fullPath, out _)) continue;
        currentAudioTracks.Add(EpisodeRenderAudioTrackKey(fullPath, Math.Clamp((double)bgm.Decimal("volume", .18m) * bgmVolume, .05, 2), 0));
    }
    var currentSubtitlePath = paths.TryResolveExisting(episode.Text("subtitlePath"), out var currentSubtitleFullPath, out _)
        ? currentSubtitleFullPath
        : null;

    var historyRows = await repo.EpisodeRenderHistoryAsync(id, ct);
    var history = new List<(Dictionary<string, object?> Row, FfmpegProbe? Probe, string[] SourceFiles, JsonElement? SourceSnapshot, int Version)>();
    for (var index = 0; index < historyRows.Count; index++)
    {
        var row = historyRows[index];
        var path = row.Text("outputPath");
        var probe = paths.TryResolveExisting(path, out var fullPath, out _) ? await ffmpeg.ProbeAsync(fullPath, ct) : null;
        history.Add((row, probe, EpisodeRenderFilesFromInput(row.Text("inputJson")), EpisodeRenderSourceSnapshotFromInput(row.Text("inputJson"), paths), EpisodeRenderVersionFromInput(row.Text("inputJson")) ?? historyRows.Count - index));
    }

    var versions = history.Select(item => new
    {
        taskId = item.Row.Long("taskId"),
        version = item.Version,
        status = item.Row.Text("status") ?? "Pending",
        progress = item.Row.Decimal("progress"),
        errorMessage = item.Row.Text("errorMessage"),
        createdAt = item.Row["createdAt"],
        startedAt = item.Row["startedAt"],
        finishedAt = item.Row["finishedAt"],
        durationMs = item.Row.LongOrNull("durationMs"),
        outputPath = paths.TryResolveExisting(item.Row.Text("outputPath"), out _, out var outputAssetPath) ? outputAssetPath : null,
        assetPath = string.IsNullOrWhiteSpace(outputAssetPath) ? null : outputAssetPath,
        mediaUrl = string.IsNullOrWhiteSpace(outputAssetPath) ? null : $"/api/media?assetPath={Uri.EscapeDataString(outputAssetPath)}",
        exists = item.Probe is not null,
        actual = item.Probe,
        sourceShotCount = item.SourceFiles.Length,
        sourceSnapshot = item.SourceSnapshot,
        preview = EpisodeRenderBoolFromInput(item.Row.Text("inputJson"), "preview")
    }).ToArray();
    var activeTask = versions.FirstOrDefault(x => x.status is "Pending" or "Running");
    var latestSuccessful = versions.FirstOrDefault(x => x.status == "Succeeded" && x.exists);
    var latestFormalSuccessful = versions.FirstOrDefault(x => x.status == "Succeeded" && x.exists && !x.preview);
    var latestFailure = versions.FirstOrDefault(x => x.status == "Failed");
    var outputPath = latestFormalSuccessful?.outputPath;
    if (outputPath is null && paths.TryResolveExisting(episode.Text("outputPath"), out _, out var episodeOutputAssetPath)) outputPath = episodeOutputAssetPath;
    var outputProbe = latestFormalSuccessful?.actual;
    if (outputProbe is null && paths.TryResolveExisting(episode.Text("outputPath"), out var episodeOutputFullPath, out _)) outputProbe = await ffmpeg.ProbeAsync(episodeOutputFullPath, ct);
    var latestSuccessfulInput = latestSuccessful is null
        ? null
        : history.First(x => x.Row.Long("taskId") == latestSuccessful.taskId).Row.Text("inputJson");
    var latestFormalInput = latestFormalSuccessful is null
        ? null
        : history.First(x => x.Row.Long("taskId") == latestFormalSuccessful.taskId).Row.Text("inputJson");
    var latestSuccessfulIsPreview = EpisodeRenderBoolFromInput(latestSuccessfulInput, "preview");
    var renderedFiles = EpisodeRenderFilesFromInput(latestFormalInput);
    var renderedAudioTracks = EpisodeRenderAudioTracksFromInput(latestFormalInput);
    var renderedSubtitlePath = EpisodeRenderStringFromInput(latestFormalInput, "subtitlePath");
    var targetChanged = EpisodeRenderIntFromInput(latestFormalInput, "targetWidth") != episode.Int("outputWidth", 1920)
        || EpisodeRenderIntFromInput(latestFormalInput, "targetHeight") != episode.Int("outputHeight", 1080)
        || EpisodeRenderIntFromInput(latestFormalInput, "targetFps") != episode.Int("outputFps", 30);
    var isStale = latestFormalSuccessful is not null &&
        (!SameEpisodeSourceFiles(currentFiles, renderedFiles)
        || !SameEpisodeSourceFiles(currentAudioTracks, renderedAudioTracks)
        || !SameEpisodePath(currentSubtitlePath, renderedSubtitlePath)
        || targetChanged);
    var outputStatus = activeTask is not null ? "Rendering"
        : latestSuccessful is not null ? (latestSuccessfulIsPreview ? (isStale ? "PreviewStale" : "PreviewReady") : (isStale ? "Stale" : "Ready"))
        : latestFailure is not null ? "Failed" : "Empty";

    return Results.Ok(new
    {
        episodeId = id,
        status = episode.Text("status") ?? "Draft",
        outputStatus,
        outputPath,
        assetPath = outputPath,
        mediaUrl = outputPath is not null ? $"/api/media?assetPath={Uri.EscapeDataString(outputPath)}" : null,
        exists = outputProbe is not null,
        target = new { width = episode.Int("outputWidth", 1920), height = episode.Int("outputHeight", 1080), fps = episode.Int("outputFps", 30) },
        actual = outputProbe,
        canRender = activeTask is null && qualityGate.FormalReady && currentSources.Length > 0 && missingSources.Length == 0,
        canPreview = activeTask is null && qualityGate.PreviewReady && currentSources.Length > 0 && missingSources.Length == 0,
        qualityGate,
        releaseEligibility = new
        {
            technicalStatus = releaseEligibility.TechnicalStatus,
            contentStatus = releaseEligibility.ContentStatus,
            releaseEligibility.ReleaseEligibility,
            canCreateCandidate = releaseEligibility.CanCreateCandidate,
            blockingReasons = releaseEligibility.BlockingReasons
        },
        renderBlockedReason = currentSources.Length == 0 ? "请先添加镜头" : missingSources.Length > 0 ? $"还有 {missingSources.Length} 个镜头没有可播放的正式视频" : null,
        formalBlockedReason = qualityGate.FormalReady ? null : string.Join("；", qualityGate.FormalBlockedReasons),
        previewBlockedReason = qualityGate.PreviewReady ? null : "没有可播放的镜头视频",
        activeTask,
        latestVersion = latestSuccessful,
        latestFormalVersion = latestFormalSuccessful,
        latestFailure = latestFailure is null ? null : new { latestFailure.taskId, latestFailure.version, latestFailure.errorMessage, latestFailure.finishedAt },
        isStale,
        source = new { total = currentSources.Length, ready = currentFiles.Length, audioTracks = currentAudioTracks.Count, missing = missingSources },
        versions
    });
});
app.MapPut("/api/episodes/{id:long}", async (long id, EpisodeInput input, StudioRepository repo, CancellationToken ct) =>
{
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    return Results.Ok(new { updated = await repo.UpdateEpisodeAsync(id, input, ct) });
});

app.MapGet("/api/characters", async (long? projectId, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => Results.Ok((await repo.CharactersAsync(projectId, ct)).Select(character => ToPublicCharacter(character, paths))));
app.MapPost("/api/characters", async (CharacterInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "角色名称不能为空" });
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    if (!TryNormalizeOptionalAssetPath(input.AnchorPath, paths, out var anchorPath)) return Results.BadRequest(new { error = "角色锚点必须通过参考图上传或引用受控媒体" });
    if (!TryNormalizeOptionalModelPath(input.EmbeddingPath, paths, out var embeddingPath) || !TryNormalizeOptionalModelPath(input.LoraPath, paths, out var loraPath)) return Results.BadRequest(new { error = "角色 Embedding/LoRA 必须引用受控模型目录中的已存在文件" });
    input.AnchorPath = anchorPath;
    input.EmbeddingPath = embeddingPath;
    input.LoraPath = loraPath;
    var id = await repo.CreateCharacterAsync(input, ct);
    return Results.Created($"/api/characters/{id}", new { id });
});
app.MapPut("/api/characters/{id:long}", async (long id, CharacterInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    if (!TryNormalizeOptionalAssetPath(input.AnchorPath, paths, out var anchorPath)) return Results.BadRequest(new { error = "角色锚点必须通过参考图上传或引用受控媒体" });
    if (!TryNormalizeOptionalModelPath(input.EmbeddingPath, paths, out var embeddingPath) || !TryNormalizeOptionalModelPath(input.LoraPath, paths, out var loraPath)) return Results.BadRequest(new { error = "角色 Embedding/LoRA 必须引用受控模型目录中的已存在文件" });
    input.AnchorPath = anchorPath;
    input.EmbeddingPath = embeddingPath;
    input.LoraPath = loraPath;
    return Results.Ok(new { updated = await repo.UpdateCharacterAsync(id, input, ct) });
});
app.MapDelete("/api/characters/{id:long}", async (long id, CharacterLibraryService library, CancellationToken ct) =>
{
    try { return Results.Ok(new { deleted = await library.DeleteUnversionedCharacterAsync(id, ct) }); }
    catch (AssetValidationException ex) { return Results.Conflict(new { error = ex.Message }); }
});

app.MapPost("/api/characters/{id:long}/references", async (long id, HttpRequest request, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if ((await repo.QueryCharacterAsync(id, ct)).FirstOrDefault() is null) return Results.NotFound(new { error = "角色不存在" });
    if (!request.HasFormContentType) return Results.BadRequest(new { error = "请使用 multipart/form-data 上传参考图" });
    var form = await request.ReadFormAsync(ct);
    var file = form.Files.GetFile("file");
    if (file is null || file.Length == 0) return Results.BadRequest(new { error = "请选择参考图" });
    try
    {
        var upload = await paths.StoreUploadAsync(file, $"Characters/{id}", UploadKind.Image, 25L * 1024 * 1024, ct);
        var kind = form["kind"].FirstOrDefault() ?? "identity";
        var reference = new ReferenceInput
        {
            Kind = kind,
            IsAnchor = string.Equals(form["isAnchor"].FirstOrDefault(), "true", StringComparison.OrdinalIgnoreCase),
            Stage = ReferenceMetadata.NormalizeStage(form["stage"].FirstOrDefault()),
            Role = ReferenceMetadata.NormalizeRole(form["role"].FirstOrDefault(), kind),
            ChangeReason = ReferenceMetadata.NormalizeChangeReason(form["changeReason"].FirstOrDefault())
        };
        var refId = await repo.AddCharacterReferenceAsync(id, upload.FullPath, reference, ct);
        return Results.Ok(new { id = refId, assetPath = upload.RelativePath, mediaUrl = $"/api/media?assetPath={Uri.EscapeDataString(upload.RelativePath)}" });
    }
    catch (AssetValidationException ex) { return Results.BadRequest(new { error = ex.Message }); }
});

app.MapGet("/api/scenes", async (long? projectId, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => Results.Ok((await repo.ScenesAsync(projectId, ct)).Select(scene => ToPublicScene(scene, paths))));
app.MapPost("/api/scenes", async (SceneInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "场景名称不能为空" });
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    if (!TryNormalizeOptionalAssetPath(input.AnchorPath, paths, out var anchorPath)) return Results.BadRequest(new { error = "场景锚点必须通过参考图上传或引用受控媒体" });
    input.AnchorPath = anchorPath;
    var id = await repo.CreateSceneAsync(input, ct);
    return Results.Created($"/api/scenes/{id}", new { id });
});
app.MapPut("/api/scenes/{id:long}", async (long id, SceneInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    if (!TryNormalizeOptionalAssetPath(input.AnchorPath, paths, out var anchorPath)) return Results.BadRequest(new { error = "场景锚点必须通过参考图上传或引用受控媒体" });
    input.AnchorPath = anchorPath;
    return Results.Ok(new { updated = await repo.UpdateSceneAsync(id, input, ct) });
});
app.MapDelete("/api/scenes/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteSceneAsync(id, ct) }));
app.MapGet("/api/scenes/{id:long}/references", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if ((await repo.QuerySceneAsync(id, ct)).FirstOrDefault() is null) return Results.NotFound(new { error = "场景不存在" });
    var references = await repo.SceneReferencesAsync(id, ct);
    return Results.Ok(references.Select(reference =>
    {
        var metadata = ReferenceMetadata.Read(reference.Text("metadataJson"), reference.Text("kind"));
        var available = paths.TryResolveExisting(reference.Text("path"), out _, out var assetPath);
        return new
        {
            id = reference.Long("id"), sceneId = id, kind = reference.Text("kind"), isAnchor = reference.Bool("isAnchor"),
            stage = metadata.Stage, role = metadata.Role, changeReason = metadata.ChangeReason, assetVersion = metadata.AssetVersion,
            assetSha256 = metadata.Sha256, available, assetPath = available ? assetPath : null,
            mediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(assetPath)}" : null, createdAt = reference["createdAt"]
        };
    }));
});
app.MapPost("/api/scenes/{id:long}/references", async (long id, HttpRequest request, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if ((await repo.QuerySceneAsync(id, ct)).FirstOrDefault() is null) return Results.NotFound(new { error = "场景不存在" });
    if (!request.HasFormContentType) return Results.BadRequest(new { error = "请使用 multipart/form-data 上传参考图" });
    var form = await request.ReadFormAsync(ct); var file = form.Files.GetFile("file");
    if (file is null || file.Length == 0) return Results.BadRequest(new { error = "请选择场景参考图" });
    try
    {
        var upload = await paths.StoreUploadAsync(file, $"Scenes/{id}", UploadKind.Image, 25L * 1024 * 1024, ct);
        var kind = form["kind"].FirstOrDefault() ?? "master";
        var refId = await repo.AddSceneReferenceAsync(id, upload.FullPath, new ReferenceInput
        {
            Kind = kind,
            IsAnchor = string.Equals(form["isAnchor"].FirstOrDefault(), "true", StringComparison.OrdinalIgnoreCase),
            Stage = ReferenceMetadata.NormalizeStage(form["stage"].FirstOrDefault()),
            Role = ReferenceMetadata.NormalizeRole(form["role"].FirstOrDefault(), "environment"),
            ChangeReason = ReferenceMetadata.NormalizeChangeReason(form["changeReason"].FirstOrDefault())
        }, ct);
        return Results.Ok(new { id = refId, assetPath = upload.RelativePath, mediaUrl = $"/api/media?assetPath={Uri.EscapeDataString(upload.RelativePath)}" });
    }
    catch (AssetValidationException ex) { return Results.BadRequest(new { error = ex.Message }); }
});

app.MapGet("/api/episodes/{episodeId:long}/shots", async (long episodeId, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => Results.Ok((await repo.ShotsAsync(episodeId, ct)).Select(shot => ToPublicShot(shot, paths))));
app.MapPost("/api/shots", async (ShotInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (await ValidateShotInputAsync(input, repo, paths, null, ct) is { } validationError) return validationError;
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    try
    {
        var id = await repo.CreateShotAsync(input, ct);
        return Results.Created($"/api/shots/{id}", new { id });
    }
    catch (MySqlConnector.MySqlException ex) when (ex.Number == 1062)
    {
        return Results.Conflict(new { error = "该集镜头号已存在，请使用其他镜头号" });
    }
});
app.MapPut("/api/shots/{id:long}", async (long id, ShotInput input, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if ((await repo.QueryShotAsync(id, ct)).FirstOrDefault() is null) return Results.NotFound(new { error = "镜头不存在" });
    if (IsFormalTerminalShotStatus(input.Status))
        return Results.Conflict(new { error = "正式终态只能由审核/发布流程设置，不能通过普通镜头编辑接口绕过审核" });
    if (await ValidateShotInputAsync(input, repo, paths, id, ct) is { } validationError) return validationError;
    if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
    try
    {
        return Results.Ok(new { updated = await repo.UpdateShotAsync(id, input, ct) });
    }
    catch (MySqlConnector.MySqlException ex) when (ex.Number == 1062)
    {
        return Results.Conflict(new { error = "该集镜头号已存在，请使用其他镜头号" });
    }
});
app.MapDelete("/api/shots/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { deleted = await repo.DeleteShotAsync(id, ct) }));
app.MapPost("/api/episodes/{episodeId:long}/shots/reorder", async (long episodeId, ReorderInput input, StudioRepository repo, CancellationToken ct) => { await repo.ReorderShotsAsync(episodeId, input.ShotIds, ct); return Results.Ok(new { reordered = input.ShotIds.Count }); });

app.MapGet("/api/workflows", async (StudioRepository repo, CancellationToken ct) => Results.Ok((await repo.WorkflowsAsync(ct)).Select(ToPublicWorkflow)));
app.MapGet("/api/workflow-contracts", (WorkflowContractService contracts) => Results.Ok(contracts.PublicCatalog()));
app.MapPost("/api/workflows/scan", async (WorkflowCatalog catalog, CancellationToken ct) => Results.Ok(new { scanned = await catalog.ScanAsync(ct) }));
app.MapGet("/api/models", async (StudioRepository repo, CancellationToken ct) => Results.Ok((await repo.ModelsAsync(ct)).Select(ToPublicModel)));
app.MapGet("/api/loras", async (StudioRepository repo, CancellationToken ct) => Results.Ok((await repo.LorasAsync(ct)).Select(ToPublicLora)));

app.MapGet("/api/assets", async (long? projectId, string? type, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    var assets = await repo.AssetsAsync(projectId, type, ct);
    return Results.Ok(assets.Select(asset => ToPublicAsset(asset, paths)));
});
app.MapDelete("/api/assets/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) =>
{
    try { return Results.Ok(new { deleted = await repo.DeleteAssetAsync(id, ct) }); }
    catch (AssetRetentionException ex) { return Results.Conflict(new { error = ex.Message, deleted = false }); }
});
app.MapGet("/api/media", async (long? assetId, string? assetPath, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    if (assetId is > 0)
    {
        var asset = (await repo.AssetAsync(assetId.Value, ct)).FirstOrDefault();
        assetPath = asset?.Text("relativePath") ?? asset?.Text("path");
    }
    if (!paths.TryResolveExisting(assetPath, out var full, out _)) return Results.NotFound();
    return Results.File(full, ContentTypeFor(full), enableRangeProcessing: true);
});

app.MapGet("/api/tasks", async (int? limit, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
    Results.Ok((await repo.TasksAsync(limit ?? 100, ct)).Select(task => ToPublicTask(task, paths))));
app.MapGet("/api/video-restore/status", (SeedVr2Service service) =>
{
    var status = service.Check();
    return Results.Ok(new { ready = status.Ready, message = status.Message, engineVersion = service.Identity, engine = "SeedVR2-3B-FP8", productionEligible = false });
});
app.MapGet("/api/video-restore/comparison", (StudioSettings settings, AssetPathPolicy paths) =>
{
    try
    {
        using var report = JsonDocument.Parse(File.ReadAllText(Path.Combine(settings.DataPath, "SeedVR2Enhancement20261022", "run.json")));
        string? Media(string name) => report.RootElement.TryGetProperty(name, out var item) && item.ValueKind == JsonValueKind.String
            && paths.TryResolveExisting(item.GetString(), out _, out var relative) && relative.StartsWith("Artifacts/", StringComparison.Ordinal)
            && relative.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase) ? relative : null;
        var original = Media("originalVideoPath"); var onePass = Media("exportTaskIdPath"); var restoredSample = Media("sampleFinalTaskIdPath");
        return original is null || onePass is null || restoredSample is null
            ? Results.NotFound(new { error = "视频细节对照尚未就绪" })
            : Results.Ok(new { original, onePass, restoredSample, restoredFull = Media("fullFinalTaskIdPath") });
    }
    catch (Exception ex) when (ex is IOException or JsonException) { return Results.NotFound(new { error = "视频细节对照尚未就绪" }); }
});
app.MapGet("/api/audio/history", async (int? limit, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
    Results.Ok((await repo.AudioTasksAsync(limit ?? 20, ct)).Select(task => ToPublicTask(task, paths))));
app.MapGet("/api/tasks/{id:long}", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
{
    var task = (await repo.TaskAsync(id, ct)).FirstOrDefault();
    if (task is null) return Results.NotFound(new { error = "任务不存在" });
    return Results.Ok(new { task = ToPublicTask(task, paths), results = (await repo.ResultsAsync(id, ct)).Select(result => ToPublicResult(result, paths)) });
});
app.MapPost("/api/tasks/preflight", async (TaskInput input, TaskSubmissionPreflightService preflight, CancellationToken ct)
    => Results.Ok(await preflight.CheckAsync(input, ct)));
app.MapPost("/api/tasks", async (TaskInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, TaskSubmissionPreflightService preflight, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(input.TaskType)) return Results.BadRequest(new { error = "任务类型不能为空" });
    input.RequestId ??= request.HttpContext.TraceIdentifier;
    input.IdempotencyKey ??= request.Headers["Idempotency-Key"].FirstOrDefault();
    var preflightResult = await preflight.CheckAsync(input, ct);
    if (!preflightResult.Passed)
        return Results.UnprocessableEntity(new { error = "任务提交前检查未通过，未创建任务", preflight = preflightResult });
    var id = await repo.CreateTaskAsync(input, ct); queue.Enqueue(id);
    return Results.Accepted($"/api/tasks/{id}", new { id, status = "Pending" });
});
app.MapPost("/api/tasks/{id:long}/cancel", async (long id, GenerationQueue queue, CancellationToken ct) => { await queue.CancelAsync(id, ct); return Results.Ok(new { id, status = "Cancelled" }); });
app.MapPost("/api/tasks/{id:long}/retry", async (long id, StudioRepository repo, TaskLeaseRepository leases, GenerationQueue queue, TaskSubmissionPreflightService preflight, CancellationToken ct) =>
{
    var old = (await repo.TaskAsync(id, ct)).FirstOrDefault();
    if (old is null) return Results.NotFound(new { error = "任务不存在" });
    using var original = old.Json("inputJson");
    var retryInput = RestoreTaskInput(old, original.RootElement);
    var preflightResult = await preflight.CheckAsync(retryInput, ct);
    if (!preflightResult.Passed)
        return Results.UnprocessableEntity(new { error = "任务重试前检查未通过，未重新入队", preflight = preflightResult });
    var changed = await leases.RetryAsync(id, ct: ct);
    if (changed == 0) return Results.Conflict(new { error = "只有失败或已取消的任务可以重试" });
    queue.Enqueue(id);
    return Results.Ok(new { id, status = "Pending" });
});
app.MapPost("/api/tasks/{id:long}/rerun", async (long id, HttpRequest request, StudioRepository repo, GenerationQueue queue, TaskSubmissionPreflightService preflight, CancellationToken ct) =>
{
    var old = (await repo.TaskAsync(id, ct)).FirstOrDefault(); if (old is null) return Results.NotFound();
    using var original = old.Json("inputJson");
    var rerunInput = RestoreTaskInput(old, original.RootElement);
    rerunInput.RequestId = request.HttpContext.TraceIdentifier;
    var preflightResult = await preflight.CheckAsync(rerunInput, ct);
    if (!preflightResult.Passed)
        return Results.UnprocessableEntity(new { error = "任务重新执行前检查未通过，未创建任务", preflight = preflightResult });
    var newId = await repo.CreateTaskAsync(rerunInput, ct);
    queue.Enqueue(newId); return Results.Accepted($"/api/tasks/{newId}", new { id = newId, status = "Pending", sourceTaskId = id });
});
app.MapPost("/api/shots/{shotId:long}/ab", async (long shotId, AbInput input, StudioRepository repo, GenerationQueue queue, TaskSubmissionPreflightService preflight, CancellationToken ct) =>
{
    if (input.Variants.Count < 2) return Results.BadRequest(new { error = "A/B 至少需要两个参数变体" });
    var candidates = input.Variants.Select(variant => new TaskInput
    {
        ProjectId = input.ProjectId,
        EpisodeId = input.EpisodeId,
        ShotId = shotId,
        TaskType = input.TaskType,
        WorkflowId = input.WorkflowId,
        InputImagePath = input.InputImagePath,
        Parameters = variant
    }).ToList();
    foreach (var candidate in candidates)
    {
        var preflightResult = await preflight.CheckAsync(candidate, ct);
        if (!preflightResult.Passed)
            return Results.UnprocessableEntity(new { error = "A/B 任务提交前检查未通过，未创建任务", preflight = preflightResult });
    }
    var ids = new List<long>();
    foreach (var candidate in candidates)
    {
        var id = await repo.CreateTaskAsync(candidate, ct);
        queue.Enqueue(id); ids.Add(id);
    }
    return Results.Accepted("/api/tasks", new { ids, count = ids.Count });
});
app.MapPost("/api/episodes/{episodeId:long}/concat", async (long episodeId, StudioRepository repo, GenerationQueue queue, StudioSettings studio, AssetPathPolicy paths, TaskSubmissionPreflightService preflight, CancellationToken ct) =>
{
    var shots = await repo.ShotsAsync(episodeId, ct);
    var files = shots.Select(x => x.Text("resultPath"))
        .Select(path => paths.TryResolveExisting(path, out var fullPath, out _) ? fullPath : null)
        .Where(path => path is not null)
        .Cast<string>()
        .ToArray();
    if (files.Length == 0) return Results.BadRequest(new { error = "本集没有可拼接的镜头结果" });
    using var parametersDoc = JsonDocument.Parse(JsonSerializer.Serialize(new { files, outputName = $"episode_{episodeId}_{DateTime.Now:yyyyMMdd_HHmmss}.mp4" }));
    var taskInput = new TaskInput { EpisodeId = episodeId, TaskType = "Concat", ResourceClass = "CPU", Parameters = parametersDoc.RootElement.Clone() };
    var preflightResult = await preflight.CheckAsync(taskInput, ct);
    if (!preflightResult.Passed)
        return Results.UnprocessableEntity(new { error = "拼接任务提交前检查未通过，未创建任务", preflight = preflightResult });
    var taskId = await repo.CreateTaskAsync(taskInput, ct); queue.Enqueue(taskId);
    return Results.Accepted($"/api/tasks/{taskId}", new { id = taskId, files = files.Length });
});

ProductionEndpoints.Map(app);
VideoQaEndpoints.Map(app);
CharacterIdentityEndpoints.Map(app);
CharacterLibraryEndpoints.Map(app);
CharacterStoryEndpoints.Map(app);

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

static object ToPublicProject(IReadOnlyDictionary<string, object?> project, AssetPathPolicy paths)
{
    string? AssetPath(string field) => paths.TryResolveExisting(project.Text(field), out _, out var relative) ? relative : null;
    return new
    {
        id = project.Long("id"),
        name = project.Text("name"),
        slug = project.Text("slug"),
        description = project.Text("description"),
        status = project.Text("status"),
        aspectRatio = project.Text("aspectRatio"),
        style = project.Text("style"),
        defaultFps = project.Int("defaultFps", 30),
        defaultWidth = project.Int("defaultWidth", 1920),
        defaultHeight = project.Int("defaultHeight", 1080),
        promptStyle = project.Text("promptStyle"),
        bgmVolume = project["bgmVolume"],
        bgmAssetPath = AssetPath("bgmPath"),
        bgmPath = AssetPath("bgmPath"),
        coverAssetPath = AssetPath("coverPath"),
        coverPath = AssetPath("coverPath"),
        episodeCount = project.Int("episodeCount"),
        shotCount = project.Int("shotCount"),
        assetCount = project.Int("assetCount"),
        createdAt = project["createdAt"],
        updatedAt = project["updatedAt"]
    };
}

static object ToPublicEpisode(IReadOnlyDictionary<string, object?> episode, AssetPathPolicy paths)
{
    string? AssetPath(string field) => paths.TryResolveExisting(episode.Text(field), out _, out var relative) ? relative : null;
    string? MediaUrl(string field)
    {
        var assetPath = AssetPath(field);
        return assetPath is null ? null : $"/api/media?assetPath={Uri.EscapeDataString(assetPath)}";
    }

    return new
    {
        id = episode.Long("id"),
        projectId = episode.LongOrNull("projectId"),
        scriptId = episode.LongOrNull("scriptId"),
        episodeNumber = episode.Int("episodeNumber", 1),
        name = episode.Text("name"),
        description = episode.Text("description"),
        status = episode.Text("status"),
        targetSeconds = episode["targetSeconds"],
        outputFps = episode.Int("outputFps", 30),
        outputWidth = episode.Int("outputWidth", 1920),
        outputHeight = episode.Int("outputHeight", 1080),
        productionMode = episode.Text("productionMode"),
        narratorVoiceId = episode.Text("narratorVoiceId"),
        voiceVolume = episode["voiceVolume"],
        bgmVolume = episode["bgmVolume"],
        sfxVolume = episode["sfxVolume"],
        qaStatus = episode.Text("qaStatus"),
        qaScore = episode["overallScore"],
        qaVersion = episode.Int("qaVersion"),
        qaLocked = episode.Bool("qaLocked"),
        totalDurationSeconds = episode["totalDurationSeconds"],
        outputAssetPath = AssetPath("outputPath"),
        outputMediaUrl = MediaUrl("outputPath"),
        subtitleAssetPath = AssetPath("subtitlePath"),
        subtitleMediaUrl = MediaUrl("subtitlePath"),
        coverAssetPath = AssetPath("coverPath"),
        coverMediaUrl = MediaUrl("coverPath"),
        createdAt = episode["createdAt"],
        updatedAt = episode["updatedAt"]
    };
}

static object ToPublicWorkflow(IReadOnlyDictionary<string, object?> workflow) => new
{
    id = workflow.Long("id"),
    name = workflow.Text("name"),
    workflowType = workflow.Text("workflowType"),
    modelName = workflow.Text("modelName"),
    enabled = workflow.Bool("enabled"),
    fileName = Path.GetFileName(workflow.Text("path") ?? string.Empty),
    path = Path.GetFileName(workflow.Text("path") ?? string.Empty),
    createdAt = workflow["createdAt"],
    updatedAt = workflow["updatedAt"]
};

static object ToPublicModel(IReadOnlyDictionary<string, object?> model) => new
{
    id = model.Long("id"),
    name = model.Text("name"),
    modelType = model.Text("modelType"),
    fileName = Path.GetFileName(model.Text("path") ?? string.Empty),
    fileSizeBytes = model.LongOrNull("fileSizeBytes"),
    sha256 = model.Text("sha256"),
    vramHintMiB = model.LongOrNull("vramHintMiB"),
    createdAt = model["createdAt"],
    updatedAt = model["updatedAt"]
};

static object ToPublicLora(IReadOnlyDictionary<string, object?> lora) => new
{
    id = lora.Long("id"),
    name = lora.Text("name"),
    strengthModel = lora["strengthModel"],
    strengthClip = lora["strengthClip"],
    fileName = Path.GetFileName(lora.Text("path") ?? string.Empty),
    createdAt = lora["createdAt"],
    updatedAt = lora["updatedAt"]
};

static object ToPublicAsset(IReadOnlyDictionary<string, object?> asset, AssetPathPolicy paths)
{
    var storedPath = asset.Text("path");
    var available = paths.TryResolveExisting(storedPath, out _, out var relativePath);
    return new
    {
        id = asset.Long("id"),
        projectId = asset.LongOrNull("projectId"),
        episodeId = asset.LongOrNull("episodeId"),
        shotId = asset.LongOrNull("shotId"),
        assetType = asset.Text("assetType"),
        name = asset.Text("name"),
        mimeType = asset.Text("mimeType"),
        sizeBytes = asset.LongOrNull("sizeBytes"),
        width = asset.Int("width", 0),
        height = asset.Int("height", 0),
        durationSeconds = asset["durationSeconds"],
        fps = asset["fps"],
        createdAt = asset["createdAt"],
        available,
        assetPath = available ? relativePath : null,
        mediaUrl = available ? $"/api/media?assetId={asset.Long("id")}" : null
    };
}

static object ToPublicTask(IReadOnlyDictionary<string, object?> task, AssetPathPolicy paths)
{
    var inputAvailable = paths.IsAllowedExistingFile(task.Text("shotInputImage"));
    return new
    {
        id = task.Long("id"),
        projectId = task.LongOrNull("projectId"),
        episodeId = task.LongOrNull("episodeId"),
        shotId = task.LongOrNull("shotId"),
        productionRunId = task.LongOrNull("productionRunId"),
        taskType = task.Text("taskType"),
        status = task.Text("status"),
        priority = task.Int("priority"),
        maxRetries = task.Int("maxRetries"),
        attempts = task.Int("attempts"),
        workflowId = task.LongOrNull("workflowId"),
        resourceClass = task.Text("resourceClass"),
        stage = task.Text("stage"),
        projectName = task.Text("projectName"),
        episodeName = task.Text("episodeName"),
        shotTitle = task.Text("shotTitle"),
        workflowName = task.Text("workflowName"),
        inputImageAvailable = inputAvailable,
        errorType = task.Text("errorType"),
        errorMessage = task.Text("errorMessage"),
        progress = task["progress"],
        vramPeakMiB = task.LongOrNull("vramPeakMib"),
        createdAt = task["createdAt"],
        queuedAt = task["queuedAt"],
        startedAt = task["startedAt"],
        finishedAt = task["finishedAt"],
        durationMs = task.LongOrNull("durationMs")
    };
}

static object ToPublicResult(IReadOnlyDictionary<string, object?> result, AssetPathPolicy paths)
{
    var storedPath = result.Text("path") ?? result.Text("assetRelativePath");
    var available = paths.TryResolveExisting(storedPath, out _, out var relativePath);
    return new
    {
        id = result.Long("id"),
        taskId = result.LongOrNull("taskId"),
        assetId = result.LongOrNull("assetId"),
        resultType = result.Text("resultType"),
        status = result.Text("status"),
        assetName = result.Text("assetName"),
        mimeType = result.Text("mimeType"),
        width = result.Int("width"),
        height = result.Int("height"),
        durationSeconds = result["durationSeconds"],
        fps = result["fps"],
        available,
        assetPath = available ? relativePath : null,
        mediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(relativePath)}" : null,
        createdAt = result["createdAt"]
    };
}

static object ToPublicShot(IReadOnlyDictionary<string, object?> shot, AssetPathPolicy paths)
{
    string? AssetPath(string field) => paths.TryResolveExisting(shot.Text(field), out _, out var relative) ? relative : null;
    string? MediaUrl(string field)
    {
        var assetPath = AssetPath(field);
        return assetPath is null ? null : $"/api/media?assetPath={Uri.EscapeDataString(assetPath)}";
    }

    return new
    {
        id = shot.Long("id"),
        projectId = shot.LongOrNull("projectId"),
        episodeId = shot.LongOrNull("episodeId"),
        shotNumber = shot.Int("shotNumber"),
        title = shot.Text("title"),
        description = shot.Text("description"),
        sceneId = shot.LongOrNull("sceneId"),
        sceneName = shot.Text("sceneName"),
        characterIds = ParseLongList(shot.Text("characterIdsJson")),
        prompt = shot.Text("prompt"),
        negativePrompt = shot.Text("negativePrompt"),
        workflowId = shot.LongOrNull("workflowId"),
        modelId = shot.LongOrNull("modelId"),
        loraIds = ParseLongList(shot.Text("loraIdsJson")),
        seed = shot.LongOrNull("seed"),
        cfgScale = shot["cfgScale"],
        steps = shot["steps"],
        width = shot["width"],
        height = shot["height"],
        frames = shot["frames"],
        fps = shot["fps"],
        motionPreset = shot.Text("motionPreset"),
        cameraPreset = shot.Text("cameraPreset"),
        status = shot.Text("status"),
        action = shot.Text("action"),
        dialogue = shot.Text("dialogue"),
        narration = shot.Text("narration"),
        emotion = shot.Text("emotion"),
        cameraType = shot.Text("cameraType"),
        cameraMotion = shot.Text("cameraMotion"),
        durationSeconds = shot["durationSeconds"],
        qualityScore = shot["qualityScore"],
        userRating = shot["userRating"],
        qaStatus = shot.Text("qaStatus"),
        qaScore = shot["qaScore"],
        inputImageAssetPath = AssetPath("inputImagePath"),
        inputImageMediaUrl = MediaUrl("inputImagePath"),
        selectedKeyframeAssetPath = AssetPath("selectedKeyframePath"),
        selectedKeyframeMediaUrl = MediaUrl("selectedKeyframePath"),
        videoAssetPath = AssetPath("videoPath"),
        videoMediaUrl = MediaUrl("videoPath"),
        finalVideoAssetPath = AssetPath("finalVideoPath"),
        finalVideoMediaUrl = MediaUrl("finalVideoPath"),
        resultAssetPath = AssetPath("resultPath"),
        resultMediaUrl = MediaUrl("resultPath"),
        createdAt = shot["createdAt"],
        updatedAt = shot["updatedAt"]
    };
}

static object ToPublicCharacter(IReadOnlyDictionary<string, object?> character, AssetPathPolicy paths)
{
    var referenceAvailable = paths.TryResolveExisting(character.Text("referencePath"), out _, out var referencePath);
    return new
    {
        id = character.Long("id"),
        projectId = character.LongOrNull("projectId"),
        name = character.Text("name"),
        ageSetting = character.Text("ageSetting"),
        faceFeatures = character.Text("faceFeatures"),
        hair = character.Text("hair"),
        clothes = character.Text("clothes"),
        bodyRatio = character.Text("bodyRatio"),
        fixedPrompt = character.Text("fixedPrompt"),
        negativePrompt = character.Text("negativePrompt"),
        voiceId = character.Text("voiceId"),
        voiceSpeed = character["voiceSpeed"],
        voicePitch = character["voicePitch"],
        referenceCount = character["referenceCount"],
        referenceAssetPath = referenceAvailable ? referencePath : null,
        referencePath = referenceAvailable ? referencePath : null,
        referenceMediaUrl = referenceAvailable ? $"/api/media?assetPath={Uri.EscapeDataString(referencePath)}" : null,
        hasAnchor = paths.IsAllowedExistingFile(character.Text("anchorPath")),
        anchorPath = paths.TryResolveExisting(character.Text("anchorPath"), out _, out var anchorAssetPath) ? anchorAssetPath : null,
        createdAt = character["createdAt"],
        updatedAt = character["updatedAt"]
    };
}

static object ToPublicScene(IReadOnlyDictionary<string, object?> scene, AssetPathPolicy paths)
{
    var referenceAvailable = paths.TryResolveExisting(scene.Text("referencePath"), out _, out var referencePath);
    return new
    {
        id = scene.Long("id"),
        projectId = scene.LongOrNull("projectId"),
        name = scene.Text("name"),
        description = scene.Text("description"),
        fixedPrompt = scene.Text("fixedPrompt"),
        negativePrompt = scene.Text("negativePrompt"),
        style = scene.Text("style"),
        referenceCount = scene["referenceCount"],
        referenceAssetPath = referenceAvailable ? referencePath : null,
        referencePath = referenceAvailable ? referencePath : null,
        referenceMediaUrl = referenceAvailable ? $"/api/media?assetPath={Uri.EscapeDataString(referencePath)}" : null,
        hasAnchor = paths.IsAllowedExistingFile(scene.Text("anchorPath")),
        anchorPath = paths.TryResolveExisting(scene.Text("anchorPath"), out _, out var anchorAssetPath) ? anchorAssetPath : null,
        createdAt = scene["createdAt"],
        updatedAt = scene["updatedAt"]
    };
}

static IReadOnlyList<long> ParseLongList(string? json)
{
    if (string.IsNullOrWhiteSpace(json)) return [];
    try
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.ValueKind == JsonValueKind.Array
            ? document.RootElement.EnumerateArray().Where(value => value.TryGetInt64(out _)).Select(value => value.GetInt64()).ToArray()
            : [];
    }
    catch { return []; }
}

static string? ResolveEpisodeSourceVideoPath(IReadOnlyDictionary<string, object?> shot, AssetPathPolicy paths)
{
    foreach (var path in new[] { shot.Text("finalVideoPath"), shot.Text("videoPath"), shot.Text("resultPath") })
        if (!string.IsNullOrWhiteSpace(path) && IsEpisodeVideoPath(path) && paths.TryResolveExisting(path, out var fullPath, out _)) return fullPath;
    return null;
}

static bool IsEpisodeVideoPath(string path) => Path.GetExtension(path).ToLowerInvariant() is ".mp4" or ".mov" or ".webm" or ".mkv";

static string[] EpisodeRenderFilesFromInput(string? inputJson)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        return TryGetJsonProperty(parameters, "files", out var files) && files.ValueKind == JsonValueKind.Array
            ? files.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)).Cast<string>().ToArray()
            : [];
    }
    catch { return []; }
}

static string[] EpisodeRenderAudioTracksFromInput(string? inputJson)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        if (!TryGetJsonProperty(parameters, "audioTracks", out var tracks) || tracks.ValueKind != JsonValueKind.Array) return [];
        return tracks.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.Object).Select(track =>
        {
            var path = TryGetJsonProperty(track, "path", out var pathElement) && pathElement.ValueKind == JsonValueKind.String ? pathElement.GetString() : null;
            var volume = TryGetJsonProperty(track, "volume", out var volumeElement) && volumeElement.TryGetDouble(out var volumeValue) ? volumeValue : 1d;
            var start = TryGetJsonProperty(track, "startSeconds", out var startElement) && startElement.TryGetDouble(out var startValue) ? startValue : 0d;
            return string.IsNullOrWhiteSpace(path) ? null : EpisodeRenderAudioTrackKey(path, volume, start);
        }).Where(x => x is not null).Cast<string>().ToArray();
    }
    catch { return []; }
}

static string? EpisodeRenderStringFromInput(string? inputJson, string propertyName)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        return TryGetJsonProperty(parameters, propertyName, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
    }
    catch { return null; }
}

static int? EpisodeRenderIntFromInput(string? inputJson, string propertyName)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        return TryGetJsonProperty(parameters, propertyName, out var value) && value.TryGetInt32(out var result) ? result : null;
    }
    catch { return null; }
}

static bool EpisodeRenderBoolFromInput(string? inputJson, string propertyName)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        return TryGetJsonProperty(parameters, propertyName, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False && value.GetBoolean();
    }
    catch { return false; }
}

static string EpisodeRenderAudioTrackKey(string path, double volume, double startSeconds)
{
    var normalizedPath = NormalizeEpisodePath(path);
    return $"{normalizedPath}|{volume.ToString("0.######", System.Globalization.CultureInfo.InvariantCulture)}|{startSeconds.ToString("0.######", System.Globalization.CultureInfo.InvariantCulture)}";
}

static JsonElement? EpisodeRenderSourceSnapshotFromInput(string? inputJson, AssetPathPolicy paths)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        if (!TryGetJsonProperty(parameters, "sourceSnapshot", out var snapshot) || snapshot.ValueKind != JsonValueKind.Array) return null;
        var safeSnapshot = snapshot.EnumerateArray().Where(item => item.ValueKind == JsonValueKind.Object).Select(item =>
        {
            var storedPath = TryGetJsonProperty(item, "path", out var pathElement) && pathElement.ValueKind == JsonValueKind.String ? pathElement.GetString() : null;
            var available = paths.TryResolveExisting(storedPath, out _, out var relativePath);
            return new
            {
                shotId = JsonNumber(item, "shotId"),
                shotNumber = JsonNumber(item, "shotNumber"),
                title = JsonString(item, "title"),
                sourceKind = JsonString(item, "sourceKind"),
                durationSeconds = JsonNumber(item, "durationSeconds"),
                ready = JsonBoolean(item, "ready"),
                available,
                assetPath = available ? relativePath : null,
                mediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(relativePath)}" : null
            };
        }).ToArray();
        return JsonSerializer.SerializeToElement(safeSnapshot);
    }
    catch { return null; }
}

static string? JsonString(JsonElement element, string propertyName)
    => TryGetJsonProperty(element, propertyName, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

static object? JsonNumber(JsonElement element, string propertyName)
{
    if (!TryGetJsonProperty(element, propertyName, out var value)) return null;
    if (value.TryGetInt64(out var integer)) return integer;
    if (value.TryGetDecimal(out var decimalValue)) return decimalValue;
    if (value.TryGetDouble(out var doubleValue)) return doubleValue;
    return null;
}

static bool JsonBoolean(JsonElement element, string propertyName)
    => TryGetJsonProperty(element, propertyName, out var value) && value.ValueKind is JsonValueKind.True;

static int? EpisodeRenderVersionFromInput(string? inputJson)
{
    try
    {
        using var document = JsonDocument.Parse(inputJson ?? "{}");
        var parameters = EpisodeRenderParameters(document.RootElement);
        return TryGetJsonProperty(parameters, "renderVersion", out var version) && version.TryGetInt32(out var value) && value > 0 ? value : null;
    }
    catch { return null; }
}

static JsonElement EpisodeRenderParameters(JsonElement root)
    => TryGetJsonProperty(root, "parameters", out var parameters) && parameters.ValueKind == JsonValueKind.Object ? parameters : root;

static bool TryGetJsonProperty(JsonElement element, string name, out JsonElement value)
{
    if (element.ValueKind == JsonValueKind.Object)
        foreach (var property in element.EnumerateObject())
            if (string.Equals(property.Name, name, StringComparison.OrdinalIgnoreCase)) { value = property.Value; return true; }
    value = default;
    return false;
}

static TaskInput RestoreTaskInput(IReadOnlyDictionary<string, object?> row, JsonElement input)
{
    string? StringValue(string name)
        => TryGetJsonProperty(input, name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    var parameters = TryGetJsonProperty(input, "parameters", out var parameterValue) && parameterValue.ValueKind == JsonValueKind.Object
        ? parameterValue.Clone()
        : JsonSerializer.SerializeToElement(new { });
    var loraIds = TryGetJsonProperty(input, "loraIds", out var loraValue) && loraValue.ValueKind == JsonValueKind.Array
        ? loraValue.EnumerateArray().Where(item => item.TryGetInt64(out _)).Select(item => item.GetInt64()).ToList()
        : null;

    return new TaskInput
    {
        ProjectId = row.LongOrNull("projectId"),
        EpisodeId = row.LongOrNull("episodeId"),
        ShotId = row.LongOrNull("shotId"),
        TaskType = row.Text("taskType") ?? "Image",
        Priority = row.Int("priority"),
        MaxRetries = row.Int("maxRetries", 2),
        WorkflowId = row.LongOrNull("workflowId"),
        LoraIds = loraIds,
        InputImagePath = StringValue("inputImagePath"),
        OutputName = StringValue("outputName"),
        Parameters = parameters,
        ResourceClass = StringValue("resourceClass") ?? row.Text("resourceClass") ?? "GPU",
        Stage = StringValue("stage") ?? row.Text("stage"),
        DependencyTaskId = row.LongOrNull("dependencyTaskId"),
        ProductionRunId = row.LongOrNull("productionRunId")
    };
}

static bool SameEpisodeSourceFiles(IEnumerable<string> currentFiles, IEnumerable<string> renderedFiles)
    => currentFiles.SequenceEqual(renderedFiles, StringComparer.OrdinalIgnoreCase);

static bool SameEpisodePath(string? currentPath, string? renderedPath)
    => string.Equals(NormalizeEpisodePath(currentPath), NormalizeEpisodePath(renderedPath), StringComparison.OrdinalIgnoreCase);

static string? NormalizeEpisodePath(string? path)
{
    if (string.IsNullOrWhiteSpace(path)) return null;
    try { return Path.GetFullPath(path); }
    catch { return path; }
}

static async Task<IResult?> ValidateShotInputAsync(ShotInput input, StudioRepository repo, AssetPathPolicy paths, long? currentShotId, CancellationToken ct)
{
    if (input.ProjectId <= 0 || input.EpisodeId <= 0 || string.IsNullOrWhiteSpace(input.Title))
        return Results.BadRequest(new { error = "镜头项目、集和标题不能为空" });
    if (input.ShotNumber <= 0)
        return Results.BadRequest(new { error = "镜头号必须从 1 开始" });

    var project = (await repo.ProjectAsync(input.ProjectId, ct)).FirstOrDefault();
    if (project is null) return Results.UnprocessableEntity(new { error = "指定项目不存在" });
    var episode = (await repo.EpisodeAsync(input.EpisodeId, ct)).FirstOrDefault();
    if (episode is null) return Results.UnprocessableEntity(new { error = "指定 Episode 不存在" });
    if (episode.LongOrNull("projectId") != input.ProjectId)
        return Results.UnprocessableEntity(new { error = "指定 Episode 不属于当前项目" });

    var sameNumber = (await repo.ShotByNumberAsync(input.EpisodeId, input.ShotNumber, ct)).FirstOrDefault();
    if (sameNumber is not null && sameNumber.Long("id") != currentShotId)
        return Results.Conflict(new { error = "该集镜头号已存在，请使用其他镜头号", existingShotId = sameNumber.Long("id") });

    if (!TryNormalizeOptionalAssetPath(input.InputImagePath, paths, out var inputPath))
        return Results.UnprocessableEntity(new { error = "输入参考图必须通过上传或引用受控数据目录中的媒体" });
    if (!TryNormalizeOptionalAssetPath(input.SelectedKeyframePath, paths, out var selectedKeyframePath))
        return Results.UnprocessableEntity(new { error = "关键帧必须位于受控数据目录" });
    if (!TryNormalizeOptionalAssetPath(input.VideoPath, paths, out var videoPath)
        || !TryNormalizeOptionalAssetPath(input.FinalVideoPath, paths, out var finalVideoPath))
        return Results.UnprocessableEntity(new { error = "镜头视频必须位于受控数据目录" });
    input.InputImagePath = inputPath;
    input.SelectedKeyframePath = selectedKeyframePath;
    input.VideoPath = videoPath;
    input.FinalVideoPath = finalVideoPath;

    return null;
}

static bool TryNormalizeOptionalAssetPath(string? value, AssetPathPolicy paths, out string? normalized)
{
    normalized = null;
    if (string.IsNullOrWhiteSpace(value)) return true;
    if (!paths.TryResolveExisting(value, out var fullPath, out _)) return false;
    normalized = fullPath;
    return true;
}

static bool TryNormalizeOptionalModelPath(string? value, AssetPathPolicy paths, out string? normalized)
{
    normalized = null;
    if (string.IsNullOrWhiteSpace(value)) return true;
    if (!paths.TryResolveExistingModel(value, out var fullPath, out _)) return false;
    normalized = fullPath;
    return true;
}

static bool IsFormalTerminalShotStatus(string? status)
    => status is not null && status.Trim() is { } normalized
        && normalized.Equals("Completed", StringComparison.OrdinalIgnoreCase)
        || status is not null && status.Trim().Equals("Approved", StringComparison.OrdinalIgnoreCase)
        || status is not null && status.Trim().Equals("Published", StringComparison.OrdinalIgnoreCase);

public sealed class AbInput
{
    public long? ProjectId { get; set; }
    public long? EpisodeId { get; set; }
    public string TaskType { get; set; } = "ImageToVideo";
    public long? WorkflowId { get; set; }
    public string? InputImagePath { get; set; }
    public List<JsonElement> Variants { get; set; } = [];
}
