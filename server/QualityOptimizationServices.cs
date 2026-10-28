using System.Text.Json;

namespace VideoStudio.Server;

public sealed record QualityPreflightCheck(string Name, bool Passed, string Message, object? Value = null);

public sealed record QualityPreflightResult(
    bool Passed,
    bool ManualReviewRequired,
    string Status,
    IReadOnlyList<QualityPreflightCheck> Checks,
    IReadOnlyList<string> Issues,
    Dictionary<string, object?> Metrics);

/// <summary>
/// Final-I2V safety gate. It validates the real character reference, keyframe,
/// workflow, dimensions, duration and current GPU headroom before a task is
/// allowed to enter the GPU queue.
/// </summary>
public sealed class QualityPreflightService
{
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly FaceQualityService _faceQuality;
    private readonly FfmpegService _ffmpeg;
    private readonly ComfyUiClient _comfy;
    private readonly AssetPathPolicy _paths;
    private readonly WorkflowContractService _contracts;
    private readonly CharacterReferenceGateService _characterReferences;

    public QualityPreflightService(StudioSettings settings, StudioRepository repository, FaceQualityService faceQuality, FfmpegService ffmpeg, ComfyUiClient comfy, AssetPathPolicy paths, WorkflowContractService contracts, CharacterReferenceGateService characterReferences)
    {
        _settings = settings; _repository = repository; _faceQuality = faceQuality; _ffmpeg = ffmpeg; _comfy = comfy; _paths = paths; _contracts = contracts; _characterReferences = characterReferences;
    }

    public async Task<QualityPreflightResult> CheckI2VAsync(long shotId, I2VPreflightInput input, CancellationToken ct = default)
    {
        var shot = (await _repository.QueryShotAsync(shotId, ct)).FirstOrDefault();
        if (shot is null)
            return Reject("镜头不存在", new QualityPreflightCheck("shot", false, "镜头不存在"));

        var checks = new List<QualityPreflightCheck>();
        var issues = new List<string>();
        var metrics = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        var characterCount = CharacterCount(shot.Text("characterIdsJson"));
        var characterGate = characterCount > 0
            ? await _characterReferences.CheckShotAsync(shotId, ct)
            : new CharacterReferenceGateResult(true, [], []);
        IReadOnlyList<string> references = characterCount > 0
            ? characterGate.References.Select(reference => reference.FullPath).ToArray()
            : await _repository.ShotReferencePathsAsync(shotId, ct);
        var requestedPath = string.IsNullOrWhiteSpace(input.InputImagePath) ? shot.Text("selectedKeyframePath") ?? shot.Text("inputImagePath") : input.InputImagePath;
        var inputExists = _paths.TryResolveExisting(requestedPath, out var inputFullPath, out var inputAssetPath);
        var path = inputExists ? inputFullPath : requestedPath;
        var parameters = input.Parameters;
        var facePriority = GetBool(parameters, "faceStabilityPriority", characterCount > 0);
        var width = GetInt(parameters, "width") ?? (characterCount > 0 ? 320 : shot.Int("width", 512));
        var height = GetInt(parameters, "height") ?? (characterCount > 0 ? 416 : shot.Int("height", 320));
        var frames = GetInt(parameters, "frames") ?? (characterCount > 0 ? 73 : shot.Int("frames", 49));
        var fps = GetDecimal(parameters, "fps") ?? shot.Decimal("fps", 24);
        var duration = GetDecimal(parameters, "duration") ?? (frames / Math.Max(1m, fps));
        var referencesRequired = GetBool(parameters, "referenceRequired", characterCount > 0);
        var guideFrameIndex = GetInt(parameters, "guideFrameIndex") ?? Math.Max(1, frames - 1);

        metrics["shotId"] = shotId;
        metrics["characterCount"] = characterCount;
        metrics["referenceCount"] = references.Count;
        metrics["characterReferenceGate"] = new { characterGate.Passed, characterGate.Issues };
        metrics["inputImageAssetPath"] = inputExists ? inputAssetPath : null;
        metrics["width"] = width;
        metrics["height"] = height;
        metrics["frames"] = frames;
        metrics["fps"] = fps;
        metrics["duration"] = duration;
        metrics["faceStabilityPriority"] = facePriority;
        metrics["guideFrameIndex"] = guideFrameIndex;

        checks.Add(new QualityPreflightCheck("inputImage", inputExists, inputExists ? "关键帧存在且位于本地 AI 根目录" : "关键帧不存在或不在允许目录", inputExists ? inputAssetPath : null));
        if (!inputExists) issues.Add("关键帧不存在或不在允许目录");

        var referenceExists = characterCount > 0
            ? characterGate.Passed && references.Count > 0 && references.All(IsAllowedFile)
            : references.Count > 0 && references.All(IsAllowedFile);
        var referenceAssets = references.Select(reference => _paths.TryResolveExisting(reference, out _, out var relative) ? relative : null).Where(relative => relative is not null).Cast<string>().ToArray();
        var characterReviewPassed = characterCount == 0 || characterGate.Passed;
        checks.Add(new QualityPreflightCheck("characterReferenceApproval", characterReviewPassed,
            characterReviewPassed ? "角色参考图已通过人工审核且版本/哈希未变化" : string.Join("；", characterGate.Issues), referenceAssets));
        if (!characterReviewPassed) issues.AddRange(characterGate.Issues);
        var referenceCheckPassed = (!referencesRequired || referenceExists) && characterReviewPassed;
        checks.Add(new QualityPreflightCheck("characterReference", referenceCheckPassed, referenceExists ? "角色参考图可用" : referencesRequired ? "任务要求角色参考图，但没有可用单脸参考" : "未要求角色参考图", referenceAssets));
        if (!referenceCheckPassed && referencesRequired && !referenceExists) issues.Add("角色参考图缺失，已阻止 I2V");

        if (inputExists)
        {
            var probe = await _ffmpeg.ProbeAsync(path!, ct);
            var probeOk = probe?.Width is > 0 && probe.Height is > 0;
            checks.Add(new QualityPreflightCheck("keyframeReadable", probeOk, probeOk ? $"关键帧可读 {probe!.Width}x{probe.Height}" : "关键帧无法读取尺寸", probe));
            if (!probeOk) issues.Add("关键帧无法读取尺寸");

            if (characterCount > 0 && references.Count > 0)
            {
                var face = await _faceQuality.AnalyzeImageAsync(path!, references.FirstOrDefault(), portraitPreferred: true, ct);
                metrics["faceQuality"] = face.Metrics;
                checks.Add(new QualityPreflightCheck("imageFaceQa", !face.Rejected, face.Rejected ? string.Join("；", face.Issues) : "静态脸部代理检查未发现硬性异常；仍需人工确认", face.Score));
                if (face.Rejected) issues.AddRange(face.Issues);
            }
        }

        var workflowPath = await ResolveWorkflowPathAsync(shot, characterCount > 0, parameters, ct);
        var workflowOk = !string.IsNullOrWhiteSpace(workflowPath) && File.Exists(workflowPath);
        checks.Add(new QualityPreflightCheck("workflow", workflowOk, workflowOk ? $"工作流可用：{Path.GetFileName(workflowPath)}" : "I2V 工作流不存在", workflowOk ? Path.GetFileName(workflowPath) : null));
        if (!workflowOk) issues.Add("I2V 工作流不存在");
        if (workflowOk)
        {
            try
            {
                var plan = _contracts.Prepare(workflowPath!, "ImageToVideo", parameters ?? JsonSerializer.SerializeToElement(new { }), requireProductionRoute: true);
                checks.Add(new QualityPreflightCheck("workflowContract", true, $"工作流契约 {plan.ContractId}@{plan.ContractVersion} 已冻结", new { plan.Width, plan.Height, plan.Fps, plan.RequestedFrameCount, plan.ExecutionLength, plan.GuideFrameIndex }));
            }
            catch (WorkflowContractException ex)
            {
                checks.Add(new QualityPreflightCheck("workflowContract", false, $"{ex.Code}: {ex.Message}", Path.GetFileName(workflowPath)));
                issues.Add($"{ex.Code}: {ex.Message}");
            }
        }

        if (facePriority)
        {
            var aspectOk = Math.Abs(Math.Log(Math.Max(.01, (double)width / height) / (320d / 416d))) <= .10;
            var motionProfile = GetString(parameters, "motionProfile");
            var motionOk = motionProfile is null or "small" or "controlled-complex";
            var durationOk = duration is >= 3m and <= 5m;
            var framesOk = frames is >= 73 and <= 121;
            var guideFrameOk = guideFrameIndex is >= 1 && guideFrameIndex < frames;
            var longVideoExplicit = GetBool(parameters, "allowLongVideo", false) || duration <= 3.1m;
            checks.Add(new QualityPreflightCheck("guideFrameIndex", guideFrameOk, guideFrameOk ? "Reference guide is placed before the final frame" : "Reference guide frame must be between 1 and the final frame", guideFrameIndex));
            if (!guideFrameOk) issues.Add("I2V reference guide frame is outside the valid frame range");
            checks.Add(new QualityPreflightCheck("portraitAspect", aspectOk, aspectOk ? "人物 Draft 画幅与 320x416 竖幅匹配" : "人物 Draft 画幅不匹配，可能裁切眼睛或脸部", new { width, height }));
            checks.Add(new QualityPreflightCheck("draftDuration", durationOk, durationOk ? "人物 Draft 时长在 3～5 秒范围" : "人物 Draft 时长超出 3～5 秒", duration));
            checks.Add(new QualityPreflightCheck("draftFrames", framesOk, framesOk ? "人物 Draft 帧数在 73～121 范围" : "人物 Draft 帧数不在 73～121 范围", frames));
            checks.Add(new QualityPreflightCheck("longVideoGate", longVideoExplicit, longVideoExplicit ? "5 秒以上仅在显式实验参数下允许" : "超过 3 秒必须显式开启实验档 allowLongVideo", new { duration, allowLongVideo = GetBool(parameters, "allowLongVideo", false) }));
            checks.Add(new QualityPreflightCheck("motionProfile", motionOk, motionOk ? "动作档位为 small" : "动作档位过于激进", GetString(parameters, "motionProfile")));
            if (!aspectOk) issues.Add("人物 I2V 画幅与首帧不匹配");
            if (!durationOk) issues.Add("人物 I2V Draft 时长应限制在 3～5 秒");
            if (!framesOk) issues.Add("人物 I2V Draft 帧数应限制在 73～121");
            if (!longVideoExplicit) issues.Add("人物 I2V 超过 3 秒必须显式开启实验档");
            if (!motionOk) issues.Add("人物 I2V Draft 不允许使用激进动作档位");
        }

        var comfy = await _comfy.CheckAsync(ct);
        var gpuOk = comfy.Online && (comfy.Gpu is null || comfy.Gpu.FreeMiB >= _settings.MinFreeVramMiB);
        checks.Add(new QualityPreflightCheck("gpu", gpuOk, !comfy.Online ? "ComfyUI 当前离线" : comfy.Gpu is null ? "ComfyUI 在线但未返回 GPU 信息" : $"GPU 可提交，剩余 {comfy.Gpu.FreeMiB} MiB", comfy.Gpu));
        if (!gpuOk) issues.Add("ComfyUI 离线或可用显存低于安全阈值");

        var manual = characterCount > 0;
        var passed = issues.Count == 0;
        return new QualityPreflightResult(passed, manual, passed ? manual ? "NeedReview" : "Passed" : "Rejected", checks, issues, metrics);
    }

    private async Task<string?> ResolveWorkflowPathAsync(IReadOnlyDictionary<string, object?> shot, bool character, JsonElement? parameters, CancellationToken ct)
    {
        var requestedVersion = GetString(parameters, "workflowVersion");
        if (!string.IsNullOrWhiteSpace(requestedVersion))
        {
            var requestedContract = _contracts.Find(null, requestedVersion);
            if (requestedContract is not null)
            {
                var requestedPath = Path.Combine(_settings.WorkflowsPath, requestedContract.FileName);
                if (_paths.TryResolveExistingWorkflow(requestedPath, out var controlledRequestedPath, out _)) return controlledRequestedPath;
            }
            return null;
        }

        var workflowId = shot.LongOrNull("workflowId");
        if (workflowId is { } id)
        {
            var row = (await _repository.WorkflowsAsync(ct)).FirstOrDefault(x => x.LongOrNull("id") == id);
            if (row?.Text("path") is { } selected && _paths.TryResolveExistingWorkflow(selected, out var controlledSelectedPath, out _)) return controlledSelectedPath;
        }
        return null;
    }

    private static QualityPreflightResult Reject(string message, QualityPreflightCheck check)
        => new(false, false, "Rejected", [check], [message], new Dictionary<string, object?>());

    private bool IsAllowedFile(string? path)
        => _paths.IsAllowedExistingFile(path);

    private static int CharacterCount(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return 0;
        try { using var doc = JsonDocument.Parse(json); return doc.RootElement.ValueKind == JsonValueKind.Array ? doc.RootElement.GetArrayLength() : 0; }
        catch { return 0; }
    }

    private static bool GetBool(JsonElement? root, string name, bool fallback)
        => TryGet(root, name, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean() : fallback;

    private static int? GetInt(JsonElement? root, string name)
        => TryGet(root, name, out var value) && value.TryGetInt32(out var result) ? result : null;

    private static decimal? GetDecimal(JsonElement? root, string name)
        => TryGet(root, name, out var value) && value.TryGetDecimal(out var result) ? result : null;

    private static string? GetString(JsonElement? root, string name)
        => TryGet(root, name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static bool TryGet(JsonElement? root, string name, out JsonElement value)
    {
        if (root is { ValueKind: JsonValueKind.Object } element)
        {
            foreach (var property in element.EnumerateObject())
                if (string.Equals(property.Name, name, StringComparison.OrdinalIgnoreCase)) { value = property.Value; return true; }
        }
        value = default;
        return false;
    }
}
