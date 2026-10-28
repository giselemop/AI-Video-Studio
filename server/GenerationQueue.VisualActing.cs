using System.Text.Json;

namespace VideoStudio.Server;

public sealed partial class GenerationQueue
{
    private async Task ExecuteVisualActingAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null
            || row.LongOrNull("productionRunId") is not null || row.Text("resourceClass") != "GPU")
            throw new AssetValidationException("参考表演仅允许独立GPU预览，不替代正式审核");
        using var doc = row.Json("inputJson"); var p = doc.RootElement;
        if (p.TryGetProperty("parameters", out var nested)) p = nested;
        var service = new VisualActingService(_settings, _paths, _ffmpeg);
        var output = _artifacts.CreateStagedPath(RequireWorkspace(row.Long("id")), "visual_acting.mp4", "visual_acting.mp4");
        var result = await service.AnimateAsync(p, output, ct);
        var qc = await _quality.CheckVideoAsync(output, result.Duration,
            result.Width, result.Height, result.Fps, ct, result.Frames);
        if (!qc.Passed) throw new InvalidOperationException("参考表演实际视频未通过完整规格检查");
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, "local_visual_acting_pilot.mp4", ct);
        qc.Metrics["contentReview"] = "NeedReview"; qc.Metrics["publicationStatus"] = "Blocked";
        qc.Metrics["engine"] = "OfficialLivePortraitLocalPilot";
        qc.Metrics["repairProfile"] = GetString(p, "repairProfile") ?? "none";
        qc.Metrics["driverIsNewHumanPerformance"] = false;
        await _repository.UpdateResultQualityAsync(row.Long("id"), published.FullPath, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
        await PublishArtifactAsync(row, ArtifactPurpose.QaReport, result.Receipt, "local_visual_acting_receipt.json", ct);
        if (result.SupportMask is not null)
            await PublishArtifactAsync(row, ArtifactPurpose.Image, result.SupportMask, "dialogue_face_support.png", ct);
    }
}
