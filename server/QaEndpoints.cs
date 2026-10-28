using System.Text.Json;
using System.Text.Json.Nodes;

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

        app.MapGet("/api/qa/episodes", async (long? projectId, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => Results.Ok((await repo.QaEpisodesAsync(projectId, ct)).Select(episode => ToPublicQaEpisode(episode, paths))));
        app.MapGet("/api/qa/episodes/{id:long}", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var shots = await repo.ShotsAsync(id, ct);
            var runs = await repo.QaRunsAsync(id, null, ct);
            var issues = await repo.QaIssuesAsync(id, null, ct);
            return Results.Ok(new
            {
                episode = ToPublicQaEpisode(episode, paths),
                shots = shots.Select(shot => new { shot = ToPublicQaShot(shot, paths), runs = runs.Where(x => x.LongOrNull("shotId") == shot.Long("id")).Select(ToPublicQaRun), issues = issues.Where(x => x.LongOrNull("shotId") == shot.Long("id")).Select(issue => ToPublicQaIssue(issue, paths)) }),
                episodeRuns = runs.Where(x => x.LongOrNull("shotId") is null).Select(ToPublicQaRun),
                episodeIssues = issues.Where(x => x.LongOrNull("shotId") is null).Select(issue => ToPublicQaIssue(issue, paths))
            });
        });
        app.MapGet("/api/qa/shots/{id:long}", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var shot = (await repo.QaShotAsync(id, ct)).FirstOrDefault();
            if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            return Results.Ok(new { shot = ToPublicQaShot(shot, paths), runs = (await repo.QaRunsAsync(null, id, ct)).Select(ToPublicQaRun), issues = (await repo.QaIssuesAsync(null, id, ct)).Select(issue => ToPublicQaIssue(issue, paths)) });
        });

        app.MapGet("/api/quality/repairs", async (long? shotId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.QualityRepairRunsAsync(shotId, ct)));
        app.MapGet("/api/quality/experiments", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.QualityExperimentsAsync(ct)));
        app.MapPost("/api/quality/experiments", async (QualityExperimentInput input, StudioRepository repo, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.Name)) return Results.BadRequest(new { error = "质量实验名称不能为空" });
            var id = await repo.CreateQualityExperimentAsync(input, ct);
            return Results.Created($"/api/quality/experiments/{id}", new { id });
        });
        app.MapGet("/api/quality/experiments/{id:long}/runs", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.QualityExperimentRunsAsync(id, ct)));
        app.MapPost("/api/quality/experiments/{id:long}/runs", async (long id, QualityExperimentRunInput input, StudioRepository repo, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.TestCase)) return Results.BadRequest(new { error = "实验测试用例不能为空" });
            var runId = await repo.AddQualityExperimentRunAsync(id, input, ct);
            return Results.Created($"/api/quality/experiments/{id}/runs/{runId}", new { id = runId });
        });
        app.MapGet("/api/quality/golden-samples", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.QualityGoldenSamplesAsync(ct)));
        app.MapPost("/api/quality/golden-samples", async (QualityGoldenSampleInput input, StudioRepository repo, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.SampleKey) || string.IsNullOrWhiteSpace(input.Path)) return Results.BadRequest(new { error = "黄金样本名称和路径不能为空" });
            var id = await repo.UpsertQualityGoldenSampleAsync(input, ct);
            return Results.Ok(new { id });
        });

        app.MapPost("/api/qa/shots/{id:long}/i2v-preflight", async (long id, I2VPreflightInput input, QualityPreflightService preflight, CancellationToken ct) =>
        {
            var result = await preflight.CheckI2VAsync(id, input, ct);
            return Results.Ok(result);
        });

        app.MapPost("/api/qa/technical-check", async (QaTechnicalCheckInput input, VideoQaService qa, CancellationToken ct) => Results.Ok(await qa.CheckTechnicalAsync(input, ct)));
        app.MapPost("/api/qa/face-image-check", async (FaceMediaCheckInput input, FaceQualityService faceQuality, CancellationToken ct) =>
        {
            var result = await faceQuality.AnalyzeImageAsync(input.Path, input.ReferenceImagePath, input.PortraitPreferred, ct);
            return Results.Ok(new { status = result.Rejected ? "Rejected" : "NeedReview", result.Score, result.Metrics, issues = result.Issues, manualReviewRequired = result.ManualReviewRequired });
        });
        app.MapPost("/api/qa/face-video-check", async (FaceMediaCheckInput input, FaceQualityService faceQuality, CancellationToken ct) =>
        {
            var result = await faceQuality.AnalyzeVideoAsync(input.Path, input.ReferenceImagePath, ct);
            return Results.Ok(new { status = result.Rejected ? "Rejected" : "NeedReview", result.Score, result.Metrics, issues = result.Issues, manualReviewRequired = result.ManualReviewRequired });
        });

        app.MapPost("/api/qa/shots/{id:long}/keyframe-check", async (long id, StudioRepository repo, FaceQualityService faceQuality, CancellationToken ct) =>
        {
            var shot = (await repo.QaShotAsync(id, ct)).FirstOrDefault();
            if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            var path = shot.Text("selectedKeyframePath") ?? shot.Text("inputImagePath");
            if (string.IsNullOrWhiteSpace(path)) return Results.BadRequest(new { error = "尚未选择关键帧候选" });
            var reference = (await repo.ShotReferencePathsAsync(id, ct)).FirstOrDefault();
            var result = await faceQuality.AnalyzeImageAsync(path, reference, shot.Int("height", 320) >= shot.Int("width", 512), ct);
            return Results.Ok(new { status = result.Rejected ? "Rejected" : "NeedReview", result.Score, result.Metrics, issues = result.Issues, manualReviewRequired = result.ManualReviewRequired });
        });

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
            var shotForReview = (await repo.QaShotAsync(id, ct)).FirstOrDefault();
            if (shotForReview is null) return Results.NotFound(new { error = "镜头不存在" });
            var gateError = ManualQaGate.Validate(decision ?? "", shotForReview.Text("qaStatus"), shotForReview.Int("qaVersion"), shotForReview.Text("qaResult"), input.OverrideHardFailure, input.Note);
            if (gateError is not null) return Results.Conflict(new { error = gateError });
            if (decision == "Passed" && (await repo.QaIssuesAsync(null, id, ct)).Any(issue => issue.Text("status") == "Open" && issue.Text("severity") is "Critical" or "Error"))
                return Results.Conflict(new { error = "仍有未关闭的严重问题，不能通过镜头审核" });
            if (decision == "Passed" && shotForReview is not null && shotForReview.Int("qaVersion", 0) <= 0)
                return Results.Conflict(new { error = "请先执行自动镜头 QA，再进行人工 Passed" });
            if (decision == "Passed" && shotForReview?.Text("qaStatus") == "Rejected" && (!input.OverrideHardFailure || string.IsNullOrWhiteSpace(input.Note)))
                return Results.Conflict(new { error = "自动 QA 已 Rejected；如人工确认可通过，必须勾选 OverrideHardFailure 并填写复核说明" });
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
            var gateError = ManualQaGate.Validate(decision, episode.Text("qaStatus"), episode.Int("qaVersion"), episode.Text("qaResult"), input.OverrideHardFailure, input.Note);
            if (gateError is not null) return Results.Conflict(new { error = gateError });
            if (decision == "Approved")
            {
                if (string.Equals(episode.Text("qaStatus"), "Rejected", StringComparison.OrdinalIgnoreCase) && (!input.OverrideHardFailure || string.IsNullOrWhiteSpace(input.Note)))
                    return Results.Conflict(new { error = "自动 Episode QA 已 Rejected；如人工确认可批准，必须勾选 OverrideHardFailure 并填写复核说明" });
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
            try
            {
                var queued = await queue.QueueQaRetryAsync(id, preset.MaxAutoRetries, ct);
                if (!queued) return Results.Conflict(new { status = "NeedManualReview", error = "原任务没有可继承的显式路线，或失败原因没有对应的定向参数调整；请人工选择替代方案" });
                var latest = await repo.LatestVideoTaskForShotAsync(id, ct);
                var taskId = latest?.LongOrNull("id");
                return Results.Accepted(taskId is { } value ? $"/api/tasks/{value}" : $"/api/qa/shots/{id}", new { taskId, status = "VideoGenerating", retry = true, policy = "inherit-original-route-and-action" });
            }
            catch (WorkflowContractException ex)
            {
                return Results.UnprocessableEntity(new { error = ex.Message, code = ex.Code, retry = false });
            }
        });

        app.MapGet("/api/qa/episodes/{id:long}/release-eligibility", async (long id, StudioRepository repo, FfmpegService ffmpeg, AssetPathPolicy paths, ReleaseEligibilityService release, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            return Results.Ok(await release.EvaluateAsync(episode, await repo.ShotsAsync(id, ct), repo, ffmpeg, paths, null, ct));
        });

        app.MapGet("/api/qa/episodes/{id:long}/release-candidates", async (long id, ReleaseCandidateRepository candidates, CancellationToken ct) =>
        {
            try { return Results.Ok(await candidates.ListAsync(id, ct)); }
            catch (MySqlConnector.MySqlException ex) when (ex.Number == 1146) { return Results.Problem("发布候选包表尚未应用迁移 009；未读取候选包", statusCode: StatusCodes.Status503ServiceUnavailable); }
        });

        app.MapPost("/api/qa/episodes/{id:long}/release-candidates", async (long id, ReleaseCandidateInput input, HttpRequest request, StudioRepository repo, FfmpegService ffmpeg, AssetPathPolicy paths, ReleaseEligibilityService release, ReleaseCandidateRepository candidates, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var eligibility = await release.EvaluateAsync(episode, await repo.ShotsAsync(id, ct), repo, ffmpeg, paths, input, ct);
            try
            {
                var idempotencyKey = request.Headers["Idempotency-Key"].FirstOrDefault()?.Trim();
                var candidate = await candidates.CreateAsync(episode.LongOrNull("projectId") ?? 0, id, eligibility, input, idempotencyKey, ct);
                return Results.Json(new { candidate, eligibility, uploadPerformed = false, publicReleasePerformed = false }, statusCode: eligibility.CanCreateCandidate ? StatusCodes.Status201Created : StatusCodes.Status422UnprocessableEntity);
            }
            catch (IdempotencyConflictException ex) { return Results.Conflict(new { error = ex.Message }); }
            catch (MySqlConnector.MySqlException ex) when (ex.Number == 1146)
            {
                return Results.Problem("发布候选包表尚未应用迁移 009；未创建候选包、未上传、未公开发布", statusCode: StatusCodes.Status503ServiceUnavailable);
            }
        });

        app.MapPost("/api/qa/episodes/{id:long}/export", async (long id, QaExportInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, ReleaseEligibilityService release, FfmpegService ffmpeg, AssetPathPolicy paths, ReleaseCandidateRepository candidates, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(id, ct)).FirstOrDefault();
            if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            if (!episode.Bool("qaLocked") || !string.Equals(episode.Text("qaStatus"), "Approved", StringComparison.OrdinalIgnoreCase)) return Results.Conflict(new { error = "Episode 必须先 Approved 才能导出" });
            if (input.CandidateId is not > 0) return Results.BadRequest(new { error = "导出必须明确指定 candidateId；不会自动选择历史 Ready 候选" });
            try
            {
                var candidate = await candidates.GetAsync(input.CandidateId.Value, id, ct);
                if (candidate is null) return Results.Conflict(new { error = "指定的发布候选包不存在或不属于当前 Episode" });
                var validation = await release.ValidateCandidateForExportAsync(candidate, id, repo, ffmpeg, paths, ct);
                if (!validation.Valid)
                {
                    if (validation.ShouldExpire) await candidates.MarkExpiredAsync(candidate.Id, validation.Reason, ct);
                    return Results.Conflict(new { error = validation.Reason, candidateId = candidate.Id, candidateVersion = candidate.Version, expired = validation.ShouldExpire, validation.CurrentEligibility.BlockingReasons });
                }
                var requestKey = request.Headers["Idempotency-Key"].FirstOrDefault()?.Trim();
                if (string.IsNullOrWhiteSpace(requestKey)) requestKey = $"qa-export:{id}:candidate:{candidate.Id}:v{candidate.Version}:{candidate.SourceManifestSha256[..16]}";
                var parameters = JsonSerializer.SerializeToDocument(new
                {
                    candidateId = candidate.Id,
                    candidateVersion = candidate.Version,
                    candidateSnapshotSha256 = candidate.SourceManifestSha256,
                    input.IncludeSubtitles,
                    input.IncludeCover
                }).RootElement.Clone();
                var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = episode.LongOrNull("projectId"), EpisodeId = id, TaskType = "QAExport", ResourceClass = "CPU", Stage = "Release", Priority = -5, MaxRetries = 0, IdempotencyKey = requestKey, Parameters = parameters }, ct);
                if (!await candidates.MarkExportTaskAsync(candidate.Id, taskId, ct))
                {
                    await queue.CancelAsync(taskId, ct);
                    return Results.Conflict(new { error = "候选包在排队过程中已失效，未执行导出", candidateId = candidate.Id });
                }
                queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "Pending", candidateId = candidate.Id, candidateVersion = candidate.Version, candidateSnapshotSha256 = candidate.SourceManifestSha256 });
            }
            catch (IdempotencyConflictException ex) { return Results.Conflict(new { error = ex.Message }); }
            catch (MySqlConnector.MySqlException ex) when (ex.Number == 1146) { return Results.Conflict(new { error = "发布候选包表尚未应用迁移 009，未执行导出" }); }
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

    private static object ToPublicQaEpisode(IReadOnlyDictionary<string, object?> episode, AssetPathPolicy paths)
    {
        string? AssetPath(string field) => paths.TryResolveExisting(episode.Text(field), out _, out var relative) ? relative : null;
        return new
        {
            id = episode.Long("id"),
            projectId = episode.LongOrNull("projectId"),
            projectName = episode.Text("projectName"),
            episodeNumber = episode.Int("episodeNumber", 1),
            name = episode.Text("name"),
            description = episode.Text("description"),
            status = episode.Text("status"),
            targetSeconds = episode["targetSeconds"],
            outputFps = episode.Int("outputFps", 30),
            outputWidth = episode.Int("outputWidth", 1920),
            outputHeight = episode.Int("outputHeight", 1080),
            qaStatus = episode.Text("qaStatus"),
            overallScore = episode["overallScore"],
            qaVersion = episode.Int("qaVersion"),
            qaLocked = episode.Bool("qaLocked"),
            shotCount = episode.Int("shotCount"),
            passedShotCount = episode.Int("passedShotCount"),
            rejectedShotCount = episode.Int("rejectedShotCount"),
            blockingIssueCount = episode.Int("blockingIssueCount"),
            outputAssetPath = AssetPath("outputPath"),
            subtitleAssetPath = AssetPath("subtitlePath"),
            coverAssetPath = AssetPath("coverPath"),
            createdAt = episode["createdAt"],
            updatedAt = episode["updatedAt"]
        };
    }

    private static object ToPublicQaShot(IReadOnlyDictionary<string, object?> shot, AssetPathPolicy paths)
    {
        string? AssetPath(string field) => paths.TryResolveExisting(shot.Text(field), out _, out var relative) ? relative : null;
        return new
        {
            id = shot.Long("id"),
            projectId = shot.LongOrNull("projectId"),
            episodeId = shot.LongOrNull("episodeId"),
            shotNumber = shot.Int("shotNumber"),
            title = shot.Text("title"),
            sceneId = shot.LongOrNull("sceneId"),
            sceneName = shot.Text("sceneName"),
            status = shot.Text("status"),
            durationSeconds = shot["durationSeconds"],
            qaStatus = shot.Text("qaStatus"),
            qaScore = shot["qaScore"],
            qaVersion = shot.Int("qaVersion"),
            prompt = shot.Text("prompt"),
            inputImageAssetPath = AssetPath("inputImagePath"),
            selectedKeyframeAssetPath = AssetPath("selectedKeyframePath"),
            videoAssetPath = AssetPath("videoPath"),
            finalVideoAssetPath = AssetPath("finalVideoPath"),
            resultAssetPath = AssetPath("resultPath"),
            createdAt = shot["createdAt"],
            updatedAt = shot["updatedAt"]
        };
    }

    private static object ToPublicQaRun(IReadOnlyDictionary<string, object?> run) => new
    {
        id = run.Long("id"),
        episodeId = run.LongOrNull("episodeId"),
        shotId = run.LongOrNull("shotId"),
        qaVersion = run.Int("qaVersion"),
        presetName = run.Text("presetName"),
        runType = run.Text("runType"),
        mode = run.Text("mode"),
        status = run.Text("status"),
        score = run["score"],
        issueCount = run.Int("issueCount"),
        startedAt = run["startedAt"],
        finishedAt = run["finishedAt"],
        createdAt = run["createdAt"]
    };

    private static object ToPublicQaIssue(IReadOnlyDictionary<string, object?> issue, AssetPathPolicy paths)
    {
        var available = paths.TryResolveExisting(issue.Text("framePath"), out _, out var frameAssetPath);
        return new
        {
            id = issue.Long("id"),
            qaRunId = issue.LongOrNull("qaRunId"),
            episodeId = issue.LongOrNull("episodeId"),
            shotId = issue.LongOrNull("shotId"),
            issueType = issue.Text("issueType"),
            severity = issue.Text("severity"),
            description = issue.Text("description"),
            frameTime = issue["frameTime"],
            frameAssetPath = available ? frameAssetPath : null,
            frameMediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(frameAssetPath)}" : null,
            status = issue.Text("status"),
            createdAt = issue["createdAt"]
        };
    }

    private static JsonObject BuildVideoSlots(string firstFrame, bool withGuide)
    {
        var slots = new JsonObject { ["firstFrame"] = firstFrame };
        if (withGuide) slots["guideFrame"] = firstFrame;
        return slots;
    }
}
