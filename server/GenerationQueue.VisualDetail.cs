using System.Text.Json;
using System.Text.Json.Nodes;
namespace VideoStudio.Server;
public sealed partial class GenerationQueue
{
    private async Task ExecuteVisualDetailAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null || row.LongOrNull("productionRunId") is not null || row.Text("resourceClass") != "CPU")
            throw new AssetValidationException("细节回补只允许独立CPU预览");
        using var doc = row.Json("inputJson"); var p = doc.RootElement;
        if (p.TryGetProperty("parameters", out var nested)) p = nested;
        var service = new VisualDetailService(_settings, _paths);
        await service.RunAsync(p, null, ct);
        var output = _artifacts.CreateStagedPath(RequireWorkspace(row.Long("id")), "detail_recovered.mp4", "detail_recovered.mp4");
        await service.RunAsync(p, output, ct);
        var receiptPath = output + ".detail.json";
        var receipt = JsonNode.Parse(await File.ReadAllTextAsync(receiptPath, ct))!.AsObject();
        if (receipt["status"]?.GetValue<string>() != "Passed" || receipt["profile"]?.GetValue<string>() != "source-detail-residual-v1"
            || receipt["manifestSha256"]?.GetValue<string>() != p.GetProperty("manifestSha256").GetString()) throw new InvalidOperationException("细节回执不符");
        foreach (var pair in new[] { (output, "source_detail_recovered_2s.mp4", "outputSha256"), (output + ".baseline.mp4", "source_detail_baseline_same_encode_2s.mp4", "baselineSha256") })
        {
            if (!File.Exists(pair.Item1) || !string.Equals(await _ffmpeg.Sha256Async(pair.Item1, ct), receipt[pair.Item3]?.GetValue<string>(), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("细节实际输出哈希不符");
            var qc = await _quality.CheckVideoAsync(pair.Item1, 2m, 2560, 1440, 24, ct, 48);
            if (!qc.Passed) throw new InvalidOperationException("细节实际视频规格不符");
            await PublishArtifactAsync(row, ArtifactPurpose.Video, pair.Item1, pair.Item2, ct);
        }
        await PublishArtifactAsync(row, ArtifactPurpose.QaReport, receiptPath, "source_detail_receipt.json", ct);
    }
}
