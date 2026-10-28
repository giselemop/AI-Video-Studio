using System.Text.Json;

namespace VideoStudio.Server;

public sealed partial class GenerationQueue
{
    private async Task ExecuteSkinCompositeAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null
            || row.LongOrNull("productionRunId") is not null || row.Text("resourceClass") != "CPU")
            throw new AssetValidationException("局部肤质合成只允许独立CPU预览");
        using var doc = row.Json("inputJson"); var p = doc.RootElement;
        if (p.TryGetProperty("parameters", out var nested)) p = nested;
        var service = new SkinPilotService(_settings);
        if (GetString(p, "engineVersion") != service.Identity) throw new InvalidOperationException("局部肤质脚本版本已改变");
        await service.ValidateAsync(p, ct);
        var output = _artifacts.CreateStagedPath(RequireWorkspace(row.Long("id")), "skin_optimized.mp4", "skin_optimized.mp4");
        await service.ComposeAsync(p, output, ct);
        foreach (var item in new[] { (output, "skin_optimized_2k_2s.mp4", 2560, 1440),
            (output + ".original.mp4", "skin_original_720p_2s.mp4", 1280, 720),
            (output + ".qhd.mp4", "skin_current_2k_2s.mp4", 2560, 1440) })
        {
            var qc = await _quality.CheckVideoAsync(item.Item1, 2m, item.Item3, item.Item4, 24, ct, 48);
            if (!qc.Passed) throw new InvalidOperationException("肤质小样的实际尺寸/帧数/时长不符");
            var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, item.Item1, item.Item2, ct);
            if (item.Item1 == output)
            {
                qc.Metrics["contentReview"] = "NeedReview"; qc.Metrics["engine"] = "Local-Skin-Patch-OpticalFlow-v1";
                qc.Metrics["originalMouthPixelsProtectedBeforeEncoding"] = true;
                await _repository.UpdateResultQualityAsync(row.Long("id"), published.FullPath, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
            }
        }
        await PublishArtifactAsync(row, ArtifactPurpose.QaReport, output + ".skin.json", "skin_composite_receipt.json", ct);
    }
}
