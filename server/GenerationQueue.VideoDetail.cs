using System.Text.Json;

namespace VideoStudio.Server;

public sealed partial class GenerationQueue
{
    private async Task ExecuteAudioRemuxAsync(IReadOnlyDictionary<string, object?> row, JsonElement p,
        IReadOnlyList<string> files, string output, string outputName, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null || row.LongOrNull("productionRunId") is not null
            || files.Count != 1 || new[] { "singlePass", "audioTracks", "originalAudioVolume", "subtitlePath", "trimStartSeconds", "targetDurationSeconds", "targetWidth", "targetHeight" }.Any(k => p.TryGetProperty(k, out _)))
            throw new AssetValidationException("无损换轨仅接收独立预览的单个同规格视频，不允许混用转码参数");
        if (!_paths.TryResolveExisting(GetString(p, "audioStreamCopyFrom"), out var audioSource, out _)) throw new AssetValidationException("完整音轨源不在受控目录");
        if (await _ffmpeg.Sha256Async(files[0], ct) != GetString(p, "videoSha256") || await _ffmpeg.Sha256Async(audioSource, ct) != GetString(p, "audioStreamCopySha256"))
            throw new AssetValidationException("无损换轨源文件已改变");
        var source = (await _ffmpeg.ProbeAsync(files[0], ct))!;
        if (GetInt(p, "targetFps") is { } requestedFps && requestedFps != source.Fps) throw new AssetValidationException("无损换轨不能改变帧率");
        var resolutionOptIn = p.TryGetProperty("allowResolutionDifference", out var resolutionFlag);
        if (resolutionOptIn && resolutionFlag.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new AssetValidationException("跨分辨率无损换轨选项必须为布尔值");
        await _ffmpeg.RemuxAudioAsync(files[0], audioSource, output, ct, resolutionOptIn && resolutionFlag.ValueKind == JsonValueKind.True);
        var qc = await _quality.CheckVideoAsync(output, (decimal)source.DurationSeconds!.Value, source.Width!.Value, source.Height!.Value, (int)source.Fps!.Value, ct, (int)source.FrameCount!.Value);
        if (!qc.Passed) throw new InvalidOperationException("无损换轨实际规格核验失败");
        qc.Metrics["videoEncodingPasses"] = 0; qc.Metrics["audioStreamCopy"] = true; qc.Metrics["contentReview"] = "NeedReview";
        qc.Metrics["allowResolutionDifference"] = resolutionOptIn && resolutionFlag.ValueKind == JsonValueKind.True;
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, outputName, ct);
        await _repository.UpdateResultQualityAsync(row.Long("id"), published.FullPath, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
    }

    private async Task ExecuteDetailExportAsync(IReadOnlyDictionary<string, object?> row, JsonElement p,
        IReadOnlyList<string> files, string output, string outputName, int fps, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null || row.LongOrNull("productionRunId") is not null) throw new AssetValidationException("保细节独立预览不替代正式Episode审核路线");
        string? subtitle = null;
        if (!string.IsNullOrWhiteSpace(GetString(p, "subtitlePath")))
        {
            subtitle = _paths.RequireExisting(GetString(p, "subtitlePath"), "一次编码字幕必须位于受控Data目录");
            if (!string.Equals(Path.GetExtension(subtitle), ".srt", StringComparison.OrdinalIgnoreCase)) throw new AssetValidationException("一次编码仅接收SRT字幕");
        }
        var tracks = new List<FfmpegAudioTrack>();
        if (p.TryGetProperty("audioTracks", out var array))
            foreach (var t in array.EnumerateArray())
            {
                if (!_paths.TryResolveExisting(GetString(t, "path"), out var path, out _)) throw new AssetValidationException("旁白路径无效");
                tracks.Add(new(path, GetDouble(t, "volume", 1), GetDouble(t, "startSeconds", 0), GetDouble(t, "tempo", 1)));
            }
        var width = GetInt(p, "targetWidth") ?? 1920; var height = GetInt(p, "targetHeight") ?? 1080;
        var duration = GetDouble(p, "targetDurationSeconds", 0);
        await _ffmpeg.ExportSinglePassAsync(files, output, width, height, fps, duration,
            GetDouble(p, "trimStartSeconds", 0), tracks, GetDouble(p, "originalAudioVolume", 1), ct, subtitle);
        var qc = await _quality.CheckVideoAsync(output, (decimal)duration, width, height, fps, ct, (int)Math.Round(duration * fps));
        if (!qc.Passed) throw new InvalidOperationException("保细节导出实际规格核验失败");
        qc.Metrics["videoEncodingPasses"] = 1; qc.Metrics["crf"] = 16; qc.Metrics["contentReview"] = "NeedReview";
        qc.Metrics["captionsInSameVideoEncode"] = subtitle is not null;
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, outputName, ct);
        await _repository.UpdateResultQualityAsync(row.Long("id"), published.FullPath, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
    }

    private async Task ExecuteSeedRestoreAsync(IReadOnlyDictionary<string, object?> row, CancellationToken ct)
    {
        if (IsFormal(row) || row.LongOrNull("episodeId") is not null || row.LongOrNull("shotId") is not null || row.LongOrNull("productionRunId") is not null || row.Text("resourceClass") != "GPU") throw new AssetValidationException("SeedVR2只接受受GPU锁保护的独立预览");
        using var doc = row.Json("inputJson"); var p = doc.RootElement;
        if (p.TryGetProperty("parameters", out var nested)) p = nested;
        var service = new SeedVr2Service(_settings);
        if (GetString(p, "engineVersion") != service.Identity) throw new InvalidOperationException("SeedVR2配置版本已改变，请重新预检");
        if (!_paths.TryResolveExisting(GetString(p, "input"), out var source, out _)) throw new AssetValidationException("修复源文件不在受控目录");
        var expected = GetString(p, "sourceSha256");
        if (await _ffmpeg.Sha256Async(source, ct) != expected) throw new AssetValidationException("修复源文件已改变");
        var probe = await _ffmpeg.ProbeAsync(source, ct);
        if (probe?.Width is not > 0 || probe.Height is not > 0 || probe.Width > 1920 || probe.Height > 1080 || probe.Fps != 24
            || probe.FrameCount is not > 0 or > 240) throw new InvalidOperationException("SeedVR2预览限1920×1080以内、24FPS、1–240帧");
        var outputSpec = SeedVr2Service.ResolveOutput(p, probe.Width.Value, probe.Height.Value);
        var strength = GetDouble(p, "strength", .65);
        if (!double.IsFinite(strength) || strength is < .25 or > 1) throw new InvalidOperationException("修复强度需为0.25–1");
        var cuts = p.TryGetProperty("cutFrames", out var cutArray) ? cutArray.EnumerateArray().Select(x => x.GetInt32()).ToArray() : [];
        if (cuts.Length > 8 || cuts.Any(x => x <= 0 || x >= probe.FrameCount) || !cuts.SequenceEqual(cuts.Distinct().Order())) throw new InvalidOperationException("镜头边界帧无效");
        await _comfy.EnsureIdleForExternalGpuAsync(ct);
        await _comfy.TryFreeMemoryAsync(ct);
        await WaitForGpuAsync(ct);
        var output = _artifacts.CreateStagedPath(RequireWorkspace(row.Long("id")), "seedvr2_restored.mp4", "seedvr2_restored.mp4");
        await service.RestoreAsync(source, expected!, output, strength, cuts, outputSpec.Width, outputSpec.Height, outputSpec.Profile, ct);
        if (await _ffmpeg.Sha256Async(source, ct) != expected) throw new AssetValidationException("修复期间源文件已改变");
        var qc = await _quality.CheckVideoAsync(output, (decimal)probe.DurationSeconds!.Value, outputSpec.Width, outputSpec.Height, 24, ct, (int)probe.FrameCount.Value);
        if (!qc.Passed) throw new InvalidOperationException("SeedVR2输出时长/帧数/尺寸校验失败");
        qc.Metrics["engine"] = "SeedVR2-3B-FP8"; qc.Metrics["strength"] = strength; qc.Metrics["sourceSha256"] = expected; qc.Metrics["contentReview"] = "NeedReview";
        qc.Metrics["outputProfile"] = outputSpec.Profile; qc.Metrics["sourceWidth"] = probe.Width; qc.Metrics["sourceHeight"] = probe.Height;
        var published = await PublishArtifactAsync(row, ArtifactPurpose.Video, output, "seedvr2_restored.mp4", ct);
        await _repository.UpdateResultQualityAsync(row.Long("id"), published.FullPath, qc.Score, JsonSerializer.Serialize(qc.Metrics), ct);
        await PublishArtifactAsync(row, ArtifactPurpose.QaReport, output + ".seedvr.json", "seedvr2_inference.json", ct);
    }
}
