using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;

namespace VideoStudio.Server;

/// <summary>
/// 单 GPU 任务调度器。RTX 4070 12GB 始终只允许一个 GPU 重任务运行；
/// CPU 的 TTS、字幕、FFmpeg 任务也走同一条可恢复队列，但不会与 GPU 任务并发。
/// 任务依赖、重试和状态更新都在数据库中记录，服务重启后从 Pending/Running 恢复。
/// </summary>
public sealed partial class GenerationQueue : BackgroundService
{
    private readonly Channel<long> _cpuSignals = Channel.CreateUnbounded<long>(new UnboundedChannelOptions { SingleReader = true, SingleWriter = false });
    private readonly Channel<long> _gpuSignals = Channel.CreateUnbounded<long>(new UnboundedChannelOptions { SingleReader = true, SingleWriter = false });
    private readonly ConcurrentDictionary<long, CancellationTokenSource> _active = new();
    private readonly ConcurrentDictionary<long, TaskLease> _activeLeases = new();
    private readonly ConcurrentDictionary<long, TaskWorkspace> _workspaces = new();
    private readonly ConcurrentDictionary<long, ConcurrentQueue<PublishedArtifact>> _publishedArtifacts = new();
    private readonly ConcurrentDictionary<long, ConcurrentQueue<Func<CancellationToken, Task>>> _postSuccessActions = new();
    private readonly StudioRepository _repository;
    private readonly ProductionCoreRepository _productionCore;
    private readonly TaskLeaseRepository _leases;
    private readonly TaskArtifactService _artifacts;
    private readonly AssetReferenceResolver _assetResolver;
    private readonly GpuGlobalGate _gpuGate;
    private readonly ComfyUiClient _comfy;
    private readonly FfmpegService _ffmpeg;
    private readonly QualityControlService _quality;
    private readonly FaceQualityService _faceQuality;
    private readonly LocalTtsService _tts;
    private readonly MiniMaxLocalService _miniMaxLocal;
    private readonly SubtitleService _subtitles;
    private readonly VideoQaService _qa;
    private readonly StudioSettings _settings;
    private readonly AssetPathPolicy _paths;
    private readonly DiskSpaceGuard _disk;
    private readonly WorkflowContractService _contracts;
    private readonly ReleaseEligibilityService _release;
    private readonly ReleaseCandidateRepository _candidates;
    private readonly CharacterReferenceGateService _characterReferences;
    private readonly CharacterLibraryService? _characterLibrary;
    private readonly CharacterStoryService? _characterStory;
    private readonly CharacterWorkshopService? _characterWorkshop;
    private readonly ILogger<GenerationQueue> _logger;
    private readonly string _workerId = $"video-studio-{Environment.MachineName}-{Guid.NewGuid():N}";
    private volatile bool _paused;

    public GenerationQueue(StudioRepository repository, ProductionCoreRepository productionCore, TaskLeaseRepository leases, TaskArtifactService artifacts, AssetReferenceResolver assetResolver, GpuGlobalGate gpuGate, ComfyUiClient comfy, FfmpegService ffmpeg, QualityControlService quality, FaceQualityService faceQuality, LocalTtsService tts, SubtitleService subtitles, VideoQaService qa, StudioSettings settings, AssetPathPolicy paths, DiskSpaceGuard disk, WorkflowContractService contracts, ReleaseEligibilityService release, ReleaseCandidateRepository candidates, CharacterReferenceGateService characterReferences, ILogger<GenerationQueue> logger, MiniMaxLocalService? miniMaxLocal = null, CharacterLibraryService? characterLibrary = null, CharacterStoryService? characterStory = null, CharacterWorkshopService? characterWorkshop = null)
    {
        _repository = repository; _productionCore = productionCore; _leases = leases; _artifacts = artifacts; _assetResolver = assetResolver; _gpuGate = gpuGate; _comfy = comfy; _ffmpeg = ffmpeg; _quality = quality; _faceQuality = faceQuality; _tts = tts; _subtitles = subtitles; _qa = qa; _settings = settings; _paths = paths; _disk = disk; _contracts = contracts; _release = release; _candidates = candidates; _characterReferences = characterReferences; _logger = logger;
        _miniMaxLocal = miniMaxLocal ?? new MiniMaxLocalService(settings);
        _characterLibrary = characterLibrary;
        _characterStory=characterStory;_characterWorkshop=characterWorkshop;
    }

    public object Status => new { enabled = _settings.WorkerEnabled, paused = _paused, activeTasks = _active.Count, cpuConcurrency = 1, gpuConcurrency = 1, crossProcessGpuLock = _gpuGate.LockPath, policy = "cross-process-file-lock-gpu-concurrency-1" };
    public bool Enqueue(long taskId)
    {
        var cpuWritten = _cpuSignals.Writer.TryWrite(taskId);
        var gpuWritten = _gpuSignals.Writer.TryWrite(taskId);
        return cpuWritten && gpuWritten;
    }
    public void Pause() => _paused = true;
    public void Resume() => _paused = false;

    public async Task CancelAsync(long taskId, CancellationToken ct = default)
    {
        if (_active.TryGetValue(taskId, out var cancellation))
        {
            cancellation.Cancel();
            var cancellingTask = (await _repository.TaskAsync(taskId, ct)).FirstOrDefault();
            if (cancellingTask?.Text("resourceClass") == "GPU" && !new[] { "Audio", "TTS", "VideoRestore", "VisualActing" }.Contains(cancellingTask.Text("taskType"), StringComparer.OrdinalIgnoreCase))
                try { await _comfy.InterruptAsync(ct); } catch { }
        }
        await _leases.CancelAsync(taskId, "用户取消", ct: ct);
    }

    public async Task CancelEpisodeAsync(long episodeId, CancellationToken ct = default)
    {
        var tasks = await _repository.TasksAsync(500, ct);
        foreach (var task in tasks.Where(x => x.LongOrNull("episodeId") == episodeId && x.Text("status") is "Pending" or "Running")) await CancelAsync(task.Long("id"), ct);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await Task.Delay(1000, stoppingToken);
        if (!await _productionCore.IsSchemaReadyAsync(stoppingToken))
        {
            _logger.LogError("Background worker refused to start because migration {Migration} is not present", Stage12SchemaMigrator.Version);
            return;
        }
        try
        {
            await _leases.RecoverExpiredAsync(stoppingToken);
            foreach (var row in await _repository.PendingTasksAsync(stoppingToken)) Enqueue(row.Long("id"));
        }
        catch (Exception ex) { _logger.LogWarning("恢复任务队列失败，将等待 API 请求后重试: {Message}", ex.Message); }

        _ = RecoverExpiredLoopAsync(stoppingToken);
        _ = RunResourceLoopAsync("CPU", _cpuSignals.Reader, stoppingToken);
        await foreach (var _ in _gpuSignals.Reader.ReadAllAsync(stoppingToken))
        {
            while (_paused && !stoppingToken.IsCancellationRequested) await Task.Delay(500, stoppingToken);
            var next = await _repository.HighestPendingTaskAsync("GPU", stoppingToken);
            if (next is null) continue;
            try { await ProcessGpuWithGateAsync(next.Long("id"), stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex) { _logger.LogError(ex, "任务 {TaskId} 未处理", next.Long("id")); }
        }
    }

    private async Task ProcessGpuWithGateAsync(long taskId, CancellationToken ct)
    {
        await using var gpuLease = await _gpuGate.AcquireAsync($"{_workerId}:task-{taskId}", ct);
        await ProcessAsync(taskId, ct);
    }
    private async Task RecoverExpiredLoopAsync(CancellationToken ct)
    {
        // Startup can occur before the previous process lease expires. Keep
        // checking so a restart does not strand a still-unexpired Running row.
        using var timer=new PeriodicTimer(TimeSpan.FromSeconds(15));
        try
        {
            while(await timer.WaitForNextTickAsync(ct))
            {
                try
                {
                    await _leases.RecoverExpiredAsync(ct,characterStoryOnly:true);
                    // A client disconnect can occur after the durable insert
                    // and before Enqueue. Pending rows remain the authority.
                    foreach(var row in await _repository.PendingTasksAsync(ct))Enqueue(row.Long("id"));
                }
                catch(OperationCanceledException)when(ct.IsCancellationRequested){break;}
                catch(Exception ex){_logger.LogWarning("恢复过期任务租约暂未完成：{Message}",ex.Message);}
            }
        }
        catch(OperationCanceledException)when(ct.IsCancellationRequested){}
    }

    private async Task RunResourceLoopAsync(string resourceClass, ChannelReader<long> signals, CancellationToken stoppingToken)
    {
        await foreach (var _ in signals.ReadAllAsync(stoppingToken))
        {
            while (_paused && !stoppingToken.IsCancellationRequested) await Task.Delay(500, stoppingToken);
            var next = await _repository.HighestPendingTaskAsync(resourceClass, stoppingToken);
            if (next is null) continue;
            try { await ProcessAsync(next.Long("id"), stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex) { _logger.LogError(ex, "Task {TaskId} was not processed", next.Long("id")); }
        }
    }

    private async Task ProcessAsync(long id, CancellationToken stoppingToken)
    {
        var row = (await _repository.TaskAsync(id, stoppingToken)).FirstOrDefault();
        if (row is null || !string.Equals(row.Text("status"), "Pending", StringComparison.OrdinalIgnoreCase)) return;
        var dependency = await _repository.TaskDependencyStateAsync(id, stoppingToken);
        if (dependency.Blocked)
        {
            await _leases.FailPendingAsync(id, "INPUT_MISSING", "上游任务失败，下游任务未执行", stoppingToken);
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
        var taskType = row.Text("taskType") ?? "Image";
        var taskDeadline = TaskDeadline(taskType, row.Text("resourceClass"), row.Text("workflowPath"));
        var lease = await _leases.ClaimAsync(id, _workerId, TimeSpan.FromMinutes(5), taskDeadline, stoppingToken);
        if (lease is null) return;
        if (DiskSpaceGuard.IsHighCostTask(taskType, row.Text("resourceClass")))
        {
            var disk = _disk.Check();
            if (!disk.Allowed)
            {
                await _leases.SetErrorAsync(lease, "DISK_SPACE_LOW", "高成本任务因目标卷可用空间不足而拒绝执行", stoppingToken);
                await _leases.CompleteAsync(lease, "Failed", "高成本任务因目标卷可用空间不足而拒绝执行", ct: stoppingToken);
                return;
            }
        }
        var workspace = _artifacts.CreateWorkspace(lease);
        using var deadlineCancellation = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        deadlineCancellation.CancelAfter(taskDeadline);
        using var taskCancellation = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken, deadlineCancellation.Token);
        using var heartbeatCancellation = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        var heartbeat = MaintainLeaseAsync(lease, heartbeatCancellation.Token);
        _active[id] = taskCancellation;
        _activeLeases[id] = lease;
        _workspaces[id] = workspace;
        _publishedArtifacts[id] = new ConcurrentQueue<PublishedArtifact>();
        _postSuccessActions[id] = new ConcurrentQueue<Func<CancellationToken, Task>>();
        var started = DateTime.UtcNow;
        try
        {
            await _repository.LogAsync("task.start", $"开始执行 {taskType}", id, ct: stoppingToken);
            if (taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase)) await ExecuteAudioAsync(row, taskCancellation.Token);
            else if (taskType.Equals("MusicSynthesis", StringComparison.OrdinalIgnoreCase)) await ExecuteMusicSynthesisAsync(row, taskCancellation.Token);
            else if (taskType.Equals("VideoRestore", StringComparison.OrdinalIgnoreCase)) await ExecuteSeedRestoreAsync(row, taskCancellation.Token);
            else if (taskType.Equals("SkinComposite", StringComparison.OrdinalIgnoreCase)) await ExecuteSkinCompositeAsync(row, taskCancellation.Token);
            else if (taskType.Equals("VisualDetail", StringComparison.OrdinalIgnoreCase)) await ExecuteVisualDetailAsync(row, taskCancellation.Token);
            else if (taskType.Equals("DialogueComposite", StringComparison.OrdinalIgnoreCase)) await ExecuteDialogueCompositeAsync(row, taskCancellation.Token);
            else if (taskType.Equals("VisualActing", StringComparison.OrdinalIgnoreCase)) await ExecuteVisualActingAsync(row, taskCancellation.Token);
            else if (taskType.Equals("Subtitles", StringComparison.OrdinalIgnoreCase)) await ExecuteSubtitlesAsync(row, taskCancellation.Token);
            else if (taskType.Equals("EpisodeRender", StringComparison.OrdinalIgnoreCase)) await ExecuteEpisodeRenderAsync(row, taskCancellation.Token);
            else if (taskType.Equals("Concat", StringComparison.OrdinalIgnoreCase) || taskType.Equals("VideoConcat", StringComparison.OrdinalIgnoreCase)) await ExecuteConcatAsync(row, taskCancellation.Token);
            else if (taskType.Equals("Enhance", StringComparison.OrdinalIgnoreCase) || taskType.Equals("VideoEnhancement", StringComparison.OrdinalIgnoreCase)) await ExecuteEnhanceAsync(row, taskCancellation.Token);
            else if (taskType.Equals("ShotQA", StringComparison.OrdinalIgnoreCase)) await ExecuteShotQaAsync(row, taskCancellation.Token);
            else if (taskType.Equals("EpisodeQA", StringComparison.OrdinalIgnoreCase)) await ExecuteEpisodeQaAsync(row, taskCancellation.Token);
            else if (taskType.Equals("QAExport", StringComparison.OrdinalIgnoreCase)) await ExecuteQaExportAsync(row, taskCancellation.Token);
            else await ExecuteComfyAsync(row, taskCancellation.Token);
            var published = _publishedArtifacts[id].ToArray();
            if (RequiresArtifact(taskType) && published.Length == 0)
                throw new InvalidOperationException($"{taskType} completed without a validated artifact manifest");
            var primaryManifestId = SelectPrimary(published)?.ManifestId;
            if (await _leases.CompleteAsync(lease, "Succeeded", manifestId: primaryManifestId, ct: stoppingToken) != 1)
                throw new StaleTaskLeaseException("Task completion lost the cancellation/lease race");
            foreach (var action in _postSuccessActions[id]) await action(stoppingToken);
            if ((taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase)) && row.LongOrNull("shotId") is { } audioShotId)
                await _repository.TryCompleteShotAudioAsync(audioShotId, stoppingToken);
            if (taskType.Equals("Audio", StringComparison.OrdinalIgnoreCase) || taskType.Equals("TTS", StringComparison.OrdinalIgnoreCase) || taskType.Equals("Subtitles", StringComparison.OrdinalIgnoreCase))
                await TryQueueAutoEpisodeRenderAsync(row.LongOrNull("episodeId"), stoppingToken);
            await _repository.LogAsync("task.finish", $"任务完成，耗时 {(DateTime.UtcNow - started).TotalSeconds:F1}s", id, ct: stoppingToken);
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested && taskCancellation.IsCancellationRequested && deadlineCancellation.IsCancellationRequested)
        {
            await HandleFailureAsync(lease, row, attempts, maxRetries, "TASK_TIMEOUT", $"Task exceeded the {taskDeadline.TotalMinutes:0.#}-minute deadline", CancellationToken.None);
        }
        catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested)
        {
            await _leases.CompleteAsync(lease, "Cancelled", "任务被取消", ct: CancellationToken.None);
        }
        catch (StaleTaskLeaseException ex)
        {
            await _repository.LogAsync("task.stale_worker", ex.Message, id, "Warning", CancellationToken.None);
        }
        catch (Exception ex)
        {
            var message = ex.Message.Length > 3000 ? ex.Message[..3000] : ex.Message;
            var errorType = ClassifyError(ex, message);
            await _leases.SetErrorAsync(lease, errorType, message, CancellationToken.None);
            if (errorType == "CUDA_OOM" && row.Text("stage") != "MiniMax-Local-Experiment"
                && !MiniMaxLocalService.IsManagedWorkflow(row.Text("workflowPath") ?? ""))
                await ReduceParametersForOomAsync(lease, row, CancellationToken.None);
            if (attempts <= maxRetries)
            {
                await _leases.RequeueAsync(lease, errorType, message, CancellationToken.None);
                await _repository.LogAsync("task.retry", $"{errorType} 第 {attempts} 次失败，自动重试: {message}", id, "Warning", CancellationToken.None);
                await Task.Delay(TimeSpan.FromSeconds(Math.Min(15, attempts * 3)), stoppingToken);
                Enqueue(id);
            }
            else
            {
                await _leases.CompleteAsync(lease, "Failed", message, ct: CancellationToken.None);
                await _repository.LogAsync("task.failed", $"{errorType}: {message}", id, "Error", CancellationToken.None);
            }
        }
        finally
        {
            heartbeatCancellation.Cancel();
            try { await heartbeat; } catch (OperationCanceledException) { }
            _active.TryRemove(id, out _);
            _activeLeases.TryRemove(id, out _);
            _workspaces.TryRemove(id, out _);
            _publishedArtifacts.TryRemove(id, out _);
            _postSuccessActions.TryRemove(id, out _);
            if (row.Text("resourceClass") is not "CPU") await _comfy.TryFreeMemoryAsync(CancellationToken.None);
        }
    }

    private async Task HandleFailureAsync(TaskLease lease, IReadOnlyDictionary<string, object?> row, int attempts, int maxRetries, string errorType, string message, CancellationToken ct)
    {
        var id = lease.TaskId;
        await _leases.SetErrorAsync(lease, errorType, message, ct);
        if (attempts <= maxRetries)
        {
            await _leases.RequeueAsync(lease, errorType, message, ct);
            await _repository.LogAsync("task.retry", $"{errorType} retry {attempts}: {message}", id, "Warning", ct);
            await Task.Delay(TimeSpan.FromSeconds(Math.Min(15, attempts * 3)), ct);
            Enqueue(id);
        }
        else
        {
            await _leases.TimeoutAsync(lease, message, ct);
            await _repository.LogAsync("task.failed", $"{errorType}: {message}", id, "Error", ct);
        }
    }

    private static TimeSpan TaskDeadline(string taskType, string? resourceClass, string? workflowPath = null)
    {
        if (taskType.Equals("VisualActing", StringComparison.OrdinalIgnoreCase)) return TimeSpan.FromMinutes(35);
        if (taskType.Equals("VideoRestore", StringComparison.OrdinalIgnoreCase)) return TimeSpan.FromMinutes(95);
        if (taskType.Equals("SkinComposite", StringComparison.OrdinalIgnoreCase)) return TimeSpan.FromMinutes(30);
        if (string.Equals(resourceClass, "CPU", StringComparison.OrdinalIgnoreCase))
            return taskType.Equals("EpisodeRender", StringComparison.OrdinalIgnoreCase) ? TimeSpan.FromMinutes(30) : TimeSpan.FromMinutes(10);
        // Measured151-frame audioCFG2 windowed preview exceeds30min on this12GB host.
        // Keep a fixed admitted filename rather than accepting client-supplied deadlines.
        if (taskType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
            && string.Equals(Path.GetFileName(workflowPath), "dialogue_sync_full_shot_3_i2v_v1_api.json", StringComparison.Ordinal))
            return TimeSpan.FromMinutes(60);
        // These admitted local audio-driven pilots run several sequential windows on 12GB VRAM.
        if (taskType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
            && Path.GetFileName(workflowPath) is "infinitetalk_dialogue_125_api.json" or "infinitetalk_dialogue_241_api.json"
                or "infinitetalk_dialogue_125_exact_api.json" or "infinitetalk_dialogue_241_exact_api.json")
            return TimeSpan.FromMinutes(120);
        if (taskType.Contains("video", StringComparison.OrdinalIgnoreCase) || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase))
            return string.Equals(Path.GetFileName(workflowPath), MiniMaxLocalService.Native1080Quality30WorkflowFileName, StringComparison.OrdinalIgnoreCase) ? TimeSpan.FromMinutes(480)
                : MiniMaxLocalService.IsNative1080Workflow(workflowPath) ? TimeSpan.FromMinutes(360)
                : Path.GetFileName(workflowPath) is "minimax_h3_local_768_i2v_api.json" or MiniMaxLocalService.Quality768TextWorkflowFileName
                    ? TimeSpan.FromMinutes(90) : TimeSpan.FromMinutes(30);
        return TimeSpan.FromMinutes(15);
    }

    private async Task MaintainLeaseAsync(TaskLease lease, CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(TimeSpan.FromSeconds(20), ct);
                if (await _leases.HeartbeatAsync(lease, TimeSpan.FromMinutes(5), ct) != 1)
                    throw new StaleTaskLeaseException("Task heartbeat lost its lease");
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
        catch (Exception ex) { _logger.LogWarning(ex, "任务 {TaskId} 租约心跳失败", lease.TaskId); }
    }

    public override void Dispose() => base.Dispose();

    private async Task ExecuteComfyAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var taskId = row.Long("id");
        var taskType = row.Text("taskType") ?? "Image";
        CharacterReferenceGateResult? characterGate = null;
        if (row.LongOrNull("shotId") is { } generationShotId)
        {
            var generationShot = (await _repository.QueryShotAsync(generationShotId, ct)).FirstOrDefault();
            if (generationShot is not null && CharacterReferenceGateService.ReadCharacterIds(generationShot.Text("characterIdsJson")).Count > 0)
            {
                characterGate = await _characterReferences.CheckShotAsync(generationShotId, ct);
                if (!characterGate.Passed) throw new WorkflowContractException("REFERENCE_NOT_APPROVED", string.Join("；", characterGate.Issues));
            }
        }
        var workflowPath = row.Text("workflowPath");
        var workflowType = row.Text("workflowType");
        var needsVideoWorkflow = taskType.Contains("video", StringComparison.OrdinalIgnoreCase) || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase);
        var workflowMatchesTask = string.IsNullOrWhiteSpace(workflowType)
            || (needsVideoWorkflow
                ? workflowType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase) || workflowType.Equals("I2V", StringComparison.OrdinalIgnoreCase) || workflowType.Equals("Video", StringComparison.OrdinalIgnoreCase)
                : workflowType.Equals("Image", StringComparison.OrdinalIgnoreCase) || workflowType.Equals("TextToImage", StringComparison.OrdinalIgnoreCase));
        if (string.IsNullOrWhiteSpace(workflowPath))
        {
            if (needsVideoWorkflow)
                throw new WorkflowContractException("WORKFLOW_REQUIRED", "视频任务没有冻结的工作流路线；拒绝在执行阶段自动选择或回退工作流");
            workflowPath = DefaultWorkflow(taskType);
        }
        else if (!workflowMatchesTask) throw new WorkflowContractException("WORKFLOW_TASK_MISMATCH", $"登记的工作流类型 {workflowType} 与任务 {taskType} 不匹配；拒绝自动切换路线");
        if (!_paths.TryResolveExistingWorkflow(workflowPath, out var controlledWorkflowPath, out _)) throw new FileNotFoundException("Workflow is missing or outside the controlled workflow directory", workflowPath);
        workflowPath = controlledWorkflowPath;
        if (!File.Exists(workflowPath)) throw new FileNotFoundException("工作流不存在", workflowPath);
        using var inputDocument = row.Json("inputJson");
        var inputRoot = inputDocument.RootElement;
        var parameters = inputRoot.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : JsonDocument.Parse("{}").RootElement;
        if (parameters.TryGetProperty("characterLibrary", out _))
        {
            if (_characterLibrary is null) throw new AssetValidationException("人物库验证服务未就绪");
            await _characterLibrary.ValidateTaskAsync(new TaskInput
            {
                ProjectId = row.LongOrNull("projectId"), EpisodeId = row.LongOrNull("episodeId"), ShotId = row.LongOrNull("shotId"),
                TaskType = taskType, WorkflowId = row.LongOrNull("workflowId"), InputImagePath = GetString(inputRoot, "inputImagePath"), Parameters = parameters
            }, ct);
        }
        if(parameters.TryGetProperty(CharacterStoryService.Marker,out _)||parameters.TryGetProperty(CharacterWorkshopService.Marker,out _))
        {
            var declared=CharacterStoryStore.RestoreTask(inputRoot,row);
            if(parameters.TryGetProperty(CharacterStoryService.Marker,out _)){if(_characterStory is null)throw new AssetValidationException("剧情校验服务未就绪");await _characterStory.ValidateTaskAsync(declared,ct);}
            if(parameters.TryGetProperty(CharacterWorkshopService.Marker,out _)){if(_characterWorkshop is null)throw new AssetValidationException("人物定型服务未就绪");await _characterWorkshop.ValidateTaskAsync(declared,ct);}
        }
        var inputImage = await ResolvePrimaryInputAsync(row, inputRoot, GetString(inputRoot, "inputImagePath") ?? row.Text("shotInputImage"), [ArtifactPurpose.Image, ArtifactPurpose.Cover], ct);
        var originalParametersJson = parameters.GetRawText();
        var requestedParameters = parameters.Clone();
        var declaredAction = GetString(parameters, "action") ?? row.Text("shotAction");
        var requestedH3 = H3WorkflowPolicy.IsH3(ComfyUiClient.LoadWorkflow(workflowPath));
        var textToVideo = MiniMaxLocalService.IsTextToVideoWorkflow(workflowPath);
        if (textToVideo != taskType.Equals("TextToVideo", StringComparison.OrdinalIgnoreCase)
            || (textToVideo && !string.IsNullOrWhiteSpace(inputImage)))
            throw new InvalidOperationException("文生视频任务、受管工作流与无首帧输入必须一致");
        if (requestedH3 && MiniMaxLocalService.IsManagedWorkflow(workflowPath))
        {
            MiniMaxLocalService.ValidateManagedParameters(parameters, workflowPath);
            await _miniMaxLocal.EnsureWorkflowPinnedAsync(workflowPath, ct);
            await _miniMaxLocal.EnsureVerifiedAsync(ct);
        }
        if (requestedH3 && (IsFormal(row) || row.LongOrNull("shotId") is not null || row.LongOrNull("episodeId") is not null))
            throw new InvalidOperationException("H3 正式生产尚未开放：需要完成本机能力验收及模型输出许可核查");
        if (requestedH3)
        {
            MiniMaxLocalService.ValidateFrameWorkflowSelection(parameters, workflowPath);
            H3WorkflowPolicy.Validate(ComfyUiClient.LoadWorkflow(workflowPath), parameters);
        }
        WorkflowExecutionPlan? contractPlan = null;
        var slotSources = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        var slotAssets = new Dictionary<string, ResolvedAssetReference>(StringComparer.OrdinalIgnoreCase);
        if (!requestedH3)
        {
            foreach (var pair in WorkflowContractService.ReadDeclaredSlotPaths(parameters)) slotSources[pair.Key] = pair.Value;
            if (IsFormal(row))
            {
                foreach (var pair in await ResolveFormalSlotAssetsAsync(row, [ArtifactPurpose.Image, ArtifactPurpose.Cover], ct))
                {
                    slotSources[pair.Key] = pair.Value.FullPath;
                    slotAssets[pair.Key] = pair.Value;
                }
            }
            contractPlan = _contracts.Prepare(
                workflowPath,
                taskType,
                parameters,
                slotSources,
                requireProductionRoute: IsFormal(row) || row.LongOrNull("shotId") is not null || row.LongOrNull("episodeId") is not null);
        }

        var copiedSlots = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        if (contractPlan is not null)
        {
            foreach (var slot in contractPlan.Slots)
            {
                if (!slotSources.TryGetValue(slot.Role, out var source) || string.IsNullOrWhiteSpace(source))
                    throw new AssetValidationException($"工作流槽位 {slot.Role} 没有可用输入资产");
                copiedSlots[slot.Role] = await CopyInputToComfyAsync(source, taskId, ct, $"_{slot.Role}");
            }
            contractPlan = _contracts.Prepare(workflowPath, taskType, parameters, copiedSlots, requireProductionRoute: IsFormal(row) || row.LongOrNull("shotId") is not null || row.LongOrNull("episodeId") is not null);
            parameters = contractPlan.ExecutionParameters;
        }
        var slotBindings = contractPlan is null ? new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase) : await BuildSlotBindingsAsync(contractPlan, slotSources, slotAssets, ct);
        if (contractPlan is not null)
            await ValidateRetrySourceSnapshotAsync(requestedParameters, contractPlan, slotSources, slotAssets, characterGate, declaredAction, inputImage, ct);

        var loraBindings = await ResolveLoraBindingsAsync(inputRoot, parameters, ct);
        var copiedImage = requestedH3
            ? await CopyInputToComfyAsync(inputImage, taskId, ct)
            : copiedSlots.GetValueOrDefault("firstFrame");
        if (parameters.TryGetProperty("characterLibrary", out var libraryBinding)
            && !string.Equals(await _ffmpeg.Sha256Async(copiedImage, ct), libraryBinding.GetProperty("referenceSha256").GetString(), StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("人物库首帧复制后哈希不符，拒绝提交GPU生成");
        object? h3FirstFrame = null;
        foreach(var marker in new[]{CharacterStoryService.Marker,CharacterWorkshopService.Marker})
            if(requestedParameters.TryGetProperty(marker,out var binding)&&binding.TryGetProperty("inputSha256",out var expectedSha)&&expectedSha.ValueKind==JsonValueKind.String
                && !string.Equals(await _ffmpeg.Sha256Async(copiedImage,ct),expectedSha.GetString(),StringComparison.OrdinalIgnoreCase))throw new AssetValidationException("剧情/人物基准首帧复制后SHA256不一致");
        foreach(var marker in new[]{CharacterStoryService.Marker,CharacterWorkshopService.Marker})
            if(requestedParameters.TryGetProperty(marker,out var binding)&&binding.TryGetProperty("inputHashes",out var hashes))
                foreach(var slot in copiedSlots)
                {
                    if(!slotSources.TryGetValue(slot.Key,out var source)||!_paths.TryResolveExisting(source,out _,out var relative)||!hashes.TryGetProperty(relative,out var expected)
                        ||!string.Equals(await _ffmpeg.Sha256Async(slot.Value,ct),expected.GetString(),StringComparison.OrdinalIgnoreCase))throw new AssetValidationException("独立身份/造型槽位复制后SHA256不符："+slot.Key);
                }
        object? h3LastFrame = null;
        string? copiedH3LastFrame = null;
        if (requestedH3 && MiniMaxLocalService.IsManagedWorkflow(workflowPath))
        {
            var h3Frames = await _miniMaxLocal.ValidateFrameAssetsAsync(inputImage, parameters, _paths, _ffmpeg, ct);
            if (MiniMaxLocalService.IsFirstLastWorkflow(workflowPath))
            {
                var tail = h3Frames.Single(frame => frame.Role == "lastFrame");
                copiedH3LastFrame = await CopyInputToComfyAsync(tail.AssetPath, taskId, ct, "_lastFrame");
                var copiedFirstHash = await _ffmpeg.Sha256Async(copiedImage, ct);
                var copiedLastHash = await _ffmpeg.Sha256Async(copiedH3LastFrame, ct);
                if (copiedFirstHash != h3Frames.Single(frame => frame.Role == "firstFrame").Sha256 || copiedLastHash != tail.Sha256)
                    throw new InvalidOperationException("H3_FRAME_COPY_HASH_DRIFT: 首尾帧复制后SHA256不同，禁止执行");
                h3LastFrame = new { role = tail.Role, assetPath = tail.AssetPath, sha256 = tail.Sha256, width = tail.Width, height = tail.Height, targetFrameIndex = 123 };
            }
            if (!textToVideo)
            {
                var inputHash = await _ffmpeg.Sha256Async(copiedImage, ct);
                if (!ReleaseEligibilityService.IsSha256ForExport(inputHash)
                    || !_paths.TryResolveExisting(inputImage, out _, out var relativeInput))
                    throw new InvalidOperationException("H3_FIRST_FRAME_TRACE_MISSING: 首帧复制或哈希记录不完整");
                h3FirstFrame = new { role = "firstFrame", assetPath = relativeInput, sha256 = inputHash };
            }
            var frozenInput = JsonNode.Parse(inputRoot.GetRawText())!.AsObject();
            frozenInput["minimaxLocalExecution"] = JsonSerializer.SerializeToNode(new
            {
                firstFrame = h3FirstFrame,
                lastFrame = h3LastFrame,
                generationMode = MiniMaxLocalService.IsFirstLastWorkflow(workflowPath) ? "FirstLastFrameToVideo" : textToVideo ? "TextToVideo" : "ImageToVideo",
                workflowSha256 = await _ffmpeg.Sha256Async(workflowPath, ct),
                loader = _miniMaxLocal.Manifest().Loader,
                parameters
            });
            await _leases.UpdateInputAsync(RequireLease(taskId), frozenInput.ToJsonString(), ct);
        }
        var copiedReferences = new List<string>();
        if (requestedH3)
        {
            foreach (var reference in GetReferenceInputs(parameters).Take(1))
            {
                var copied = await CopyInputToComfyAsync(reference, taskId, ct, $"_reference_{copiedReferences.Count + 1}");
                if (copied is not null) copiedReferences.Add(copied);
            }
        }
        var workflow = ComfyUiClient.LoadWorkflow(workflowPath);
        var hasControlNet = HasNodeClass(workflow, "ControlNet");
        var hasIpAdapter = HasNodeClass(workflow, "IPAdapter");
        var explicitControlImages = GetControlInputs(parameters);
        if (hasControlNet && contractPlan is null && explicitControlImages.Count == 0) throw new InvalidOperationException("ControlNet workflow requires an explicit controlImages/controlImagePath pose input");
        if (hasControlNet && contractPlan is null && GetStrings(parameters, "referenceImages").Count > 0) throw new InvalidOperationException("ControlNet pose input must be separate from identity referenceImages");
        if (hasIpAdapter && string.IsNullOrWhiteSpace(copiedImage) && copiedReferences.Count == 0 && copiedSlots.Count == 0) throw new InvalidOperationException("IP-Adapter workflow requires an input or reference image");
        if (contractPlan is not null || !string.Equals(originalParametersJson, parameters.GetRawText(), StringComparison.Ordinal))
        {
            var patchedInput = JsonNode.Parse(inputRoot.GetRawText())?.AsObject();
            if (patchedInput is not null)
            {
                patchedInput["requestParameters"] = JsonNode.Parse(originalParametersJson);
                patchedInput["parameters"] = JsonNode.Parse(parameters.GetRawText());
                if (contractPlan is not null)
                {
                    patchedInput["workflowContract"] = JsonNode.Parse(JsonSerializer.Serialize(new
                    {
                        validationStatus = "Passed",
                        contractId = contractPlan.ContractId,
                        contractVersion = contractPlan.ContractVersion,
                        workflow = contractPlan.WorkflowFileName,
                        sha256 = contractPlan.WorkflowSha256,
                        workflowFileName = contractPlan.WorkflowFileName,
                        workflowSha256 = contractPlan.WorkflowSha256,
                        productionEligible = contractPlan.ProductionEligible,
                        licenseStatus = contractPlan.LicenseStatus,
                        modelFingerprints = contractPlan.ModelFingerprints,
                        modelPaths = contractPlan.ModelPaths.ToDictionary(pair => pair.Key, pair => ModelTracePath(pair.Value), StringComparer.OrdinalIgnoreCase),
                        runtimeDependencyFingerprint = contractPlan.RuntimeDependencyFingerprint
                    }));
                    patchedInput["workflowExecution"] = JsonNode.Parse(JsonSerializer.Serialize(new
                    {
                        width = contractPlan.Width,
                        height = contractPlan.Height,
                        fps = contractPlan.Fps,
                        requestedFrameCount = contractPlan.RequestedFrameCount,
                        executionLength = contractPlan.ExecutionLength,
                        guideFrameIndex = contractPlan.GuideFrameIndex,
                        slotPaths = contractPlan.SlotPaths.ToDictionary(pair => pair.Key, pair => Path.GetFileName(pair.Value), StringComparer.OrdinalIgnoreCase),
                        slotBindings,
                        modelPaths = contractPlan.ModelPaths.ToDictionary(pair => pair.Key, pair => ModelTracePath(pair.Value), StringComparer.OrdinalIgnoreCase),
                        modelFingerprints = contractPlan.ModelFingerprints,
                        action = declaredAction,
                        characterReferences = characterGate?.References.Select(reference => new
                        {
                            characterId = reference.CharacterId,
                            referenceId = reference.ReferenceId,
                            relativePath = reference.RelativePath,
                            assetVersion = reference.AssetVersion,
                            assetSha256 = reference.AssetSha256,
                            reviewStatus = reference.ReviewStatus,
                            reviewer = reference.Reviewer
                        }),
                        nodes = contractPlan.Nodes,
                        slots = contractPlan.Slots,
                        normalizations = contractPlan.Normalizations
                    }));
                }
                await _leases.UpdateInputAsync(RequireLease(taskId), patchedInput.ToJsonString(), ct);
            }
        }
        var attempt = RequireLease(taskId);
        var positive = GetString(parameters, "positive", "prompt") ?? row.Text("shotPrompt");
        var negative = GetString(parameters, "negative", "negativePrompt") ?? row.Text("shotNegativePrompt");
        if (contractPlan is not null)
        {
            await _repository.AddTaskEventAsync(
                taskId,
                row.Text("status") ?? "Running",
                row.Text("status") ?? "Running",
                "worker",
                _workerId,
                "工作流契约、输入槽位与执行规格已冻结",
                metadataJson: JsonSerializer.Serialize(new
                {
                    contractId = contractPlan.ContractId,
                    contractVersion = contractPlan.ContractVersion,
                    workflow = contractPlan.WorkflowFileName,
                    workflowSha256 = contractPlan.WorkflowSha256,
                    sha256 = contractPlan.WorkflowSha256,
                     validationStatus = "Passed",
                     modelFingerprints = contractPlan.ModelFingerprints,
                     modelPaths = contractPlan.ModelPaths.ToDictionary(pair => pair.Key, pair => ModelTracePath(pair.Value), StringComparer.OrdinalIgnoreCase),
                     runtimeDependencyFingerprint = contractPlan.RuntimeDependencyFingerprint,
                     requested = contractPlan.RequestedParameters,
                    execution = contractPlan.ExecutionParameters,
                    contractPlan.ExecutionLength,
                    contractPlan.GuideFrameIndex,
                    slots = contractPlan.Slots,
                    slotBindings,
                    normalizations = contractPlan.Normalizations
                }),
                ct: ct);
        }
        var appliedReferences = ComfyUiClient.PatchWorkflow(workflow, taskType, positive, negative, copiedImage, copiedReferences, loraBindings, parameters, $"video_studio/task_{taskId}_attempt_{attempt.AttemptNo}_{attempt.LeaseToken[..8]}", contractPlan);
        if (requestedH3 && MiniMaxLocalService.IsFirstLastWorkflow(workflowPath))
            H3WorkflowPolicy.BindCopiedFrames(workflow, parameters, copiedImage, copiedH3LastFrame);
        if (hasControlNet && appliedReferences == 0) throw new InvalidOperationException("ControlNet control image was not bound to a contract slot");
        if (requestedH3 && GetBool(parameters, "referenceRequired", false) && copiedReferences.Count == 0)
            throw new InvalidOperationException("任务要求参考图，但参考图文件不存在或未找到");
        if (row.Text("resourceClass") is not "CPU") await WaitForGpuAsync(ct);
        if (contractPlan is not null)
        {
            var modelDrift = _contracts.ValidateCurrentModelFingerprints(contractPlan);
            if (modelDrift.Count > 0)
                throw new WorkflowContractException("WORKFLOW_MODEL_RUNTIME_DRIFT", string.Join("；", modelDrift));
        }
        var before = await _comfy.CheckAsync(ct);
        var peak = before.Gpu is null ? 0 : before.Gpu.TotalMiB - before.Gpu.FreeMiB;
        var governedStory= requestedParameters.TryGetProperty(CharacterStoryService.Marker,out _)||requestedParameters.TryGetProperty(CharacterWorkshopService.Marker,out _);
        string promptId;
        if(governedStory)
        {
            var checkpointRoot=Path.Combine(_settings.DataPath,"CharacterStoryTrace",$"task_{taskId}");Directory.CreateDirectory(checkpointRoot);
            var receipt=Path.Combine(checkpointRoot,"submission.json");var intent=Path.Combine(checkpointRoot,"submission-intent.json");
            if(File.Exists(receipt))
            {
                var previous=JsonNode.Parse(await File.ReadAllTextAsync(receipt,ct))!;
                promptId=previous["promptId"]!.GetValue<string>();
                if(previous["taskId"]!.GetValue<long>()!=taskId||string.IsNullOrWhiteSpace(promptId))throw new AssetValidationException("剧情恢复检查点归属无效");
                workflow=JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(checkpointRoot,"submitted-workflow.json"),ct))!.AsObject();
                _logger.LogInformation("任务 {TaskId} 恢复既有Comfy执行 {PromptId}，不重新生成",taskId,promptId);
            }
            else if(!string.IsNullOrWhiteSpace(row.Text("comfyPromptId")))promptId=row.Text("comfyPromptId")!;
            else
            {
                if(File.Exists(intent))throw new AssetValidationException("STORY_SUBMISSION_UNCERTAIN: 已有提交意图但缺少回执，禁止重复生成；请核对原Comfy队列/历史后恢复");
                await File.WriteAllTextAsync(Path.Combine(checkpointRoot,"submitted-workflow.json"),workflow.ToJsonString(),ct);
                await using(var stream=new FileStream(intent,FileMode.CreateNew,FileAccess.Write,FileShare.None))
                {await JsonSerializer.SerializeAsync(stream,new{taskId,attemptNo=attempt.AttemptNo,submittedAt=DateTimeOffset.UtcNow},cancellationToken:ct);await stream.FlushAsync(ct);}
                promptId=await _comfy.QueueAsync(workflow,ct);
                var temporary=receipt+".tmp";await File.WriteAllTextAsync(temporary,JsonSerializer.Serialize(new{taskId,promptId,attemptNo=attempt.AttemptNo}),ct);File.Move(temporary,receipt,false);
            }
        }
        else promptId = await _comfy.QueueAsync(workflow, ct);
        await _leases.UpdatePromptAsync(RequireLease(taskId), promptId, ct);
        var history = await _comfy.WaitForHistoryAsync(promptId, snapshot =>
        {
            if (snapshot.Gpu is not null) peak = Math.Max(peak, snapshot.Gpu.TotalMiB - snapshot.Gpu.FreeMiB);
            _ = _leases.UpdateGpuAsync(RequireLease(taskId), snapshot.Gpu, peak);
        }, ct);
        var isVideo = taskType.Contains("video", StringComparison.OrdinalIgnoreCase) || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase);
        if(requestedParameters.TryGetProperty(CharacterStoryService.Marker,out _)||requestedParameters.TryGetProperty(CharacterWorkshopService.Marker,out _))
        {
            var trace=Path.Combine(_settings.DataPath,"CharacterStoryTrace",$"task_{taskId}",$"attempt_{attempt.AttemptNo}");Directory.CreateDirectory(trace);
            await File.WriteAllTextAsync(Path.Combine(trace,"comfy-history.json"),JsonSerializer.Serialize(history),ct);
            await File.WriteAllTextAsync(Path.Combine(trace,"applied-workflow.json"),JsonSerializer.Serialize(workflow),ct);
            await File.WriteAllTextAsync(Path.Combine(trace,"requested-input.json"),inputRoot.GetRawText(),ct);
        }
        var target = RequireWorkspace(taskId).FullPath;
        var outputFiles = await _comfy.DownloadOutputsAsync(history, target, $"task_{taskId}", ct);
        if (outputFiles.Count == 0) throw new InvalidOperationException("ComfyUI 完成但没有可下载的输出文件");
        var candidateIndex = GetInt(parameters, "candidateIndex") ?? 1;
        var seed = GetLong(parameters, "seed");
        foreach (var file in outputFiles)
        {
            var finalPath = file.Path;
            if (isVideo && string.Equals(Path.GetExtension(finalPath), ".webp", StringComparison.OrdinalIgnoreCase))
            {
                finalPath = Path.ChangeExtension(finalPath, ".mp4");
                await _ffmpeg.ConvertToMp4Async(file.Path, finalPath, ct, contractPlan?.Fps, preserveAudio: true);
            }
            var probe = await _ffmpeg.ProbeAsync(finalPath, ct);
            var faceStabilityPriority = GetBool(parameters, "faceStabilityPriority", false);
            var expectedDuration = contractPlan?.RequestedFrameCount is > 0
                ? (decimal)(contractPlan.RequestedFrameCount.Value / contractPlan.Fps)
                : faceStabilityPriority ? GetDecimal(parameters, "duration", row.Decimal("shotDurationSeconds", 5)) : row.Decimal("shotDurationSeconds", 5);
            var expectedWidth = contractPlan?.Width ?? (faceStabilityPriority ? GetInt(parameters, "width") ?? row.Int("shotWidth", 512) : row.Int("shotWidth", 512));
            var expectedHeight = contractPlan?.Height ?? (faceStabilityPriority ? GetInt(parameters, "height") ?? row.Int("shotHeight", 320) : row.Int("shotHeight", 320));
            if (requestedH3)
            {
                var h3Inputs = workflow.Select(pair => pair.Value).OfType<JsonObject>()
                    .First(node => node["class_type"]?.GetValue<string>() == "MiniMaxH3ImageToVideo")["inputs"]!.AsObject();
                expectedWidth = h3Inputs["width"]!.GetValue<int>();
                expectedHeight = h3Inputs["height"]!.GetValue<int>();
                if (MiniMaxLocalService.IsNative1080Workflow(workflowPath))
                    expectedHeight = 1080;
                expectedDuration = 124m / 24m;
            }
            QualityCheckResult qc = isVideo
                ? await _quality.CheckVideoAsync(finalPath, expectedDuration, expectedWidth, expectedHeight, requestedH3 ? 24 : (decimal)(contractPlan?.Fps ?? (double)row.Decimal("shotFps", 24)), ct, requestedH3 ? 124 : contractPlan?.RequestedFrameCount)
                : await _quality.CheckImageAsync(finalPath, row.Int("shotWidth", 512), row.Int("shotHeight", 320), ct);
            var outputHash = await _ffmpeg.Sha256Async(finalPath, ct);
            if (contractPlan is not null)
            {
                if (!ReleaseEligibilityService.IsSha256ForExport(outputHash)) throw new InvalidOperationException("OUTPUT_HASH_MISSING: 无法登记输出文件哈希");
                qc.Metrics["workflowContract"] = new
                {
                    validationStatus = qc.Passed ? "Passed" : "Failed",
                    contractId = contractPlan.ContractId,
                    contractVersion = contractPlan.ContractVersion,
                    workflow = contractPlan.WorkflowFileName,
                    sha256 = contractPlan.WorkflowSha256,
                    workflowFileName = contractPlan.WorkflowFileName,
                     workflowSha256 = contractPlan.WorkflowSha256,
                     licenseStatus = contractPlan.LicenseStatus,
                     modelFingerprints = contractPlan.ModelFingerprints,
                     modelPaths = contractPlan.ModelPaths.ToDictionary(pair => pair.Key, pair => ModelTracePath(pair.Value), StringComparer.OrdinalIgnoreCase),
                     runtimeDependencyFingerprint = contractPlan.RuntimeDependencyFingerprint,
                     action = declaredAction,
                     characterReferences = characterGate?.References.Select(reference => new
                     {
                         characterId = reference.CharacterId,
                         referenceId = reference.ReferenceId,
                         relativePath = reference.RelativePath,
                         assetVersion = reference.AssetVersion,
                         assetSha256 = reference.AssetSha256,
                         reviewStatus = reference.ReviewStatus,
                         reviewer = reference.Reviewer
                     }),
                     requestedFrameCount = contractPlan.RequestedFrameCount,
                    executionLength = contractPlan.ExecutionLength,
                    guideFrameIndex = contractPlan.GuideFrameIndex
                };
                qc.Metrics["slotBindings"] = slotBindings;
                qc.Metrics["outputProbe"] = probe is null ? null : new
                {
                    status = qc.Passed ? "Passed" : "Failed",
                    fileSha256 = outputHash,
                    probe.Width,
                    probe.Height,
                    probe.DurationSeconds,
                    probe.Fps,
                    probe.FrameCount,
                    probe.HasAudio,
                    probe.AudioDurationSeconds,
                    probe.Codec
                };
            }
            if (!qc.Passed) throw new InvalidOperationException($"{qc.ErrorType}: output quality validation failed");
            if (requestedH3)
            {
                if (probe?.HasAudio != true) throw new InvalidOperationException("H3_NATIVE_AUDIO_MISSING: 本地声画生成没有可解码音轨");
                qc.Metrics["nativeAudio"] = new { present = true, durationSeconds = probe.AudioDurationSeconds, reviewStatus = "NeedReview" };
                qc.Metrics["contentReview"] = "NeedReview";
                if (MiniMaxLocalService.IsNative1080Workflow(workflowPath))
                    qc.Metrics["nativeCanvas"] = new { width = 1920, height = 1088, cropX = 0, cropY = 4, deliveryWidth = 1920, deliveryHeight = 1080, spatialUpscale = false };
                if (MiniMaxLocalService.IsManagedWorkflow(workflowPath))
                    qc.Metrics["minimaxLocal"] = new
                    {
                        provider = "MiniMaxLocal", route = _miniMaxLocal.Manifest().Route,
                        workflowSha256 = await _ffmpeg.Sha256Async(workflowPath, ct),
                        firstFrame = h3FirstFrame, lastFrame = h3LastFrame, outputSha256 = outputHash,
                        loader = _miniMaxLocal.Manifest().Loader,
                        models = _miniMaxLocal.Manifest().Assets.Select(asset => new { asset.Role, asset.File, asset.Repository, asset.Revision, asset.Sha256 }),
                        productionEligible = false, licenseReview = "NeedReview"
                    };
                if (GetBool(parameters, "extractNativeAudio", false))
                {
                    var audioPath = Path.Combine(target, $"native_audio_task_{taskId}.wav");
                    await _ffmpeg.ExtractAudioAsync(finalPath, audioPath, ct);
                    var audio = await PublishArtifactAsync(row, ArtifactPurpose.Audio, audioPath, Path.GetFileName(audioPath), ct);
                    await _repository.UpdateResultQualityAsync(taskId, audio.FullPath, qc.Score, JsonSerializer.Serialize(new { provider = "MiniMaxLocal", contentReview = "NeedReview", sourceVideoSha256 = outputHash }), ct);
                    qc.Metrics["nativeAudioAsset"] = audio.RelativePath;
                }
            }
            var published = await PublishArtifactAsync(row, isVideo ? ArtifactPurpose.Video : ArtifactPurpose.Image, finalPath, Path.GetFileName(finalPath), ct);
            finalPath = published.FullPath;
            var resultScore = qc.Score;
            if (row.LongOrNull("shotId") is { } shotId)
            {
                if (!qc.Passed) throw new InvalidOperationException($"{qc.ErrorType}: {(qc.Metrics.TryGetValue("message", out var msg) ? msg : "输出质量检查失败")}");
                if (isVideo)
                {
                    var referencePath = (await _repository.ShotReferencePathsAsync(shotId, ct)).FirstOrDefault();
                    var face = await _faceQuality.AnalyzeVideoAsync(finalPath, referencePath, ct);
                    qc.Metrics["faceQuality"] = face.Metrics;
                    qc.Metrics["faceIssues"] = face.Issues;
                    var combinedScore = Math.Min(qc.Score, face.Score);
                    resultScore = combinedScore;
                    if (GetBool(parameters, "qaRetry", false))
                        await _repository.UpdateQualityRepairRunAsync(taskId, face.Rejected ? "Rejected" : "NeedReview", JsonSerializer.SerializeToDocument(qc.Metrics).RootElement.Clone(), ct);
                    await _repository.UpdateShotVideoAsync(shotId, finalPath, probe, JsonSerializer.Serialize(qc.Metrics), combinedScore, "VideoReview", ct);
                    var qaRetry = string.Equals(row.Text("stage"), "QA-Retry", StringComparison.OrdinalIgnoreCase);
                    if (!face.Rejected && (qaRetry || string.Equals(row.Text("episodeProductionMode"), "AutoProduction", StringComparison.OrdinalIgnoreCase)))
                        await QueueEnhanceAsync(row, shotId, taskId, finalPath, ct, qaRetry, parameters);
                    if (face.Rejected)
                        await _repository.LogAsync("face.video.rejected", $"Shot {shotId} 视频脸部代理检查未通过：{string.Join("；", face.Issues)}", taskId, "Warning", ct);
                }
                else
                {
                    var referencePath = (await _repository.ShotReferencePathsAsync(shotId, ct)).FirstOrDefault();
                    var portraitPreferred = row.Int("shotHeight", 320) >= row.Int("shotWidth", 512);
                    var face = await _faceQuality.AnalyzeImageAsync(finalPath, referencePath, portraitPreferred, ct);
                    qc.Metrics["faceQuality"] = face.Metrics;
                    qc.Metrics["faceIssues"] = face.Issues;
                    var candidateStatus = face.Rejected ? "Rejected" : "NeedReview";
                    var candidateScore = Math.Round(Math.Min(qc.Score, face.Score), 2);
                    resultScore = candidateScore;
                    await _repository.AddCandidateAsync(shotId, taskId, finalPath, candidateIndex, seed, candidateStatus, candidateScore, JsonSerializer.Serialize(qc.Metrics), ct);
                    await _repository.UpdateShotStatusAsync(shotId, "ImageReview", ct);
                    if (face.Rejected)
                        await _repository.LogAsync("face.keyframe.rejected", $"Shot {shotId} 候选 {candidateIndex} 未通过脸部代理检查：{string.Join("；", face.Issues)}", taskId, "Warning", ct);
                    else
                        await AutoAdvanceAsync(row, shotId, taskId, ct);
                }
            }
            else if (isVideo)
            {
                // Quality-lab tasks deliberately omit shotId so they cannot mutate
                // production shot state. When a reference is supplied explicitly,
                // still run the same face/temporal proxy and persist it in qc_json.
                var qualityReferencePath = GetString(parameters, "qualityReferenceImagePath")
                    ?? GetReferenceInputs(parameters).FirstOrDefault();
                if (_paths.TryResolveExisting(qualityReferencePath, out var qualityReferenceFullPath, out _))
                {
                    var face = await _faceQuality.AnalyzeVideoAsync(finalPath, qualityReferenceFullPath, ct);
                    qc.Metrics["faceQuality"] = face.Metrics;
                    qc.Metrics["faceIssues"] = face.Issues;
                    resultScore = Math.Min(qc.Score, face.Score);
                }
            }
            await _repository.UpdateResultQualityAsync(taskId, finalPath, resultScore, JsonSerializer.Serialize(qc.Metrics), ct);
        }
        await _leases.UpdateGpuAsync(RequireLease(taskId), (await _comfy.CheckAsync(ct)).Gpu, peak, ct);
    }

    private async Task<JsonElement> NormalizeVideoParametersAsync(JsonElement parameters, string taskType, string? inputImage, long taskId, CancellationToken ct)
    {
        var isVideo = taskType.Contains("video", StringComparison.OrdinalIgnoreCase) || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase);
        if (!isVideo || !_paths.TryResolveExisting(inputImage, out var inputImageFullPath, out _)) return parameters;

        var probe = await _ffmpeg.ProbeAsync(inputImageFullPath, ct);
        if (probe?.Width is not > 0 || probe.Height is not > 0) return parameters;

        var root = parameters.ValueKind == JsonValueKind.Object
            ? JsonNode.Parse(parameters.GetRawText())?.AsObject()
            : new JsonObject();
        if (root is null) return parameters;

        var sourceAspect = (double)probe.Width.Value / probe.Height.Value;
        var target = sourceAspect <= .9 ? (Width: 320, Height: 416) : sourceAspect >= 1.35 ? (Width: 512, Height: 320) : (Width: 384, Height: 384);
        var currentWidth = GetInt(parameters, "width");
        var currentHeight = GetInt(parameters, "height");
        var currentAspect = currentWidth is > 0 && currentHeight is > 0 ? (double)currentWidth.Value / currentHeight.Value : 0;
        var changed = false;
        if (currentWidth is null || currentHeight is null || Math.Abs(Math.Log(Math.Max(.01, currentAspect) / ((double)target.Width / target.Height))) > .1)
        {
            root["width"] = target.Width;
            root["height"] = target.Height;
            changed = true;
        }

        var requestedFrames = GetInt(parameters, "frames") ?? GetInt(parameters, "length");
        var allowLongVideo = GetBool(parameters, "allowLongVideo", false);
        var faceStabilityPriority = GetBool(parameters, "faceStabilityPriority", false);
        var portraitDraft = faceStabilityPriority && target.Height > target.Width && !allowLongVideo;
        if ((portraitDraft && requestedFrames is > 73) || (requestedFrames is > 121 && !allowLongVideo))
        {
            var safeFrames = target.Height > target.Width ? 73 : 121;
            root["frames"] = safeFrames;
            var fps = Math.Max(1, GetDecimal(parameters, "fps", 24));
            root["duration"] = Math.Round(safeFrames / fps, 3);
            changed = true;
        }

        if (!changed) return parameters;
        await _repository.LogAsync("video.parameters.normalized", $"任务 {taskId} 已按首帧画幅和 RTX 4070 稳定档修正 I2V 参数：{target.Width}x{target.Height}，帧数 {root["frames"]?.GetValue<int?>() ?? requestedFrames}", taskId, "Info", ct);
        return JsonDocument.Parse(root.ToJsonString()).RootElement.Clone();
    }

    private async Task QueueEnhanceAsync(IReadOnlyDictionary<string, object?> row, long shotId, long dependencyTaskId, string inputPath, CancellationToken ct, bool qaRetry = false, JsonElement? retryParameters = null)
    {
        // QA 回炉必须拥有自己的后处理链。原始视频的 Enhance 可能仍在队列中，
        // 不能因此吞掉回炉输出，否则新 Seed 的视频不会进入下一轮 QA。
        if (!qaRetry && await _repository.HasActiveTaskForShotAsync(shotId, "Enhance", ct)) return;
        var deliveryEpisode = row.LongOrNull("episodeId") is { } deliveryEpisodeId
            ? (await _repository.EpisodeAsync(deliveryEpisodeId, ct)).FirstOrDefault() : null;
        var payload = new Dictionary<string, object?>
        {
            ["inputImagePath"] = inputPath,
            ["fps"] = deliveryEpisode?.Int("outputFps", 24) ?? 24,
            ["width"] = deliveryEpisode?.Int("outputWidth", 1280) ?? 1280,
            ["height"] = deliveryEpisode?.Int("outputHeight", 720) ?? 720,
            ["deflicker"] = false,
            ["interpolate"] = false,
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
            await _repository.LogAsync("qa.retry.enhance", $"Shot {shotId} QA 回炉增强已排队；回炉次数 {GetInt(parameters, "retryCount") ?? 0}，输入资产 {Path.GetFileName(inputPath)}", taskId, "Info", ct);
        await _repository.UpdateShotStatusAsync(shotId, "PostProcessing", ct);
        Enqueue(taskId);
    }

    private async Task AutoAdvanceAudioAsync(IReadOnlyDictionary<string, object?> row, long shotId, CancellationToken ct)
    {
        if (!string.Equals(row.Text("episodeProductionMode"), "AutoProduction", StringComparison.OrdinalIgnoreCase)) return;
        var shot = (await _repository.QueryShotAsync(shotId, ct)).FirstOrDefault();
        if (shot is null) return;
        if (string.Equals(shot.Text("audioStatus"), "Completed", StringComparison.OrdinalIgnoreCase)) return;
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
                var instruction = Qwen3TtsService.IsQwen(voiceId) ? shot.Text("emotion") ?? "" : "";
                var parameters = JsonSerializer.SerializeToDocument(new { text = line.Text, voiceId, speed, pitch, instruction, engineVersion = _tts.EngineIdentity(voiceId), outputName = $"shot_{shotId}_{audioTasks.Count + 1}.wav" }).RootElement.Clone();
                var taskId = await _repository.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = shotId, TaskType = "Audio", ResourceClass = Qwen3TtsService.ResourceClass(voiceId), Stage = "TTS", MaxRetries = 0, IdempotencyKey = $"auto-audio:{shotId}:{StableTaskKey(line.Text, voiceId, speed.ToString(), pitch.ToString(), instruction, _tts.EngineIdentity(voiceId))}", Parameters = parameters }, ct);
                audioTasks.Add(taskId); Enqueue(taskId);
            }
            await _repository.UpdateShotStatusAsync(shotId, "AudioGenerating", ct);
        }
        var episodeId = shot.LongOrNull("episodeId");
        if (episodeId is { } episode && !await _repository.HasActiveTaskForEpisodeAsync(episode, "Subtitles", ct))
        {
            var subtitleTask = await _repository.CreateTaskAsync(new TaskInput { EpisodeId = episode, TaskType = "Subtitles", ResourceClass = "CPU", Stage = "Subtitle", MaxRetries = 1, IdempotencyKey = $"auto-subtitles:{episode}", Parameters = JsonSerializer.SerializeToDocument(new { episodeId = episode }).RootElement.Clone() }, ct);
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
        var qualityGate = await EpisodeQualityGateEvaluator.EvaluateAsync(episode, shots, _repository, _ffmpeg, _paths, ct);
        if (!qualityGate.FormalReady)
        {
            await _repository.LogAsync("episode.render.gate", $"Episode {id} 自动合成已暂停：{string.Join("；", qualityGate.FormalBlockedReasons)}", null, "Info", ct);
            return;
        }
        var files = qualityGate.Sources.Select(x => x.FinalVideoPath).Where(x => !string.IsNullOrWhiteSpace(x) && File.Exists(x)).Cast<string>().ToArray();
        if (files.Length != shots.Count) return;
        var sourceSnapshot = shots.Select(x => new { shotId = x.Long("id"), shotNumber = x.Int("shotNumber"), title = x.Text("title") ?? $"镜头 {x.Int("shotNumber")}", path = x.Text("finalVideoPath") ?? x.Text("videoPath") ?? x.Text("resultPath"), durationSeconds = x.Decimal("durationSeconds", 5), ready = true }).ToArray();
        var starts = new Dictionary<long, double>(); var cursor = 0d;
        foreach (var shot in shots) { starts[shot.Long("id")] = cursor; cursor += Math.Max(1, Convert.ToDouble(shot.Decimal("durationSeconds", 5))); }
        var audioTracks = new List<object>();
        var voiceVolume = (double)episode.Decimal("voiceVolume", 1); var bgmVolume = (double)episode.Decimal("bgmVolume", .18m); var sfxVolume = (double)episode.Decimal("sfxVolume", .6m);
        foreach (var audio in await _repository.EpisodeAudioResultsAsync(id, ct))
        {
            var path = audio.Text("path"); if (!_paths.TryResolveExisting(path, out var fullPath, out _)) continue;
            var start = audio.LongOrNull("shotId") is { } shotId && starts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
            audioTracks.Add(new { path = fullPath, volume = voiceVolume, startSeconds = start });
        }
        foreach (var effect in await _repository.EpisodeSoundEffectsAsync(id, ct))
        {
            var path = effect.Text("path"); if (!_paths.TryResolveExisting(path, out var fullPath, out _)) continue;
            var start = effect.LongOrNull("shotId") is { } shotId && starts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
            audioTracks.Add(new { path = fullPath, volume = Math.Clamp((double)effect.Decimal("volume", .6m) * sfxVolume, .05, 2), startSeconds = start + (double)effect.Decimal("startSeconds", 0) });
        }
        foreach (var bgm in await _repository.EpisodeBgmAsync(id, ct))
        {
            var path = bgm.Text("path"); if (!_paths.TryResolveExisting(path, out var fullPath, out _)) continue;
            audioTracks.Add(new { path = fullPath, volume = Math.Clamp((double)bgm.Decimal("volume", .18m) * bgmVolume, .05, 2), startSeconds = 0d });
        }
        var subtitlePath = _paths.TryResolveExisting(episode.Text("subtitlePath"), out var subtitleFullPath, out _) ? subtitleFullPath : null;
        var renderVersion = (await _repository.EpisodeRenderHistoryAsync(id, ct)).Count + 1;
        var parameters = JsonSerializer.SerializeToDocument(new { files, sourceSnapshot, renderVersion, preview = false, renderMode = "Formal", outputName = $"{episode.Text("name") ?? "Episode"}_{episode.Int("episodeNumber", 1):000}_V{renderVersion:00}.mp4", targetWidth = episode.Int("outputWidth", 1920), targetHeight = episode.Int("outputHeight", 1080), targetFps = episode.Int("outputFps", 30), subtitlePath, audioTracks }).RootElement.Clone();
        var taskId = await _repository.CreateTaskAsync(new TaskInput { ProjectId = episode.LongOrNull("projectId"), EpisodeId = id, TaskType = "EpisodeRender", ResourceClass = "CPU", Stage = "Episode", MaxRetries = 1, IdempotencyKey = $"auto-render:{id}:v{renderVersion}", Parameters = parameters }, ct);
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
        if (shot is null || !_paths.TryResolveExisting(path, out var selectedPath, out _)) return;
        var workflowId = shot.LongOrNull("workflowId");
        if (workflowId is null)
        {
            await _repository.LogAsync("production.auto.blocked", $"Shot {shotId} 没有显式 I2V 工作流路线，未按参考图数量自动选择模型", dependencyTaskId, "Warning", ct);
            return;
        }
        var workflowRow = (await _repository.WorkflowsAsync(ct)).FirstOrDefault(x => x.LongOrNull("id") == workflowId);
        var workflowFile = Path.GetFileName(workflowRow?.Text("path") ?? "");
        if (workflowRow is null || !string.Equals(workflowRow.Text("workflowType"), "ImageToVideo", StringComparison.OrdinalIgnoreCase))
        {
            await _repository.LogAsync("production.auto.blocked", $"Shot {shotId} 的工作流未明确登记为 I2V，未静默切换路线", dependencyTaskId, "Warning", ct);
            return;
        }
        if (!_paths.TryResolveExistingWorkflow(workflowRow.Text("path"), out var controlledWorkflowPath, out _)) return;
        var contract = _contracts.Find(controlledWorkflowPath, workflowFile);
        if (contract is null || !contract.ProductionEligible) throw new WorkflowContractException("WORKFLOW_EXPERIMENTAL", $"Shot {shotId} 的 I2V 路线未通过生产契约");
        var frames = contract.Media.OutputFrames.FirstOrDefault();
        var fps = (decimal)contract.Media.NativeFps;
        var width = contract.Media.DefaultWidth;
        var height = contract.Media.DefaultHeight;
        var duration = Math.Round(frames / fps, 3);
        var slots = new JsonObject { ["firstFrame"] = selectedPath };
        if (contract.Media.RequiresGuide) slots["guideFrame"] = selectedPath;
        var parametersObject = new JsonObject
        {
            ["positive"] = shot.Text("prompt"),
            ["negative"] = shot.Text("negativePrompt"),
            ["inputSlots"] = slots,
            ["referenceRequired"] = CharacterReferenceGateService.ReadCharacterIds(shot.Text("characterIdsJson")).Count > 0,
            ["workflowVersion"] = workflowFile,
            ["width"] = width,
            ["height"] = height,
            ["frames"] = frames,
            ["fps"] = (double)fps,
            ["duration"] = (double)duration,
            ["cameraMotion"] = shot.Text("cameraMotion"),
            ["action"] = shot.Text("action")
        };
        if (shot.LongOrNull("seed") is { } seed) parametersObject["seed"] = seed;
        using var parametersDocument = JsonDocument.Parse(parametersObject.ToJsonString());
        _contracts.Prepare(controlledWorkflowPath, "ImageToVideo", parametersDocument.RootElement, requireProductionRoute: true);
        var parameters = parametersDocument.RootElement.Clone();
        var taskId = await _repository.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = shotId, TaskType = "ImageToVideo", WorkflowId = workflowId, InputImagePath = selectedPath, MaxRetries = 2, Stage = "I2V", DependencyTaskId = dependencyTaskId, Parameters = parameters }, ct);
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
        var retryReason = string.Join("; ", evaluation.Issues.Select(issue => $"{issue.IssueType}:{issue.Description}"));
        if (evaluation.Status == "Rejected" && evaluation.ShouldRetry && autoRetry && await QueueQaRetryAsync(shot, preset.MaxAutoRetries, ct, evaluation.Status, evaluation.Score, retryReason))
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
        var taskId = row.Long("id");
        using var document = row.Json("inputJson");
        var root = document.RootElement.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : document.RootElement;
        var input = JsonSerializer.Deserialize<QaExportInput>(root.GetRawText()) ?? new QaExportInput();
        var candidateId = GetLong(root, "candidateId") ?? input.CandidateId ?? throw new WorkflowContractException("RELEASE_CANDIDATE_REQUIRED", "QAExport 必须绑定 candidateId");
        var candidateVersion = GetInt(root, "candidateVersion") ?? throw new WorkflowContractException("RELEASE_CANDIDATE_VERSION_REQUIRED", "QAExport 缺少候选包版本");
        var candidateSnapshotSha256 = GetString(root, "candidateSnapshotSha256") ?? throw new WorkflowContractException("RELEASE_CANDIDATE_SNAPSHOT_REQUIRED", "QAExport 缺少候选包快照哈希");
        var candidate = await _candidates.GetAsync(candidateId, episodeId, ct) ?? throw new WorkflowContractException("RELEASE_CANDIDATE_NOT_FOUND", "指定的发布候选包不存在或不属于当前 Episode");
        if (!ReleaseCandidatePolicy.VersionAndSnapshotMatch(candidate, candidateVersion, candidateSnapshotSha256))
            throw new WorkflowContractException("RELEASE_CANDIDATE_VERSION_DRIFT", "队列任务中的候选包版本或快照哈希已漂移");
        var startValidation = await _release.ValidateCandidateForExportAsync(candidate, episodeId, _repository, _ffmpeg, _paths, ct);
        if (!startValidation.Valid)
        {
            if (startValidation.ShouldExpire) await _candidates.MarkExpiredAsync(candidate.Id, startValidation.Reason, ct);
            throw new WorkflowContractException("RELEASE_CANDIDATE_STALE", startValidation.Reason);
        }
        var prepared = await _qa.PrepareMasterAsync(episodeId, input, candidate.SourceManifest, candidate.Id, candidate.Version, candidate.SourceManifestSha256, RequireWorkspace(taskId).FullPath, ct);
        var finalValidation = await _release.ValidateCandidateForExportAsync(candidate, episodeId, _repository, _ffmpeg, _paths, ct);
        if (!finalValidation.Valid)
        {
            if (finalValidation.ShouldExpire) await _candidates.MarkExpiredAsync(candidate.Id, finalValidation.Reason, ct);
            throw new WorkflowContractException("RELEASE_CANDIDATE_STALE", finalValidation.Reason);
        }
        await EnsureCandidateArtifactHashAsync(prepared.MasterPath, candidate.SourceManifest.EpisodeOutput?.Sha256, "Master", ct);
        var master = await PublishArtifactAsync(row, ArtifactPurpose.Master, prepared.MasterPath, Path.GetFileName(prepared.MasterPath), ct);
        EnsurePublishedCandidateHash(master, candidate.SourceManifest.EpisodeOutput?.Sha256, "Master");
        PublishedArtifact? subtitle = null;
        PublishedArtifact? cover = null;
        if (!string.IsNullOrWhiteSpace(prepared.SubtitlePath))
        {
            await EnsureCandidateArtifactHashAsync(prepared.SubtitlePath, candidate.SourceManifest.Subtitle?.Sha256, "字幕", ct);
            subtitle = await PublishArtifactAsync(row, ArtifactPurpose.Subtitle, prepared.SubtitlePath, Path.GetFileName(prepared.SubtitlePath), ct);
            EnsurePublishedCandidateHash(subtitle, candidate.SourceManifest.Subtitle?.Sha256, "字幕");
        }
        if (!string.IsNullOrWhiteSpace(prepared.CoverPath))
        {
            await EnsureCandidateArtifactHashAsync(prepared.CoverPath, candidate.SourceManifest.Cover?.Sha256, "封面", ct);
            cover = await PublishArtifactAsync(row, ArtifactPurpose.Cover, prepared.CoverPath, Path.GetFileName(prepared.CoverPath), ct);
            EnsurePublishedCandidateHash(cover, candidate.SourceManifest.Cover?.Sha256, "封面");
        }
        var postPublishCandidate = await _candidates.GetAsync(candidateId, episodeId, ct);
        if (postPublishCandidate is null || !ReleaseCandidatePolicy.VersionAndSnapshotMatch(postPublishCandidate, candidateVersion, candidateSnapshotSha256))
        {
            await _candidates.MarkExpiredAsync(candidateId, "导出落盘期间候选包版本或来源快照发生变化", ct);
            throw new WorkflowContractException("RELEASE_CANDIDATE_VERSION_DRIFT", "导出落盘期间候选包版本或快照哈希已漂移");
        }
        var postPublishValidation = await _release.ValidateCandidateForExportAsync(postPublishCandidate, episodeId, _repository, _ffmpeg, _paths, ct);
        if (!postPublishValidation.Valid)
        {
            if (postPublishValidation.ShouldExpire) await _candidates.MarkExpiredAsync(candidateId, postPublishValidation.Reason, ct);
            throw new WorkflowContractException("RELEASE_CANDIDATE_STALE", postPublishValidation.Reason);
        }
        await EnsureCandidateArtifactHashAsync(master.FullPath, postPublishCandidate.SourceManifest.EpisodeOutput?.Sha256, "发布后的 Master", ct);
        if (subtitle is not null) await EnsureCandidateArtifactHashAsync(subtitle.FullPath, postPublishCandidate.SourceManifest.Subtitle?.Sha256, "发布后的字幕", ct);
        if (cover is not null) await EnsureCandidateArtifactHashAsync(cover.FullPath, postPublishCandidate.SourceManifest.Cover?.Sha256, "发布后的封面", ct);
        var markdown = await PublishArtifactAsync(row, ArtifactPurpose.QaReport, prepared.ReportPath, Path.GetFileName(prepared.ReportPath), ct);
        var json = await PublishArtifactAsync(row, ArtifactPurpose.QaReport, prepared.ReportJsonPath, Path.GetFileName(prepared.ReportJsonPath), ct);
        AfterSuccess(taskId, postCt => _repository.UpdateEpisodeReleaseAsync(episodeId, master.FullPath, cover?.FullPath, markdown.FullPath, json.FullPath, postCt));
    }

    private async Task EnsureCandidateArtifactHashAsync(string path, string? expectedHash, string displayName, CancellationToken ct)
    {
        var actualHash = await _ffmpeg.Sha256Async(path, ct);
        if (!ReleaseEligibilityService.IsSha256ForExport(expectedHash) || !string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RELEASE_CANDIDATE_ARTIFACT_DRIFT", $"{displayName}落盘前哈希与候选包不一致");
    }

    private static void EnsurePublishedCandidateHash(PublishedArtifact artifact, string? expectedHash, string displayName)
    {
        if (!ReleaseEligibilityService.IsSha256ForExport(expectedHash) || !string.Equals(artifact.Sha256, expectedHash, StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RELEASE_CANDIDATE_ARTIFACT_DRIFT", $"{displayName}发布后的哈希与候选包不一致");
    }

    public async Task<bool> QueueQaRetryAsync(long shotId, int maxRetries, CancellationToken ct = default)
    {
        var shot = (await _repository.QaShotAsync(shotId, ct)).FirstOrDefault();
        return shot is not null && await QueueQaRetryAsync(shot, maxRetries, ct);
    }

    private async Task<bool> QueueQaRetryAsync(IReadOnlyDictionary<string, object?> shot, int maxRetries, CancellationToken ct, string? previousStatusOverride = null, decimal? previousScoreOverride = null, string? failureReasonOverride = null)
    {
        var shotId = shot.LongOrNull("id");
        if (shotId is null) return false;
        var original = await _repository.LatestVideoTaskForShotAsync(shotId.Value, ct);
        if (original is null) return false;
        using var originalDocument = original.Json("inputJson");
        var originalRoot = originalDocument.RootElement;
        var originalParameters = originalRoot.TryGetProperty("requestParameters", out var requestParameterElement) && requestParameterElement.ValueKind == JsonValueKind.Object
            ? requestParameterElement.Clone()
            : originalRoot.TryGetProperty("parameters", out var originalParameterElement) && originalParameterElement.ValueKind == JsonValueKind.Object
                ? originalParameterElement.Clone()
            : JsonSerializer.SerializeToElement(new { });
        if (GetBool(originalParameters, "qaRetry", false) && original.Text("status") is "Pending" or "Running") return true;
        var workflowFile = GetString(originalParameters, "workflowVersion") ?? Path.GetFileName(original.Text("workflowPath") ?? "");
        if (string.IsNullOrWhiteSpace(workflowFile)) throw new WorkflowContractException("RETRY_ROUTE_UNKNOWN", "原任务没有可继承的工作流路线，已阻止自动重试");
        var workflowId = original.LongOrNull("workflowId") ?? await FindWorkflowIdAsync(workflowFile, ct)
            ?? throw new WorkflowContractException("WORKFLOW_RECORD_MISSING", $"数据库未登记原任务路线 {workflowFile}");
        var originalTaskType = original.Text("taskType") ?? "ImageToVideo";
        if (!originalTaskType.Contains("video", StringComparison.OrdinalIgnoreCase) && !originalTaskType.Contains("i2v", StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RETRY_TASK_TYPE_INVALID", $"原任务类型 {originalTaskType} 不是视频任务，已阻止自动重试");
        var workflowPath = original.Text("workflowPath") ?? Path.Combine(_settings.WorkflowsPath, workflowFile);
        if (!_paths.TryResolveExistingWorkflow(workflowPath, out var controlledWorkflowPath, out _))
            throw new WorkflowContractException("RETRY_ROUTE_UNCONTROLLED", $"原任务路线不在受控工作流目录：{workflowFile}");
        var originalSlotSources = WorkflowContractService.ReadDeclaredSlotPaths(originalParameters)
            .ToDictionary(pair => pair.Key, pair => (string?)pair.Value, StringComparer.OrdinalIgnoreCase);
        var originalSlotAssets = new Dictionary<string, ResolvedAssetReference>(StringComparer.OrdinalIgnoreCase);
        if (IsFormal(original))
        {
            foreach (var pair in await ResolveFormalSlotAssetsAsync(original, [ArtifactPurpose.Image, ArtifactPurpose.Cover], ct))
            {
                originalSlotSources[pair.Key] = pair.Value.FullPath;
                originalSlotAssets[pair.Key] = pair.Value;
            }
        }
        var originalPlan = _contracts.Prepare(controlledWorkflowPath, originalTaskType, originalParameters, originalSlotSources, requireProductionRoute: true);
        if (!TryGetObject(originalRoot, "workflowContract", out var originalContractTrace)
            || !TryGetObject(originalRoot, "workflowExecution", out var originalExecutionTrace))
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_MISSING", "原任务没有完整的工作流执行快照，无法安全继承路线和来源；请人工选择并重新审核");

        var originalAction = GetString(originalParameters, "action") ?? GetString(originalExecutionTrace, "action");
        if (string.IsNullOrWhiteSpace(originalAction))
            throw new WorkflowContractException("RETRY_ACTION_TRACE_MISSING", "原任务没有冻结的动作目标，已阻止自动重试");
        var inputImage = GetString(originalRoot, "inputImagePath") ?? GetString(originalParameters, "inputImagePath") ?? originalSlotSources.GetValueOrDefault("firstFrame") ?? GetSlotPath(originalParameters, "firstFrame") ?? GetSnapshotSlotPath(originalExecutionTrace, "firstFrame");
        if (!_paths.TryResolveExisting(inputImage, out var inputImageFullPath, out _))
            throw new WorkflowContractException("RETRY_INPUT_MISSING", "原任务的首帧来源不存在，已阻止自动重试");
        var modelDrift = _contracts.ValidateCurrentModelFingerprints(originalPlan);
        if (modelDrift.Count > 0)
            throw new WorkflowContractException("RETRY_SOURCE_DRIFT", string.Join("；", modelDrift));
        var characterGate = (CharacterReferenceGateService.ReadCharacterIds(shot.Text("characterIdsJson")).Count > 0)
            ? await _characterReferences.CheckShotAsync(shotId.Value, ct)
            : null;
        if (characterGate is not null && !characterGate.Passed)
            throw new WorkflowContractException("REFERENCE_NOT_APPROVED", string.Join("；", characterGate.Issues));
        var retrySourceSnapshot = await BuildRetrySourceSnapshotAsync(
            original.Long("id"),
            originalContractTrace,
            originalExecutionTrace,
            originalPlan,
            originalSlotSources,
            originalSlotAssets,
            characterGate,
            originalAction,
            inputImageFullPath,
            ct);

        var previousStatus = previousStatusOverride ?? shot.Text("qaStatus") ?? "Rejected";
        var previousScore = previousScoreOverride ?? shot.Decimal("qaScore", 0);
        var retryCount = shot.Int("qaRetryCount", 0) + 1;
        var retryReason = string.IsNullOrWhiteSpace(failureReasonOverride) ? ReadRetryReason(shot) : failureReasonOverride.Trim();
        var retryParameters = JsonNode.Parse(originalParameters.GetRawText())?.AsObject() ?? new JsonObject();
        var changedParameters = new JsonObject();
        switch (QaRetryPolicy.SelectTarget(retryReason))
        {
            case QaRetryParameterTarget.Seed when TryGetLong(originalParameters, "seed", out var originalSeed):
            {
                var retrySeed = originalSeed == 899999999 ? 1 : originalSeed + 1;
                retryParameters["seed"] = retrySeed;
                changedParameters["seed"] = retrySeed;
                break;
            }
            case QaRetryParameterTarget.ReferenceStrength when TryGetDouble(originalParameters, "referenceStrength", out var originalStrength):
            {
                var retryStrength = Math.Round(Math.Clamp(originalStrength + .05, 0, 1), 3);
                if (Math.Abs(retryStrength - originalStrength) > .0001)
                {
                    retryParameters["referenceStrength"] = retryStrength;
                    changedParameters["referenceStrength"] = retryStrength;
                }
                break;
            }
        }
        if (changedParameters.Count == 0)
        {
            await _repository.LogAsync("qa.retry.blocked", $"Shot {shotId} 没有可依据失败原因修改的原任务参数；保留原路线/动作并转人工", null, "Warning", ct);
            return false;
        }
        var retryIdempotencyKey = $"qa-retry:{shotId}:{original.Long("id")}:{StableTaskKey(originalPlan.ContractId, originalPlan.ContractVersion, originalPlan.WorkflowSha256, originalAction, retryReason, changedParameters.ToJsonString())}";
        if (await _repository.TaskByIdempotencyKeyAsync(retryIdempotencyKey, ct) is not null) return true;
        retryParameters["action"] = originalAction;
        retryParameters["qaRetry"] = true;
        retryParameters["retryCount"] = retryCount;
        retryParameters["previousQaStatus"] = previousStatus;
        retryParameters["previousQaScore"] = previousScore;
        retryParameters["retryReason"] = retryReason;
        retryParameters["changedParameters"] = JsonNode.Parse(changedParameters.ToJsonString());
        retryParameters["retryRoutePolicy"] = QaRetryPolicy.RoutePolicy;
        retryParameters["retrySourceSnapshot"] = retrySourceSnapshot;
        if (!await _repository.IncrementQaRetryAsync(shotId.Value, maxRetries, ct)) return false;
        using var retryDocument = JsonDocument.Parse(retryParameters.ToJsonString());
        var taskId = await _repository.CreateTaskAsync(new TaskInput
        {
            ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = shotId, TaskType = originalTaskType, WorkflowId = workflowId,
            InputImagePath = inputImageFullPath, Priority = 5, MaxRetries = 2, Stage = "QA-Retry",
            IdempotencyKey = retryIdempotencyKey,
            Parameters = retryDocument.RootElement.Clone()
        }, ct);
        using var repairParameters = JsonDocument.Parse(changedParameters.ToJsonString());
        await _repository.AddQualityRepairRunAsync(shotId, original.Long("id"), taskId, "TARGETED_PARAMETER_RETRY", $"inherit-route:{workflowFile};preserve-action;source-snapshot;changed:{string.Join(',', changedParameters.Select(pair => pair.Key))}", repairParameters.RootElement.Clone(), "Queued", ct: ct);
        await _repository.LogAsync("qa.retry", $"Shot {shotId} 第 {retryCount} 次 QA 回炉；继承路线 {workflowFile} 与原动作；原因 {retryReason}；仅修改 {string.Join(',', changedParameters.Select(pair => pair.Key))}", taskId, "Warning", ct);
        await _repository.SetShotQaStatusAsync(shotId.Value, "AutoChecking", ct);
        await _repository.UpdateShotStatusAsync(shotId.Value, "VideoGenerating", ct);
        Enqueue(taskId);
        return true;
    }

    private async Task<JsonObject> BuildRetrySourceSnapshotAsync(
        long parentTaskId,
        JsonElement contractTrace,
        JsonElement executionTrace,
        WorkflowExecutionPlan plan,
        IReadOnlyDictionary<string, string?> slotSources,
        IReadOnlyDictionary<string, ResolvedAssetReference> slotAssets,
        CharacterReferenceGateResult? characterGate,
        string action,
        string inputImageFullPath,
        CancellationToken ct)
    {
        if (!string.Equals(GetString(contractTrace, "validationStatus"), "Passed", StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_INVALID", "原任务的工作流契约没有 Passed 执行记录，已阻止自动重试");
        if (!string.Equals(GetString(contractTrace, "contractId"), plan.ContractId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(GetString(contractTrace, "contractVersion"), plan.ContractVersion, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(GetString(contractTrace, "sha256") ?? GetString(contractTrace, "workflowSha256"), plan.WorkflowSha256, StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_INVALID", "原任务契约版本或工作流哈希与当前受控路线不一致，已阻止自动重试");
        if (!string.Equals(GetString(contractTrace, "runtimeDependencyFingerprint"), plan.RuntimeDependencyFingerprint, StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_INVALID", "原任务运行依赖指纹已变化，必须重新验证路线后再重试");

        if (!TryGetObject(contractTrace, "modelFingerprints", out var traceModels) || !traceModels.EnumerateObject().Any())
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_MISSING", "原任务没有模型权重哈希，无法证明重试仍使用同一模型版本");
        foreach (var model in plan.ModelFingerprints)
        {
            var traceHash = traceModels.TryGetProperty(model.Key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            if (!string.Equals(traceHash, model.Value, StringComparison.OrdinalIgnoreCase))
                throw new WorkflowContractException("RETRY_SOURCE_DRIFT", $"原任务模型 {model.Key} 的权重哈希与当前路线不一致");
        }

        if (!TryGetObject(executionTrace, "slotBindings", out var traceSlots) || !traceSlots.EnumerateObject().Any())
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_MISSING", "原任务没有输入槽位绑定快照，无法安全重试");
        var snapshotSlots = new JsonObject();
        foreach (var slot in traceSlots.EnumerateObject())
        {
            if (slot.Value.ValueKind != JsonValueKind.Object)
                throw new WorkflowContractException("RETRY_SOURCE_TRACE_INVALID", $"原任务槽位 {slot.Name} 绑定记录不是对象");
            var relativePath = GetString(slot.Value, "relativePath", "path");
            var expectedHash = GetString(slot.Value, "sha256");
            if (!ReleaseEligibilityService.IsSha256ForExport(expectedHash) || !_paths.TryResolveExisting(relativePath, out var fullPath, out var currentRelativePath))
                throw new WorkflowContractException("RETRY_SOURCE_TRACE_INVALID", $"原任务槽位 {slot.Name} 没有可核验的受控资产哈希/路径");
            var actualHash = await _ffmpeg.Sha256Async(fullPath, ct);
            if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
                throw new WorkflowContractException("RETRY_SOURCE_DRIFT", $"原任务槽位 {slot.Name} 文件已变化，旧重试来源已失效");
            if (slotSources.TryGetValue(slot.Name, out var declaredSource)
                && _paths.TryResolveExisting(declaredSource, out _, out var declaredRelativePath)
                && !string.Equals(NormalizeTracePath(declaredRelativePath), NormalizeTracePath(currentRelativePath), StringComparison.OrdinalIgnoreCase))
                throw new WorkflowContractException("RETRY_SOURCE_DRIFT", $"原任务槽位 {slot.Name} 的声明来源已变化");
            if (GetLong(slot.Value, "assetId") is { } traceAssetId
                && (!slotAssets.TryGetValue(slot.Name, out var currentAsset) || currentAsset.AssetId != traceAssetId || GetInt(slot.Value, "assetVersion") != currentAsset.AssetVersion))
                throw new WorkflowContractException("RETRY_SOURCE_DRIFT", $"原任务槽位 {slot.Name} 的资产版本已变化");

            var snapshotSlot = new JsonObject
            {
                ["relativePath"] = currentRelativePath,
                ["sha256"] = expectedHash
            };
            CopyNumber(slot.Value, snapshotSlot, "assetId");
            CopyNumber(slot.Value, snapshotSlot, "assetVersion");
            CopyNumber(slot.Value, snapshotSlot, "manifestId");
            snapshotSlots[slot.Name] = snapshotSlot;
        }
        foreach (var required in plan.Slots.Where(slot => slot.Required))
            if (!snapshotSlots.TryGetPropertyValue(required.Role, out _))
                throw new WorkflowContractException("RETRY_SOURCE_TRACE_MISSING", $"原任务缺少必需槽位 {required.Role} 的绑定快照");

        var firstFramePath = GetSnapshotSlotPath(executionTrace, "firstFrame");
        if (!string.IsNullOrWhiteSpace(firstFramePath)
            && _paths.TryResolveExisting(firstFramePath, out var firstFrameFullPath, out _)
            && !string.Equals(Path.GetFullPath(firstFrameFullPath), Path.GetFullPath(inputImageFullPath), StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("RETRY_SOURCE_DRIFT", "原任务首帧与工作流 firstFrame 槽位不一致");
        if (!_paths.TryResolveExisting(inputImageFullPath, out _, out var inputRelativePath))
            throw new WorkflowContractException("RETRY_INPUT_MISSING", "原任务首帧不在受控媒体目录");
        var inputHash = await _ffmpeg.Sha256Async(inputImageFullPath, ct);
        if (!ReleaseEligibilityService.IsSha256ForExport(inputHash))
            throw new WorkflowContractException("RETRY_SOURCE_TRACE_INVALID", "原任务首帧无法计算哈希");

        var tracedAction = GetString(executionTrace, "action");
        if (!string.IsNullOrWhiteSpace(tracedAction) && !string.Equals(tracedAction, action, StringComparison.Ordinal))
            throw new WorkflowContractException("RETRY_SOURCE_DRIFT", "原任务动作目标已变化，已阻止自动重试");

        var snapshot = new JsonObject
        {
            ["snapshotVersion"] = 1,
            ["parentTaskId"] = parentTaskId,
            ["contractId"] = plan.ContractId,
            ["contractVersion"] = plan.ContractVersion,
            ["workflowFileName"] = plan.WorkflowFileName,
            ["workflowSha256"] = plan.WorkflowSha256,
            ["runtimeDependencyFingerprint"] = plan.RuntimeDependencyFingerprint,
            ["action"] = action,
            ["inputImage"] = new JsonObject { ["relativePath"] = inputRelativePath, ["sha256"] = inputHash },
            ["slotBindings"] = snapshotSlots
        };
        var modelFingerprints = new JsonObject();
        foreach (var model in plan.ModelFingerprints) modelFingerprints[model.Key] = model.Value;
        snapshot["modelFingerprints"] = modelFingerprints;
        var modelPaths = new JsonObject();
        foreach (var model in plan.ModelPaths) modelPaths[model.Key] = ModelTracePath(model.Value);
        snapshot["modelPaths"] = modelPaths;

        if (characterGate is not null)
        {
            if (!TryGetPropertyIgnoreCase(executionTrace, "characterReferences", out var traceReferences) || traceReferences.ValueKind != JsonValueKind.Array)
                throw new WorkflowContractException("RETRY_SOURCE_TRACE_MISSING", "原任务没有角色参考版本快照，已阻止自动重试");
            if (!CharacterReferencesMatch(traceReferences, characterGate.References, out var characterIssue))
                throw new WorkflowContractException("RETRY_SOURCE_DRIFT", characterIssue);
            var references = new JsonArray();
            foreach (var reference in traceReferences.EnumerateArray()) references.Add(JsonNode.Parse(reference.GetRawText()) ?? new JsonObject());
            snapshot["characterReferences"] = references;
        }
        else snapshot["characterReferences"] = new JsonArray();
        return snapshot;
    }

    private async Task ValidateRetrySourceSnapshotAsync(
        JsonElement requestedParameters,
        WorkflowExecutionPlan plan,
        IReadOnlyDictionary<string, string?> slotSources,
        IReadOnlyDictionary<string, ResolvedAssetReference> slotAssets,
        CharacterReferenceGateResult? characterGate,
        string? action,
        string? inputImagePath,
        CancellationToken ct)
    {
        if (!TryGetObject(requestedParameters, "retrySourceSnapshot", out var snapshot)) return;
        var issues = new List<string>();
        if (GetInt(snapshot, "snapshotVersion") != 1) issues.Add("retrySourceSnapshot 版本不受支持");
        if (!string.Equals(GetString(snapshot, "contractId"), plan.ContractId, StringComparison.OrdinalIgnoreCase)) issues.Add("重试契约 ID 已变化");
        if (!string.Equals(GetString(snapshot, "contractVersion"), plan.ContractVersion, StringComparison.OrdinalIgnoreCase)) issues.Add("重试契约版本已变化");
        if (!string.Equals(GetString(snapshot, "workflowSha256"), plan.WorkflowSha256, StringComparison.OrdinalIgnoreCase)) issues.Add("重试工作流哈希已变化");
        if (!string.Equals(GetString(snapshot, "runtimeDependencyFingerprint"), plan.RuntimeDependencyFingerprint, StringComparison.OrdinalIgnoreCase)) issues.Add("重试运行依赖指纹已变化");
        if (!string.Equals(GetString(snapshot, "action"), action, StringComparison.Ordinal)) issues.Add("重试动作目标已变化");

        if (!TryGetObject(snapshot, "modelFingerprints", out var snapshotModels)) issues.Add("重试模型哈希快照缺失");
        else
        {
            foreach (var model in plan.ModelFingerprints)
            {
                var snapshotHash = snapshotModels.TryGetProperty(model.Key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
                if (!string.Equals(snapshotHash, model.Value, StringComparison.OrdinalIgnoreCase)) issues.Add($"重试模型 {model.Key} 权重哈希已变化");
            }
        }

        if (!TryGetObject(snapshot, "slotBindings", out var snapshotSlots)) issues.Add("重试输入槽位快照缺失");
        else
        {
            foreach (var required in plan.Slots.Where(slot => slot.Required))
                if (!snapshotSlots.TryGetProperty(required.Role, out _)) issues.Add($"重试缺少必需槽位 {required.Role}");
            foreach (var slot in snapshotSlots.EnumerateObject())
            {
                if (slot.Value.ValueKind != JsonValueKind.Object)
                {
                    issues.Add($"重试槽位 {slot.Name} 记录无效");
                    continue;
                }
                var relativePath = GetString(slot.Value, "relativePath", "path");
                var expectedHash = GetString(slot.Value, "sha256");
                if (!ReleaseEligibilityService.IsSha256ForExport(expectedHash) || !_paths.TryResolveExisting(relativePath, out var fullPath, out var currentRelativePath))
                {
                    issues.Add($"重试槽位 {slot.Name} 来源不可核验");
                    continue;
                }
                var currentHash = await _ffmpeg.Sha256Async(fullPath, ct);
                if (!string.Equals(currentHash, expectedHash, StringComparison.OrdinalIgnoreCase)) issues.Add($"重试槽位 {slot.Name} 文件哈希已变化");
                if (slotSources.TryGetValue(slot.Name, out var declaredSource)
                    && _paths.TryResolveExisting(declaredSource, out _, out var declaredRelativePath)
                    && !string.Equals(NormalizeTracePath(declaredRelativePath), NormalizeTracePath(currentRelativePath), StringComparison.OrdinalIgnoreCase))
                    issues.Add($"重试槽位 {slot.Name} 声明来源已变化");
                var snapshotAssetId = GetLong(slot.Value, "assetId");
                var snapshotAssetVersion = GetInt(slot.Value, "assetVersion");
                if (snapshotAssetId is { } assetId)
                {
                    if (!slotAssets.TryGetValue(slot.Name, out var currentAsset) || currentAsset.AssetId != assetId)
                        issues.Add($"重试槽位 {slot.Name} AssetId 已变化");
                    else if (snapshotAssetVersion is null || snapshotAssetVersion <= 0 || currentAsset.AssetVersion != snapshotAssetVersion)
                        issues.Add($"重试槽位 {slot.Name} 资产版本已变化");
                }
            }
        }

        if (!TryGetObject(snapshot, "inputImage", out var inputImage) || string.IsNullOrWhiteSpace(inputImagePath)) issues.Add("重试首帧快照缺失");
        else
        {
            var relativePath = GetString(inputImage, "relativePath", "path");
            var expectedHash = GetString(inputImage, "sha256");
            if (!ReleaseEligibilityService.IsSha256ForExport(expectedHash) || !_paths.TryResolveExisting(relativePath, out var fullPath, out var currentRelativePath)) issues.Add("重试首帧来源不可核验");
            else
            {
                var currentHash = await _ffmpeg.Sha256Async(fullPath, ct);
                if (!string.Equals(currentHash, expectedHash, StringComparison.OrdinalIgnoreCase)) issues.Add("重试首帧文件哈希已变化");
                if (!_paths.TryResolveExisting(inputImagePath, out _, out var inputRelativePath)
                    || !string.Equals(NormalizeTracePath(inputRelativePath), NormalizeTracePath(currentRelativePath), StringComparison.OrdinalIgnoreCase)) issues.Add("重试首帧路径已变化");
            }
        }

        if (!TryGetPropertyIgnoreCase(snapshot, "characterReferences", out var snapshotReferences) || snapshotReferences.ValueKind != JsonValueKind.Array)
            issues.Add("重试角色参考快照缺失");
        else if (!CharacterReferencesMatch(snapshotReferences, characterGate?.References ?? [], out var characterIssue)) issues.Add(characterIssue);
        if (issues.Count > 0) throw new WorkflowContractException("RETRY_SOURCE_DRIFT", string.Join("；", issues.Distinct(StringComparer.Ordinal)));
    }

    private static bool CharacterReferencesMatch(JsonElement trace, IReadOnlyList<CharacterReferenceBinding> current, out string issue)
    {
        issue = "角色参考版本与原任务快照不一致";
        if (trace.ValueKind != JsonValueKind.Array || trace.GetArrayLength() != current.Count) return false;
        foreach (var reference in current)
        {
            var match = trace.EnumerateArray().FirstOrDefault(item => item.ValueKind == JsonValueKind.Object && GetLong(item, "characterId") == reference.CharacterId && GetLong(item, "referenceId") == reference.ReferenceId);
            if (match.ValueKind != JsonValueKind.Object
                || !string.Equals(NormalizeTracePath(GetString(match, "relativePath")), NormalizeTracePath(reference.RelativePath), StringComparison.OrdinalIgnoreCase)
                || GetInt(match, "assetVersion") != reference.AssetVersion
                || !string.Equals(GetString(match, "assetSha256"), reference.AssetSha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(GetString(match, "reviewStatus"), reference.ReviewStatus, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(GetString(match, "reviewer"), reference.Reviewer, StringComparison.Ordinal)) return false;
        }
        return true;
    }

    private static string? GetSnapshotSlotPath(JsonElement executionTrace, string role)
    {
        if (!TryGetObject(executionTrace, "slotBindings", out var bindings) || !TryGetPropertyIgnoreCase(bindings, role, out var binding) || binding.ValueKind != JsonValueKind.Object) return null;
        return GetString(binding, "relativePath", "path");
    }

    private static void CopyNumber(JsonElement source, JsonObject target, string name)
    {
        if (TryGetPropertyIgnoreCase(source, name, out var value) && value.ValueKind == JsonValueKind.Number) target[name] = JsonNode.Parse(value.GetRawText());
    }

    private static string NormalizeTracePath(string? path) => (path ?? string.Empty).Replace('\\', '/').TrimStart('/');

    private async Task ExecuteAudioAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        using var document = row.Json("inputJson"); var root = document.RootElement; var parameters = root.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : root;
        var text = GetString(parameters, "text") ?? ""; var voice = GetString(parameters, "voiceId") ?? ""; var outputName = GetString(parameters, "outputName"); var speed = GetDecimal(parameters, "speed", 1); var pitch = GetDecimal(parameters, "pitch", 0);
        var taskId = row.Long("id");
        var requested = SafeFileName(outputName, $"task_{taskId}.wav");
        var staged = _artifacts.CreateStagedPath(RequireWorkspace(taskId), Path.ChangeExtension(requested, ".wav"), $"task_{taskId}.wav");
        var instruction = GetString(parameters, "instruction") ?? "";
        if (Qwen3TtsService.IsQwen(voice))
        {
            if (!string.Equals(row.Text("resourceClass"), "GPU", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Qwen3-TTS 必须通过 GPU 队列执行");
            if (GetString(parameters, "engineVersion") != _tts.EngineIdentity(voice))
                throw new InvalidOperationException("Qwen3-TTS 配置版本发生变化，请重新确认后提交");
            await _comfy.EnsureIdleForExternalGpuAsync(ct);
            await _comfy.TryFreeMemoryAsync(ct);
            await WaitForGpuAsync(ct);
        }
        await _tts.SynthesizeToAsync(text, voice, speed, pitch, staged, ct, instruction);
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Audio, staged, Path.GetFileName(staged), ct);
        if (Qwen3TtsService.IsQwen(voice) && File.Exists(staged + ".qwen.json"))
            await PublishArtifactAsync(row, ArtifactPurpose.QaReport, staged + ".qwen.json", Path.GetFileName(staged) + ".qwen.json", ct);
        if (row.LongOrNull("shotId") is { } shotId)
            AfterSuccess(taskId, postCt => _repository.UpdateShotAudioStatusAsync(shotId, "Completed", postCt));
    }

    private async Task ExecuteSubtitlesAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        using var document = row.Json("inputJson"); var root = document.RootElement; var parameters = root.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : root;
        var taskId = row.Long("id");
        var episodeId = GetLong(parameters, "episodeId") ?? row.Long("episodeId");
        var shots = await _repository.ShotsAsync(episodeId, ct);
        var name = SafeFileName(GetString(parameters, "outputName"), $"Episode_{episodeId:000}.srt");
        var staged = _artifacts.CreateStagedPath(RequireWorkspace(taskId), Path.ChangeExtension(name, ".srt"), $"Episode_{episodeId:000}.srt");
        await _subtitles.GenerateToAsync(staged, shots, ct);
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Subtitle, staged, Path.GetFileName(staged), ct);
        AfterSuccess(taskId, postCt => _subtitles.PersistAsync(episodeId, published.FullPath, shots, postCt));
    }

    private async Task ExecuteEpisodeRenderAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var taskId = row.Long("id");
        using var document = row.Json("inputJson"); var root = document.RootElement; var parameters = root.TryGetProperty("parameters", out var p) && p.ValueKind == JsonValueKind.Object ? p : root;
        var files = IsFormal(row)
            ? (await ResolveFormalAssetsAsync(row, [ArtifactPurpose.Video, ArtifactPurpose.Episode, ArtifactPurpose.EpisodePreview], ct)).Select(asset => asset.FullPath).ToArray()
            : ResolveAssetPaths(parameters, "files").ToArray();
        var rawFiles = parameters.TryGetProperty("files", out var rawFileElement) ? rawFileElement : default;
        if (IsFormal(row) && rawFiles.ValueKind == JsonValueKind.Array && rawFiles.GetArrayLength() > 0)
            throw new AssetValidationException("Formal Episode tasks reject raw file paths; submit InputAssetIds");
        if (files.Length == 0) throw new InvalidOperationException("Episode 没有可合成视频");
        var episode = (await _repository.EpisodeAsync(row.Long("episodeId"), ct)).FirstOrDefault();
        var targetWidth = Math.Max(256, GetInt(parameters, "targetWidth") ?? episode?.Int("outputWidth", 1920) ?? 1920);
        var targetHeight = Math.Max(256, GetInt(parameters, "targetHeight") ?? episode?.Int("outputHeight", 1080) ?? 1080);
        var targetFps = Math.Clamp(GetInt(parameters, "targetFps") ?? episode?.Int("outputFps", 30) ?? 30, 24, 60);
        var outputName = SafeFileName(GetString(parameters, "outputName"), $"Episode_{row.Long("episodeId"):000}.mp4");
        var workspace = RequireWorkspace(taskId);
        var output = _artifacts.CreateStagedPath(workspace, Path.ChangeExtension(outputName, ".mp4"), $"Episode_{row.Long("episodeId"):000}.mp4");
        var temp = _artifacts.CreateStagedPath(workspace, "episode_concat.mp4", "episode_concat.mp4");
        var normalized = _artifacts.CreateStagedPath(workspace, "episode_normalized.mp4", "episode_normalized.mp4");
        var episodeShots = await _repository.ShotsAsync(row.Long("episodeId"), ct);
        var targetDuration = episodeShots.Sum(x => Math.Max(1, Convert.ToDouble(x.Decimal("durationSeconds", 5))));
        await _leases.UpdateProgressAsync(RequireLease(taskId), .08m, ct);
        await _ffmpeg.ConcatAsync(files, temp, targetFps, ct);
        await _leases.UpdateProgressAsync(RequireLease(taskId), .32m, ct);
        var current = await _ffmpeg.NormalizeVideoAsync(temp, normalized, targetWidth, targetHeight, targetFps, ct, targetDuration);
        await _leases.UpdateProgressAsync(RequireLease(taskId), .62m, ct);
        var audioTracks = new List<FfmpegAudioTrack>();
        if (parameters.TryGetProperty("audioTracks", out var trackList) && trackList.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in trackList.EnumerateArray())
            {
                if (!item.TryGetProperty("path", out var pathValue) || pathValue.ValueKind != JsonValueKind.String) continue;
                var path = pathValue.GetString(); if (!_paths.TryResolveExisting(path, out var fullPath, out _)) continue;
                var volume = item.TryGetProperty("volume", out var volumeValue) && volumeValue.TryGetDouble(out var parsedVolume) ? parsedVolume : 1d;
                var start = item.TryGetProperty("startSeconds", out var startValue) && startValue.TryGetDouble(out var parsedStart) ? parsedStart : 0d;
                audioTracks.Add(new FfmpegAudioTrack(fullPath, volume, start));
            }
        }
        if (parameters.TryGetProperty("audioPaths", out var audioList) && audioList.ValueKind == JsonValueKind.Array)
            audioTracks.AddRange(audioList.EnumerateArray().Select(x => x.GetString()).Select(path => _paths.TryResolveExisting(path, out var fullPath, out _) ? fullPath : null).Where(path => path is not null).Select(path => new FfmpegAudioTrack(path!, 1d)));
        if (audioTracks.Count > 0) { var mixed = _artifacts.CreateStagedPath(workspace, "episode_audio.mp4", "episode_audio.mp4"); await _ffmpeg.MixAudioAsync(current, audioTracks, mixed, ct); current = mixed; }
        await _leases.UpdateProgressAsync(RequireLease(taskId), .78m, ct);
        var subtitlePath = GetString(parameters, "subtitlePath"); if (_paths.TryResolveExisting(subtitlePath, out var subtitleFullPath, out _)) { await _ffmpeg.BurnSubtitlesAsync(current, subtitleFullPath, output, ct); current = output; }
        await _leases.UpdateProgressAsync(RequireLease(taskId), .92m, ct);
        if (!string.Equals(current, output, StringComparison.OrdinalIgnoreCase)) File.Copy(current, output, false);
        var probe = await _ffmpeg.ProbeAsync(output, ct);
        var preview = GetBool(parameters, "preview", false);
        var published = await PublishArtifactAsync(row, preview ? ArtifactPurpose.EpisodePreview : ArtifactPurpose.Episode, output, outputName, ct);
        if (!preview) AfterSuccess(taskId, postCt => _repository.UpdateEpisodeOutputAsync(row.Long("episodeId"), published.FullPath, probe, postCt));
        await _leases.UpdateProgressAsync(RequireLease(taskId), .99m, ct);
    }

    private async Task ExecuteEnhanceAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        var taskId = row.Long("id"); using var inputDocument = row.Json("inputJson"); var inputRoot = inputDocument.RootElement; var parameters = inputRoot.TryGetProperty("parameters", out var nestedParameters) && nestedParameters.ValueKind == JsonValueKind.Object ? nestedParameters : JsonDocument.Parse("{}").RootElement; var input = await ResolvePrimaryInputAsync(row, inputRoot, GetString(inputRoot, "inputImagePath") ?? GetString(inputRoot, "input"), [ArtifactPurpose.Video, ArtifactPurpose.Episode, ArtifactPurpose.EpisodePreview], ct);
        if (!_paths.TryResolveExisting(input, out var inputFullPath, out _)) throw new FileNotFoundException("增强输入视频不存在", input);
        var targetWidth = GetInt(parameters, "width") ?? 1920;
        var targetHeight = GetInt(parameters, "height") ?? 1080;
        var targetFps = GetInt(parameters, "fps") ?? 24;
        var deflicker = GetBool(parameters, "deflicker", false);
        var interpolate = GetBool(parameters, "interpolate", false);
        var output = _artifacts.CreateStagedPath(RequireWorkspace(taskId), $"task_{taskId}_{targetWidth}x{targetHeight}_{targetFps}fps.mp4", $"task_{taskId}_enhanced.mp4");
        await _ffmpeg.EnhanceAsync(inputFullPath, output, targetFps, ct, deflicker, interpolate, targetWidth, targetHeight);
        var qc = await _quality.CheckVideoAsync(output, row.Decimal("shotDurationSeconds", 5), targetWidth, targetHeight, targetFps, ct); if (!qc.Passed) throw new InvalidOperationException("QUALITY_FAILED: 增强后视频 QC 未通过");
        var probe = await _ffmpeg.ProbeAsync(output, ct);
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, Path.GetFileName(output), ct);
        output = published.FullPath;
        await _repository.UpdateResultQualityAsync(taskId, output, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
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
        var files = IsFormal(row)
            ? (await ResolveFormalAssetsAsync(row, [ArtifactPurpose.Video, ArtifactPurpose.Episode, ArtifactPurpose.EpisodePreview], ct)).Select(asset => asset.FullPath).ToList()
            : ResolveAssetPaths(inputRoot, "files").ToList();
        await ConcatSourceIntegrity.ValidateAsync(inputRoot,_paths,_ffmpeg,ct);
        var rawFiles = inputRoot.TryGetProperty("files", out var rawFileElement) ? rawFileElement : default;
        if (IsFormal(row) && rawFiles.ValueKind == JsonValueKind.Array && rawFiles.GetArrayLength() > 0)
            throw new AssetValidationException("Formal concat tasks reject raw file paths; submit InputAssetIds");
        if (files.Count == 0) throw new InvalidOperationException("拼接任务未提供有效 files");
        var outputName = inputRoot.TryGetProperty("outputName", out var name) && name.ValueKind == JsonValueKind.String ? Path.GetFileName(name.GetString()!) : $"task_{taskId}_concat.mp4";
        var output = _artifacts.CreateStagedPath(RequireWorkspace(taskId), Path.ChangeExtension(outputName, ".mp4"), $"task_{taskId}_concat.mp4");
        var concatFps = GetInt(inputRoot, "targetFps") ?? 30;
        if (concatFps is < 24 or > 60) throw new InvalidOperationException("拼接帧率必须为24–60FPS");
        if (!string.IsNullOrWhiteSpace(GetString(inputRoot, "audioStreamCopyFrom")))
        {
            await ExecuteAudioRemuxAsync(row, inputRoot, files, output, outputName, ct);
            return;
        }
        if (GetBool(inputRoot, "singlePass", false))
        {
            await ExecuteDetailExportAsync(row, inputRoot, files, output, outputName, concatFps, ct);
            return;
        }
        var storyPreview=inputRoot.TryGetProperty(CharacterStoryService.PreviewMarker,out var preview);
        if(storyPreview)
        {
            if(_characterStory is null)throw new AssetValidationException("剧情预览校验服务未就绪");
            await _characterStory.ValidatePreviewAsync(CharacterStoryStore.RestoreTask(document.RootElement,row),ct);
        }
        await _ffmpeg.ConcatAsync(files, output, concatFps, ct,preserveAudio:!storyPreview||GetString(preview,"audioStrategy")=="NativeH3",requireAllInputs:storyPreview);
        if(storyPreview&&GetString(preview,"audioStrategy")=="ExistingDubbing")
        {
            if(!_paths.TryResolveExisting(GetString(preview,"audioPath"),out var track,out _))throw new AssetValidationException("配音文件已缺失");
            var mixed=_artifacts.CreateStagedPath(RequireWorkspace(taskId),$"task_{taskId}_dubbed.mp4",$"task_{taskId}_dubbed.mp4");
            await _ffmpeg.MixAudioAsync(output,new[]{new FfmpegAudioTrack(track,1)},mixed,ct,originalVolume:0);output=mixed;
        }
        var targetDuration = GetDouble(inputRoot, "targetDurationSeconds", 0);
        QualityCheckResult? deliveryQc = null;
        if (targetDuration > 0)
        {
            var width = GetInt(inputRoot, "targetWidth") ?? 1280;
            var height = GetInt(inputRoot, "targetHeight") ?? 720;
            var fps = GetInt(inputRoot, "targetFps") ?? 30;
            if (!double.IsFinite(targetDuration) || targetDuration > 3600 || width is < 256 or > 3840 || height is < 256 or > 3840
                || width % 2 != 0 || height % 2 != 0 || fps is < 24 or > 60
                || Math.Abs(targetDuration * fps - Math.Round(targetDuration * fps)) > .001)
                throw new InvalidOperationException("CONCAT_DELIVERY_SPEC_INVALID: 交付时长、尺寸或帧率无效");
            var sourceProbe = await _ffmpeg.ProbeAsync(output, ct);
            if (sourceProbe?.DurationSeconds is not > 0 || sourceProbe.DurationSeconds < targetDuration - 1d / fps)
                throw new InvalidOperationException("CONCAT_DELIVERY_SOURCE_SHORT: 源视频不足以生成目标时长；不会用末帧补足");
            var normalized = _artifacts.CreateStagedPath(RequireWorkspace(taskId), $"task_{taskId}_delivery.mp4", $"task_{taskId}_delivery.mp4");
            await _ffmpeg.NormalizeVideoAsync(output, normalized, width, height, fps, ct, targetDuration);
            deliveryQc = await _quality.CheckVideoAsync(normalized, (decimal)targetDuration, width, height, fps, ct, (int)Math.Round(targetDuration * fps));
            var finalProbe = await _ffmpeg.ProbeAsync(normalized, ct);
            if (!deliveryQc.Passed || finalProbe?.Width != width || finalProbe.Height != height || finalProbe.Fps != fps)
                throw new InvalidOperationException("CONCAT_DELIVERY_QC_FAILED: 拼接交付规格未通过实际文件校验");
            deliveryQc.Metrics["deliveryTarget"] = new { targetDurationSeconds = targetDuration, width, height, fps, contentReview = "NeedReview" };
            output = normalized;
        }
        var narrationTracks = new List<FfmpegAudioTrack>();
        if (inputRoot.TryGetProperty("audioTracks", out var narration) && narration.ValueKind == JsonValueKind.Array)
        {
            if (IsFormal(row)) throw new AssetValidationException("Formal concat narration must use the approved Episode render route");
            foreach (var item in narration.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object) throw new InvalidOperationException("剧情旁白的每一项必须是音轨对象");
                var path = GetString(item, "path");
                if (!_paths.TryResolveExisting(path, out var fullPath, out _)) throw new AssetValidationException("剧情旁白文件不存在或不在允许目录");
                var volume = GetDouble(item, "volume", 1);
                var start = GetDouble(item, "startSeconds", 0);
                var tempo = GetDouble(item, "tempo", 1);
                var fadeStart=GetDouble(item,"fadeOutStartSeconds",0);var fadeDuration=GetDouble(item,"fadeOutDurationSeconds",0);
                if (!double.IsFinite(volume) || !double.IsFinite(start) || !double.IsFinite(tempo) || !double.IsFinite(fadeStart) || !double.IsFinite(fadeDuration) || volume is < 0.05 or > 2 || start is < 0 or > 3600 || tempo is < .5 or > 2 || fadeStart is <0 or >3600 || fadeDuration is <0 or >60)
                    throw new InvalidOperationException("剧情旁白的音量、开始时间或变速无效");
                narrationTracks.Add(new FfmpegAudioTrack(fullPath, volume, start, tempo,fadeStart,fadeDuration));
            }
        }
        var originalGain = GetDouble(inputRoot, "originalAudioVolume", 1);
        if (narrationTracks.Count > 0 || originalGain != 1)
        {
            if (IsFormal(row)) throw new AssetValidationException("Formal concat audio changes must use the approved Episode render route");
            var mixed = _artifacts.CreateStagedPath(RequireWorkspace(taskId), $"task_{taskId}_narrated.mp4", $"task_{taskId}_narrated.mp4");
            output = await _ffmpeg.MixAudioAsync(output, narrationTracks, mixed, ct, originalGain);
        }
        var subtitlePath = GetString(inputRoot, "subtitlePath");
        if (!string.IsNullOrWhiteSpace(subtitlePath))
        {
            if (IsFormal(row)) throw new AssetValidationException("Formal concat captions must use the approved Episode render route");
            if (!_paths.TryResolveExisting(subtitlePath, out var subtitle, out _)) throw new AssetValidationException("剧情字幕文件不存在或不在允许目录");
            var captioned = _artifacts.CreateStagedPath(RequireWorkspace(taskId), $"task_{taskId}_captioned.mp4", $"task_{taskId}_captioned.mp4");
            await _ffmpeg.BurnSubtitlesAsync(output, subtitle, captioned, ct);
            output = captioned;
        }
        if (targetDuration > 0)
        {
            deliveryQc = await _quality.CheckVideoAsync(output, (decimal)targetDuration, GetInt(inputRoot, "targetWidth") ?? 1280,
                GetInt(inputRoot, "targetHeight") ?? 720, concatFps, ct, (int)Math.Round(targetDuration * concatFps));
            if (!deliveryQc.Passed) throw new InvalidOperationException("CONCAT_FINAL_QC_FAILED: 旁白/字幕后的交付文件未通过核验");
            deliveryQc.Metrics["storyAudioTracks"] = narrationTracks.Count;
            deliveryQc.Metrics["storyCaptions"] = !string.IsNullOrWhiteSpace(subtitlePath);
            deliveryQc.Metrics["contentReview"] = "NeedReview";
        }
        if(storyPreview)
        {
            var probe=await _ffmpeg.ProbeAsync(output,ct);var first=await _ffmpeg.ProbeAsync(files[0],ct);var strategy=GetString(preview,"audioStrategy");
            if(probe?.FrameCount!=files.Count*124||probe.Fps!=24||probe.Width!=first?.Width||probe.Height!=first?.Height
                ||(strategy=="PostDubbing"&&probe.HasAudio)||(strategy is "NativeH3" or "ExistingDubbing"&&!probe.HasAudio))throw new InvalidOperationException("STORY_PREVIEW_QC_FAILED: 合成帧数、规格或音轨策略不符合所选源片");
        }
        await ConcatSourceIntegrity.ValidateAsync(inputRoot,_paths,_ffmpeg,ct);
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, outputName, ct);
        if (deliveryQc is not null)
            await _repository.UpdateResultQualityAsync(taskId, published.FullPath, deliveryQc.Score, JsonSerializer.Serialize(deliveryQc.Metrics), ct);
    }

    private async Task<string?> CopyInputToComfyAsync(string? input, long taskId, CancellationToken ct, string suffix = "")
    {
        if (string.IsNullOrWhiteSpace(input)) return null;
        if (!_paths.TryResolveExisting(input, out var full, out _)) throw new InvalidOperationException("参考图必须位于受控数据目录");
        Directory.CreateDirectory(_settings.ComfyInputPath);
        var lease = RequireLease(taskId);
        var target = Path.Combine(_settings.ComfyInputPath, $"video_studio_input_{taskId}_attempt_{lease.AttemptNo}_{lease.LeaseToken[..8]}{suffix}{Path.GetExtension(full)}");
        var temporary = $"{target}.part-{Guid.NewGuid():N}";
        try
        {
            await using var source = File.OpenRead(full);
            await using (var destination = File.Create(temporary))
                await source.CopyToAsync(destination, ct);
            if (!File.Exists(temporary) || new FileInfo(temporary).Length == 0) throw new InvalidDataException("ComfyUI input copy was empty");
            File.Move(temporary, target, false);
            return target;
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
        }
    }

    private async Task WaitForGpuAsync(CancellationToken ct)
    {
        for (var i = 0; i < 120; i++) { var snapshot = await _comfy.CheckAsync(ct); if (snapshot.Gpu is null || snapshot.Gpu.FreeMiB >= _settings.MinFreeVramMiB) return; await Task.Delay(5000, ct); }
        throw new TimeoutException("GPU 可用显存持续低于安全阈值，任务未提交");
    }

    private async Task ReduceParametersForOomAsync(TaskLease lease, IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        try
        {
            using var doc = row.Json("inputJson"); var root = JsonNode.Parse(doc.RootElement.GetRawText())?.AsObject(); var parameters = root?["parameters"]?.AsObject(); if (parameters is null) return;
            if (parameters["width"] is JsonValue width && width.TryGetValue<int>(out var w)) parameters["width"] = Math.Max(256, w - 64);
            if (parameters["height"] is JsonValue height && height.TryGetValue<int>(out var h)) parameters["height"] = Math.Max(192, h - 64);
            if (parameters["frames"] is JsonValue frames && frames.TryGetValue<int>(out var f)) parameters["frames"] = Math.Max(49, f - 24);
            await _leases.UpdateInputAsync(lease, root!.ToJsonString(), ct);
        }
        catch (Exception ex) { _logger.LogDebug(ex, "OOM 参数降级失败"); }
    }

    private TaskLease RequireLease(long taskId)
        => _activeLeases.TryGetValue(taskId, out var lease) ? lease : throw new StaleTaskLeaseException($"Task {taskId} has no active lease");

    private TaskWorkspace RequireWorkspace(long taskId)
        => _workspaces.TryGetValue(taskId, out var workspace) ? workspace : throw new StaleTaskLeaseException($"Task {taskId} has no active workspace");

    private bool IsFormal(IReadOnlyDictionary<string, object?> row)
        => row.LongOrNull("productionProfileId") is > 0 || row.LongOrNull("shotPlanId") is > 0;

    private async Task<string?> ResolvePrimaryInputAsync(IReadOnlyDictionary<string, object?> row, JsonElement inputRoot, string? legacyPath, ArtifactPurpose[] purposes, CancellationToken ct)
    {
        if (!IsFormal(row)) return legacyPath;
        var assets = await ResolveFormalAssetsAsync(row, purposes, ct, allowEmpty: true);
        if (assets.Length == 0) return null;
        var primaryId = row.LongOrNull("inputAssetId") ?? GetLong(inputRoot, "inputAssetId");
        return primaryId is { } id ? assets.FirstOrDefault(asset => asset.AssetId == id)?.FullPath ?? throw new AssetValidationException("Formal primary InputAssetId is not in the task asset set") : assets[0].FullPath;
    }

    private async Task<ResolvedAssetReference[]> ResolveFormalAssetsAsync(IReadOnlyDictionary<string, object?> row, ArtifactPurpose[] purposes, CancellationToken ct, bool allowEmpty = false)
    {
        if (!IsFormal(row)) return [];
        var projectId = row.LongOrNull("projectId") ?? throw new AssetValidationException("Formal task has no project ownership");
        using var document = row.Json("inputJson");
        var root = document.RootElement;
        var ids = new List<long>();
        if (row.LongOrNull("inputAssetId") is { } rowPrimary) ids.Add(rowPrimary);
        if (GetLong(root, "inputAssetId") is { } jsonPrimary) ids.Add(jsonPrimary);
        ids.AddRange(GetLongs(root, "inputAssetIds"));
        ids = ids.Where(id => id > 0).Distinct().ToList();
        if (ids.Count == 0)
        {
            if (allowEmpty) return [];
            throw new AssetValidationException("Formal task requires one or more InputAssetIds");
        }
        var resolved = new List<ResolvedAssetReference>(ids.Count);
        foreach (var id in ids) resolved.Add(await _assetResolver.ResolveAsync(id, projectId, purposes, ct));
        return resolved.ToArray();
    }

    private async Task<IReadOnlyDictionary<string, ResolvedAssetReference>> ResolveFormalSlotAssetsAsync(IReadOnlyDictionary<string, object?> row, ArtifactPurpose[] purposes, CancellationToken ct)
    {
        var result = new Dictionary<string, ResolvedAssetReference>(StringComparer.OrdinalIgnoreCase);
        if (!IsFormal(row)) return result;
        using var document = row.Json("inputJson");
        var root = document.RootElement;
        if (!TryGetPropertyIgnoreCase(root, "parameters", out var parameters) || parameters.ValueKind != JsonValueKind.Object
            || !TryGetPropertyIgnoreCase(parameters, "inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object) return result;
        var projectId = row.LongOrNull("projectId") ?? throw new AssetValidationException("Formal task has no project ownership");
        foreach (var property in slots.EnumerateObject())
        {
            long? assetId = property.Value.ValueKind == JsonValueKind.Number && property.Value.TryGetInt64(out var direct) ? direct : null;
            if (property.Value.ValueKind == JsonValueKind.Object && TryGetPropertyIgnoreCase(property.Value, "assetId", out var asset) && asset.TryGetInt64(out var nested))
                assetId = nested;
            if (assetId is null or <= 0)
                throw new AssetValidationException($"Formal input slot {property.Name} must reference an AssetId, not a raw path");
            var resolved = await _assetResolver.ResolveAsync(assetId.Value, projectId, purposes, ct);
            result[property.Name] = resolved;
        }
        return result;
    }

    private async Task<IReadOnlyDictionary<string, string>> ResolveFormalSlotPathsAsync(IReadOnlyDictionary<string, object?> row, ArtifactPurpose[] purposes, CancellationToken ct)
        => (await ResolveFormalSlotAssetsAsync(row, purposes, ct)).ToDictionary(pair => pair.Key, pair => pair.Value.FullPath, StringComparer.OrdinalIgnoreCase);

    private async Task<PublishedArtifact> PublishArtifactAsync(IReadOnlyDictionary<string, object?> row, ArtifactPurpose purpose, string stagedPath, string requestedName, CancellationToken ct)
    {
        var taskId = row.Long("id");
        var projectId = row.LongOrNull("projectId") ?? throw new AssetValidationException("Formal task output must belong to a project");
        using var input = row.Json("inputJson");
        var spec = new ArtifactPublishSpec(projectId, row.LongOrNull("episodeId"), row.LongOrNull("shotId"), purpose, requestedName,
            row.LongOrNull("productionProfileId"), row.LongOrNull("shotPlanId"), input.RootElement.Clone());
        var published = await _artifacts.PublishAsync(RequireWorkspace(taskId), spec, stagedPath, ct);
        _publishedArtifacts[taskId].Enqueue(published);
        return published;
    }

    private void AfterSuccess(long taskId, Func<CancellationToken, Task> action)
        => _postSuccessActions.GetOrAdd(taskId, _ => new ConcurrentQueue<Func<CancellationToken, Task>>()).Enqueue(action);

    private static bool RequiresArtifact(string taskType)
        => !taskType.Equals("ShotQA", StringComparison.OrdinalIgnoreCase)
           && !taskType.Equals("EpisodeQA", StringComparison.OrdinalIgnoreCase);

    private static PublishedArtifact? SelectPrimary(IEnumerable<PublishedArtifact> artifacts)
    {
        var ordered = new[] { ArtifactPurpose.Master, ArtifactPurpose.Episode, ArtifactPurpose.EpisodePreview, ArtifactPurpose.Video, ArtifactPurpose.Image, ArtifactPurpose.Audio, ArtifactPurpose.Subtitle, ArtifactPurpose.QaReport, ArtifactPurpose.Cover };
        var materialized = artifacts.ToArray();
        return ordered.Select(purpose => materialized.FirstOrDefault(artifact => artifact.Purpose == purpose)).FirstOrDefault(artifact => artifact is not null);
    }

    private string DefaultWorkflow(string taskType)
    {
        if (!taskType.Contains("video", StringComparison.OrdinalIgnoreCase) && !taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase))
            return Path.Combine(_settings.WorkflowsPath, "01_portrait_quality_api.json");

        throw new WorkflowContractException("WORKFLOW_REQUIRED", "视频任务必须在提交前冻结已审查的工作流路线");
    }
    private static string SafeFileName(string? value, string fallback)
    {
        var candidate = Path.GetFileName(value ?? string.Empty);
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string(candidate.Select(ch => invalid.Contains(ch) ? '_' : ch).ToArray()).Trim().TrimEnd('.');
        return string.IsNullOrWhiteSpace(cleaned) || cleaned is "." or ".." ? fallback : cleaned;
    }
    private IReadOnlyList<string> ResolveAssetPaths(JsonElement root, string property)
    {
        if (!TryGetPropertyIgnoreCase(root, property, out var values) || values.ValueKind != JsonValueKind.Array) return [];
        return values.EnumerateArray()
            .Where(value => value.ValueKind == JsonValueKind.String)
            .Select(value => value.GetString())
            .Select(path => _paths.TryResolveExisting(path, out var fullPath, out _) ? fullPath : null)
            .Where(path => path is not null)
            .Cast<string>()
            .ToArray();
    }
    private string? RelativeToData(string path) => _paths.TryResolveExisting(path, out _, out var relative) ? relative : null;
    private static bool TryGetPropertyIgnoreCase(JsonElement root, string name, out JsonElement value)
    {
        if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty(name, out value)) return true;
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

    private static bool TryGetObject(JsonElement root, string name, out JsonElement value)
    {
        if (TryGetPropertyIgnoreCase(root, name, out value) && value.ValueKind == JsonValueKind.Object) return true;
        value = default;
        return false;
    }

    private async Task<IReadOnlyList<LoraBinding>> ResolveLoraBindingsAsync(JsonElement inputRoot, JsonElement parameters, CancellationToken ct)
    {
        var ids = GetLongs(inputRoot, "loraIds").Concat(GetLongs(parameters, "loraIds")).Distinct().ToList();
        var names = GetStrings(parameters, "loraNames")
            .Concat(new[] { GetString(parameters, "loraName") }.Where(x => !string.IsNullOrWhiteSpace(x)).Cast<string>())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
        if (ids.Count == 0 && names.Count == 0) return [];
        var rows = await _repository.LorasAsync(ct);
        var bindings = new List<LoraBinding>();
        var used = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        void AddRow(IReadOnlyDictionary<string, object?> row)
        {
            var path = row.Text("path");
            if (string.IsNullOrWhiteSpace(path) || !_paths.IsAllowedExistingModelFile(path)) throw new InvalidOperationException($"LoRA 文件不存在或未扫描到: {row.Text("name") ?? path}");
            var loraRoot = Path.GetFullPath(Path.Combine(_settings.ModelsPath, "loras"));
            var fullPath = Path.GetFullPath(path);
            var comfyName = fullPath.StartsWith(loraRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                ? Path.GetRelativePath(loraRoot, fullPath).Replace(Path.DirectorySeparatorChar, '/')
                : Path.GetFileName(fullPath);
            if (!used.Add(comfyName)) return;
            var modelStrength = GetDouble(parameters, "loraStrengthModel", (double)row.Decimal("strength_model", 1));
            var clipStrength = GetDouble(parameters, "loraStrengthClip", (double)row.Decimal("strength_clip", 1));
            bindings.Add(new LoraBinding(comfyName, Math.Clamp(modelStrength, -2, 2), Math.Clamp(clipStrength, -2, 2)));
        }

        foreach (var id in ids)
        {
            var row = rows.FirstOrDefault(candidate => candidate.Long("id") == id)
                ?? throw new InvalidOperationException($"请求的 LoRA id 未在本地目录扫描到: {id}");
            AddRow(row);
        }
        foreach (var name in names)
        {
            var row = rows.FirstOrDefault(candidate =>
                string.Equals(candidate.Text("name"), name, StringComparison.OrdinalIgnoreCase)
                || string.Equals(Path.GetFileName(candidate.Text("path") ?? string.Empty), Path.GetFileName(name), StringComparison.OrdinalIgnoreCase));
            if (row is null) throw new InvalidOperationException($"请求的 LoRA 未在本地目录扫描到: {name}");
            AddRow(row);
        }
        return bindings;
    }

    private async Task<Dictionary<string, object?>> BuildSlotBindingsAsync(WorkflowExecutionPlan plan, IReadOnlyDictionary<string, string?> slotSources, IReadOnlyDictionary<string, ResolvedAssetReference>? slotAssets, CancellationToken ct)
    {
        var result = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        foreach (var slot in plan.Slots)
        {
            var source = slotSources.GetValueOrDefault(slot.Role) ?? plan.SlotPaths.GetValueOrDefault(slot.Role);
            if (!_paths.TryResolveExisting(source, out var fullPath, out var relativePath))
                throw new AssetValidationException($"工作流槽位 {slot.Role} 的来源在执行前已失效");
            var hash = await _ffmpeg.Sha256Async(fullPath, ct);
            if (!ReleaseEligibilityService.IsSha256ForExport(hash))
                throw new AssetValidationException($"工作流槽位 {slot.Role} 无法计算资产哈希");
            ResolvedAssetReference? asset = null;
            if (slotAssets is not null) slotAssets.TryGetValue(slot.Role, out asset);
            result[slot.Role] = new
            {
                relativePath,
                sha256 = hash,
                assetId = asset?.AssetId,
                assetVersion = asset?.AssetVersion,
                manifestId = asset?.ManifestId
            };
        }
        return result;
    }

    private static bool HasNodeClass(JsonObject workflow, string token)
        => workflow.Any(pair => pair.Value is JsonObject node && (node["class_type"]?.GetValue<string>() ?? string.Empty).Contains(token, StringComparison.OrdinalIgnoreCase));

    private static string? GetString(JsonElement root, params string[] names) => names.Select(n => TryGetPropertyIgnoreCase(root, n, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null).FirstOrDefault(x => !string.IsNullOrWhiteSpace(x));
    private static bool TryGetLong(JsonElement root, string name, out long value)
    {
        value = default;
        return TryGetPropertyIgnoreCase(root, name, out var element) && element.TryGetInt64(out value);
    }
    private static bool TryGetDouble(JsonElement root, string name, out double value)
    {
        value = default;
        return TryGetPropertyIgnoreCase(root, name, out var element) && element.TryGetDouble(out value);
    }
    private static string? GetSlotPath(JsonElement root, string role)
    {
        if (!TryGetPropertyIgnoreCase(root, "inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object || !TryGetPropertyIgnoreCase(slots, role, out var value)) return null;
        if (value.ValueKind == JsonValueKind.String) return value.GetString();
        return value.ValueKind == JsonValueKind.Object && TryGetPropertyIgnoreCase(value, "path", out var path) && path.ValueKind == JsonValueKind.String ? path.GetString() : null;
    }

    private static string ReadRetryReason(IReadOnlyDictionary<string, object?> shot)
    {
        try
        {
            using var document = shot.Json("videoQcJson");
            var root = document.RootElement;
            foreach (var propertyName in new[] { "faceIssues", "issues" })
            {
                if (!TryGetPropertyIgnoreCase(root, propertyName, out var issues) || issues.ValueKind != JsonValueKind.Array) continue;
                var text = string.Join("; ", issues.EnumerateArray().Select(item => item.ValueKind == JsonValueKind.String ? item.GetString() : item.GetRawText()).Where(value => !string.IsNullOrWhiteSpace(value)));
                if (!string.IsNullOrWhiteSpace(text)) return text;
            }
            var error = GetString(root, "errorType", "status");
            if (!string.IsNullOrWhiteSpace(error)) return error;
        }
        catch { }
        return shot.Text("qaStatus") ?? "Rejected";
    }

    private static bool ContainsAny(string? value, params string[] tokens)
        => !string.IsNullOrWhiteSpace(value) && tokens.Any(token => value.Contains(token, StringComparison.OrdinalIgnoreCase));

    private string ModelTracePath(string path)
    {
        var fullPath = Path.GetFullPath(path);
        var root = Path.GetFullPath(_settings.ModelsPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase)
            ? Path.GetRelativePath(_settings.ModelsPath, fullPath).Replace(Path.DirectorySeparatorChar, '/')
            : fullPath;
    }

    private static IReadOnlyList<string> GetReferenceInputs(JsonElement root)
        => GetStrings(root, "referenceImages")
            .Concat(GetStrings(root, "controlImages"))
            .Concat(new[] { GetString(root, "controlImagePath") }.Where(x => !string.IsNullOrWhiteSpace(x)).Cast<string>())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    private static IReadOnlyList<string> GetControlInputs(JsonElement root)
        => GetStrings(root, "controlImages")
            .Concat(new[] { GetString(root, "controlImagePath") }.Where(x => !string.IsNullOrWhiteSpace(x)).Cast<string>())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    private static IReadOnlyList<string> GetStrings(JsonElement root, string name)
    {
        if (!TryGetPropertyIgnoreCase(root, name, out var value) || value.ValueKind != JsonValueKind.Array) return [];
        return value.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)).Cast<string>().ToList();
    }
    private static IReadOnlyList<long> GetLongs(JsonElement root, string name)
    {
        if (!TryGetPropertyIgnoreCase(root, name, out var value) || value.ValueKind != JsonValueKind.Array) return [];
        return value.EnumerateArray().Where(x => x.TryGetInt64(out _)).Select(x => x.GetInt64()).ToList();
    }
    private static bool GetBool(JsonElement root, string name, bool fallback) => TryGetPropertyIgnoreCase(root, name, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean() : fallback;
    private static int? GetInt(JsonElement root, string name) => TryGetPropertyIgnoreCase(root, name, out var value) && value.TryGetInt32(out var result) ? result : null;
    private static long? GetLong(JsonElement root, string name) => TryGetPropertyIgnoreCase(root, name, out var value) && value.TryGetInt64(out var result) ? result : null;
    private static decimal GetDecimal(JsonElement root, string name, decimal fallback) => TryGetPropertyIgnoreCase(root, name, out var value) && value.TryGetDecimal(out var result) ? result : fallback;
    private static double GetDouble(JsonElement root, string name, double fallback) => TryGetPropertyIgnoreCase(root, name, out var value) && value.TryGetDouble(out var result) ? result : fallback;

    private static string StableTaskKey(params string?[] values)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", values.Select(x => x ?? "")))))[..24].ToLowerInvariant();

    private async Task<long?> FindWorkflowIdAsync(string fileName, CancellationToken ct)
        => (await _repository.WorkflowsAsync(ct)).FirstOrDefault(row =>
            string.Equals(Path.GetFileName(row.Text("path") ?? ""), fileName, StringComparison.OrdinalIgnoreCase))?.LongOrNull("id");

    private static JsonObject BuildVideoSlotObject(string firstFrame, bool withGuide)
    {
        var slots = new JsonObject { ["firstFrame"] = firstFrame };
        if (withGuide) slots["guideFrame"] = firstFrame;
        return slots;
    }

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
