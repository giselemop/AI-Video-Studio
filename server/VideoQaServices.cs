using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace VideoStudio.Server;

/// <summary>
/// CPU/FFmpeg 优先的视频验收服务。它不会加载大模型；无法可靠判断人脸、动作或语义时，
/// 会记录为 NeedReview，绝不把“未检测”伪装成通过。
/// </summary>
public sealed class VideoQaService
{
    private const int SampleWidth = 64;
    private const int SampleHeight = 36;
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly FfmpegService _ffmpeg;
    private readonly ILogger<VideoQaService> _logger;

    public VideoQaService(StudioSettings settings, StudioRepository repository, FfmpegService ffmpeg, ILogger<VideoQaService> logger)
    {
        _settings = settings;
        _repository = repository;
        _ffmpeg = ffmpeg;
        _logger = logger;
    }

    public async Task<QaPresetOptions> GetPresetAsync(string? name, CancellationToken ct = default)
    {
        var normalized = name is "Draft" or "HighQuality" ? name : "Standard";
        try
        {
            var row = await _repository.QaPresetAsync(normalized, ct);
            if (row is not null)
            {
                return new QaPresetOptions(
                    normalized,
                    row.Decimal("shotPassScore", normalized == "HighQuality" ? 88 : normalized == "Draft" ? 70 : 80),
                    row.Decimal("shotReviewScore", normalized == "HighQuality" ? 80 : normalized == "Draft" ? 60 : 70),
                    row.Decimal("episodePassScore", normalized == "Draft" ? 75 : normalized == "HighQuality" ? 88 : 85),
                    row.Decimal("blackFrameMaxPercent", 2), row.Decimal("durationTolerancePercent", 10),
                    row.Decimal("fpsTolerance", 1), row.Int("maxAutoRetries", 2));
            }
        }
        catch (Exception ex) { _logger.LogDebug(ex, "QA preset database unavailable; using built-in preset"); }

        return normalized switch
        {
            "Draft" => new QaPresetOptions("Draft", 70, 60, 75, 2, 10, 1, 2),
            "HighQuality" => new QaPresetOptions("HighQuality", 88, 80, 88, 2, 10, 1, 2),
            _ => new QaPresetOptions("Standard", 80, 70, 85, 2, 10, 1, 2)
        };
    }

    public async Task<QaTechnicalEvaluation> CheckTechnicalAsync(QaTechnicalCheckInput input, CancellationToken ct = default)
    {
        var issues = new List<QaIssueDraft>();
        var result = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["checkedAt"] = DateTimeOffset.Now,
            ["path"] = input.Path,
            ["standard"] = new { input.ExpectedWidth, input.ExpectedHeight, input.ExpectedFps, input.ExpectedDuration, input.RequireAudio, input.RequireSubtitle }
        };
        var emptyMetrics = new QaFrameMetrics(0, 0, 0, 0, 0, [], null);

        if (!TryAllowedFile(input.Path, out var fullPath))
        {
            issues.Add(new QaIssueDraft("FILE_NOT_ALLOWED", "Critical", "媒体路径为空、文件不存在或不在 C:\\install\\AI 范围内"));
            return new QaTechnicalEvaluation("Rejected", 0, true, result, issues, emptyMetrics);
        }

        var info = new FileInfo(fullPath);
        result["fileSizeBytes"] = info.Length;
        if (info.Length < 16 * 1024) issues.Add(new QaIssueDraft("FILE_TOO_SMALL", "Critical", "视频文件小于 16KB，疑似空文件或不完整输出"));

        var probe = await _ffmpeg.ProbeDetailedAsync(fullPath, ct);
        if (probe is null)
        {
            issues.Add(new QaIssueDraft("PROBE_FAILED", "Critical", "FFprobe 无法读取视频流信息"));
            return BuildTechnical(issues, result, emptyMetrics, true);
        }
        result["probe"] = probe;

        var decode = await _ffmpeg.CheckDecodeAsync(fullPath, ct);
        result["decode"] = decode;
        if (!decode.Passed) issues.Add(new QaIssueDraft("DECODE_ERROR", "Critical", $"视频解码检查失败：{decode.Error ?? "存在解码错误"}"));

        if (probe.Width != input.ExpectedWidth || probe.Height != input.ExpectedHeight)
            issues.Add(new QaIssueDraft("WRONG_RESOLUTION", "Critical", $"分辨率为 {probe.Width}x{probe.Height}，要求 {input.ExpectedWidth}x{input.ExpectedHeight}"));
        if (probe.Fps is null || Math.Abs(probe.Fps.Value - (double)input.ExpectedFps) > (double)Math.Max(0, input.FpsTolerance))
            issues.Add(new QaIssueDraft("WRONG_FPS", "Critical", $"FPS 为 {probe.Fps?.ToString("0.###", CultureInfo.InvariantCulture) ?? "未知"}，要求 {input.ExpectedFps:0.###}±{input.FpsTolerance:0.###}"));
        if (probe.DurationSeconds is null || probe.DurationSeconds <= 0)
            issues.Add(new QaIssueDraft("INVALID_DURATION", "Critical", "视频时长为空或小于等于 0"));
        else if (input.ExpectedDuration is { } expected && expected > 0)
        {
            var deviation = Math.Abs(probe.DurationSeconds.Value - (double)expected) / (double)expected * 100;
            if (deviation > (double)Math.Max(0, input.DurationTolerancePercent))
                issues.Add(new QaIssueDraft("WRONG_DURATION", "Critical", $"时长为 {probe.DurationSeconds.Value:0.###} 秒，目标 {expected:0.###} 秒，偏差 {deviation:0.##}%"));
        }

        if (probe.Codec is null || !new[] { "h264", "h265", "hevc" }.Contains(probe.Codec, StringComparer.OrdinalIgnoreCase))
            issues.Add(new QaIssueDraft("UNSUPPORTED_CODEC", "Critical", $"视频编码 {probe.Codec ?? "未知"} 不在 H.264/H.265 验收范围内"));
        if (input.RequireAudio && !probe.HasAudio) issues.Add(new QaIssueDraft("AUDIO_MISSING", "Critical", "该镜头包含对白或旁白，但视频没有音频流"));
        if (probe.HasAudio && probe.AudioDurationSeconds is { } audioDuration && probe.DurationSeconds is { } videoDuration && Math.Abs(audioDuration - videoDuration) > Math.Max(.25, videoDuration * .1))
            issues.Add(new QaIssueDraft("AUDIO_DURATION_MISMATCH", "Error", $"音频时长 {audioDuration:0.###} 秒与视频 {videoDuration:0.###} 秒差异较大"));

        if (input.RequireSubtitle)
        {
            if (!TryAllowedFile(input.SubtitlePath, out var subtitlePath)) issues.Add(new QaIssueDraft("SUBTITLE_MISSING", "Critical", "该镜头需要字幕，但字幕文件不存在或不在允许目录"));
            else issues.AddRange(await ValidateSubtitleAsync(subtitlePath, probe.DurationSeconds, ct));
        }
        else if (!string.IsNullOrWhiteSpace(input.SubtitlePath) && TryAllowedFile(input.SubtitlePath, out var optionalSubtitle))
            issues.AddRange(await ValidateSubtitleAsync(optionalSubtitle, probe.DurationSeconds, ct));

        var metrics = await SampleFramesAsync(fullPath, probe.DurationSeconds, ct);
        result["frameMetrics"] = metrics;
        if (metrics.Error is not null || metrics.FrameCount == 0)
            issues.Add(new QaIssueDraft("FRAME_SAMPLE_FAILED", "Critical", metrics.Error ?? "无法抽取有效视频帧"));
        else
        {
            if (metrics.BlackFramePercent >= (double)Math.Max(0, input.BlackFrameMaxPercent))
            {
                var frameTime = metrics.BlackFrameTimes.FirstOrDefault();
                var framePath = await SaveIssueFrameAsync(fullPath, frameTime, "black", ct);
                issues.Add(new QaIssueDraft("BLACK_FRAME", "Critical", $"黑帧比例 {metrics.BlackFramePercent:0.##}%，上限 {input.BlackFrameMaxPercent:0.##}%", frameTime, framePath));
            }
            if (metrics.SuddenChangePercent > 35)
            {
                var frameTime = Math.Max(0, probe.DurationSeconds.GetValueOrDefault() / 2);
                var framePath = await SaveIssueFrameAsync(fullPath, frameTime, "temporal", ct);
                issues.Add(new QaIssueDraft("TEMPORAL_INSTABILITY", "Warning", $"相邻采样帧变化异常比例 {metrics.SuddenChangePercent:0.##}%，需要人工确认闪烁/跳帧", frameTime, framePath));
            }
        }

        return BuildTechnical(issues, result, metrics, issues.Any(x => x.Severity is "Critical" or "Error"));
    }

    public async Task<ShotQaEvaluation> EvaluateShotAsync(IReadOnlyDictionary<string, object?> shot, IReadOnlyDictionary<string, object?> episode, QaPresetOptions preset, CancellationToken ct = default)
    {
        var path = shot.Text("finalVideoPath") ?? shot.Text("videoPath") ?? shot.Text("resultPath");
        var hasDialogue = !string.IsNullOrWhiteSpace(shot.Text("dialogue")) || !string.IsNullOrWhiteSpace(shot.Text("narration"));
        var technical = await CheckTechnicalAsync(new QaTechnicalCheckInput
        {
            Path = path ?? "",
            ExpectedWidth = episode.Int("outputWidth", 1920),
            ExpectedHeight = episode.Int("outputHeight", 1080),
            ExpectedFps = episode.Decimal("outputFps", 30),
            ExpectedDuration = shot.Decimal("durationSeconds", 5),
            SubtitlePath = episode.Text("subtitlePath"),
            RequireAudio = hasDialogue,
            RequireSubtitle = hasDialogue,
            DurationTolerancePercent = preset.DurationTolerancePercent,
            FpsTolerance = preset.FpsTolerance,
            BlackFrameMaxPercent = preset.BlackFrameMaxPercent
        }, ct);

        var issues = new List<QaIssueDraft>(technical.Issues);
        var manual = false;
        var characterCount = JsonArrayCount(shot.Text("characterIdsJson"));
        var hasScene = shot.LongOrNull("sceneId") is not null || !string.IsNullOrWhiteSpace(shot.Text("sceneName"));
        var hasAction = !string.IsNullOrWhiteSpace(shot.Text("action")) || !string.IsNullOrWhiteSpace(shot.Text("expectedAction"));
        var requiredProps = shot.Text("requiredPropsJson");

        var character = characterCount == 0 ? 100m : 78m;
        if (characterCount > 0)
        {
            manual = true;
            issues.Add(new QaIssueDraft("MANUAL_CONTENT_REVIEW", "Warning", "当前环境未加载大型人脸/身份检测模型；请人工确认脸、发型、服装、年龄和身体比例一致"));
        }

        var motion = technical.Metrics.FrameCount < 2 ? 65m : Math.Clamp(82m - (decimal)Math.Max(0, technical.Metrics.AverageMotion - .30) * 55m, 65m, 92m);
        if (hasAction)
        {
            manual = true;
            issues.Add(new QaIssueDraft("MANUAL_MOTION_REVIEW", "Warning", "动作语义和肢体自然度采用人工复核；CPU 基线只能发现明显帧变化异常"));
        }
        else motion = 70m;

        var temporal = Math.Clamp(96m - (decimal)technical.Metrics.SuddenChangePercent * .45m - (decimal)technical.Metrics.BlackFramePercent * 4m, 50m, 100m);
        if (technical.Metrics.SuddenChangePercent > 10) { manual = true; issues.Add(new QaIssueDraft("TEMPORAL_REVIEW", "Warning", "存在明显帧间变化，需要人工确认闪烁、脸部漂移和连续帧一致性")); }

        var semantic = hasAction ? 78m : 70m;
        if (hasAction) { manual = true; issues.Add(new QaIssueDraft("SEMANTIC_REVIEW_REQUIRED", "Warning", "动作完成度和物体交互未使用大型视觉语言模型自动判定，请人工确认")); }
        var visual = Math.Clamp(92m - (decimal)technical.Metrics.BlackFramePercent * 10m - (decimal)technical.Metrics.SuddenChangePercent * .15m, 55m, 98m);
        var composition = string.IsNullOrWhiteSpace(shot.Text("cameraType")) && string.IsNullOrWhiteSpace(shot.Text("cameraMotion")) ? 70m : 80m;
        if (composition < 80) { manual = true; issues.Add(new QaIssueDraft("COMPOSITION_REVIEW_REQUIRED", "Warning", "未提供完整镜头构图元数据，请人工确认主体位置、景别和镜头运动")); }
        else { manual = true; issues.Add(new QaIssueDraft("COMPOSITION_REVIEW_REQUIRED", "Warning", "景别、构图和镜头运动仍需人工确认")); }
        var scene = hasScene ? 80m : 70m;
        if (hasScene) { manual = true; issues.Add(new QaIssueDraft("SCENE_REVIEW_REQUIRED", "Warning", "当前未加载场景视觉比对模型，请人工确认建筑、房间、光照和道具连续性")); }
        else { manual = true; issues.Add(new QaIssueDraft("SCENE_REVIEW_REQUIRED", "Warning", "缺少场景引用信息，请人工确认场景")); }

        var audio = hasDialogue && technical.Issues.Any(x => x.IssueType is "AUDIO_MISSING" or "AUDIO_DURATION_MISMATCH") ? 0m : 100m;
        var subtitle = hasDialogue && technical.Issues.Any(x => x.IssueType is "SUBTITLE_MISSING" or "SUBTITLE_INVALID" or "SUBTITLE_TIMEOUT" or "SUBTITLE_OVERLAP") ? 0m : 100m;
        var audioSubtitles = (audio + subtitle) / 2m;
        if (string.IsNullOrWhiteSpace(requiredProps) || requiredProps is "[]" or "{}") { }
        else { manual = true; issues.Add(new QaIssueDraft("PROP_REVIEW_REQUIRED", "Warning", "required_props 已登记，但当前未加载物体检测模型，请人工确认道具存在、位置和交互")); }

        var components = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase)
        {
            ["Technical"] = technical.Score, ["Character"] = character, ["Motion"] = motion, ["Temporal"] = temporal,
            ["Semantic"] = semantic, ["Visual"] = visual, ["Composition"] = composition, ["Scene"] = scene, ["AudioSubtitles"] = audioSubtitles
        };
        var score = Math.Round(technical.Score * .15m + character * .15m + motion * .15m + temporal * .15m + semantic * .15m + visual * .10m + composition * .05m + scene * .05m + audioSubtitles * .05m, 2);
        var hard = technical.HardFailure || score < 70 || issues.Any(x => x.Severity is "Critical" or "Error");
        var status = hard ? "Rejected" : manual ? "NeedReview" : score >= preset.ShotPassScore ? "Passed" : score >= preset.ShotReviewScore ? "NeedReview" : "Rejected";
        var result = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["score"] = score, ["status"] = status, ["preset"] = preset.Name, ["weights"] = new { Technical = .15, Character = .15, Motion = .15, Temporal = .15, Semantic = .15, Visual = .10, Composition = .05, Scene = .05, AudioSubtitles = .05 },
            ["components"] = components, ["technical"] = technical.Result, ["manualReviewRequired"] = manual,
            ["detectorPolicy"] = "未加载大型内容模型的项目统一标记为人工复核，不自动放行", ["expectedAction"] = shot.Text("expectedAction") ?? shot.Text("action"), ["requiredProps"] = requiredProps
        };
        return new ShotQaEvaluation(status, score, components, result, issues, manual, hard);
    }

    public async Task<EpisodeQaEvaluation> EvaluateEpisodeAsync(long episodeId, QaPresetOptions preset, CancellationToken ct = default)
    {
        var episode = (await _repository.EpisodeAsync(episodeId, ct)).FirstOrDefault() ?? throw new InvalidOperationException("Episode 不存在");
        var shots = await _repository.ShotsAsync(episodeId, ct);
        if (shots.Count == 0) throw new InvalidOperationException("Episode 没有可验收镜头");

        var shotResults = new List<(long Id, ShotQaEvaluation Evaluation)>();
        foreach (var shot in shots.OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))))
        {
            var version = shot.Int("qaVersion") + 1;
            var runId = await _repository.CreateQaRunAsync(episodeId, shot.Long("id"), version, preset.Name, "Shot", "Auto", ct);
            try
            {
                var evaluation = await EvaluateShotAsync(shot, episode, preset, ct);
                await _repository.UpdateShotQaAsync(shot.Long("id"), evaluation, version, ct: ct);
                foreach (var issue in evaluation.Issues) await _repository.AddQaIssueAsync(runId, episodeId, shot.Long("id"), issue, ct);
                await _repository.CompleteQaRunAsync(runId, evaluation.Status, evaluation.Score, evaluation.Issues.Count, evaluation.ResultJson, ct);
                shotResults.Add((shot.Long("id"), evaluation));
            }
            catch (Exception ex)
            {
                var issue = new QaIssueDraft("QA_EXECUTION_ERROR", "Critical", ex.Message);
                await _repository.AddQaIssueAsync(runId, episodeId, shot.Long("id"), issue, CancellationToken.None);
                await _repository.CompleteQaRunAsync(runId, "Rejected", 0, 1, JsonSerializer.Serialize(new { error = ex.Message }), CancellationToken.None);
                throw;
            }
        }

        var episodeIssues = new List<QaIssueDraft>();
        var continuity = 88m;
        for (var i = 1; i < shots.Count; i++)
        {
            var previous = shots[i - 1];
            var current = shots[i];
            if (!string.Equals(previous.Text("sceneName"), current.Text("sceneName"), StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(previous.Text("sceneName")) && !string.IsNullOrWhiteSpace(current.Text("sceneName")))
            {
                continuity -= 4; episodeIssues.Add(new QaIssueDraft("CONTINUITY_SCENE_REVIEW", "Warning", $"Shot {previous.Int("shotNumber")} 到 Shot {current.Int("shotNumber")} 场景发生变化，请确认是否为剧本规定的转场"));
            }
            if (!string.IsNullOrWhiteSpace(current.Text("characterIdsJson")) && current.Text("characterIdsJson") != "[]")
            {
                continuity -= 1; episodeIssues.Add(new QaIssueDraft("CONTINUITY_CHARACTER_REVIEW", "Warning", $"Shot {current.Int("shotNumber")} 的人物服装、发型和脸部连续性需要人工比对"));
            }
        }
        continuity = Math.Clamp(continuity, 60, 100);

        var durations = shots.Select(x => x.Decimal("durationSeconds", 5)).ToArray();
        var pacing = 100m;
        if (durations.Any(x => x < 2 || x > 10)) { pacing -= 12; episodeIssues.Add(new QaIssueDraft("PACING_WARNING", "Warning", "存在小于 2 秒或大于 10 秒的镜头，建议人工确认节奏；该项不会单独自动拒绝")); }
        if (durations.Length > 2 && durations.Max() - durations.Min() < .1m) { pacing -= 4; episodeIssues.Add(new QaIssueDraft("PACING_VARIETY_WARNING", "Warning", "连续镜头时长过于一致，建议人工确认节奏变化")); }
        var audio = shotResults.Average(x => x.Evaluation.ComponentScores.GetValueOrDefault("AudioSubtitles", 100));
        var subtitles = audio;
        var visualConsistency = 80m;
        if (shots.Count > 1) { visualConsistency -= 5; episodeIssues.Add(new QaIssueDraft("DUPLICATE_VISUAL_REVIEW", "Warning", "跨镜头重复画面、色彩和角色服装当前采用人工复核；未加载大型视觉相似度模型")); }
        var shotAverage = shotResults.Average(x => x.Evaluation.Score);
        var components = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase)
        {
            ["ShotAverage"] = Math.Round(shotAverage, 2), ["Continuity"] = continuity, ["Audio"] = audio, ["Subtitles"] = subtitles, ["Pacing"] = pacing, ["VisualConsistency"] = visualConsistency
        };
        var score = Math.Round(shotAverage * .60m + continuity * .15m + audio * .10m + subtitles * .05m + pacing * .05m + visualConsistency * .05m, 2);
        var anyRejected = shotResults.Any(x => x.Evaluation.Status == "Rejected");
        var manual = shotResults.Any(x => x.Evaluation.ManualReviewRequired) || episodeIssues.Count > 0;
        var status = anyRejected ? "Rejected" : manual ? "NeedReview" : score >= preset.EpisodePassScore ? "Passed" : score >= 75 ? "NeedReview" : "Rejected";
        var result = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["score"] = score, ["status"] = status, ["preset"] = preset.Name,
            ["weights"] = new { ShotAverage = .60, Continuity = .15, Audio = .10, Subtitles = .05, Pacing = .05, VisualConsistency = .05 },
            ["components"] = components,
            ["shots"] = shotResults.Select(x => new { id = x.Id, x.Evaluation.Status, x.Evaluation.Score, issues = x.Evaluation.Issues.Count }).ToArray(),
            ["issues"] = episodeIssues,
            ["manualReviewRequired"] = manual
        };
        var evaluationResult = new EpisodeQaEvaluation(status, score, components, result, episodeIssues, manual);
        var episodeRunId = await _repository.CreateQaRunAsync(episodeId, null, episode.Int("qaVersion") + 1, preset.Name, "Episode", "Auto", ct);
        foreach (var issue in episodeIssues) await _repository.AddQaIssueAsync(episodeRunId, episodeId, null, issue, ct);
        await _repository.CompleteQaRunAsync(episodeRunId, status, score, episodeIssues.Count, evaluationResult.ResultJson, ct);
        await _repository.UpdateEpisodeQaAsync(episodeId, evaluationResult, episode.Int("qaVersion") + 1, preset.Name, ct);
        return evaluationResult;
    }

    public async Task<QaExportResult> ExportMasterAsync(long episodeId, QaExportInput input, CancellationToken ct = default)
    {
        var episode = (await _repository.EpisodeAsync(episodeId, ct)).FirstOrDefault() ?? throw new InvalidOperationException("Episode 不存在");
        if (!episode.Bool("qaLocked") || !string.Equals(episode.Text("status"), "Approved", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Episode 尚未 Approved，不能导出 Master");
        if (!await _repository.AllEpisodeShotsPassedAsync(episodeId, ct)) throw new InvalidOperationException("仍有未 Passed 的镜头，不能导出 Master");
        if (await _repository.EpisodeHasOpenBlockingIssueAsync(episodeId, ct)) throw new InvalidOperationException("存在未关闭的 Critical/Error QA 问题，不能导出 Master");

        var source = episode.Text("outputPath");
        if (!TryAllowedFile(source, out var sourcePath)) throw new FileNotFoundException("Episode 最终视频不存在", source);
        var project = episode.LongOrNull("projectId") is { } projectId ? (await _repository.ProjectAsync(projectId, ct)).FirstOrDefault() : null;
        var projectName = SafeName(project?.Text("name") ?? "Project");
        var number = Math.Max(1, episode.Int("episodeNumber", 1));
        var release = Path.Combine(_settings.DataPath, "Output", "Release", projectName, $"Episode{number:000}");
        Directory.CreateDirectory(release);
        var master = Path.Combine(release, $"{projectName}_Episode_{number:000}_MASTER.mp4");
        File.Copy(sourcePath, master, true);

        string? subtitle = null;
        if (input.IncludeSubtitles && TryAllowedFile(episode.Text("subtitlePath"), out var subtitleSource))
        {
            subtitle = Path.Combine(release, $"{projectName}_Episode_{number:000}.srt");
            File.Copy(subtitleSource, subtitle, true);
        }
        string? cover = null;
        if (input.IncludeCover)
        {
            cover = Path.Combine(release, $"{projectName}_Episode_{number:000}_COVER.jpg");
            if (TryAllowedFile(episode.Text("coverPath"), out var existingCover)) File.Copy(existingCover, cover, true);
            else await _ffmpeg.ExtractFrameAsync(sourcePath, 0, cover, ct);
        }

        var runs = await _repository.QaRunsAsync(episodeId, null, ct);
        var issues = await _repository.QaIssuesAsync(episodeId, null, ct);
        var report = new { generatedAt = DateTimeOffset.Now, episodeId, episodeNumber = number, preset = episode.Text("qaPreset") ?? "Standard", masterPath = master, subtitlePath = subtitle, coverPath = cover, runs, issues };
        var jsonPath = Path.Combine(release, "QA_REPORT.json");
        var markdownPath = Path.Combine(release, "QA_REPORT.md");
        await File.WriteAllTextAsync(jsonPath, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false), ct);
        var md = new StringBuilder().AppendLine($"# QA 报告 - {projectName} Episode {number:000}").AppendLine().AppendLine($"- 生成时间：{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}").AppendLine($"- Master：`{master}`").AppendLine($"- 结论：Approved").AppendLine($"- QA 问题数：{issues.Count}").AppendLine().AppendLine("## 发布检查").AppendLine().AppendLine("- [x] Episode Approved 且已锁定").AppendLine("- [x] 所有镜头 Passed").AppendLine("- [x] 无未关闭 Critical/Error").AppendLine("- [x] 视频、字幕、封面和报告已导出").ToString();
        await File.WriteAllTextAsync(markdownPath, md, new UTF8Encoding(false), ct);
        await _repository.UpdateEpisodeReleaseAsync(episodeId, master, cover, markdownPath, jsonPath, ct);
        return new QaExportResult(master, subtitle, cover, markdownPath, jsonPath);
    }

    private QaTechnicalEvaluation BuildTechnical(List<QaIssueDraft> issues, Dictionary<string, object?> result, QaFrameMetrics metrics, bool hardFailure)
    {
        var score = Math.Clamp(100m - issues.Count(x => x.Severity == "Warning") * 3m - issues.Count(x => x.Severity == "Error") * 20m - issues.Count(x => x.Severity == "Critical") * 35m, 0, 100);
        var status = hardFailure ? "Rejected" : issues.Any(x => x.Severity == "Warning") || score < 80 ? "NeedReview" : "Passed";
        result["status"] = status; result["score"] = score; result["hardFailure"] = hardFailure;
        return new QaTechnicalEvaluation(status, score, hardFailure, result, issues, metrics);
    }

    private async Task<QaFrameMetrics> SampleFramesAsync(string path, double? duration, CancellationToken ct)
    {
        if (!File.Exists(_settings.FfmpegPath)) return new QaFrameMetrics(0, 0, 0, 0, 0, [], "FFmpeg 不存在");
        var maxFrames = Math.Clamp((int)Math.Ceiling(Math.Max(1, duration.GetValueOrDefault(5)) * 2), 2, 48);
        var psi = new ProcessStartInfo { FileName = _settings.FfmpegPath, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        foreach (var arg in new[] { "-hide_banner", "-loglevel", "error", "-i", path, "-an", "-vf", "fps=2,scale=64:36:flags=bilinear,format=gray", "-frames:v", maxFrames.ToString(CultureInfo.InvariantCulture), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1" }) psi.ArgumentList.Add(arg);
        using var process = new Process { StartInfo = psi };
        if (!process.Start()) return new QaFrameMetrics(0, 0, 0, 0, 0, [], "无法启动 FFmpeg 帧采样");
        using var buffer = new MemoryStream();
        var outputTask = process.StandardOutput.BaseStream.CopyToAsync(buffer, ct);
        var errorTask = process.StandardError.ReadToEndAsync(ct);
        await process.WaitForExitAsync(ct);
        await outputTask;
        var error = await errorTask;
        var bytes = buffer.ToArray();
        var frameSize = SampleWidth * SampleHeight;
        var count = bytes.Length / frameSize;
        if (count == 0) return new QaFrameMetrics(0, 0, 0, 0, 0, [], string.IsNullOrWhiteSpace(error) ? "FFmpeg 未返回有效帧" : error.Trim());
        var means = new List<double>(count);
        var blackTimes = new List<double>();
        var black = 0;
        for (var frame = 0; frame < count; frame++)
        {
            var offset = frame * frameSize; var sum = 0; var dark = 0;
            for (var i = 0; i < frameSize; i++) { var value = bytes[offset + i]; sum += value; if (value < 8) dark++; }
            var mean = (double)sum / frameSize; means.Add(mean);
            if ((double)dark / frameSize >= .95) { black++; blackTimes.Add(frame / 2d); }
        }
        var differences = new List<double>(); var sudden = 0;
        for (var frame = 1; frame < count; frame++)
        {
            var a = (frame - 1) * frameSize; var b = frame * frameSize; var sum = 0;
            for (var i = 0; i < frameSize; i++) sum += Math.Abs(bytes[a + i] - bytes[b + i]);
            var diff = (double)sum / frameSize / 255d; differences.Add(diff); if (diff > .35) sudden++;
        }
        return new QaFrameMetrics(count, black * 100d / count, means.Average(), differences.DefaultIfEmpty(0).Average(), differences.Count == 0 ? 0 : sudden * 100d / differences.Count, blackTimes, process.ExitCode == 0 ? null : error.Trim());
    }

    private async Task<List<QaIssueDraft>> ValidateSubtitleAsync(string path, double? duration, CancellationToken ct)
    {
        var issues = new List<QaIssueDraft>();
        string text;
        try
        {
            var bytes = await File.ReadAllBytesAsync(path, ct);
            text = new UTF8Encoding(false, true).GetString(bytes);
            if (text.Contains('\uFFFD')) issues.Add(new QaIssueDraft("SUBTITLE_INVALID", "Critical", "SRT 含 UTF-8 替换字符，可能存在乱码"));
        }
        catch (Exception ex) { issues.Add(new QaIssueDraft("SUBTITLE_INVALID", "Critical", $"SRT 不是有效 UTF-8：{ex.Message}")); return issues; }
        var lines = text.Replace("\r", "").Split('\n');
        double previousEnd = -1;
        for (var i = 0; i < lines.Length;)
        {
            while (i < lines.Length && string.IsNullOrWhiteSpace(lines[i])) i++;
            if (i >= lines.Length) break;
            i++;
            if (i >= lines.Length || !lines[i].Contains("-->")) { issues.Add(new QaIssueDraft("SUBTITLE_INVALID", "Critical", "SRT 时间轴行缺失或格式错误")); break; }
            var parts = lines[i].Split("-->", 2, StringSplitOptions.TrimEntries);
            i++;
            if (parts.Length != 2 || !TryParseSrtTime(parts[0], out var start) || !TryParseSrtTime(parts[1], out var end) || end <= start)
            { issues.Add(new QaIssueDraft("SUBTITLE_INVALID", "Critical", "SRT 时间轴无效")); continue; }
            if (start < previousEnd - .001) issues.Add(new QaIssueDraft("SUBTITLE_OVERLAP", "Critical", $"SRT 时间轴重叠：{start:0.###} 秒"));
            if (duration is { } total && end > total + .05) issues.Add(new QaIssueDraft("SUBTITLE_TIMEOUT", "Critical", $"字幕结束时间 {end:0.###} 秒超出视频 {total:0.###} 秒"));
            previousEnd = Math.Max(previousEnd, end);
            while (i < lines.Length && !string.IsNullOrWhiteSpace(lines[i])) i++;
        }
        return issues;
    }

    private async Task<string?> SaveIssueFrameAsync(string video, double seconds, string kind, CancellationToken ct)
    {
        try
        {
            var folder = Path.Combine(_settings.DataPath, "QA", "Frames"); Directory.CreateDirectory(folder);
            var name = SafeName(Path.GetFileNameWithoutExtension(video));
            var output = Path.Combine(folder, $"{name}_{kind}_{DateTime.Now:yyyyMMdd_HHmmss}_{Guid.NewGuid().ToString("N")[..6]}.jpg");
            return await _ffmpeg.ExtractFrameAsync(video, seconds, output, ct);
        }
        catch (Exception ex) { _logger.LogDebug(ex, "问题帧抽取失败"); return null; }
    }

    private bool TryAllowedFile(string? path, out string full)
    {
        full = "";
        if (string.IsNullOrWhiteSpace(path)) return false;
        try
        {
            full = Path.GetFullPath(path);
            var root = Path.GetFullPath(Path.Combine(_settings.RootPath, ".."));
            return File.Exists(full) && (full.Equals(root, StringComparison.OrdinalIgnoreCase) || full.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase));
        }
        catch { return false; }
    }

    private static int JsonArrayCount(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return 0;
        try { using var doc = JsonDocument.Parse(raw); return doc.RootElement.ValueKind == JsonValueKind.Array ? doc.RootElement.GetArrayLength() : 0; }
        catch { return 0; }
    }

    private static bool TryParseSrtTime(string value, out double seconds)
    {
        seconds = 0;
        var parts = value.Trim().Replace('.', ',').Split(':');
        if (parts.Length != 3 || !int.TryParse(parts[0], out var hours) || !int.TryParse(parts[1], out var minutes)) return false;
        var sec = parts[2].Split(',', 2); if (!double.TryParse(sec[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var whole)) return false;
        var millis = sec.Length == 2 && int.TryParse(sec[1].PadRight(3, '0')[..3], out var ms) ? ms : 0;
        seconds = hours * 3600 + minutes * 60 + whole + millis / 1000d; return true;
    }

    private static string SafeName(string value)
    {
        var invalid = new string(Path.GetInvalidFileNameChars());
        var sanitized = new string(value.Select(x => invalid.Contains(x) ? '_' : x).ToArray()).Trim();
        return string.IsNullOrWhiteSpace(sanitized) ? "Project" : sanitized;
    }
}
