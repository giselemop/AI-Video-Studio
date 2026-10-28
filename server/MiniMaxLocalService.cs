using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

public sealed record MiniMaxLocalAsset(string Role, string Repository, string Revision, string File, string Target, long Size, string Sha256);
public sealed record MiniMaxLocalLoader(string Repository, string Revision);
public sealed record MiniMaxLocalManifest(int SchemaVersion, string Route, string License, string LicenseUrl, MiniMaxLocalAsset[] Assets, MiniMaxLocalLoader? Loader = null);
public sealed record MiniMaxLocalAssetStatus(string Role, string File, long ExpectedBytes, long DownloadedBytes, bool Present, bool Verified);
public sealed record MiniMaxLocalInput(long ProjectId, string Prompt, string InputImagePath, long Seed = 2026101801, string Profile = "baseline480", bool TextToVideo = false, int Steps = 20,
    string? LastFramePath = null, string? FirstFrameSha256 = null, string? LastFrameSha256 = null);
public sealed record MiniMaxLocalProfile(string Id, string Label, string WorkflowFileName, int Width, int Height, int Steps = 20);
public sealed record H3FrameAsset(string Role, string AssetPath, string Sha256, int Width, int Height);

/// <summary>Explicit, pinned local H3 route. No API key, remote fallback or production approval.</summary>
public sealed class MiniMaxLocalService
{
    public const string WorkflowFileName = "minimax_h3_local_i2v_api.json";
    public const string Native1080WorkflowFileName = "minimax_h3_local_1088_i2v_api.json";
    public const string Native1080TextWorkflowFileName = "minimax_h3_local_1088_t2v_api.json";
    public const string Native1080Quality30WorkflowFileName = "minimax_h3_local_1088_i2v_30steps_api.json";
    public const string Quality768TextWorkflowFileName = "minimax_h3_local_768_t2v_api.json";
    public const string FirstLastProfile = "firstlast480";
    public const string FirstLastWorkflowFileName = "minimax_h3_local_fl2v_480_api.json";
    public static readonly MiniMaxLocalProfile[] Profiles =
    [
        new("baseline480", "480p 基线", WorkflowFileName, 864, 480),
        new("quality768", "768p 画质实验", "minimax_h3_local_768_i2v_api.json", 1376, 768),
        new("native1080", "1080p 原生实验", Native1080WorkflowFileName, 1920, 1088),
        new(FirstLastProfile, "480p 首尾双帧实验", FirstLastWorkflowFileName, 864, 480)
    ];
    public static MiniMaxLocalProfile ResolveProfile(string? id) => Profiles.FirstOrDefault(p => p.Id == (id ?? "baseline480"))
        ?? throw new InvalidOperationException("请选择已登记的 H3 生成规格");
    public static string ResolveWorkflowFileName(MiniMaxLocalProfile profile, bool textToVideo, int steps = 20)
    {
        if (steps == 30 && profile.Id == "native1080" && !textToVideo) return Native1080Quality30WorkflowFileName;
        if (steps != 20) throw new InvalidOperationException("30步仅用于原生1080p图生视频对照，其他路线固定20步");
        return !textToVideo ? profile.WorkflowFileName
            : profile.Id switch { "native1080" => Native1080TextWorkflowFileName, "quality768" => Quality768TextWorkflowFileName,
                _ => throw new InvalidOperationException("文生视频仅开放显式768p或原生1080p实验") };
    }
    public static IEnumerable<MiniMaxLocalProfile> ManagedProfiles => Profiles.Concat(Profiles.Where(p => p.Id is "native1080" or "quality768")
        .Select(p => p with { WorkflowFileName = ResolveWorkflowFileName(p, true) }))
        .Append(Profiles.Single(p => p.Id == "native1080") with { WorkflowFileName = Native1080Quality30WorkflowFileName, Steps = 30 });
    public static bool IsManagedWorkflow(string path) => ManagedProfiles.Any(p => string.Equals(p.WorkflowFileName, Path.GetFileName(path), StringComparison.OrdinalIgnoreCase));
    public static bool IsTextToVideoWorkflow(string? path) => new[] { Native1080TextWorkflowFileName, Quality768TextWorkflowFileName }.Contains(Path.GetFileName(path), StringComparer.OrdinalIgnoreCase);
    public static bool IsFirstLastWorkflow(string? path) => string.Equals(Path.GetFileName(path), FirstLastWorkflowFileName, StringComparison.OrdinalIgnoreCase);
    public static bool IsNative1080Workflow(string? path) => new[] { Native1080WorkflowFileName, Native1080TextWorkflowFileName, Native1080Quality30WorkflowFileName }.Contains(Path.GetFileName(path), StringComparer.OrdinalIgnoreCase);
    private readonly StudioSettings _settings;
    private readonly SemaphoreSlim _verification = new(1, 1);
    private readonly ConcurrentDictionary<string, (long Size, long Timestamp)> _verified = new(StringComparer.OrdinalIgnoreCase);
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    public MiniMaxLocalService(StudioSettings settings) => _settings = settings;

    public MiniMaxLocalManifest Manifest()
    {
        var path = Path.Combine(_settings.RootPath, "config", "minimax-local-assets.json");
        var manifest = JsonSerializer.Deserialize<MiniMaxLocalManifest>(File.ReadAllText(path), JsonOptions)
            ?? throw new InvalidOperationException("MiniMax 本地模型清单不可读");
        if (manifest.SchemaVersion != 1 || manifest.Assets is not { Length: 4 })
            throw new InvalidOperationException("MiniMax 本地模型清单版本不兼容");
        foreach (var asset in manifest.Assets)
        {
            _ = ModelPath(asset.Target);
            if (asset.Size <= 0 || asset.Sha256.Length != 64 || !asset.Sha256.All(Uri.IsHexDigit))
                throw new InvalidOperationException("MiniMax 模型清单缺少完整哈希或文件大小");
        }
        return manifest;
    }

    private string ModelPath(string relative)
    {
        var root = Path.GetFullPath(_settings.ModelsPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var path = Path.GetFullPath(Path.Combine(root, relative));
        if (Path.IsPathRooted(relative) || !path.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("MiniMax 模型必须位于中央模型目录内");
        return path;
    }

    public IReadOnlyList<MiniMaxLocalAssetStatus> AssetStatus()
        => Manifest().Assets.Select(asset =>
        {
            var path = ModelPath(asset.Target);
            var info = new FileInfo(path);
            var present = info.Exists && info.Length == asset.Size;
            var verified = present && _verified.TryGetValue(path, out var stamp)
                && stamp == (info.Length, info.LastWriteTimeUtc.Ticks);
            long downloaded = present ? info.Length : 0;
            // The partial file is preallocated, so its length is not download progress.
            var checkpoint = path + ".download.json";
            if (!present && File.Exists(checkpoint))
            {
                try
                {
                    using var document = JsonDocument.Parse(File.ReadAllText(checkpoint));
                    var saved = document.RootElement;
                    if (saved.GetProperty("sha256").GetString() == asset.Sha256)
                    {
                        var chunk = saved.GetProperty("chunk_size").GetInt64();
                        if (chunk > 0)
                            downloaded = saved.GetProperty("completed").EnumerateArray().Select(value => value.GetInt64()).Distinct()
                                .Where(index => index >= 0 && index < (asset.Size + chunk - 1) / chunk)
                                .Sum(index => Math.Min(chunk, asset.Size - index * chunk));
                    }
                }
                catch (Exception ex) when (ex is IOException or JsonException or KeyNotFoundException or InvalidOperationException) { }
            }
            return new MiniMaxLocalAssetStatus(asset.Role, Path.GetFileName(path), asset.Size, downloaded, present, verified);
        }).ToArray();

    public async Task EnsureVerifiedAsync(CancellationToken ct = default)
    {
        await _verification.WaitAsync(ct);
        try
        {
            foreach (var asset in Manifest().Assets)
            {
                var path = ModelPath(asset.Target);
                var info = new FileInfo(path);
                if (!info.Exists || info.Length != asset.Size)
                    throw new InvalidOperationException($"MiniMax 本地组件尚未下载完整：{asset.Role}");
                var stamp = (info.Length, info.LastWriteTimeUtc.Ticks);
                if (_verified.TryGetValue(path, out var prior) && prior == stamp) continue;
                await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
                var hash = Convert.ToHexString(await SHA256.HashDataAsync(stream, ct)).ToLowerInvariant();
                info.Refresh();
                if (hash != asset.Sha256 || stamp != (info.Length, info.LastWriteTimeUtc.Ticks))
                    throw new InvalidOperationException($"MiniMax 本地组件哈希不匹配：{asset.Role}；不会更换模型或继续执行");
                _verified[path] = stamp;
            }
        }
        finally { _verification.Release(); }
    }

    public async Task InstallWorkflowAsync(CancellationToken ct = default)
    {
        foreach (var profile in ManagedProfiles) await InstallProfileWorkflowAsync(profile, ct);
    }

    private async Task InstallProfileWorkflowAsync(MiniMaxLocalProfile profile, CancellationToken ct)
    {
        var source = Path.Combine(_settings.RootPath, "tools", "minimax", profile.WorkflowFileName);
        var target = Path.Combine(_settings.WorkflowsPath, profile.WorkflowFileName);
        var expected = await File.ReadAllTextAsync(source, ct);
        H3WorkflowPolicy.Validate(JsonNode.Parse(expected)!.AsObject(), JsonSerializer.SerializeToElement(new { profile = profile.Id }));
        Directory.CreateDirectory(_settings.WorkflowsPath);
        if (File.Exists(target))
        {
            if (await File.ReadAllTextAsync(target, ct) != expected)
                throw new InvalidOperationException("MiniMax 本地工作流已有不同版本，已保留；请先检查差异");
            return;
        }
        var temporary = target + $".{Guid.NewGuid():N}.tmp";
        try
        {
            await File.WriteAllTextAsync(temporary, expected, ct);
            File.Move(temporary, target, false);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    public JsonElement? IntegrationRun()
    {
        var path = Path.Combine(_settings.DataPath, "MiniMaxLocal", "integration-run.json");
        if (!File.Exists(path) || new FileInfo(path).Length > 1024 * 1024) return null;
        try { using var document = JsonDocument.Parse(File.ReadAllText(path)); return document.RootElement.Clone(); }
        catch (Exception ex) when (ex is IOException or JsonException) { return null; }
    }

    public async Task RegisterAsync(StudioRepository repository, CancellationToken ct = default)
    {
        await InstallWorkflowAsync(ct);
        var manifest = Manifest();
        foreach (var profile in ManagedProfiles)
        {
            var path = Path.Combine(_settings.WorkflowsPath, profile.WorkflowFileName);
            await repository.UpsertWorkflowAsync(Path.GetFileNameWithoutExtension(path), IsTextToVideoWorkflow(path) ? "Video" : "ImageToVideo", path,
                manifest.Assets.Single(asset => asset.Role == "diffusion").File,
                IsTextToVideoWorkflow(path) ? "{\"positiveNode\":\"6\",\"seedNodes\":[\"7\"],\"outputNodes\":[\"15\"]}" : "{\"positiveNode\":\"6\",\"imageNode\":\"5\",\"seedNodes\":[\"7\"],\"outputNodes\":[\"15\"]}", ct);
        }
        foreach (var asset in manifest.Assets)
        {
            var model = ModelPath(asset.Target);
            var info = new FileInfo(model);
            if (!info.Exists || info.Length != asset.Size) continue;
            var modelType = asset.Role switch { "diffusion" => "diffusion", "text_encoder" => "text_encoder", _ => "vae" };
            await repository.UpsertModelAsync(asset.File, modelType, model, info.Length, ct);
        }
    }

    public async Task EnsureWorkflowPinnedAsync(string path, CancellationToken ct = default)
    {
        var profile = ManagedProfiles.FirstOrDefault(p => string.Equals(p.WorkflowFileName, Path.GetFileName(path), StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException("H3 工作流未登记为本地固定路线");
        var expectedPath = Path.GetFullPath(Path.Combine(_settings.WorkflowsPath, profile.WorkflowFileName));
        if (!string.Equals(Path.GetFullPath(path), expectedPath, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("MiniMax 本地工作流路径与登记路线不同");
        var source = Path.Combine(_settings.RootPath, "tools", "minimax", profile.WorkflowFileName);
        if (!File.Exists(path) || await File.ReadAllTextAsync(path, ct) != await File.ReadAllTextAsync(source, ct))
            throw new InvalidOperationException("MiniMax 本地工作流已发生变化，请先检查版本；不会静默替换");
    }

    public static TaskInput BuildTask(MiniMaxLocalInput input, long workflowId, string requestId, string idempotencyKey)
    {
        var profile = ResolveProfile(input.Profile);
        if (string.IsNullOrWhiteSpace(input.Prompt) || input.Prompt.Length > 7000)
            throw new InvalidOperationException("请填写 1–7000 字符的镜头与声音描述");
        _ = ResolveWorkflowFileName(profile, input.TextToVideo, input.Steps);
        if (!input.TextToVideo && string.IsNullOrWhiteSpace(input.InputImagePath)) throw new InvalidOperationException("请选择本次镜头的首帧");
        if (input.TextToVideo && !string.IsNullOrWhiteSpace(input.InputImagePath)) throw new InvalidOperationException("文生视频不接受首帧；需要参考图片时请选择图生视频");
        if (input.ProjectId <= 0 || workflowId <= 0 || input.Seed < 0) throw new InvalidOperationException("项目、工作流或种子无效");
        var firstLast = profile.Id == FirstLastProfile;
        if (firstLast && (input.TextToVideo || string.IsNullOrWhiteSpace(input.LastFramePath)
            || !ReleaseEligibilityService.IsSha256ForExport(input.FirstFrameSha256)
            || !ReleaseEligibilityService.IsSha256ForExport(input.LastFrameSha256)))
            throw new InvalidOperationException("首尾双帧实验必须提供两张图片和各自明确的SHA256，禁止文生模式");
        if (!firstLast && (!string.IsNullOrWhiteSpace(input.LastFramePath)
            || !string.IsNullOrWhiteSpace(input.FirstFrameSha256) || !string.IsNullOrWhiteSpace(input.LastFrameSha256)))
            throw new InvalidOperationException("目标尾帧和双帧哈希只属于显式firstlast480实验，不能隐式改变现有路线");
        var parameters = JsonSerializer.SerializeToNode(new
        {
            provider = "MiniMaxLocal", profile = profile.Id, textToVideo = input.TextToVideo, prompt = input.Prompt.Trim(), seed = input.Seed,
            width = profile.Width, height = profile.Height, frames = 124, fps = 24, steps = input.Steps,
            duration = 124m / 24m, preserveAudio = true, extractNativeAudio = true,
            qualityReferenceImagePath = input.InputImagePath, contentReview = "NeedReview"
        })!.AsObject();
        if (firstLast)
        {
            parameters["conditioningMode"] = "FirstLastFrame";
            parameters["lastFramePath"] = input.LastFramePath;
            parameters["firstFrameSha256"] = input.FirstFrameSha256!.ToLowerInvariant();
            parameters["lastFrameSha256"] = input.LastFrameSha256!.ToLowerInvariant();
            parameters["inputSlots"] = new JsonObject { ["firstFrame"] = input.InputImagePath, ["lastFrame"] = input.LastFramePath };
        }
        return new TaskInput
        {
            ProjectId = input.ProjectId, TaskType = input.TextToVideo ? "TextToVideo" : "ImageToVideo", ResourceClass = "GPU", WorkflowId = workflowId,
            InputImagePath = input.InputImagePath, Stage = "MiniMax-Local-Experiment", MaxRetries = 0,
            RequestId = requestId, IdempotencyKey = idempotencyKey,
            Parameters = JsonSerializer.SerializeToElement(parameters)
        };
    }

    public static void ValidateManagedParameters(JsonElement parameters, string? workflowPath = null)
    {
        var profile = ResolveProfile(parameters.TryGetProperty("profile", out var selected) ? selected.GetString() : null);
        if (parameters.TryGetProperty("textToVideo", out var mode) && mode.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidOperationException("textToVideo必须为明确的布尔值");
        var textToVideo = mode.ValueKind == JsonValueKind.True;
        var expectedSteps = string.Equals(Path.GetFileName(workflowPath), Native1080Quality30WorkflowFileName, StringComparison.OrdinalIgnoreCase) ? 30 : 20;
        if (workflowPath is not null && !string.Equals(Path.GetFileName(workflowPath), ResolveWorkflowFileName(profile, textToVideo, expectedSteps), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("H3 生成规格与所选工作流不匹配");
        foreach (var (name, expected) in new[] { ("width", profile.Width), ("height", profile.Height), ("frames", 124), ("fps", 24), ("steps", expectedSteps) })
            if (!parameters.TryGetProperty(name, out var value) || !value.TryGetInt32(out var actual) || actual != expected)
                throw new InvalidOperationException($"本地 H3 {profile.Id} 固定 {name}={expected}；不会隐式改变生成规格");
        if (!parameters.TryGetProperty("seed", out var seed) || !seed.TryGetInt64(out var number) || number < 0)
            throw new InvalidOperationException("本地 H3 必须显式保存非负种子");
        if (!parameters.TryGetProperty("prompt", out var prompt) || prompt.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(prompt.GetString()) || prompt.GetString()!.Length > 7000)
            throw new InvalidOperationException("本地 H3 必须显式保存本次镜头和声音描述");
        ValidateFrameParameters(parameters, profile.Id == FirstLastProfile);
    }

    public static string? LastFramePath(JsonElement parameters) => parameters.ValueKind == JsonValueKind.Object
        && parameters.TryGetProperty("lastFramePath", out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    public static void ValidateFrameWorkflowSelection(JsonElement parameters, string workflowPath)
    {
        var firstLast = parameters.ValueKind == JsonValueKind.Object && parameters.TryGetProperty("profile", out var profile)
            && profile.ValueKind == JsonValueKind.String && profile.GetString() == FirstLastProfile;
        if (firstLast != IsFirstLastWorkflow(workflowPath))
            throw new InvalidOperationException("H3首尾双帧参数只能绑定受管firstlast480工作流，禁止借用其他H3图绕过双帧核验");
    }

    public static void ValidateFrameParameters(JsonElement parameters, bool firstLast)
    {
        var tail = LastFramePath(parameters);
        if (!firstLast)
        {
            if (!string.IsNullOrWhiteSpace(tail) || parameters.TryGetProperty("conditioningMode", out _)
                || parameters.TryGetProperty("firstFrameSha256", out _) || parameters.TryGetProperty("lastFrameSha256", out _)
                || parameters.TryGetProperty("inputSlots", out var extraSlots) && extraSlots.ValueKind == JsonValueKind.Object
                    && extraSlots.TryGetProperty("lastFrame", out _))
                throw new InvalidOperationException("H3目标尾帧必须使用显式firstlast480实验");
            return;
        }
        if (parameters.TryGetProperty("textToVideo", out var mode) && mode.ValueKind == JsonValueKind.True)
            throw new InvalidOperationException("首尾双帧实验不能使用文生模式");
        if (!parameters.TryGetProperty("conditioningMode", out var conditioning) || conditioning.GetString() != "FirstLastFrame")
            throw new InvalidOperationException("首尾双帧实验必须明确conditioningMode=FirstLastFrame");
        if (string.IsNullOrWhiteSpace(tail) || !parameters.TryGetProperty("inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object
            || slots.EnumerateObject().Count() != 2
            || !slots.TryGetProperty("firstFrame", out var first) || first.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(first.GetString())
            || !slots.TryGetProperty("lastFrame", out var last) || last.ValueKind != JsonValueKind.String || last.GetString() != tail)
            throw new InvalidOperationException("首尾双帧必须且只能声明firstFrame/lastFrame两个明确输入槽，尾帧路径必须一致");
        foreach (var name in new[] { "firstFrameSha256", "lastFrameSha256" })
            if (!parameters.TryGetProperty(name, out var hash) || hash.ValueKind != JsonValueKind.String || !ReleaseEligibilityService.IsSha256ForExport(hash.GetString()))
                throw new InvalidOperationException($"首尾双帧缺少有效{name}");
    }

    public async Task<IReadOnlyList<H3FrameAsset>> ValidateFrameAssetsAsync(string? firstPath, JsonElement parameters, AssetPathPolicy paths,
        FfmpegService ffmpeg, CancellationToken ct = default)
    {
        var firstLast = parameters.TryGetProperty("profile", out var p) && p.GetString() == FirstLastProfile;
        ValidateFrameParameters(parameters, firstLast);
        if (!firstLast) return [];
        var slots = parameters.GetProperty("inputSlots");
        if (slots.GetProperty("firstFrame").GetString() != firstPath)
            throw new InvalidOperationException("H3首帧路径与firstFrame槽位不一致");
        var result = new List<H3FrameAsset>();
        foreach (var (role, source, hashName) in new[] { ("firstFrame", firstPath, "firstFrameSha256"), ("lastFrame", LastFramePath(parameters), "lastFrameSha256") })
        {
            if (!paths.TryResolveExisting(source, out var full, out var relative)
                || !new[] { ".png", ".jpg", ".jpeg", ".webp" }.Contains(Path.GetExtension(full), StringComparer.OrdinalIgnoreCase))
                throw new InvalidOperationException($"H3 {role}必须是受控数据目录内的现有静态图片");
            var hash = await ffmpeg.Sha256Async(full, ct);
            if (!string.Equals(hash, parameters.GetProperty(hashName).GetString(), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException($"H3 {role} SHA256与提交时绑定值不一致");
            var probe = await ffmpeg.ProbeAsync(full, ct);
            var profile = ResolveProfile(FirstLastProfile);
            if (probe?.Width != profile.Width || probe.Height != profile.Height || probe.FrameCount is not (null or 1))
                throw new InvalidOperationException($"H3 {role}必须为{profile.Width}×{profile.Height}单帧，禁止隐式裁切或拉伸首尾参考");
            result.Add(new H3FrameAsset(role, relative, hash!, profile.Width, profile.Height));
        }
        return result;
    }
}
public static class MiniMaxLocalEndpoints
{
    public static void MapMiniMaxLocalEndpoints(this WebApplication app)
    {
        app.MapGet("/api/minimax/local/realistic-preview", (StudioSettings settings, AssetPathPolicy paths) =>
        {
            try
            {
                var file = Path.Combine(settings.DataPath, "RealisticI2V20261022", "run.json");
                if (!File.Exists(file) || new FileInfo(file).Length > 1024 * 1024) return Results.NotFound(new { error = "写实图生视频对照尚未准备" });
                using var report = JsonDocument.Parse(File.ReadAllText(file)); var root = report.RootElement;
                string? Media(string name, string extension) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
                    && paths.TryResolveExisting(value.GetString(), out _, out var relative) && relative.StartsWith("Artifacts/", StringComparison.Ordinal)
                    && relative.EndsWith(extension, StringComparison.OrdinalIgnoreCase) ? relative : null;
                long? Number(string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number) ? number : null;
                string? Text(string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString()?[..Math.Min(value.GetString()!.Length, 500)] : null;
                return Results.Ok(new { stage = root.TryGetProperty("stage", out var stage) ? stage.GetString() : "Preparing",
                    reference = Media("referencePath", ".png"), video20 = Media("video20TaskIdPath", ".mp4"), video30 = Media("video30TaskIdPath", ".mp4"),
                    finalVideo = Media("finalVideoPath", ".mp4"), selectedSteps = Number("selectedSteps"),
                    task20 = Number("video20TaskId"), task30 = Number("video30TaskId"), continuationTask = Number("continuationTaskId"), finalTask = Number("finalTaskId"),
                    referenceCandidates = Enumerable.Range(1, 5).Select(number => new { candidate = number, taskId = Number($"reference{number}TaskId"),
                        path = Media($"reference{number}TaskIdPath", ".png"), review = Text($"reference{number}Review") }).Where(candidate => candidate.path is not null).ToArray() });
            }
            catch (Exception ex) when (ex is IOException or JsonException) { return Results.NotFound(new { error = "写实图生视频对照暂不可读" }); }
        });
        app.MapGet("/api/minimax/local/history", async (StudioRepository repo, CancellationToken ct) =>
        {
            var rows = await repo.TasksAsync(200, ct, recentFirst: true);
            return Results.Ok(rows.Where(row => row.Text("stage") == "MiniMax-Local-Experiment").Take(20).Select(row =>
            {
                using var input = row.Json("inputJson");
                var parameters = input.RootElement.TryGetProperty("parameters", out var value) ? value : default;
                return new
                {
                    id = row.Long("id"), projectId = row.LongOrNull("projectId"), status = row.Text("status"),
                    progress = row.Decimal("progress"), createdAt = row.GetValueOrDefault("createdAt"),
                    errorMessage = row.Text("errorMessage"), provider = "MiniMaxLocal",
                    seed = parameters.ValueKind == JsonValueKind.Object && parameters.TryGetProperty("seed", out var seed) ? seed.GetRawText() : null,
                    profile = parameters.ValueKind == JsonValueKind.Object && parameters.TryGetProperty("profile", out var profile) ? profile.GetString() : "baseline480"
                };
            }));
        });
        app.MapGet("/api/minimax/local/status", async (MiniMaxLocalService local, StudioRepository repo, ComfyUiClient comfy, GenerationQueue queue, CancellationToken ct) =>
        {
            var assets = local.AssetStatus();
            var workflows = await repo.WorkflowsAsync(ct);
            var workflow = workflows.FirstOrDefault(row => Path.GetFileName(row.Text("path")) == MiniMaxLocalService.WorkflowFileName);
            var runtime = await comfy.CheckAsync(ct);
            return Results.Ok(new
            {
                provider = "MiniMaxLocal", apiKeyRequired = false, productionEligible = false,
                assets, downloadedBytes = assets.Sum(asset => asset.DownloadedBytes), totalBytes = assets.Sum(asset => asset.ExpectedBytes),
                modelsPresent = assets.All(asset => asset.Present), modelsVerified = assets.All(asset => asset.Verified),
                workflowId = workflow?.Long("id"), comfyOnline = runtime.Online, gpu = runtime.Gpu, queue = queue.Status,
                license = local.Manifest().License, licenseUrl = local.Manifest().LicenseUrl,
                generation = new { width = 864, height = 480, frames = 124, fps = 24, nativeAudio = true }, integrationRun = local.IntegrationRun(),
                generationProfiles = MiniMaxLocalService.Profiles.Select(p => new { id = p.Id, label = p.Label, width = p.Width, height = p.Height, fps = 24, frames = 124, steps = 20,
                    workflowId = workflows.FirstOrDefault(row => Path.GetFileName(row.Text("path")) == p.WorkflowFileName)?.Long("id"),
                    stepOptions = p.Id == "native1080" ? new[] { 20, 30 } : new[] { 20 }, requiresLastFrame = p.Id == MiniMaxLocalService.FirstLastProfile }),
                message = "本地 H3 量化实验；先审核短片的角色、动作和声音，再决定是否进入剧集。"
            });
        });
        app.MapPost("/api/minimax/local/register", async (MiniMaxLocalService local, StudioRepository repository, CancellationToken ct) =>
        {
            try { await local.RegisterAsync(repository, ct); return Results.Ok(new { registered = true }); }
            catch (InvalidOperationException ex) { return Results.UnprocessableEntity(new { error = ex.Message }); }
        });
        app.MapPost("/api/minimax/local/verify", async (MiniMaxLocalService local, CancellationToken ct) =>
        {
            try { await local.EnsureVerifiedAsync(ct); return Results.Ok(new { verified = true, assets = local.AssetStatus() }); }
            catch (InvalidOperationException ex) { return Results.UnprocessableEntity(new { error = ex.Message }); }
        });
        app.MapPost("/api/minimax/local/reference", async (HttpRequest request, AssetPathPolicy paths, StudioRepository repo, CancellationToken ct) =>
        {
            if (!request.HasFormContentType) return Results.BadRequest(new { error = "请上传首帧图片" });
            var form = await request.ReadFormAsync(ct);
            if (!long.TryParse(form["projectId"], out var projectId) || projectId <= 0
                || (await repo.ProjectAsync(projectId, ct)).Count == 0)
                return Results.UnprocessableEntity(new { error = "请先选择已有项目" });
            var file = form.Files.GetFile("file");
            if (file is null) return Results.BadRequest(new { error = "请上传首帧图片" });
            var uploaded = await paths.StoreUploadAsync(file, $"Projects/{projectId}/MiniMaxReferences", UploadKind.Image, 25L * 1024 * 1024, ct);
            return Results.Ok(new { assetPath = uploaded.RelativePath, mediaUrl = $"/api/media?assetPath={Uri.EscapeDataString(uploaded.RelativePath)}" });
        });
        app.MapPost("/api/minimax/local/video", async (MiniMaxLocalInput input, HttpRequest request, MiniMaxLocalService local, StudioRepository repo, TaskSubmissionPreflightService preflight, GenerationQueue queue, CancellationToken ct) =>
        {
            var key = request.Headers["Idempotency-Key"].FirstOrDefault();
            if (string.IsNullOrWhiteSpace(key) || key.Length > 100) return Results.BadRequest(new { error = "提交时必须提供稳定的 Idempotency-Key" });
            try
            {
                var profile = MiniMaxLocalService.ResolveProfile(input.Profile);
                var workflowFileName = MiniMaxLocalService.ResolveWorkflowFileName(profile, input.TextToVideo, input.Steps);
                var workflow = (await repo.WorkflowsAsync(ct)).FirstOrDefault(row => Path.GetFileName(row.Text("path")) == workflowFileName);
                if (workflow is null) return Results.UnprocessableEntity(new { error = "请先登记 MiniMax 本地工作流" });
                var task = MiniMaxLocalService.BuildTask(input, workflow.Long("id"), request.HttpContext.TraceIdentifier, $"minimax-local:{key}");
                await local.EnsureWorkflowPinnedAsync(workflow.Text("path")!, ct);
                await local.EnsureVerifiedAsync(ct);
                var result = await preflight.CheckAsync(task, ct);
                if (!result.Passed) return Results.UnprocessableEntity(new { error = "本地 H3 提交前检查未通过", preflight = result });
                var id = await repo.CreateTaskAsync(task, ct);
                queue.Enqueue(id);
                return Results.Accepted($"/api/tasks/{id}", new { id, provider = "MiniMaxLocal", status = "Pending", contentReview = "NeedReview" });
            }
            catch (InvalidOperationException ex) { return Results.UnprocessableEntity(new { error = ex.Message }); }
        });
    }
}
