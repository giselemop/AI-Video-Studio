using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace VideoStudio.Server;

public sealed record TaskSubmissionPreflightCheck(string Name, bool Passed, string Message, object? Value = null);

public sealed record TaskSubmissionPreflightResult(
    bool Passed,
    IReadOnlyList<TaskSubmissionPreflightCheck> Checks,
    IReadOnlyList<string> Issues);

/// <summary>
/// Validates user-submitted low-level tasks before a row is written to
/// generation_tasks. Queue-time validation remains as a safety net, but known
/// configuration failures should never become avoidable failed tasks.
/// </summary>
public sealed class TaskSubmissionPreflightService
{
    private static readonly HashSet<string> SupportedTaskTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "Image", "Keyframe", "ImageToVideo", "Video", "TextToVideo",
        "Enhance", "VideoEnhancement",
        "Audio", "TTS", "MusicSynthesis",
        "Subtitles",
        "Concat", "VideoConcat", "VideoRestore", "SkinComposite", "VisualActing", "VisualDetail", "DialogueComposite"
    };

    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly ComfyUiClient _comfy;
    private readonly LocalTtsService _tts;
    private readonly MiniMaxLocalService _miniMaxLocal;
    private readonly AssetPathPolicy _paths;
    private readonly DiskSpaceGuard _disk;
    private readonly WorkflowContractService _contracts;
    private readonly CharacterReferenceGateService _characterReferences;
    private readonly SeedVr2Service _seedVr2;
    private readonly FfmpegService _ffmpeg;
    private readonly CharacterLibraryService? _characterLibrary;
    private readonly CharacterStoryService? _characterStory;
    private readonly CharacterWorkshopService? _characterWorkshop;

    public TaskSubmissionPreflightService(
        StudioSettings settings,
        StudioRepository repository,
        ComfyUiClient comfy,
        LocalTtsService tts,
        AssetPathPolicy paths,
        DiskSpaceGuard disk,
        WorkflowContractService contracts,
        CharacterReferenceGateService characterReferences,
        MiniMaxLocalService? miniMaxLocal = null, SeedVr2Service? seedVr2 = null, FfmpegService? ffmpeg = null, CharacterLibraryService? characterLibrary = null, CharacterStoryService? characterStory = null, CharacterWorkshopService? characterWorkshop = null)
    {
        _settings = settings; _repository = repository; _comfy = comfy; _tts = tts; _paths = paths; _disk = disk; _contracts = contracts; _characterReferences = characterReferences;
        _miniMaxLocal = miniMaxLocal ?? new MiniMaxLocalService(settings);
        _seedVr2 = seedVr2 ?? new SeedVr2Service(settings);
        _ffmpeg = ffmpeg ?? new FfmpegService(settings, Microsoft.Extensions.Logging.Abstractions.NullLogger<FfmpegService>.Instance);
        _characterLibrary = characterLibrary;
        _characterStory = characterStory; _characterWorkshop = characterWorkshop;
    }

    public async Task<TaskSubmissionPreflightResult> CheckAsync(TaskInput input, CancellationToken ct = default, bool businessSubmission = false)
    {
        var checks = new List<TaskSubmissionPreflightCheck>();
        var issues = new List<string>();
        void Check(string name, bool passed, string message, object? value = null)
        {
            checks.Add(new TaskSubmissionPreflightCheck(name, passed, message, SanitizeDiagnosticValue(value)));
            if (!passed) issues.Add(message);
        }

        var taskType = input.TaskType?.Trim() ?? string.Empty;
        var supported = SupportedTaskTypes.Contains(taskType);
        Check("taskType", supported,
            supported ? $"任务类型 {taskType} 可以通过通用提交入口执行" : "该任务类型必须使用对应的业务接口提交，不能绕过业务门禁",
            taskType);
        if (!supported) return new(false, checks, issues);

        if (TextEncodingGuard.FindError(input) is { } encodingError)
            Check("textEncoding", false, encodingError);

        using var emptyParameters = JsonDocument.Parse("{}");
        var parameters = input.Parameters is { ValueKind: JsonValueKind.Object } provided
            ? provided
            : emptyParameters.RootElement;
        if (Regex.IsMatch(parameters.GetRawText(), @"\?{2,}", RegexOptions.CultureInvariant))
            Check("parametersEncoding", false, "任务参数包含连续问号，疑似文本编码损坏；请使用 UTF-8 文本重新提交。");

        if (parameters.TryGetProperty("characterLibrary", out _))
        {
            try
            {
                if (_characterLibrary is null) throw new AssetValidationException("人物库验证服务未就绪");
                await _characterLibrary.ValidateTaskAsync(input, ct);
                Check("characterLibrary", true, "人物版本、首帧、固定设定和工作流与冻结快照一致");
            }
            catch (Exception ex) when (ex is ArgumentException or InvalidOperationException)
            { Check("characterLibrary", false, ex.Message); return new(false, checks, issues); }
        }

        foreach(var marker in new[]{CharacterStoryService.Marker,CharacterWorkshopService.Marker,CharacterStoryService.PreviewMarker})
        {
            if(!parameters.TryGetProperty(marker,out _))continue;
            if(!businessSubmission){Check(marker,false,"人物定型和剧情任务须经对应业务提交接口；重做失败项须提供定向修复记录，不能从通用提交或重试入口绕过次数限制");return new(false,checks,issues);}
            try
            {
                if(marker==CharacterStoryService.Marker){if(_characterStory is null)throw new AssetValidationException("剧情校验服务未就绪");await _characterStory.ValidateTaskAsync(input,ct);}
                else if(marker==CharacterStoryService.PreviewMarker){if(_characterStory is null)throw new AssetValidationException("剧情预览校验服务未就绪");await _characterStory.ValidatePreviewAsync(input,ct);}
                else {if(_characterWorkshop is null)throw new AssetValidationException("人物定型校验服务未就绪");await _characterWorkshop.ValidateTaskAsync(input,ct);}
                Check(marker,true,"不可变计划、基准、实际来源哈希和工作流一致");
            }
            catch(Exception ex)when(ex is ArgumentException or InvalidOperationException or JsonException or KeyNotFoundException){Check(marker,false,ex.Message);return new(false,checks,issues);}
        }
        var project = await ValidateProjectAsync(input.ProjectId, Check, ct);
        var episode = await ValidateEpisodeAsync(input.EpisodeId, Check, ct);
        var shot = await ValidateShotAsync(input.ShotId, Check, ct);
        ValidateParentRelations(input, project, episode, shot, Check);
        await ValidateDependencyAsync(input.DependencyTaskId, Check, ct);

        if(taskType.Equals("MusicSynthesis",StringComparison.OrdinalIgnoreCase))
        {
            Check("musicProject",input.ProjectId is >0&&input.EpisodeId is null&&input.ShotId is null&&input.ProductionRunId is null,"原创配乐仅允许绑定项目的独立预览任务");
            Check("musicCpu",input.ResourceClass=="CPU"&&input.WorkflowId is null&&input.MaxRetries==0&&string.IsNullOrWhiteSpace(input.InputImagePath),"原创配乐须经CPU队列，不接收工作流或输入图片");
            Check("musicComposition",OriginalMusicService.Valid(parameters),"仅接受明确登记的本地原创配乐与固定时长");
            return new(issues.Count==0,checks,issues);
        }

        if (taskType.Equals("DialogueComposite", StringComparison.OrdinalIgnoreCase))
        {
            Check("dialoguePreviewOnly", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null, "对话合成仅开放独立预览");
            Check("dialogueCpuOnly", input.ResourceClass == "CPU", "对话合成必须经过CPU队列");
            Check("dialogueDisk", _disk.Check(additionalBytes: 2L * 1024 * 1024 * 1024).Allowed, "对话合成需要磁盘余量");
            try { await new DialogueComposeService(_settings, _paths).RunAsync(parameters, null, ct); Check("dialogueManifest", true, "角色、遮罩、SHA及镜头时序已校验"); }
            catch (Exception ex) when (ex is IOException or InvalidOperationException or JsonException or ArgumentException) { Check("dialogueManifest", false, ex.Message); }
            return new(issues.Count == 0, checks, issues);
        }
        if (taskType.Equals("VisualDetail", StringComparison.OrdinalIgnoreCase))
        {
            Check("detailPreviewOnly", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null, "细节回补仅开放独立预览");
            Check("detailCpuOnly", input.ResourceClass == "CPU", "细节回补必须使用CPU队列");
            Check("detailDisk", _disk.Check(additionalBytes: 2L * 1024 * 1024 * 1024).Allowed, "细节回补需要磁盘余量");
            try { await new VisualDetailService(_settings, _paths).RunAsync(parameters, null, ct); Check("detailManifest", true, "源片与精修片的48帧、规格和SHA已绑定"); }
            catch (Exception ex) when (ex is IOException or InvalidOperationException or JsonException or ArgumentException) { Check("detailManifest", false, ex.Message); }
            return new(issues.Count == 0, checks, issues);
        }
        if (taskType.Equals("VisualActing", StringComparison.OrdinalIgnoreCase))
        {
            Check("actingPreviewOnly", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null,
                "参考表演仅开放独立实验预览");
            Check("actingGpuQueue", input.ResourceClass == "GPU", "参考表演必须经过GPU全局互斥队列");
            var disk = _disk.Check(additionalBytes: 20L * 1024 * 1024 * 1024);
            Check("actingDisk", disk.Allowed, "参考表演需要至少20GiB磁盘余量");
            try
            {
                await new VisualActingService(_settings, _paths, _ffmpeg).ValidateAsync(parameters, true, ct);
                Check("actingManifest", true, "本地运行时、输入哈希、许可与片段规格已通过预检");
            }
            catch (Exception ex) when (ex is IOException or InvalidOperationException or JsonException or ArgumentException or KeyNotFoundException)
            { Check("actingManifest", false, ex.Message); }
            return new(issues.Count == 0, checks, issues);
        }

        if (taskType.Equals("SkinComposite", StringComparison.OrdinalIgnoreCase))
        {
            var skinDisk = _disk.Check();
            Check("skinDisk", skinDisk.Allowed, skinDisk.Allowed ? "肤质小样的目标卷空间充足" : "肤质小样因可用空间不足被阻止", DiskSpaceGuard.Diagnostic(skinDisk));
            Check("skinPreviewOnly", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null,
                "局部肤质小样只接受独立预览，不替代正式审核");
            Check("skinResource", input.ResourceClass == "CPU", "肤质纹理的跨帧合成必须使用CPU队列；扩散关键帧另走GPU队列");
            var service = new SkinPilotService(_settings);
            Check("skinVersion", FirstString(parameters, "engineVersion") == service.Identity, "局部肤质合成须绑定当前脚本版本");
            try { await service.ValidateAsync(parameters, ct); Check("skinManifest", true, "两秒源片、关键帧与保护区域文件已绑定SHA256"); }
            catch (Exception ex) when (ex is IOException or InvalidOperationException or JsonException or ArgumentException)
            { Check("skinManifest", false, ex.Message); }
            return new(issues.Count == 0, checks, issues);
        }

        CharacterReferenceGateResult? characterGate = null;
        if (shot is not null && CharacterReferenceGateService.ReadCharacterIds(shot.Text("characterIdsJson")).Count > 0)
        {
            characterGate = await _characterReferences.CheckShotAsync(shot.Long("id"), ct);
            Check("characterReferenceApproval", characterGate.Passed,
                characterGate.Passed ? "镜头所用角色参考图已由登录审核人批准且版本/哈希未变化" : string.Join("；", characterGate.Issues),
                characterGate.References.Select(reference => new { reference.CharacterId, reference.ReferenceId, reference.AssetVersion, reference.AssetSha256 }));
        }

        var isAudio = taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase);
        var isComfy = taskType.Equals("Image", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Keyframe", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("TextToVideo", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Video", StringComparison.OrdinalIgnoreCase);
        var needsInputFile = taskType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Video", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Enhance", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("VideoEnhancement", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("VideoRestore", StringComparison.OrdinalIgnoreCase);
        var isQwenAudio = isAudio && Qwen3TtsService.IsQwen(FirstString(parameters, "voiceId"));
        var isCpuTask = (isAudio && !isQwenAudio)
            || taskType.Equals("Subtitles", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Concat", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("VideoConcat", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Enhance", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("VideoEnhancement", StringComparison.OrdinalIgnoreCase);

        if (DiskSpaceGuard.IsHighCostTask(taskType, input.ResourceClass))
        {
            var disk = _disk.Check();
            Check("diskSpace", disk.Allowed, disk.Allowed ? "高成本任务的目标卷空间充足" : "高成本任务因目标卷可用空间不足而拒绝提交", DiskSpaceGuard.Diagnostic(disk));
        }

        if (isCpuTask)
        {
            var cpu = string.Equals(input.ResourceClass, "CPU", StringComparison.OrdinalIgnoreCase);
            Check("resourceClass", cpu, cpu ? "CPU 任务资源类别正确" : "音频、字幕、拼接和增强任务必须使用 CPU 队列", input.ResourceClass);
        }
        if (isQwenAudio)
        {
            Check("resourceClass", string.Equals(input.ResourceClass, "GPU", StringComparison.OrdinalIgnoreCase), "Qwen3-TTS 必须使用受互斥锁保护的 GPU 队列", input.ResourceClass);
            Check("audioEngineVersion", FirstString(parameters, "engineVersion") == _tts.EngineIdentity(FirstString(parameters, "voiceId")!), "Qwen3-TTS 必须显式绑定当前引擎版本");
        }

        var inputPath = string.IsNullOrWhiteSpace(input.InputImagePath)
            ? FirstString(parameters, "inputImagePath", "input")
            : input.InputImagePath;
        var inputValid = IsAllowedExistingFile(inputPath);
        if (needsInputFile)
            Check("inputMedia", inputValid, inputValid ? "输入媒体存在且位于允许目录" : "任务要求存在于本地 AI 数据目录的输入媒体", inputPath);
        else if (!string.IsNullOrWhiteSpace(inputPath))
            Check("optionalInputMedia", inputValid, inputValid ? "可选输入媒体存在且位于允许目录" : "输入媒体不存在或不在允许目录", inputPath);

        var referencePaths = StringValues(parameters, "referenceImages");
        var controlPaths = StringValues(parameters, "controlImages")
            .Concat(new[] { FirstString(parameters, "controlImagePath") }.Where(path => !string.IsNullOrWhiteSpace(path)).Cast<string>())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        ValidatePathList("referenceImages", referencePaths, "角色参考图", Check);
        if (characterGate is not null && characterGate.Passed && referencePaths.Count > 0)
        {
            var approvedPaths = characterGate.References.Select(reference => Path.GetFullPath(reference.FullPath)).ToHashSet(StringComparer.OrdinalIgnoreCase);
            var explicitlyBound = referencePaths.All(path => _paths.TryResolveExisting(path, out var fullPath, out _) && approvedPaths.Contains(fullPath));
            Check("characterReferenceBinding", explicitlyBound,
                explicitlyBound ? "任务显式绑定的身份参考图与已批准角色资产一致" : "任务显式身份参考图不是当前已批准的角色资产版本，已阻止提交", referencePaths);
        }
        ValidatePathList("controlImages", controlPaths, "ControlNet 姿态图", Check);
        ValidateInputSlots(parameters, Check);

        if (taskType.Equals("VideoRestore", StringComparison.OrdinalIgnoreCase))
        {
            var ready = _seedVr2.Check();
            Check("restoreEngine", ready.Ready, ready.Message);
            Check("restoreVersion", ready.Ready && FirstString(parameters, "engineVersion") == _seedVr2.Identity, "修复任务必须绑定当前SeedVR2版本");
            Check("restoreResource", input.ResourceClass == "GPU", "SeedVR2必须使用GPU互斥队列");
            Check("restorePreviewOnly", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null, "SeedVR2当前仅用于独立预览修复");
            var strengthValid = !parameters.TryGetProperty("strength", out var strength)
                || strength.ValueKind == JsonValueKind.Number && strength.TryGetDouble(out var s) && double.IsFinite(s) && s is >= .25 and <= 1;
            Check("restoreStrength", strengthValid, "修复强度必须为0.25–1的有限数值");
            if (inputValid && _paths.TryResolveExisting(inputPath, out var fullPath, out _))
            {
                var probe = await _ffmpeg.ProbeAsync(fullPath, ct);
                var validMedia = probe?.Width is > 0 and <= 1920 && probe.Height is > 0 and <= 1080 && probe.Fps == 24 && probe.FrameCount is > 0 and <= 240;
                Check("restoreMedia", validMedia, "修复视频需为1920×1080以内、24FPS、1–240帧");
                try
                {
                    var outputSpec = SeedVr2Service.ResolveOutput(parameters, probe?.Width ?? 0, probe?.Height ?? 0);
                    Check("restoreOutput", true, $"SeedVR2输出{outputSpec.Width}×{outputSpec.Height}，规格{outputSpec.Profile}");
                }
                catch (InvalidOperationException ex) { Check("restoreOutput", false, ex.Message); }
                var expectedHash = FirstString(parameters, "sourceSha256");
                Check("restoreSourceBinding", expectedHash?.Length == 64 && expectedHash == await _ffmpeg.Sha256Async(fullPath, ct), "修复任务必须绑定当前源文件SHA256");
                if (parameters.TryGetProperty("cutFrames", out var cuts))
                {
                    var values = new List<int>();
                    var validCuts = cuts.ValueKind == JsonValueKind.Array && cuts.GetArrayLength() <= 8;
                    if (validCuts) foreach (var cut in cuts.EnumerateArray())
                    {
                        if (cut.ValueKind != JsonValueKind.Number || !cut.TryGetInt32(out var frame) || frame <= 0 || frame >= probe?.FrameCount) { validCuts = false; break; }
                        values.Add(frame);
                    }
                    Check("restoreCuts", validCuts && values.SequenceEqual(values.Distinct().Order()), "镜头边界须为升序、唯一、源片内部的帧号");
                }
            }
        }

        if (isAudio)
        {
            var text = FirstString(parameters, "text") ?? string.Empty;
            Check("audioText", !string.IsNullOrWhiteSpace(text),
                !string.IsNullOrWhiteSpace(text) ? "音频任务已提供对白或旁白文本" : "音频任务必须提供非空对白或旁白文本");
            if (!string.IsNullOrWhiteSpace(text))
            {
                var voice = FirstString(parameters, "voiceId") ?? string.Empty;
                var audioInput = new TtsInput { Text = text, VoiceId = voice,
                    Instruction = FirstString(parameters, "instruction") ?? "",
                    Speed = parameters.TryGetProperty("speed", out var speedElement) && speedElement.ValueKind == JsonValueKind.Number && speedElement.TryGetDecimal(out var audioSpeed) ? audioSpeed : 1,
                    Pitch = parameters.TryGetProperty("pitch", out var pitchElement) && pitchElement.ValueKind == JsonValueKind.Number && pitchElement.TryGetDecimal(out var audioPitch) ? audioPitch : 0 };
                var validation = _tts.ValidateInput(audioInput);
                Check("audioParameters", validation is null, validation ?? "配音参数有效");
                var tts = await _tts.PreflightAsync(voice, ct);
                Check("tts", tts.Passed,
                    tts.Passed ? "中文 TTS 实际预检通过" : $"中文 TTS 预检失败：{tts.Message}",
                    new { tts.VoiceId, tts.DurationSeconds });
            }
        }

        if (taskType.Equals("Subtitles", StringComparison.OrdinalIgnoreCase))
            Check("subtitleEpisode", input.EpisodeId is > 0, "字幕任务必须关联有效 Episode", input.EpisodeId);

        if (taskType.Equals("Concat", StringComparison.OrdinalIgnoreCase) || taskType.Equals("VideoConcat", StringComparison.OrdinalIgnoreCase))
        {
            try {await ConcatSourceIntegrity.ValidateAsync(parameters,_paths,_ffmpeg,ct);}
            catch(Exception ex)when(ex is ArgumentException or InvalidOperationException or IOException or JsonException){Check("concatSourceIntegrity",false,ex.Message);}
            if (parameters.TryGetProperty("audioStreamCopyFrom", out _))
            {
                var sources = StringValues(parameters, "files");
                var audioSource = FirstString(parameters, "audioStreamCopyFrom");
                Check("remuxMode", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null && sources.Count == 1
                    && !new[] { "singlePass", "audioTracks", "originalAudioVolume", "subtitlePath", "trimStartSeconds", "targetDurationSeconds", "targetWidth", "targetHeight" }.Any(k => parameters.TryGetProperty(k, out _)), "无损换轨限独立单视频，不允许混用转码参数");
                var resolved = _paths.TryResolveExisting(audioSource, out var audioFull, out _);
                Check("remuxAudioSource", resolved, "无损换轨要求受控目录内的完整音轨源");
                if (sources.Count == 1 && _paths.TryResolveExisting(sources[0], out var videoFull, out _) && resolved)
                {
                    Check("remuxSourceBinding", FirstString(parameters, "videoSha256") == await _ffmpeg.Sha256Async(videoFull, ct)
                        && FirstString(parameters, "audioStreamCopySha256") == await _ffmpeg.Sha256Async(audioFull, ct), "无损换轨必须绑定两个源SHA256");
                    var v = await _ffmpeg.ProbeAsync(videoFull, ct); var a = await _ffmpeg.ProbeAsync(audioFull, ct);
                    var resolutionOptInValid = !parameters.TryGetProperty("allowResolutionDifference", out var resolutionOptIn)
                        || resolutionOptIn.ValueKind is JsonValueKind.True or JsonValueKind.False;
                    var allowResolutionDifference = resolutionOptIn.ValueKind == JsonValueKind.True;
                    Check("remuxResolutionOptIn", resolutionOptInValid, "跨分辨率无损换轨选项必须为布尔值");
                    var compatibleGeometry = FfmpegService.IsRemuxGeometryCompatible(v?.Width, v?.Height, a?.Width, a?.Height, allowResolutionDifference);
                    Check("remuxMedia", v?.DurationSeconds is > 0 && a?.HasAudio == true && v.FrameCount is > 0 && v.FrameCount == a.FrameCount
                        && v.Fps == a.Fps && compatibleGeometry && Math.Abs(v.DurationSeconds.Value - (a.DurationSeconds ?? 0)) < .001,
                        "无损换轨要求同时长、同帧率帧数；不同分辨率须显式启用且宽高比相同，音轨源必须有声音");
                    Check("remuxFps", !parameters.TryGetProperty("targetFps", out var requestedFps) || requestedFps.ValueKind == JsonValueKind.Number
                        && requestedFps.TryGetInt32(out var nativeFps) && nativeFps == v?.Fps, "无损换轨不改变帧率，targetFps须与源一致");
                }
            }
            if (parameters.TryGetProperty("singlePass", out var singlePass))
            {
                Check("singlePassBoolean", singlePass.ValueKind is JsonValueKind.True or JsonValueKind.False, "singlePass必须为布尔值");
                if (singlePass.ValueKind == JsonValueKind.True)
                {
                    Check("singlePassMode", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null, "保细节导出暂用于独立预览");
                    Check("singlePassSpec", new[] { "targetWidth", "targetHeight", "targetFps", "targetDurationSeconds" }.All(k => parameters.TryGetProperty(k, out _)), "保细节导出必须明确尺寸、帧率和时长");
                    var caption = FirstString(parameters, "subtitlePath");
                    Check("singlePassCaptions", string.IsNullOrWhiteSpace(caption) || Path.GetExtension(caption).Equals(".srt", StringComparison.OrdinalIgnoreCase), "一次编码字幕仅接收受控SRT文件");
                }
            }
            if (parameters.TryGetProperty("trimStartSeconds", out var trim))
            {
                var fps = parameters.TryGetProperty("targetFps", out var f) && f.ValueKind == JsonValueKind.Number && f.TryGetInt32(out var rate) ? rate : 0;
                Check("singlePassTrim", parameters.TryGetProperty("singlePass", out var enabled) && enabled.ValueKind == JsonValueKind.True
                    && trim.ValueKind == JsonValueKind.Number && trim.TryGetDouble(out var begin) && double.IsFinite(begin) && begin is >= 0 and <= 3600
                    && fps > 0 && Math.Abs(begin * fps - Math.Round(begin * fps)) < .001, "裁剪起点只用于保细节导出且必须对齐整帧");
            }
            var files = StringValues(parameters, "files");
            Check("concatFiles", files.Count > 0, "拼接任务必须提供至少一个视频文件", files.Count);
            ValidatePathList("concatFiles", files, "拼接视频", Check);
            if (parameters.TryGetProperty("targetFps", out var concatFps))
                Check("concatFps", concatFps.ValueKind == JsonValueKind.Number && concatFps.TryGetInt32(out var concatRate) && concatRate is >= 24 and <= 60,
                    "拼接帧率必须为24–60FPS");
            if (parameters.TryGetProperty("audioTracks", out var tracks))
            {
                Check("concatNarrationMode", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null,
                    "低层剧情预览旁白只用于独立实验；正式Episode沿用审核资产渲染入口");
                Check("concatAudioTracks", tracks.ValueKind == JsonValueKind.Array, "剧情旁白必须是明确的音轨数组");
                if (tracks.ValueKind == JsonValueKind.Array)
                    foreach (var track in tracks.EnumerateArray())
                    {
                        if (track.ValueKind != JsonValueKind.Object)
                        {
                            Check("concatAudioTrack", false, "剧情旁白的每一项必须是音轨对象");
                            continue;
                        }
                        var trackPath = FirstString(track, "path");
                        Check("concatAudioPath", IsAllowedExistingFile(trackPath) && Path.GetExtension(trackPath)?.ToLowerInvariant() is ".wav" or ".mp3" or ".m4a",
                            "剧情旁白必须为允许目录中的有效音频路径");
                        bool TrackNumber(string name, double minimum, double maximum) => !track.TryGetProperty(name, out var value)
                            || (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number) && double.IsFinite(number) && number >= minimum && number <= maximum);
                        Check("concatAudioTiming", TrackNumber("startSeconds", 0, 3600) && TrackNumber("volume", .05, 2) && TrackNumber("tempo", .5, 2) && TrackNumber("fadeOutStartSeconds",0,3600) && TrackNumber("fadeOutDurationSeconds",0,60), "剧情旁白时间/音量/变速或淡出无效");
                    }
            }
            if (parameters.TryGetProperty("originalAudioVolume", out var originalVolume))
            {
                Check("concatOriginalVolumeMode", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null,
                    "低层预览原音音量只用于独立实验；正式Episode沿用审核资产渲染入口");
                Check("concatOriginalVolume", originalVolume.ValueKind == JsonValueKind.Number && originalVolume.TryGetDouble(out var originalGain)
                    && double.IsFinite(originalGain) && originalGain is >= 0 and <= 2, "原音音量必须为0–2的有限数值");
            }
            var captionPath = FirstString(parameters, "subtitlePath");
            if (!string.IsNullOrWhiteSpace(captionPath))
            {
                Check("concatCaptionMode", input.EpisodeId is null && input.ShotId is null && input.ProductionRunId is null, "实验字幕不替代正式Episode审核入口");
                Check("concatCaptionPath", IsAllowedExistingFile(captionPath) && Path.GetExtension(captionPath)?.ToLowerInvariant() is ".srt" or ".ass", "剧情字幕必须为允许目录中的SRT/ASS文件");
            }
            if (parameters.TryGetProperty("targetDurationSeconds", out var duration))
            {
                var seconds = duration.ValueKind == JsonValueKind.Number && duration.TryGetDouble(out var number) ? number : 0;
                int DeliveryInt(string name, int fallback) => !parameters.TryGetProperty(name, out var element) ? fallback
                    : element.ValueKind == JsonValueKind.Number && element.TryGetInt32(out var integer) ? integer : 0;
                var width = DeliveryInt("targetWidth", 1280);
                var height = DeliveryInt("targetHeight", 720);
                var fps = DeliveryInt("targetFps", 30);
                Check("concatDelivery", double.IsFinite(seconds) && seconds is > 0 and <= 3600
                    && width is >= 256 and <= 3840 && height is >= 256 and <= 3840 && width % 2 == 0 && height % 2 == 0
                    && fps is >= 24 and <= 60 && Math.Abs(seconds * fps - Math.Round(seconds * fps)) < .001,
                    "拼接交付规格必须为0–3600秒、偶数尺寸256–3840、24–60FPS，且时长对应完整帧", null);
            }
        }

        if (isComfy)
            await ValidateComfyTaskAsync(input, taskType, inputPath, referencePaths, controlPaths, parameters, Check, ct);

        return new(issues.Count == 0, checks, issues);
    }

    private async Task<Dictionary<string, object?>?> ValidateProjectAsync(long? projectId, Action<string, bool, string, object?> check, CancellationToken ct)
    {
        if (projectId is null) return null;
        if (projectId <= 0)
        {
            check("project", false, "项目 ID 必须为正整数", projectId);
            return null;
        }

        var project = (await _repository.ProjectAsync(projectId.Value, ct)).FirstOrDefault();
        check("project", project is not null, project is null ? "项目不存在，任务未提交" : "项目存在", projectId);
        return project;
    }

    private async Task<Dictionary<string, object?>?> ValidateEpisodeAsync(long? episodeId, Action<string, bool, string, object?> check, CancellationToken ct)
    {
        if (episodeId is null) return null;
        if (episodeId <= 0)
        {
            check("episode", false, "Episode ID 必须为正整数", episodeId);
            return null;
        }

        var episode = (await _repository.EpisodeAsync(episodeId.Value, ct)).FirstOrDefault();
        check("episode", episode is not null, episode is null ? "Episode 不存在，任务未提交" : "Episode 存在", episodeId);
        return episode;
    }

    private async Task<Dictionary<string, object?>?> ValidateShotAsync(long? shotId, Action<string, bool, string, object?> check, CancellationToken ct)
    {
        if (shotId is null) return null;
        if (shotId <= 0)
        {
            check("shot", false, "镜头 ID 必须为正整数", shotId);
            return null;
        }

        var shot = (await _repository.QueryShotAsync(shotId.Value, ct)).FirstOrDefault();
        check("shot", shot is not null, shot is null ? "镜头不存在，任务未提交" : "镜头存在", shotId);
        return shot;
    }

    private async Task ValidateDependencyAsync(long? taskId, Action<string, bool, string, object?> check, CancellationToken ct)
    {
        if (taskId is null) return;
        if (taskId <= 0)
        {
            check("dependency", false, "依赖任务 ID 必须为正整数", taskId);
            return;
        }

        var task = (await _repository.TaskAsync(taskId.Value, ct)).FirstOrDefault();
        check("dependency", task is not null, task is null ? "依赖任务不存在，任务未提交" : "依赖任务存在", taskId);
    }

    private static void ValidateParentRelations(
        TaskInput input,
        IReadOnlyDictionary<string, object?>? project,
        IReadOnlyDictionary<string, object?>? episode,
        IReadOnlyDictionary<string, object?>? shot,
        Action<string, bool, string, object?> check)
    {
        if (project is not null && episode is not null)
            check("projectEpisode", episode.LongOrNull("projectId") == input.ProjectId,
                episode.LongOrNull("projectId") == input.ProjectId ? "Episode 属于指定项目" : "Episode 不属于指定项目，任务未提交",
                new { input.ProjectId, input.EpisodeId });
        if (episode is not null && shot is not null)
            check("episodeShot", shot.LongOrNull("episodeId") == input.EpisodeId,
                shot.LongOrNull("episodeId") == input.EpisodeId ? "镜头属于指定 Episode" : "镜头不属于指定 Episode，任务未提交",
                new { input.EpisodeId, input.ShotId });
        if (project is not null && shot is not null)
            check("projectShot", shot.LongOrNull("projectId") == input.ProjectId,
                shot.LongOrNull("projectId") == input.ProjectId ? "镜头属于指定项目" : "镜头不属于指定项目，任务未提交",
                new { input.ProjectId, input.ShotId });
    }

    private async Task ValidateComfyTaskAsync(
        TaskInput input,
        string taskType,
        string? inputPath,
        IReadOnlyList<string> referencePaths,
        IReadOnlyList<string> controlPaths,
        JsonElement parameters,
        Action<string, bool, string, object?> check,
        CancellationToken ct)
    {
        var videoTask = taskType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("TextToVideo", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Video", StringComparison.OrdinalIgnoreCase);
        var workflows = await _repository.WorkflowsAsync(ct);
        var selected = input.WorkflowId is { } workflowId
            ? workflows.FirstOrDefault(row => row.LongOrNull("id") == workflowId)
            : null;
        var requestedVersion = FirstString(parameters, "workflowVersion");
        var requestedContract = _contracts.Find(null, requestedVersion);
        var path = selected?.Text("path")
            ?? (requestedContract is not null ? Path.Combine(_settings.WorkflowsPath, requestedContract.FileName) : null)
            ?? (!videoTask ? DefaultWorkflowPath() : null);
        var workflowType = selected?.Text("workflowType") ?? requestedContract?.WorkflowType;
        var workflowFullPath = string.Empty;

        if (input.WorkflowId is not null)
            check("workflowRecord", selected is not null, selected is null ? "所选工作流不存在，任务未提交" : "所选工作流已登记", input.WorkflowId);
        if (videoTask && input.WorkflowId is null && string.IsNullOrWhiteSpace(requestedVersion))
            check("workflowSelection", false, "图生视频任务必须显式声明 WorkflowId 或 workflowVersion；不会按模型可用性自动切换路线", null);
        if (videoTask && input.WorkflowId is null && !string.IsNullOrWhiteSpace(requestedVersion) && requestedContract is null)
            check("workflowSelection", false, "请求的 workflowVersion 未登记契约；不会按任务类型自动选择路线", requestedVersion);
        var typeMatches = string.IsNullOrWhiteSpace(workflowType)
            || (videoTask
                ? workflowType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
                    || workflowType.Equals("I2V", StringComparison.OrdinalIgnoreCase)
                    || workflowType.Equals("Video", StringComparison.OrdinalIgnoreCase)
                : workflowType.Equals("Image", StringComparison.OrdinalIgnoreCase)
                    || workflowType.Equals("TextToImage", StringComparison.OrdinalIgnoreCase));
        check("workflowType", typeMatches, typeMatches ? "工作流类型与任务一致" : "工作流类型与任务不匹配，任务未提交", workflowType);
        var workflowExists = !string.IsNullOrWhiteSpace(path) && _paths.TryResolveExistingWorkflow(path, out workflowFullPath, out _);
        check("workflowFile", workflowExists, workflowExists ? "工作流文件存在" : "工作流文件不存在，任务未提交", path);

        if (workflowExists)
        {
            try
            {
                var workflow = ComfyUiClient.LoadWorkflow(workflowFullPath);
                WorkflowExecutionPlan? contractPlan = null;
                var textTask = taskType.Equals("TextToVideo", StringComparison.OrdinalIgnoreCase);
                var textWorkflow = MiniMaxLocalService.IsTextToVideoWorkflow(workflowFullPath);
                check("textToVideoMode", textTask == textWorkflow && (!textTask || string.IsNullOrWhiteSpace(inputPath)),
                    "文生视频必须绑定无首帧的受管H3工作流；图生视频必须保持首帧语义", null);
                if (H3WorkflowPolicy.IsH3(workflow))
                {
                    try { MiniMaxLocalService.ValidateFrameWorkflowSelection(parameters, workflowFullPath); }
                    catch (InvalidOperationException ex) { check("h3FrameWorkflow", false, Trim(ex.Message), null); }
                    if (MiniMaxLocalService.IsManagedWorkflow(workflowFullPath))
                    {
                        try
                        {
                            MiniMaxLocalService.ValidateManagedParameters(parameters, workflowFullPath);
                            await _miniMaxLocal.EnsureWorkflowPinnedAsync(workflowFullPath, ct);
                            await _miniMaxLocal.EnsureVerifiedAsync(ct);
                            var h3Frames = await _miniMaxLocal.ValidateFrameAssetsAsync(inputPath, parameters, _paths, _ffmpeg, ct);
                            if (h3Frames.Count > 0) check("h3FrameSlots", true, "H3首尾双帧路径、SHA256和864×480单帧规格已核对", h3Frames);
                            check("minimaxLocalAssets", true, "本地 H3 工作流版本与四个组件的 SHA-256 已核对", null);
                        }
                        catch (InvalidOperationException ex) { check("minimaxLocalAssets", false, Trim(ex.Message), null); }
                    }
                    check("h3ExperimentalOnly", input.ShotId is null && input.ProductionRunId is null && input.EpisodeId is null,
                        "H3 当前仅支持无生产关联的独立实验；能力与许可验收前禁止进入成片链", null);
                    try
                    {
                        H3WorkflowPolicy.Validate(workflow, parameters);
                        check("h3Parameters", true, "H3 原生尺寸、帧数及节点范围校验通过", null);
                    }
                    catch (Exception ex) when (ex is InvalidOperationException or FormatException or OverflowException)
                    {
                        check("h3Parameters", false, Trim(ex.Message), null);
                    }
                    check("h3ReferenceRoles", referencePaths.Count <= 1 && !(referencePaths.Count > 0 && !string.IsNullOrWhiteSpace(inputPath)),
                        "H3 首轮只接受一张首帧，不接受含糊的多参考自动绑定", null);
                }
                else
                {
                    try
                    {
                        var plan = _contracts.Prepare(
                            workflowFullPath,
                            taskType,
                            parameters,
                            requireProductionRoute: input.ShotId is not null || input.EpisodeId is not null || input.ProductionRunId is not null);
                        contractPlan = plan;
                        check("workflowContract", true, $"工作流契约 {plan.ContractId}@{plan.ContractVersion} 已通过哈希、节点、模型和媒体规格检查", new { plan.ContractId, plan.ContractVersion, plan.WorkflowSha256, plan.Width, plan.Height, plan.Fps, plan.RequestedFrameCount, plan.ExecutionLength, plan.GuideFrameIndex });
                    }
                    catch (WorkflowContractException ex)
                    {
                        check("workflowContract", false, $"{ex.Code}: {ex.Message}", new { ex.Code, workflow = Path.GetFileName(workflowFullPath) });
                    }
                }
                var hasControlNet = HasNodeClass(workflow, "ControlNet");
                var hasIpAdapter = HasNodeClass(workflow, "IPAdapter");
                if (hasControlNet)
                {
                    var hasPoseSlot = contractPlan?.Slots.Any(slot => slot.Role.Equals("pose", StringComparison.OrdinalIgnoreCase)
                        && contractPlan.SlotPaths.TryGetValue(slot.Role, out var posePath) && IsAllowedExistingFile(posePath)) == true;
                    var hasPoseInput = hasPoseSlot || controlPaths.Count > 0;
                    check("controlNetInput", hasPoseInput,
                        hasPoseInput ? "ControlNet 已提供独立姿态图" : "ControlNet 工作流必须提供显式 pose 槽位或独立姿态图",
                        new { poseSlot = hasPoseSlot, legacyControlCount = controlPaths.Count });
                    check("controlNetIdentitySeparation", referencePaths.Count == 0,
                        referencePaths.Count == 0 ? "ControlNet 姿态输入未与身份参考图混用" : "ControlNet 姿态图必须与 referenceImages 身份参考图分开提交",
                        referencePaths.Count);
                }

                if (hasIpAdapter)
                {
                    var hasIdentityInput = IsAllowedExistingFile(inputPath) || referencePaths.Count > 0;
                    check("ipAdapterInput", hasIdentityInput,
                        hasIdentityInput ? "IP-Adapter 已提供输入或身份参考图" : "IP-Adapter 工作流必须提供输入图或 referenceImages 身份参考图",
                        new { inputAssetPath = SanitizeDiagnosticValue(inputPath), referenceCount = referencePaths.Count });
                }
            }
            catch (Exception ex)
            {
                check("workflowReadable", false, $"工作流无法读取：{Trim(ex.Message)}", Path.GetFileName(path));
            }
        }

        await ValidateLorasAsync(input, parameters, check, ct);
        var comfy = await _comfy.CheckAsync(ct);
        var gpuReady = comfy.Online && (comfy.Gpu is null || comfy.Gpu.FreeMiB >= _settings.MinFreeVramMiB);
        check("gpu", gpuReady,
            !comfy.Online ? "ComfyUI 当前离线，任务未提交" : comfy.Gpu is null ? "ComfyUI 在线，未返回 GPU 指标" : gpuReady ? $"GPU 可提交，剩余 {comfy.Gpu.FreeMiB} MiB" : $"GPU 可用显存不足，当前 {comfy.Gpu.FreeMiB} MiB，要求至少 {_settings.MinFreeVramMiB} MiB",
            comfy.Gpu);
    }

    private async Task ValidateLorasAsync(TaskInput input, JsonElement parameters, Action<string, bool, string, object?> check, CancellationToken ct)
    {
        var ids = (input.LoraIds ?? [])
            .Concat(LongValues(parameters, "loraIds"))
            .Distinct()
            .ToArray();
        var names = StringValues(parameters, "loraNames")
            .Concat(new[] { FirstString(parameters, "loraName") }.Where(name => !string.IsNullOrWhiteSpace(name)).Cast<string>())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (ids.Length == 0 && names.Length == 0) return;

        var rows = await _repository.LorasAsync(ct);
        foreach (var id in ids)
        {
            var row = rows.FirstOrDefault(candidate => candidate.Long("id") == id);
            var ready = row?.Text("path") is { } path && _paths.IsAllowedExistingModelFile(path);
            check($"lora:{id}", ready, ready ? "LoRA 已扫描且文件存在" : $"LoRA {id} 未扫描或文件不存在，任务未提交", id);
        }
        foreach (var name in names)
        {
            var row = rows.FirstOrDefault(candidate =>
                string.Equals(candidate.Text("name"), name, StringComparison.OrdinalIgnoreCase)
                || string.Equals(Path.GetFileName(candidate.Text("path") ?? string.Empty), Path.GetFileName(name), StringComparison.OrdinalIgnoreCase));
            var ready = row?.Text("path") is { } path && _paths.IsAllowedExistingModelFile(path);
            check($"lora:{name}", ready, ready ? "LoRA 已扫描且文件存在" : $"LoRA {name} 未扫描或文件不存在，任务未提交", name);
        }
    }

    private string DefaultWorkflowPath() => Path.Combine(_settings.WorkflowsPath, "01_portrait_quality_api.json");

    private bool IsAllowedExistingFile(string? path)
        => _paths.IsAllowedExistingFile(path);

    private void ValidatePathList(string name, IReadOnlyList<string> paths, string display, Action<string, bool, string, object?> check)
    {
        foreach (var path in paths)
        {
            var allowed = IsAllowedExistingFile(path);
            check($"{name}:{Path.GetFileName(path)}", allowed,
                allowed ? $"{display}存在且位于允许目录" : $"{display}不存在或不在允许目录",
                path);
        }
    }

    private void ValidateInputSlots(JsonElement parameters, Action<string, bool, string, object?> check)
    {
        if (parameters.ValueKind != JsonValueKind.Object || !parameters.TryGetProperty("inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object) return;
        foreach (var property in slots.EnumerateObject())
        {
            string? path = property.Value.ValueKind == JsonValueKind.String
                ? property.Value.GetString()
                : property.Value.ValueKind == JsonValueKind.Object && property.Value.TryGetProperty("path", out var pathValue) && pathValue.ValueKind == JsonValueKind.String
                    ? pathValue.GetString()
                    : null;
            if (string.IsNullOrWhiteSpace(path))
            {
                check($"inputSlot:{property.Name}", false, $"输入槽位 {property.Name} 必须提交位于受控目录的本地路径；AssetId 请使用正式任务接口", property.Name);
                continue;
            }
            var allowed = IsAllowedExistingFile(path);
            check($"inputSlot:{property.Name}", allowed, allowed ? $"输入槽位 {property.Name} 的媒体存在且位于允许目录" : $"输入槽位 {property.Name} 的媒体不存在或不在允许目录", path);
        }
    }

    private static bool HasNodeClass(JsonObject workflow, string token)
        => workflow.Any(pair => pair.Value is JsonObject node
            && (node["class_type"]?.GetValue<string>() ?? string.Empty).Contains(token, StringComparison.OrdinalIgnoreCase));

    private static string? FirstString(JsonElement root, params string[] names)
        => names.Select(name => TryGet(root, name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null)
            .FirstOrDefault(value => !string.IsNullOrWhiteSpace(value));

    private static IReadOnlyList<string> StringValues(JsonElement root, string name)
    {
        if (!TryGet(root, name, out var value)) return [];
        if (value.ValueKind == JsonValueKind.String) return string.IsNullOrWhiteSpace(value.GetString()) ? [] : [value.GetString()!];
        if (value.ValueKind != JsonValueKind.Array) return [];
        return value.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Cast<string>()
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IReadOnlyList<long> LongValues(JsonElement root, string name)
    {
        if (!TryGet(root, name, out var value)) return [];
        if (value.TryGetInt64(out var single)) return [single];
        if (value.ValueKind != JsonValueKind.Array) return [];
        return value.EnumerateArray().Where(item => item.TryGetInt64(out _)).Select(item => item.GetInt64()).Distinct().ToArray();
    }

    private static bool TryGet(JsonElement root, string name, out JsonElement value)
    {
        if (root.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in root.EnumerateObject())
            {
                if (string.Equals(property.Name, name, StringComparison.OrdinalIgnoreCase))
                {
                    value = property.Value;
                    return true;
                }
            }
        }
        value = default;
        return false;
    }

    private object? SanitizeDiagnosticValue(object? value)
    {
        if (value is null) return null;
        if (value is string text)
        {
            if (_paths.TryResolveExisting(text, out _, out var relative)) return relative;
            return Path.IsPathRooted(text) ? Path.GetFileName(text) : text;
        }
        if (value is IEnumerable<string> strings)
            return strings.Select(SanitizeDiagnosticValue).ToArray();
        return value;
    }

    private static string Trim(string value) => value.Length <= 300 ? value : value[..300];
}
