using System.Text.Json;

namespace VideoStudio.Server;

public static class VideoQaEndpoints
{
    public static void Map(WebApplication app)
    {
        app.MapGet("/api/qa/presets", async (StudioRepository repo, VideoQaService qa, CancellationToken ct) =>
        {
            try { return Results.Ok(await repo.QaPresetsAsync(ct)); }
            catch { return Results.Ok(new[] { await qa.GetPresetAsync("Draft", ct), await qa.GetPresetAsync("Standard", ct), await qa.GetPresetAsync("HighQuality", ct) }); }
        });

        app.MapGet("/api/qa/episodes", async (long? projectId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.QaEpisodesAsync(projectId, ct)));
        app.MapGet("/api/qa/episodes/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var shots = await repo.ShotsAsync(id, ct);
            var runs = await repo.QaRunsAsync(id, null, ct);
            var issues = await repo.QaIssuesAsync(id, null, ct);
            return Results.Ok(new { episode, shots = shots.Select(shot => new { shot, runs = runs.Where(x => x.LongOrNull("shotId") == shot.Long("id")), issues = issues.Where(x => x.LongOrNull("shotId") == shot.Long("id")) }), episodeRuns = runs.Where(x => x.LongOrNull("shotId") is null), episodeIssues = issues.Where(x => x.LongOrNull("shotId") is null) });
        });
        app.MapGet("/api/qa/shots/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) =>
        {
            var shot = (await repo.QaShotAsync(id, ct)).FirstOrDefault();
            if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            return Results.Ok(new { shot, runs = await repo.QaRunsAsync(null, id, ct), issues = await repo.QaIssuesAsync(null, id, ct) });
        });

        app.MapPost("/api/qa/technical-check", async (QaTechnicalCheckInput input, VideoQaService qa, CancellationToken ct) => Results.Ok(await qa.CheckTechnicalAsync(input, ct)));

        app.MapPost("/api/qa/shots/{id:long}/check", async (long id, QaCheckInput input, StudioRepository repo, GenerationQueue queue, VideoQaService qa, CancellationToken ct) =>
        {
            var shot = (await repo.QaShotAsync(id, ct)).FirstOrDefault();
            if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            var episodeId = shot.LongOrNull("episodeId");
            if (episodeId is null) return Results.BadRequest(new { error = "镜头没有所属 Episode" });
            var episode = (await repo.EpisodeAsync(episodeId.Value, ct)).FirstOrDefault();
            if (episode?.Bool("qaLocked") == true) return Results.Conflict(new { error = "Episode 已锁定，请先解锁后再验收" });
            var preset = await qa.GetPresetAsync(input.Preset, ct);
            await repo.SetShotQaStatusAsync(id, "AutoChecking", ct);
            var taskId = await repo.CreateTaskAsync(new TaskInput
            {
                ProjectId = shot.LongOrNull("projectId"), EpisodeId = episodeId, ShotId = id, TaskType = "ShotQA", ResourceClass = "CPU", Stage = "QA", Priority = -10, MaxRetries = 0,
                Parameters = JsonSerializer.SerializeToDocument(new { preset = preset.Name, autoRetry = input.AutoRetry }).RootElement.Clone()
            }, ct);
            queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "AutoChecking", preset = preset.Name });
        });

        app.MapPost("/api/qa/episodes/{id:long}/check", async (long id, QaCheckInput input, StudioRepository repo, GenerationQueue queue, VideoQaService qa, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            if (episode.Bool("qaLocked")) return Results.Conflict(new { error = "Episode 已锁定，请先解锁后再验收" });
            var preset = await qa.GetPresetAsync(input.Preset, ct);
            await repo.SetEpisodeQaStatusAsync(id, "Checking", ct);
            var taskId = await repo.CreateTaskAsync(new TaskInput
            {
                ProjectId = episode.LongOrNull("projectId"), EpisodeId = id, TaskType = "EpisodeQA", ResourceClass = "CPU", Stage = "QA", Priority = -10, MaxRetries = 0,
                Parameters = JsonSerializer.SerializeToDocument(new { preset = preset.Name, autoRetry = input.AutoRetry }).RootElement.Clone()
            }, ct);
            queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "Checking", preset = preset.Name });
        });

        app.MapPost("/api/qa/shots/{id:long}/review", async (long id, QaReviewInput input, StudioRepository repo, CancellationToken ct) =>
        {
            var decision = NormalizeShotDecision(input.Decision);
            if (decision is null) return Results.BadRequest(new { error = "镜头审核决定必须是 Passed、Rejected 或 NeedReview" });
            if (!(await repo.QaShotAsync(id, ct)).Any()) return Results.NotFound(new { error = "镜头不存在" });
            return Results.Ok(new { updated = await repo.ReviewShotQaAsync(id, decision, input.Reviewer, input.Note, ct), status = decision });
        });

        app.MapPost("/api/qa/episodes/{id:long}/review", async (long id, QaReviewInput input, StudioRepository repo, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var decision = NormalizeEpisodeDecision(input.Decision);
            if (decision is null) return Results.BadRequest(new { error = "Episode 审核决定必须是 Passed、Rejected、NeedReview 或 Approved" });
            if (decision == "Approved")
            {
                if (!await repo.AllEpisodeShotsPassedAsync(id, ct)) return Results.Conflict(new { error = "所有镜头必须先 Passed 才能 Approved" });
                if (await repo.EpisodeHasOpenBlockingIssueAsync(id, ct)) return Results.Conflict(new { error = "仍有未关闭的 Critical/Error 问题，不能 Approved" });
            }
            return Results.Ok(new { updated = await repo.ReviewEpisodeQaAsync(id, decision, input.Reviewer, input.Note, ct), status = decision, locked = decision == "Approved" });
        });

        app.MapPost("/api/qa/episodes/{id:long}/unlock", async (long id, StudioRepository repo, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            return Results.Ok(new { updated = await repo.UnlockEpisodeQaAsync(id, ct), status = "NeedReview", locked = false });
        });

        app.MapPost("/api/qa/issues/{id:long}/resolve", async (long id, QaIssueResolveInput input, StudioRepository repo, CancellationToken ct) =>
        {
            var status = input.Status is "Resolved" or "Ignored" or "Open" ? input.Status : "Ignored";
            return Results.Ok(new { updated = await repo.ResolveQaIssueAsync(id, status, input.Note, ct), status });
        });

        app.MapPost("/api/qa/shots/{id:long}/regenerate", async (long id, QaCheckInput input, StudioRepository repo, GenerationQueue queue, VideoQaService qa, CancellationToken ct) =>
        {
            var shot = (await repo.QaShotAsync(id, ct)).FirstOrDefault();
            if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            var episode = shot.LongOrNull("episodeId") is { } episodeId ? (await repo.EpisodeAsync(episodeId, ct)).FirstOrDefault() : null;
            if (episode?.Bool("qaLocked") == true) return Results.Conflict(new { error = "Episode 已锁定，不能重新生成" });
            var preset = await qa.GetPresetAsync(input.Preset, ct);
            if (!await repo.IncrementQaRetryAsync(id, preset.MaxAutoRetries, ct)) return Results.Conflict(new { status = "NeedManualReview", error = $"已达到 {preset.MaxAutoRetries} 次自动重生成上限" });
            var inputImage = shot.Text("selectedKeyframePath") ?? shot.Text("inputImagePath");
            if (string.IsNullOrWhiteSpace(inputImage) || !File.Exists(inputImage)) return Results.BadRequest(new { error = "没有可用的关键帧/参考图" });
            var fps = shot.Decimal("fps", 24); var duration = shot.Decimal("durationSeconds", 5);
            var retryCount = shot.Int("qaRetryCount", 0) + 1;
            var previousStatus = shot.Text("qaStatus") ?? "Rejected";
            var previousScore = shot.Decimal("qaScore", 0);
            var previousSeed = shot.LongOrNull("seed");
            var retrySeed = Random.Shared.NextInt64(1, 900000000);
            if (previousSeed is { } seed && retrySeed == seed) retrySeed = seed == 899999999 ? 1 : seed + 1;
            var taskId = await repo.CreateTaskAsync(new TaskInput
            {
                ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = id, TaskType = "ImageToVideo", WorkflowId = shot.LongOrNull("workflowId"), InputImagePath = inputImage, Priority = 5, MaxRetries = 2, Stage = "QA-Retry",
                Parameters = JsonSerializer.SerializeToDocument(new { positive = shot.Text("prompt"), negative = shot.Text("negativePrompt"), seed = retrySeed, width = shot.Int("width", 512), height = shot.Int("height", 320), frames = Math.Clamp((int)Math.Round(duration * fps), 49, 241), fps, duration, action = shot.Text("action"), cameraMotion = shot.Text("cameraMotion"), qaRetry = true, retryCount, previousQaStatus = previousStatus, previousQaScore = previousScore, retryReason = $"Shot QA {previousStatus}", changedParameters = new { seed = retrySeed }, preset = preset.Name, autoRetry = input.AutoRetry }).RootElement.Clone()
            }, ct);
            await repo.LogAsync("qa.retry", $"Shot {id} 第 {retryCount} 次 QA 回炉；原状态 {previousStatus}，原分数 {previousScore:0.##}，修改 Seed 为 {retrySeed}", taskId, "Warning", ct);
            await repo.SetShotQaStatusAsync(id, "AutoChecking", ct); await repo.UpdateShotStatusAsync(id, "VideoGenerating", ct); queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "VideoGenerating", retry = true });
        });

        app.MapPost("/api/qa/episodes/{id:long}/export", async (long id, QaExportInput input, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            if (!episode.Bool("qaLocked") || !string.Equals(episode.Text("status"), "Approved", StringComparison.OrdinalIgnoreCase)) return Results.Conflict(new { error = "Episode 必须先 Approved 才能导出" });
            var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = episode.LongOrNull("projectId"), EpisodeId = id, TaskType = "QAExport", ResourceClass = "CPU", Stage = "Release", Priority = -5, MaxRetries = 0, Parameters = JsonSerializer.SerializeToDocument(input).RootElement.Clone() }, ct);
            queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "Pending" });
        });
    }

    private static string? NormalizeShotDecision(string value) => value switch
    {
        "Passed" or "通过" => "Passed", "Rejected" or "拒绝" => "Rejected", "NeedReview" or "人工复核" => "NeedReview", _ => null
    };

    private static string? NormalizeEpisodeDecision(string value) => value switch
    {
        "Passed" or "通过" => "Passed", "Rejected" or "拒绝" => "Rejected", "NeedReview" or "人工复核" => "NeedReview", "Approved" or "批准发布" => "Approved", _ => null
    };
}
