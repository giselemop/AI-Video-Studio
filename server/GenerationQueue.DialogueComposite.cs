using System.Text.Json;
using System.Text.Json.Nodes;
namespace VideoStudio.Server;
public sealed partial class GenerationQueue
{
    private async Task ExecuteDialogueCompositeAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null || row.LongOrNull("productionRunId") is not null || row.Text("resourceClass") != "CPU")
            throw new AssetValidationException("对话画面合成仅允许独立CPU预览");
        using var doc = row.Json("inputJson"); var p = doc.RootElement;
        if (p.TryGetProperty("parameters", out var nested)) p = nested;
        var service = new DialogueComposeService(_settings, _paths);
        await service.RunAsync(p, null, ct);
        var manifest = _paths.RequireExisting(GetString(p, "manifest"), "对话合成清单缺失");
        var request = JsonNode.Parse(await File.ReadAllTextAsync(manifest, ct))!.AsObject();
        var width = request["width"]!.GetValue<int>(); var height = request["height"]!.GetValue<int>();
        var frames = request["frames"]!.GetValue<int>(); var fps = request["fps"]!.GetValue<decimal>();
        var phase = request["phase"]!.GetValue<string>();
        var profile = GetString(p, "compositionProfile") ?? "dialogue-compose-v1";
        var hybrid = profile == "dialogue-hybrid-compose-v1";
        var sync = profile is "dialogue-sync-compose-v1" or "dialogue-hybrid-compose-v1";
        if (profile is "dialogue-stable-compose-v1" or "dialogue-eye-hair-guard-v1" && phase != "merge")
            throw new InvalidOperationException("稳定合成分支仅开放双人原画幅合并");
        if (!(phase == "merge" && width == 1024 && height == 576 && frames == (sync ? 57 : 151) && fps == 25)
            && !(phase == "detail" && width == 2560 && height == 1440 && (hybrid ? new[] { 54 } : sync ? new[] { 48, 54 } : new[] { 53, 43, 144 }).Contains(frames) && fps == 24))
            throw new InvalidOperationException("对话合成规格未登记");
        var output = _artifacts.CreateStagedPath(RequireWorkspace(row.Long("id")), "dialogue_visual.mp4", "dialogue_visual.mp4");
        await service.RunAsync(p, output, ct);
        var receiptPath = output + ".dialogue.json";
        var receipt = JsonNode.Parse(await File.ReadAllTextAsync(receiptPath, ct))!.AsObject();
        if (receipt["status"]?.GetValue<string>() != "Passed" || receipt["profile"]?.GetValue<string>() != profile
            || receipt["manifestSha256"]?.GetValue<string>() != GetString(p, "manifestSha256")
            || receipt["phase"]?.GetValue<string>() != phase || receipt["width"]?.GetValue<int>() != width || receipt["height"]?.GetValue<int>() != height
            || receipt["fps"]?.GetValue<decimal>() != fps || receipt["frameCount"]?.GetValue<int>() != frames
            || !string.Equals(await _ffmpeg.Sha256Async(output, ct), receipt["outputSha256"]?.GetValue<string>(), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("对话合成回执与输入/输出不符");
        var qc = await _quality.CheckVideoAsync(output, frames / fps, width, height, fps, ct, frames);
        if (!qc.Passed) throw new InvalidOperationException("对话合成真实视频规格不符");
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, "dialogue_" + phase + ".mp4", ct);
        qc.Metrics["contentReview"] = "NeedReview"; qc.Metrics["publicationStatus"] = "Blocked";
        await _repository.UpdateResultQualityAsync(row.Long("id"), published.FullPath, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
        await PublishArtifactAsync(row, ArtifactPurpose.QaReport, receiptPath, "dialogue_composition_receipt.json", ct);
    }
}
