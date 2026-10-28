namespace VideoStudio.Server;

/// <summary>
/// The release gate deliberately separates a playable preview from a publishable
/// episode. A low-resolution I2V result can be useful for review, but it must not
/// silently become the formal episode source.
/// </summary>
public sealed record EpisodeSourceGate(
    long ShotId,
    int ShotNumber,
    string Title,
    string QaStatus,
    string? PreviewPath,
    string? FinalVideoPath,
    string? SelectedPath,
    bool PreviewReady,
    bool FormalReady,
    FfmpegProbe? Probe,
    string? BlockedReason);

public sealed record EpisodeQualityGateSummary(
    int ShotCount,
    int PassedShotCount,
    int NeedReviewShotCount,
    int RejectedShotCount,
    int OpenBlockingIssueCount,
    bool AllShotsPassed,
    bool EpisodeApproved,
    bool QaLocked,
    bool PreviewReady,
    bool FormalReady,
    IReadOnlyList<string> FormalBlockedReasons,
    IReadOnlyList<EpisodeSourceGate> Sources);

public static class EpisodeQualityGateEvaluator
{
    public static async Task<EpisodeQualityGateSummary> EvaluateAsync(
        IReadOnlyDictionary<string, object?> episode,
        IReadOnlyList<Dictionary<string, object?>> shots,
        StudioRepository repository,
        FfmpegService ffmpeg,
        AssetPathPolicy paths,
        CancellationToken ct = default)
    {
        var targetWidth = episode.Int("outputWidth", 1920);
        var targetHeight = episode.Int("outputHeight", 1080);
        var sources = new List<EpisodeSourceGate>(shots.Count);
        foreach (var shot in shots)
        {
            var previewPath = FirstExistingVideoPath(paths, shot.Text("videoPath"), shot.Text("resultPath"), shot.Text("selectedKeyframePath"));
            var finalPath = FirstExistingVideoPath(paths, shot.Text("finalVideoPath"));
            var selectedPath = finalPath ?? previewPath;
            var probe = string.IsNullOrWhiteSpace(selectedPath) ? null : await ffmpeg.ProbeAsync(selectedPath, ct);
            var sourcePreviewReady = probe is { Width: > 0, Height: > 0 };
            var qaStatus = shot.Text("qaStatus") ?? "NotChecked";
            var formalReady = finalPath is not null
                && probe is { Width: > 0, Height: > 0 }
                && probe.Width == targetWidth
                && probe.Height == targetHeight
                && string.Equals(qaStatus, "Passed", StringComparison.OrdinalIgnoreCase);
            var reason = formalReady
                ? null
                : finalPath is null
                    ? "缺少正式增强视频"
                    : probe is not { Width: > 0, Height: > 0 }
                        ? "正式视频无法读取"
                        : probe.Width != targetWidth || probe.Height != targetHeight
                            ? $"正式视频分辨率为 {probe.Width}x{probe.Height}，目标为 {targetWidth}x{targetHeight}"
                            : $"镜头 QA 状态为 {qaStatus}，需要 Passed";
            sources.Add(new EpisodeSourceGate(
                shot.Long("id"),
                shot.Int("shotNumber"),
                shot.Text("title") ?? $"镜头 {shot.Int("shotNumber")}",
                qaStatus,
                previewPath,
                finalPath,
                selectedPath,
                sourcePreviewReady,
                formalReady,
                probe,
                reason));
        }

        var passed = shots.Count(x => string.Equals(x.Text("qaStatus"), "Passed", StringComparison.OrdinalIgnoreCase));
        var rejected = shots.Count(x => string.Equals(x.Text("qaStatus"), "Rejected", StringComparison.OrdinalIgnoreCase));
        var needReview = shots.Count - passed - rejected;
        var allShotsPassed = await repository.AllEpisodeShotsPassedAsync(episode.Long("id"), ct);
        var blockingIssueCount = await repository.OpenBlockingIssueCountAsync(episode.Long("id"), ct);
        var episodeApproved = string.Equals(episode.Text("qaStatus"), "Approved", StringComparison.OrdinalIgnoreCase);
        var qaLocked = episode.Bool("qaLocked");
        var previewReady = shots.Count > 0 && sources.All(x => x.PreviewReady);
        var formalBlockedReasons = new List<string>();
        if (shots.Count == 0) formalBlockedReasons.Add("本集没有镜头");
        if (!allShotsPassed) formalBlockedReasons.Add($"镜头 QA 尚未全部 Passed（{passed}/{shots.Count}）");
        if (!episodeApproved || !qaLocked) formalBlockedReasons.Add("Episode 尚未完成 Approved 并锁定");
        if (blockingIssueCount > 0) formalBlockedReasons.Add($"仍有 {blockingIssueCount} 个 Critical/Error QA 问题未关闭");
        var sourceFailures = sources.Count(x => !x.FormalReady);
        if (sourceFailures > 0) formalBlockedReasons.Add($"有 {sourceFailures} 个镜头缺少符合目标分辨率的正式增强视频");

        return new EpisodeQualityGateSummary(
            shots.Count,
            passed,
            needReview,
            rejected,
            blockingIssueCount,
            allShotsPassed,
            episodeApproved,
            qaLocked,
            previewReady,
            formalBlockedReasons.Count == 0,
            formalBlockedReasons,
            sources);
    }

    private static string? FirstExistingVideoPath(AssetPathPolicy policy, params string?[] paths)
    {
        foreach (var path in paths)
        {
            if (!string.IsNullOrWhiteSpace(path)
                && IsVideoPath(path)
                && policy.TryResolveExisting(path, out var fullPath, out _))
                return fullPath;
        }
        return null;
    }

    private static bool IsVideoPath(string path)
        => Path.GetExtension(path).ToLowerInvariant() is ".mp4" or ".mov" or ".webm" or ".mkv";
}
