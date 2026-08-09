using System.Collections.Concurrent;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;

namespace VideoStudio.Server;

/// <summary>
/// 单 GPU 任务调度器。RTX 4070 12GB 始终只允许一个 GPU 重任务运行；
/// CPU 的 TTS、字幕、FFmpeg 任务也走同一条可恢复队列，但不会与 GPU 任务并发。
/// 任务依赖、重试和状态更新都在数据库中记录，服务重启后从 Pending/Running 恢复。
/// </summary>
public sealed class GenerationQueue : BackgroundService
{
    private readonly Channel<long> _signals = Channel.CreateUnbounded<long>(new UnboundedChannelOptions { SingleReader = true, SingleWriter = false });
    private readonly ConcurrentDictionary<long, CancellationTokenSource> _active = new();
    private readonly StudioRepository _repository;
    private readonly ComfyUiClient _comfy;
    private readonly FfmpegService _ffmpeg;
    private readonly QualityControlService _quality;
    private readonly LocalTtsService _tts;
    private readonly SubtitleService _subtitles;
    private readonly VideoQaService _qa;
    private readonly StudioSettings _settings;
    private readonly ILogger<GenerationQueue> _logger;
    private volatile bool _paused;

    public GenerationQueue(StudioRepository repository, ComfyUiClient comfy, FfmpegService ffmpeg, QualityControlService quality, LocalTtsService tts, SubtitleService subtitles, VideoQaService qa, StudioSettings settings, ILogger<GenerationQueue> logger)
    {
        _repository = repository; _comfy = comfy; _ffmpeg = ffmpeg; _quality = quality; _tts = tts; _subtitles = subtitles; _qa = qa; _settings = settings; _logger = logger;
    }

    public object Status => new { paused = _paused, activeTasks = _active.Count, gpuConcurrency = 1, policy = "RTX4070-12GB-serial" };
    public bool Enqueue(long taskId) => _signals.Writer.TryWrite(taskId);
    public void Pause() => _paused = true;
    public void Resume() => _paused = false;

    public async Task CancelAsync(long taskId, CancellationToken ct = default)
    {
        if (_active.TryGetValue(taskId, out var cancellation))
        {
            cancellation.Cancel();
            try { await _comfy.InterruptAsync(ct); } catch { }
        }
        await _repository.MarkTaskAsync(taskId, "Cancelled", "用户取消", ct: ct);
    }

    public async Task CancelEpisodeAsync(long episodeId, CancellationToken ct = default)
    {
        var tasks = await _repository.TasksAsync(500, ct);
        foreach (var task in tasks.Where(x => x.LongOrNull("episodeId") == episodeId && x.Text("status") is "Pending" or "Running")) await CancelAsync(task.Long("id"), ct);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await Task.Delay(1000, stoppingToken);
        try
        {
            await _repository.RecoverRunningTasksAsync(stoppingToken);
            foreach (var row in await _repository.PendingTasksAsync(stoppingToken)) Enqueue(row.Long("id"));
        }
        catch (Exception ex) { _logger.LogWarning("恢复任务队列失败，将等待 API 请求后重试: {Message}", ex.Message); }

        await foreach (var _ in _signals.Reader.ReadAllAsync(stoppingToken))
        {
            while (_paused && !stoppingToken.IsCancellationRequested) await Task.Delay(500, stoppingToken);
            var next = await _repository.HighestPendingTaskAsync(stoppingToken);
            if (next is null) continue;
            try { await ProcessAsync(next.Long("id"), stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex) { _logger.LogError(ex, "任务 {TaskId} 未处理", next.Long("id")); }
        }
    }

    private async Task ProcessAsync(long id, CancellationToken stoppingToken)
    {
        var row = (await _repository.TaskAsync(id, stoppingToken)).FirstOrDefault();
        if (row is null || !string.Equals(row.Text("status"), "Pending", StringComparison.OrdinalIgnoreCase)) return;
        var dependency = await _repository.TaskDependencyStateAsync(id, stoppingToken);
        if (dependency.Blocked)
        {
            await _repository.SetTaskErrorAsync(id, "INPUT_MISSING", "上游任务失败，下游任务未执行", stoppingToken);
            await _repository.MarkTaskAsync(id, "Failed", "上游任务失败，下游任务未执行", ct: stoppingToken);
            return;
        }
        if (!dependency.Ready)
        {
            await Task.Delay(800, stoppingToken);
            Enqueue(id);
            return;
        }

        var attempts = row.Int("attempts") + 1;
        var maxRetries = row.Int("maxRetries", 2);
        await _repository.MarkTaskRunningAsync(id, stoppingToken);
        using var taskCancellation = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        _active[id] = taskCancellation;
        var started = DateTime.UtcNow;
        var taskType = row.Text("taskType") ?? "Image";
        try
        {
            await _repository.LogAsync("task.start", $"开始执行 {taskType}", id, ct: stoppingToken);
            if (taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase)) await ExecuteAudioAsync(row, taskCancellation.Token);
            else if (taskType.Equals("Subtitles", StringComparison.OrdinalIgnoreCase)) await ExecuteSubtitlesAsync(row, taskCancellation.Token);
            else if (taskType.Equals("EpisodeRender", StringComparison.OrdinalIgnoreCase)) await ExecuteEpisodeRenderAsync(row, taskCancellation.Token);
            else if (taskType.Equals("Concat", StringComparison.OrdinalIgnoreCase) || taskType.Equals("VideoConcat", StringComparison.OrdinalIgnoreCase)) await ExecuteConcatAsync(row, taskCancellation.Token);
            else if (taskType.Equals("Enhance", StringComparison.OrdinalIgnoreCase) || taskType.Equals("VideoEnhancement", StringComparison.OrdinalIgnoreCase)) await ExecuteEnhanceAsync(row, taskCancellation.Token);
            else if (taskType.Equals("ShotQA", StringComparison.OrdinalIgnoreCase)) await ExecuteShotQaAsync(row, taskCancellation.Token);
            else if (taskType.Equals("EpisodeQA", StringComparison.OrdinalIgnoreCase)) await ExecuteEpisodeQaAsync(row, taskCancellation.Token);
            else if (taskType.Equals("QAExport", StringComparison.OrdinalIgnoreCase)) await ExecuteQaExportAsync(row, taskCancellation.Token);
            else await ExecuteComfyAsync(row, taskCancellation.Token);
            await _repository.MarkTaskAsync(id, "Succeeded", progress: 1, ct: stoppingToken);
            if ((taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase)) && row.LongOrNull("shotId") is { } audioShotId)
                await _repository.TryCompleteShotAudioAsync(audioShotId, stoppingToken);
            if (taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase) || taskType.Equals("Subtitles", StringComparison.OrdinalIgnoreCase))
                await TryQueueAutoEpisodeRenderAsync(row.LongOrNull("episodeId"), stoppingToken);
            await _repository.LogAsync("task.finish", $"任务完成，耗时 {(DateTime.UtcNow - started).TotalSeconds:F1}s", id, ct: stoppingToken);
        }
        catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested)
        {
            await _repository.MarkTaskAsync(id, "Cancelled", "任务被取消", ct: CancellationToken.None);
        }
        catch (Exception ex)
        {
            var message = ex.Message.Length > 3000 ? ex.Message[..3000] : ex.Message;
            var errorType = ClassifyError(ex, message);
            await _repository.SetTaskErrorAsync(id, errorType, message, CancellationToken.None);
            if (errorType == "CUDA_OOM") await ReduceParametersForOomAsync(id, row, CancellationToken.None);
            if (attempts <= maxRetries)
            {
                await _repository.MarkTaskAsync(id, "Failed", message, ct: CancellationToken.None);
                await _repository.ResetTaskForRetryAsync(id, CancellationToken.None);
                await _repository.LogAsync("task.retry", $"{errorType} 第 {attempts} 次失败，自动重试: {message}", id, "Warning", CancellationToken.None);
                await Task.Delay(TimeSpan.FromSeconds(Math.Min(15, attempts * 3)), stoppingToken);
                Enqueue(id);
            }
            else
            {
                await _repository.MarkTaskAsync(id, "Failed", message, ct: CancellationToken.None);
                await _repository.LogAsync("task.failed", $"{errorType}: {message}", id, "Error", CancellationToken.None);
            }
        }
        finally
        {
            _active.TryRemove(id, out _);
            if (row.Text("resourceClass") is not "CPU") await _comfy.TryFreeMemoryAsync(CancellationToken.None);
        }
    }

    private async Task ExecuteComfyAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var taskId = row.Long("id");
        var taskType = row.Text("taskType") ?? "Image";
        var workflowPath = row.Text("workflowPath");
        if (string.IsNullOrWhiteSpace(workflowPath)) workflowPath = DefaultWorkflow(taskType);
        if (!File.Exists(workflowPath)) throw new FileNotFoundException("工作流不存在", workflowPath);
        using var inputDocument = row.Json("inputJson");
        var inputRoot = inputDocument.RootElement;
        var parameters = inputRoot.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : JsonDocument.Parse("{}").RootElement;
        var inputImage = GetString(inputRoot, "inputImagePath") ?? row.Text("shotInputImage");
        var positive = GetString(parameters, "positive", "prompt") ?? row.Text("shotPrompt");
        var negative = GetString(parameters, "negative", "negativePrompt") ?? row.Text("shotNegativePrompt");
        var copiedImage = await CopyInputToComfyAsync(inputImage, taskId, ct);
        var workflow = ComfyUiClient.LoadWorkflow(workflowPath);
        ComfyUiClient.PatchWorkflow(workflow, taskType, positive, negative, copiedImage, parameters, $"video_studio/task_{taskId}");
        if (row.Text("resourceClass") is not "CPU") await WaitForGpuAsync(ct);
        var before = await _comfy.CheckAsync(ct);
        var peak = before.Gpu is null ? 0 : before.Gpu.TotalMiB - before.Gpu.FreeMiB;
        var promptId = await _comfy.QueueAsync(workflow, ct);
        await _repository.UpdateTaskPromptAsync(taskId, promptId, ct);
        var history = await _comfy.WaitForHistoryAsync(promptId, snapshot =>
        {
            if (snapshot.Gpu is not null) peak = Math.Max(peak, snapshot.Gpu.TotalMiB - snapshot.Gpu.FreeMiB);
            _ = _repository.UpdateTaskGpuAsync(taskId, snapshot.Gpu, peak);
        }, ct);
        var isVideo = taskType.Contains("video", StringComparison.OrdinalIgnoreCase) || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase);
        var target = Path.Combine(_settings.DataPath, isVideo ? "Videos" : "Images");
        var outputFiles = await _comfy.DownloadOutputsAsync(history, target, $"task_{taskId}", ct);
        if (outputFiles.Count == 0) throw new InvalidOperationException("ComfyUI 完成但没有可下载的输出文件");
        var candidateIndex = GetInt(parameters, "candidateIndex") ?? 1;
        var seed = GetLong(parameters, "seed");
        foreach (var file in outputFiles)
        {
            var finalPath = file.Path;
            if (isVideo && string.Equals(Path.GetExtension(finalPath), ".webp", StringComparison.OrdinalIgnoreCase))
            {
                finalPath = Path.ChangeExtension(finalPath, ".mp4"); await _ffmpeg.ConvertToMp4Async(file.Path, finalPath, ct);
            }
            var probe = await _ffmpeg.ProbeAsync(finalPath, ct);
            QualityCheckResult qc = isVideo
                ? await _quality.CheckVideoAsync(finalPath, row.Decimal("shotDurationSeconds", 5), row.Int("shotWidth", 512), row.Int("shotHeight", 320), row.Decimal("shotFps", 24), ct)
                : await _quality.CheckImageAsync(finalPath, row.Int("shotWidth", 512), row.Int("shotHeight", 320), ct);
            var assetId = await _repository.AddAssetAsync(row.LongOrNull("projectId"), row.LongOrNull("episodeId"), row.LongOrNull("shotId"), isVideo ? "video" : "image", Path.GetFileName(finalPath), finalPath, RelativeToData(finalPath), probe, ct);
            await _repository.AddResultAsync(taskId, assetId, isVideo ? "video" : "image", finalPath, ct);
            if (row.LongOrNull("shotId") is { } shotId)
            {
                if (!qc.Passed) throw new InvalidOperationException($"{qc.ErrorType}: {(qc.Metrics.TryGetValue("message", out var msg) ? msg : "输出质量检查失败")}");
                if (isVideo)
                {
                    await _repository.UpdateShotVideoAsync(shotId, finalPath, probe, JsonSerializer.Serialize(qc.Metrics), qc.Score, "VideoReview", ct);
                    var qaRetry = string.Equals(row.Text("stage"), "QA-Retry", StringComparison.OrdinalIgnoreCase);
                    if (qaRetry || string.Equals(row.Text("episodeProductionMode"), "AutoProduction", StringComparison.OrdinalIgnoreCase))
                        await QueueEnhanceAsync(row, shotId, taskId, finalPath, ct, qaRetry, parameters);
                }
                else
                {
                    await _repository.AddCandidateAsync(shotId, taskId, finalPath, candidateIndex, seed, "Passed", qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
                    await _repository.UpdateShotStatusAsync(shotId, "ImageReview", ct);
                    await AutoAdvanceAsync(row, shotId, taskId, ct);
                }
            }
            if (!string.Equals(finalPath, file.Path, StringComparison.OrdinalIgnoreCase)) try { File.Delete(file.Path); } catch { }
        }
        await _repository.UpdateTaskGpuAsync(taskId, (await _comfy.CheckAsync(ct)).Gpu, peak, ct);
    }

    private async Task QueueEnhanceAsync(IReadOnlyDictionary<string, object?> row, long shotId, long dependencyTaskId, string inputPath, CancellationToken ct, bool qaRetry = false, JsonElement? retryParameters = null)
    {
        if (await _repository.HasActiveTaskForShotAsync(shotId, "Enhance", ct)) return;
        var payload = new Dictionary<string, object?>
        {
            ["inputImagePath"] = inputPath,
            ["fps"] = 30,
            ["width"] = 1920,
            ["height"] = 1080,
            ["qaRetry"] = qaRetry
        };
        if (qaRetry && retryParameters is { } retry)
        {
            foreach (var name in new[] { "retryCount", "previousQaStatus", "previousQaScore", "retryReason", "changedParameters", "preset", "autoRetry" })
                if (retry.TryGetProperty(name, out var value)) payload[name] = value.Clone();
        }
        var parameters = JsonSerializer.SerializeToDocument(payload).RootElement.Clone();
        var taskId = await _repository.CreateTaskAsync(new TaskInput
        {
            ProjectId = row.LongOrNull("projectId"), EpisodeId = row.LongOrNull("episodeId"), ShotId = shotId,
            TaskType = "Enhance", ResourceClass = "CPU", Stage = "PostProcessing", DependencyTaskId = dependencyTaskId,
            InputImagePath = inputPath, MaxRetries = 1, Parameters = parameters
        }, ct);
        await _repository.AddTaskDependencyAsync(taskId, dependencyTaskId, ct);
        if (qaRetry)
            await _repository.LogAsync("qa.retry.enhance", $"Shot {shotId} QA 回炉增强已排队；回炉次数 {GetInt(parameters, "retryCount") ?? 0}，输入 {inputPath}", taskId, "Info", ct);
        await _repository.UpdateShotStatusAsync(shotId, "PostProcessing", ct);
        Enqueue(taskId);
    }

    private async Task AutoAdvanceAudioAsync(IReadOnlyDictionary<string, object?> row, long shotId, CancellationToken ct)
    {
        if (!string.Equals(row.Text("episodeProductionMode"), "AutoProduction", StringComparison.OrdinalIgnoreCase)) return;
        var shot = (await _repository.QueryShotAsync(shotId, ct)).FirstOrDefault();
        if (shot is null) return;
        var characters = await _repository.CharactersAsync(shot.LongOrNull("projectId"), ct);
        var audioTasks = new List<long>();
        var dialogue = shot.Text("dialogue") ?? "";
        var lines = dialogue.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Select(line =>
        {
            var separator = line.IndexOfAny([':', '：']);
            return separator > 0 ? (Voice: line[..separator].Trim(), Text: line[(separator + 1)..].Trim()) : (Voice: "", Text: line);
        }).Where(x => !string.IsNullOrWhiteSpace(x.Text)).ToList();
        if (!string.IsNullOrWhiteSpace(shot.Text("narration"))) lines.Add((row.Text("episodeNarratorVoiceId") ?? "", shot.Text("narration")!));
        if (lines.Count == 0)
        {
            await _repository.UpdateShotStatusAsync(shotId, "Completed", ct);
        }
        else if (!await _repository.HasActiveTaskForShotAsync(shotId, "Audio", ct))
        {
            foreach (var line in lines)
            {
                var character = characters.FirstOrDefault(x => string.Equals(x.Text("name"), line.Voice, StringComparison.OrdinalIgnoreCase));
                var voiceId = character?.Text("voiceId") ?? (character is null && string.Equals(line.Voice, row.Text("episodeNarratorVoiceId"), StringComparison.OrdinalIgnoreCase) ? line.Voice : "");
                var speed = character?.Decimal("voiceSpeed", 1) ?? 1;
                var pitch = character?.Decimal("voicePitch", 0) ?? 0;
                var parameters = JsonSerializer.SerializeToDocument(new { text = line.Text, voiceId, speed, pitch, outputName = $"shot_{shotId}_{audioTasks.Count + 1}.wav" }).RootElement.Clone();
                var taskId = await _repository.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = shotId, TaskType = "Audio", ResourceClass = "CPU", Stage = "TTS", MaxRetries = 1, Parameters = parameters }, ct);
                audioTasks.Add(taskId); Enqueue(taskId);
            }
            await _repository.UpdateShotStatusAsync(shotId, "AudioGenerating", ct);
        }
        var episodeId = shot.LongOrNull("episodeId");
        if (episodeId is { } episode && !await _repository.HasActiveTaskForEpisodeAsync(episode, "Subtitles", ct))
        {
            var subtitleTask = await _repository.CreateTaskAsync(new TaskInput { EpisodeId = episode, TaskType = "Subtitles", ResourceClass = "CPU", Stage = "Subtitle", MaxRetries = 1, Parameters = JsonSerializer.SerializeToDocument(new { episodeId = episode }).RootElement.Clone() }, ct);
            Enqueue(subtitleTask);
        }
    }

    private async Task TryQueueAutoEpisodeRenderAsync(long? episodeId, CancellationToken ct)
    {
        if (episodeId is not { } id) return;
        var episode = (await _repository.EpisodeAsync(id, ct)).FirstOrDefault();
        if (episode is null || !string.Equals(episode.Text("productionMode"), "AutoProduction", StringComparison.OrdinalIgnoreCase)) return;
        if (!await _repository.HasSucceededTaskForEpisodeAsync(id, "Subtitles", ct) || await _repository.HasActiveTaskForEpisodeAsync(id, "EpisodeRender", ct)) return;
        var shots = (await _repository.ShotsAsync(id, ct)).OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))).ToList();
        if (shots.Count == 0 || shots.Any(x => !string.Equals(x.Text("status"), "Completed", StringComparison.OrdinalIgnoreCase))) return;
        var files = shots.Select(x => x.Text("finalVideoPath") ?? x.Text("videoPath") ?? x.Text("resultPath")).Where(x => !string.IsNullOrWhiteSpace(x) && File.Exists(x)).Cast<string>().ToArray();
        if (files.Length != shots.Count) return;
        var starts = new Dictionary<long, double>(); var cursor = 0d;
        foreach (var shot in shots) { starts[shot.Long("id")] = cursor; cursor += Math.Max(1, Convert.ToDouble(shot.Decimal("durationSeconds", 5))); }
        var audioTracks = new List<object>();
        var voiceVolume = (double)episode.Decimal("voiceVolume", 1); var bgmVolume = (double)episode.Decimal("bgmVolume", .18m); var sfxVolume = (double)episode.Decimal("sfxVolume", .6m);
        foreach (var audio in await _repository.EpisodeAudioResultsAsync(id, ct))
        {
            var path = audio.Text("path"); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
            var start = audio.LongOrNull("shotId") is { } shotId && starts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
            audioTracks.Add(new { path, volume = voiceVolume, startSeconds = start });
        }
        foreach (var effect in await _repository.EpisodeSoundEffectsAsync(id, ct))
        {
            var path = effect.Text("path"); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
            var start = effect.LongOrNull("shotId") is { } shotId && starts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
            audioTracks.Add(new { path, volume = Math.Clamp((double)effect.Decimal("volume", .6m) * sfxVolume, .05, 2), startSeconds = start + (double)effect.Decimal("startSeconds", 0) });
        }
        foreach (var bgm in await _repository.EpisodeBgmAsync(id, ct))
        {
            var path = bgm.Text("path"); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
            audioTracks.Add(new { path, volume = Math.Clamp((double)bgm.Decimal("volume", .18m) * bgmVolume, .05, 2), startSeconds = 0d });
        }
        var subtitlePath = episode.Text("subtitlePath");
        var parameters = JsonSerializer.SerializeToDocument(new { files, outputName = $"{episode.Text("name") ?? "Episode"}_{episode.Int("episodeNumber", 1):000}.mp4", subtitlePath, audioTracks }).RootElement.Clone();
        var taskId = await _repository.CreateTaskAsync(new TaskInput { ProjectId = episode.LongOrNull("projectId"), EpisodeId = id, TaskType = "EpisodeRender", ResourceClass = "CPU", Stage = "Episode", MaxRetries = 1, Parameters = parameters }, ct);
        Enqueue(taskId);
    }

    private async Task AutoAdvanceAsync(IReadOnlyDictionary<string, object?> row, long shotId, long dependencyTaskId, CancellationToken ct)
    {
        if (!string.Equals(row.Text("episodeProductionMode"), "AutoProduction", StringComparison.OrdinalIgnoreCase)) return;
        if (await _repository.HasActiveTaskForShotAsync(shotId, "ImageToVideo", ct)) return;
        var candidate = (await _repository.CandidatesAsync(shotId, ct)).FirstOrDefault(x => x.Text("qcStatus") == "Passed");
        if (candidate is null) return;
        var path = await _repository.SelectCandidateAsync(shotId, candidate.Long("id"), ct);
        var shot = (await _repository.QueryShotAsync(shotId, ct)).FirstOrDefault();
        if (shot is null || string.IsNullOrWhiteSpace(path)) return;
        var parameters = JsonSerializer.SerializeToDocument(new { positive = shot.Text("prompt"), negative = shot.Text("negativePrompt"), seed = shot.LongOrNull("seed") ?? Random.Shared.NextInt64(1, 900000000), width = shot.Int("width", 512), height = shot.Int("height", 320), frames = Math.Clamp((int)Math.Round(shot.Decimal("durationSeconds", 5) * shot.Decimal("fps", 24)), 49, 241), fps = shot.Decimal("fps", 24), duration = shot.Decimal("durationSeconds", 5), action = shot.Text("action"), cameraMotion = shot.Text("cameraMotion") }).RootElement.Clone();
        var taskId = await _repository.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = shotId, TaskType = "ImageToVideo", WorkflowId = shot.LongOrNull("workflowId"), InputImagePath = path, MaxRetries = 2, Stage = "I2V", DependencyTaskId = dependencyTaskId, Parameters = parameters }, ct);
        await _repository.AddTaskDependencyAsync(taskId, dependencyTaskId, ct);
        await _repository.UpdateShotStatusAsync(shotId, "VideoGenerating", ct);
        Enqueue(taskId);
    }

    private async Task ExecuteShotQaAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var shotId = row.LongOrNull("shotId");
        var episodeId = row.LongOrNull("episodeId");
        if (shotId is null || episodeId is null) throw new InvalidOperationException("ShotQA 缺少 shot_id 或 episode_id");
        var shot = (await _repository.QaShotAsync(shotId.Value, ct)).FirstOrDefault() ?? throw new InvalidOperationException("验收镜头不存在");
        var episode = (await _repository.EpisodeAsync(episodeId.Value, ct)).FirstOrDefault() ?? throw new InvalidOperationException("验收 Episode 不存在");
        using var document = row.Json("inputJson");
        var parameters = document.RootElement.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : document.RootElement;
        var preset = await _qa.GetPresetAsync(GetString(parameters, "preset") ?? "Standard", ct);
        var autoRetry = GetBool(parameters, "autoRetry", true);
        var runId = await _repository.CreateQaRunAsync(episodeId, shotId, shot.Int("qaVersion") + 1, preset.Name, "Shot", "Auto", ct);
        var evaluation = await _qa.EvaluateShotAsync(shot, episode, preset, ct);
        await _repository.UpdateShotQaAsync(shotId.Value, evaluation, shot.Int("qaVersion") + 1, ct: ct);
        foreach (var issue in evaluation.Issues) await _repository.AddQaIssueAsync(runId, episodeId, shotId, issue, ct);
        await _repository.CompleteQaRunAsync(runId, evaluation.Status, evaluation.Score, evaluation.Issues.Count, evaluation.ResultJson, ct);
        if (GetBool(parameters, "qaRetry", false))
            await _repository.LogAsync("qa.retry.result", $"Shot {shotId} QA 回炉结果：{evaluation.Status}，新 QA 分数 {evaluation.Score:0.##}", row.Long("id"), "Info", ct);
        if (evaluation.Status == "Rejected" && evaluation.ShouldRetry && autoRetry && await QueueQaRetryAsync(shot, preset.MaxAutoRetries, ct, evaluation.Status, evaluation.Score))
            await _repository.SetShotQaStatusAsync(shotId.Value, "AutoChecking", ct);
    }

    private async Task ExecuteEpisodeQaAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var episodeId = row.LongOrNull("episodeId") ?? throw new InvalidOperationException("EpisodeQA 缺少 episode_id");
        using var document = row.Json("inputJson");
        var parameters = document.RootElement.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : document.RootElement;
        var preset = await _qa.GetPresetAsync(GetString(parameters, "preset") ?? "Standard", ct);
        var autoRetry = GetBool(parameters, "autoRetry", true);
        var evaluation = await _qa.EvaluateEpisodeAsync(episodeId, preset, ct);
        if (evaluation.Status == "Rejected" && autoRetry)
        {
            foreach (var shot in await _repository.ShotsAsync(episodeId, ct))
                if (string.Equals(shot.Text("qaStatus"), "Rejected", StringComparison.OrdinalIgnoreCase)) await QueueQaRetryAsync(shot, preset.MaxAutoRetries, ct);
        }
    }

    private async Task ExecuteQaExportAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var episodeId = row.LongOrNull("episodeId") ?? throw new InvalidOperationException("QAExport 缺少 episode_id");
        using var document = row.Json("inputJson");
        var root = document.RootElement.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : document.RootElement;
        var input = JsonSerializer.Deserialize<QaExportInput>(root.GetRawText()) ?? new QaExportInput();
        await _qa.ExportMasterAsync(episodeId, input, ct);
    }

    private async Task<bool> QueueQaRetryAsync(IReadOnlyDictionary<string, object?> shot, int maxRetries, CancellationToken ct, string? previousStatusOverride = null, decimal? previousScoreOverride = null)
    {
        var shotId = shot.LongOrNull("id");
        if (shotId is null) return false;
        var inputImage = shot.Text("selectedKeyframePath") ?? shot.Text("inputImagePath");
        if (string.IsNullOrWhiteSpace(inputImage) || !File.Exists(inputImage)) return false;
        if (!await _repository.IncrementQaRetryAsync(shotId.Value, maxRetries, ct)) return false;
        var fps = shot.Decimal("fps", 24); var duration = shot.Decimal("durationSeconds", 5);
        var retryCount = shot.Int("qaRetryCount", 0) + 1;
        var previousStatus = previousStatusOverride ?? shot.Text("qaStatus") ?? "Rejected";
        var previousScore = previousScoreOverride ?? shot.Decimal("qaScore", 0);
        var previousSeed = shot.LongOrNull("seed");
        var retrySeed = Random.Shared.NextInt64(1, 900000000);
        if (previousSeed is { } seed && retrySeed == seed) retrySeed = seed == 899999999 ? 1 : seed + 1;
        var taskId = await _repository.CreateTaskAsync(new TaskInput
        {
            ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = shotId, TaskType = "ImageToVideo", WorkflowId = shot.LongOrNull("workflowId"),
            InputImagePath = inputImage, Priority = 5, MaxRetries = 2, Stage = "QA-Retry",
            Parameters = JsonSerializer.SerializeToDocument(new { positive = shot.Text("prompt"), negative = shot.Text("negativePrompt"), seed = retrySeed, width = shot.Int("width", 512), height = shot.Int("height", 320), frames = Math.Clamp((int)Math.Round(duration * fps), 49, 241), fps, duration, action = shot.Text("action"), cameraMotion = shot.Text("cameraMotion"), qaRetry = true, retryCount, previousQaStatus = previousStatus, previousQaScore = previousScore, retryReason = $"Shot QA {previousStatus}", changedParameters = new { seed = retrySeed }, preset = "Standard", autoRetry = true }).RootElement.Clone()
        }, ct);
        await _repository.LogAsync("qa.retry", $"Shot {shotId} 第 {retryCount} 次 QA 回炉；原状态 {previousStatus}，原分数 {previousScore:0.##}，修改 Seed 为 {retrySeed}", taskId, "Warning", ct);
        await _repository.SetShotQaStatusAsync(shotId.Value, "AutoChecking", ct);
        await _repository.UpdateShotStatusAsync(shotId.Value, "VideoGenerating", ct);
        Enqueue(taskId);
        return true;
    }

    private async Task ExecuteAudioAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        using var document = row.Json("inputJson"); var root = document.RootElement; var parameters = root.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : root;
        var text = GetString(parameters, "text") ?? ""; var voice = GetString(parameters, "voiceId") ?? ""; var outputName = GetString(parameters, "outputName"); var speed = GetDecimal(parameters, "speed", 1); var pitch = GetDecimal(parameters, "pitch", 0);
        var path = await _tts.SynthesizeAsync(text, voice, speed, pitch, outputName, ct);
        var assetId = await _repository.AddAssetAsync(row.LongOrNull("projectId"), row.LongOrNull("episodeId"), row.LongOrNull("shotId"), "audio", Path.GetFileName(path), path, RelativeToData(path), await _ffmpeg.ProbeAsync(path, ct), ct);
        await _repository.AddResultAsync(row.Long("id"), assetId, "audio", path, ct);
        if (row.LongOrNull("shotId") is { } shotId) await _repository.UpdateShotAudioStatusAsync(shotId, "Completed", ct);
    }

    private async Task ExecuteSubtitlesAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        using var document = row.Json("inputJson"); var root = document.RootElement; var parameters = root.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : root;
        var episodeId = GetLong(parameters, "episodeId") ?? row.Long("episodeId"); var shots = await _repository.ShotsAsync(episodeId, ct); var output = await _subtitles.GenerateAsync(episodeId, GetString(parameters, "outputName"), shots, ct);
        var assetId = await _repository.AddAssetAsync(row.LongOrNull("projectId"), episodeId, null, "subtitle", Path.GetFileName(output), output, RelativeToData(output), null, ct);
        await _repository.AddResultAsync(row.Long("id"), assetId, "subtitle", output, ct);
    }

    private async Task ExecuteEpisodeRenderAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        using var document = row.Json("inputJson"); var root = document.RootElement; var parameters = root.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : root;
        var files = parameters.TryGetProperty("files", out var list) && list.ValueKind == JsonValueKind.Array ? list.EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x) && File.Exists(x)).Cast<string>().ToArray() : [];
        if (files.Length == 0) throw new InvalidOperationException("Episode 没有可合成视频");
        var outputName = GetString(parameters, "outputName") ?? $"Episode_{row.Long("episodeId"):000}.mp4";
        var output = Path.Combine(_settings.DataPath, "Output", Path.GetFileName(outputName)); var temp = Path.Combine(_settings.DataPath, "Temp", $"episode_{row.Long("id")}_concat.mp4");
        await _ffmpeg.ConcatAsync(files, temp, 30, ct); var current = temp;
        var audioTracks = new List<FfmpegAudioTrack>();
        if (parameters.TryGetProperty("audioTracks", out var trackList) && trackList.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in trackList.EnumerateArray())
            {
                if (!item.TryGetProperty("path", out var pathValue) || pathValue.ValueKind != JsonValueKind.String) continue;
                var path = pathValue.GetString(); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
                var volume = item.TryGetProperty("volume", out var volumeValue) && volumeValue.TryGetDouble(out var parsedVolume) ? parsedVolume : 1d;
                var start = item.TryGetProperty("startSeconds", out var startValue) && startValue.TryGetDouble(out var parsedStart) ? parsedStart : 0d;
                audioTracks.Add(new FfmpegAudioTrack(path, volume, start));
            }
        }
        if (parameters.TryGetProperty("audioPaths", out var audioList) && audioList.ValueKind == JsonValueKind.Array)
            audioTracks.AddRange(audioList.EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x) && File.Exists(x)).Select(x => new FfmpegAudioTrack(x!, 1d)));
        if (audioTracks.Count > 0) { var mixed = Path.Combine(_settings.DataPath, "Temp", $"episode_{row.Long("id")}_audio.mp4"); await _ffmpeg.MixAudioAsync(current, audioTracks, mixed, ct); current = mixed; }
        var subtitlePath = GetString(parameters, "subtitlePath"); if (!string.IsNullOrWhiteSpace(subtitlePath) && File.Exists(subtitlePath)) { await _ffmpeg.BurnSubtitlesAsync(current, subtitlePath, output, ct); current = output; }
        if (!string.Equals(current, output, StringComparison.OrdinalIgnoreCase)) File.Copy(current, output, true);
        var probe = await _ffmpeg.ProbeAsync(output, ct); var assetId = await _repository.AddAssetAsync(row.LongOrNull("projectId"), row.LongOrNull("episodeId"), null, "episode", Path.GetFileName(output), output, RelativeToData(output), probe, ct); await _repository.AddResultAsync(row.Long("id"), assetId, "episode", output, ct); await _repository.UpdateEpisodeOutputAsync(row.Long("episodeId"), output, probe?.DurationSeconds, ct);
    }

    private async Task ExecuteEnhanceAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var taskId = row.Long("id"); using var inputDocument = row.Json("inputJson"); var inputRoot = inputDocument.RootElement; var parameters = inputRoot.TryGetProperty("parameters", out var nestedParameters) && nestedParameters.ValueKind == JsonValueKind.Object ? nestedParameters : JsonDocument.Parse("{}").RootElement; var input = GetString(inputRoot, "inputImagePath") ?? GetString(inputRoot, "input");
        if (string.IsNullOrWhiteSpace(input) || !File.Exists(input)) throw new FileNotFoundException("增强输入视频不存在", input);
        var output = Path.Combine(_settings.DataPath, "Output", $"task_{taskId}_1080p.mp4"); await _ffmpeg.EnhanceAsync(input, output, 30, ct); var qc = await _quality.CheckVideoAsync(output, row.Decimal("shotDurationSeconds", 5), 1920, 1080, 30, ct); if (!qc.Passed) throw new InvalidOperationException("QUALITY_FAILED: 增强后视频 QC 未通过");
        var probe = await _ffmpeg.ProbeAsync(output, ct); var assetId = await _repository.AddAssetAsync(row.LongOrNull("projectId"), row.LongOrNull("episodeId"), row.LongOrNull("shotId"), "video", Path.GetFileName(output), output, RelativeToData(output), probe, ct); await _repository.AddResultAsync(taskId, assetId, "video", output, ct);
        if (row.LongOrNull("shotId") is { } shotId)
        {
            await _repository.UpdateShotFinalVideoAsync(shotId, output, JsonSerializer.Serialize(qc.Metrics), qc.Score, ct);
            if (GetBool(parameters, "qaRetry", false))
            {
                var qaTaskId = await _repository.CreateTaskAsync(new TaskInput
                {
                    ProjectId = row.LongOrNull("projectId"), EpisodeId = row.LongOrNull("episodeId"), ShotId = shotId, TaskType = "ShotQA", ResourceClass = "CPU", Stage = "QA", Priority = -10, MaxRetries = 0,
                    Parameters = JsonSerializer.SerializeToDocument(new
                    {
                        preset = GetString(parameters, "preset") ?? "Standard",
                        autoRetry = GetBool(parameters, "autoRetry", true),
                        qaRetry = true,
                        retryCount = GetInt(parameters, "retryCount") ?? 0,
                        previousQaStatus = GetString(parameters, "previousQaStatus"),
                        previousQaScore = GetDecimal(parameters, "previousQaScore", 0),
                        retryReason = GetString(parameters, "retryReason"),
                        changedParameters = parameters.TryGetProperty("changedParameters", out var changed) ? changed.Clone() : (JsonElement?)null
                    }).RootElement.Clone()
                }, ct);
                await _repository.SetShotQaStatusAsync(shotId, "AutoChecking", ct);
                await _repository.LogAsync("qa.retry.output", $"Shot {shotId} 回炉新视频已生成：{output}，增强 QC 分数 {qc.Score:0.##}，已排队再次 QA", qaTaskId, "Info", ct);
                Enqueue(qaTaskId);
            }
            else
            {
                await AutoAdvanceAudioAsync(row, shotId, ct);
            }
        }
    }

    private async Task ExecuteConcatAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var taskId = row.Long("id"); using var document = row.Json("inputJson"); var inputRoot = document.RootElement; if (!inputRoot.TryGetProperty("files", out _) && inputRoot.TryGetProperty("parameters", out var nested) && nested.ValueKind == JsonValueKind.Object) inputRoot = nested;
        var files = inputRoot.TryGetProperty("files", out var list) && list.ValueKind == JsonValueKind.Array ? list.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).Where(File.Exists).ToList() : [];
        if (files.Count == 0) throw new InvalidOperationException("拼接任务未提供有效 files"); var output = Path.Combine(_settings.DataPath, "Output", inputRoot.TryGetProperty("outputName", out var name) && name.ValueKind == JsonValueKind.String ? Path.GetFileName(name.GetString()!) : $"task_{taskId}_concat.mp4"); await _ffmpeg.ConcatAsync(files, output, 30, ct); var assetId = await _repository.AddAssetAsync(row.LongOrNull("projectId"), row.LongOrNull("episodeId"), null, "video", Path.GetFileName(output), output, RelativeToData(output), await _ffmpeg.ProbeAsync(output, ct), ct); await _repository.AddResultAsync(taskId, assetId, "video", output, ct);
    }

    private async Task<string?> CopyInputToComfyAsync(string? input, long taskId, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(input)) return null; var full = Path.GetFullPath(input); var aiRoot = Path.GetFullPath(Path.Combine(_settings.RootPath, ".."));
        if (!File.Exists(full) || !full.StartsWith(aiRoot, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("参考图必须位于 C:\\install\\AI 内");
        Directory.CreateDirectory(_settings.ComfyInputPath); var target = Path.Combine(_settings.ComfyInputPath, $"video_studio_input_{taskId}{Path.GetExtension(full)}"); await using var source = File.OpenRead(full); await using var destination = File.Create(target); await source.CopyToAsync(destination, ct); return target;
    }

    private async Task WaitForGpuAsync(CancellationToken ct)
    {
        for (var i = 0; i < 120; i++) { var snapshot = await _comfy.CheckAsync(ct); if (snapshot.Gpu is null || snapshot.Gpu.FreeMiB >= _settings.MinFreeVramMiB) return; await Task.Delay(5000, ct); }
        throw new TimeoutException("GPU 可用显存持续低于安全阈值，任务未提交");
    }

    private async Task ReduceParametersForOomAsync(long id, IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        try
        {
            using var doc = row.Json("inputJson"); var root = JsonNode.Parse(doc.RootElement.GetRawText())?.AsObject(); var parameters = root?["parameters"]?.AsObject(); if (parameters is null) return;
            if (parameters["width"] is JsonValue width && width.TryGetValue<int>(out var w)) parameters["width"] = Math.Max(256, w - 64);
            if (parameters["height"] is JsonValue height && height.TryGetValue<int>(out var h)) parameters["height"] = Math.Max(192, h - 64);
            if (parameters["frames"] is JsonValue frames && frames.TryGetValue<int>(out var f)) parameters["frames"] = Math.Max(49, f - 24);
            await _repository.UpdateTaskInputAsync(id, root!.ToJsonString(), ct);
        }
        catch (Exception ex) { _logger.LogDebug(ex, "OOM 参数降级失败"); }
    }

    private string DefaultWorkflow(string taskType) => taskType.Contains("video", StringComparison.OrdinalIgnoreCase) || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase)
        ? Path.Combine(_settings.WorkflowsPath, "02_ltx_i2v_quality_api.json") : Path.Combine(_settings.WorkflowsPath, "01_portrait_quality_api.json");
    private string? RelativeToData(string path) => Path.GetFullPath(path).StartsWith(Path.GetFullPath(_settings.DataPath), StringComparison.OrdinalIgnoreCase) ? Path.GetRelativePath(_settings.DataPath, path) : null;
    private static string? GetString(JsonElement root, params string[] names) => names.Select(n => root.TryGetProperty(n, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null).FirstOrDefault(x => !string.IsNullOrWhiteSpace(x));
    private static bool GetBool(JsonElement root, string name, bool fallback) => root.TryGetProperty(name, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean() : fallback;
    private static int? GetInt(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.TryGetInt32(out var result) ? result : null;
    private static long? GetLong(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.TryGetInt64(out var result) ? result : null;
    private static decimal GetDecimal(JsonElement root, string name, decimal fallback) => root.TryGetProperty(name, out var value) && value.TryGetDecimal(out var result) ? result : fallback;

    private static string ClassifyError(Exception ex, string message)
    {
        if (ex is FileNotFoundException && message.Contains("工作流", StringComparison.OrdinalIgnoreCase)) return "WORKFLOW_ERROR";
        if (message.Contains("out of memory", StringComparison.OrdinalIgnoreCase) || message.Contains("cuda", StringComparison.OrdinalIgnoreCase) && message.Contains("memory", StringComparison.OrdinalIgnoreCase)) return "CUDA_OOM";
        if (message.Contains("ComfyUI", StringComparison.OrdinalIgnoreCase) && (message.Contains("HTTP", StringComparison.OrdinalIgnoreCase) || message.Contains("连接", StringComparison.OrdinalIgnoreCase))) return "COMFYUI_OFFLINE";
        if (message.Contains("模型", StringComparison.OrdinalIgnoreCase) && message.Contains("不存在", StringComparison.OrdinalIgnoreCase)) return "MODEL_MISSING";
        if (message.Contains("参考图", StringComparison.OrdinalIgnoreCase) || ex is FileNotFoundException) return "INPUT_MISSING";
        if (message.Contains("FFmpeg", StringComparison.OrdinalIgnoreCase) || message.Contains("FFprobe", StringComparison.OrdinalIgnoreCase)) return "FFMPEG_ERROR";
        if (ex is TimeoutException) return "TIMEOUT";
        if (message.Contains("QA", StringComparison.OrdinalIgnoreCase) || message.Contains("验收", StringComparison.OrdinalIgnoreCase)) return "QA_ERROR";
        if (message.Contains("QUALITY_FAILED", StringComparison.OrdinalIgnoreCase) || message.Contains("质量", StringComparison.OrdinalIgnoreCase) || message.Contains("QC", StringComparison.OrdinalIgnoreCase)) return "QUALITY_FAILED";
        return "UNKNOWN";
    }
}
