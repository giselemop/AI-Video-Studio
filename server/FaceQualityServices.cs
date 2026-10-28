using System.Diagnostics;
using System.Globalization;

namespace VideoStudio.Server;

/// <summary>
/// Lightweight CPU-only face-region checks. This is intentionally a safety net,
/// not a replacement for a landmark/face-recognition model. It catches bad
/// layouts, large identity drift and extreme frame changes without adding a
/// multi-GB model to the 4070 workflow.
/// </summary>
public sealed class FaceQualityService
{
    private const int SampleWidth = 96;
    private const int SampleHeight = 96;
    private const int FeatureWidth = 16;
    private const int FeatureHeight = 16;
    private const int Channels = 3;
    private const int BytesPerFrame = SampleWidth * SampleHeight * Channels;
    private const int MaxVideoFrames = 24;
    private readonly StudioSettings _settings;
    private readonly FfmpegService _ffmpeg;
    private readonly AssetPathPolicy _paths;
    private readonly ILogger<FaceQualityService> _logger;

    public FaceQualityService(StudioSettings settings, FfmpegService ffmpeg, AssetPathPolicy paths, ILogger<FaceQualityService> logger)
    {
        _settings = settings;
        _ffmpeg = ffmpeg;
        _paths = paths;
        _logger = logger;
    }

    public async Task<FaceImageQualityEvaluation> AnalyzeImageAsync(string path, string? referencePath = null, bool portraitPreferred = false, CancellationToken ct = default)
    {
        var metrics = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["assetPath"] = _paths.TryResolveExisting(path, out _, out var assetPath) ? assetPath : null,
            ["detector"] = "cpu-face-roi-proxy-no-landmark-model",
            ["manualReviewRequired"] = true
        };
        var issues = new List<string>();
        if (!TryAllowedFile(path, out var fullPath))
            return new FaceImageQualityEvaluation(true, true, 0, metrics, ["关键帧不存在或不在允许目录"]);

        var probe = await _ffmpeg.ProbeAsync(fullPath, ct);
        if (probe?.Width is not > 0 || probe.Height is not > 0)
            return new FaceImageQualityEvaluation(true, true, 0, metrics, ["关键帧无法读取尺寸"]);

        var aspect = (double)probe.Width.Value / probe.Height.Value;
        metrics["width"] = probe.Width;
        metrics["height"] = probe.Height;
        metrics["aspect"] = Math.Round(aspect, 4);
        metrics["portraitPreferred"] = portraitPreferred;
        if (portraitPreferred && (aspect < .58 || aspect > 1.12))
            issues.Add($"角色标准图画幅异常：{probe.Width}x{probe.Height}，应以竖幅单人图为主");

        var frames = await DecodeFramesAsync(fullPath, 1, ct);
        if (frames.Count == 0)
            return new FaceImageQualityEvaluation(true, true, 0, metrics, ["关键帧无法解码供脸部检查"]);

        var feature = BuildFeature(frames[0]);
        var panelScore = PanelLayoutScore(frames[0]);
        var detailScore = Math.Clamp(feature.EdgeEnergy * 2.6, 0, 1);
        metrics["panelLayoutScore"] = Math.Round(panelScore, 4);
        metrics["faceRegionDetailScore"] = Math.Round(detailScore, 4);
        metrics["faceRegionMean"] = Math.Round(feature.Mean, 4);
        metrics["faceRegionContrast"] = Math.Round(feature.Std, 4);

        if (panelScore >= .28)
            issues.Add("检测到疑似拼图、分屏或多格参考图布局");
        if (detailScore < .08)
            issues.Add("脸部区域细节过低，可能是模糊、过度缩小或被遮挡");
        if (feature.Std < .035)
            issues.Add("脸部区域对比度异常低，需人工确认五官是否清楚");

        if (TryAllowedFile(referencePath, out var referenceFullPath) && !string.Equals(fullPath, referenceFullPath, StringComparison.OrdinalIgnoreCase))
        {
            var referenceFrames = await DecodeFramesAsync(referenceFullPath, 1, ct);
            if (referenceFrames.Count > 0)
            {
                var similarity = FeatureSimilarity(feature, BuildFeature(referenceFrames[0]));
                metrics["referenceSimilarityProxy"] = Math.Round(similarity * 100, 2);
                if (similarity < .27) issues.Add("与角色单脸锚点的脸部区域相似度代理值偏低");
            }
        }

        var score = 100m;
        score -= (decimal)Math.Clamp(panelScore * 100, 0, 70);
        score -= detailScore < .08 ? 20 : 0;
        score -= feature.Std < .035 ? 15 : 0;
        score = Math.Clamp(Math.Round(score, 2), 0, 100);
        var rejected = panelScore >= .42 || detailScore < .035 || feature.Std < .018;
        metrics["score"] = score;
        metrics["status"] = rejected ? "Rejected" : "NeedReview";
        metrics["issues"] = issues;
        return new FaceImageQualityEvaluation(rejected, true, score, metrics, issues);
    }

    public async Task<FaceVideoQualityEvaluation> AnalyzeVideoAsync(string path, string? referencePath = null, CancellationToken ct = default)
    {
        var metrics = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["assetPath"] = _paths.TryResolveExisting(path, out _, out var assetPath) ? assetPath : null,
            ["detector"] = "cpu-face-roi-proxy-no-landmark-model",
            ["manualReviewRequired"] = true
        };
        var issues = new List<string>();
        if (!TryAllowedFile(path, out var fullPath))
            return new FaceVideoQualityEvaluation(true, true, 0, metrics, ["视频不存在或不在允许目录"]);

        var probe = await _ffmpeg.ProbeAsync(fullPath, ct);
        var frames = await DecodeFramesAsync(fullPath, 2, ct);
        if (frames.Count < 3)
            return new FaceVideoQualityEvaluation(false, true, 50, metrics, ["视频可抽样帧数不足，必须人工确认脸部稳定性"]);

        var features = frames.Select(BuildFeature).ToList();
        var baseline = features[0];
        var similarities = features.Select(x => FeatureSimilarity(baseline, x)).ToArray();
        var adjacent = features.Zip(features.Skip(1), FeatureSimilarity).ToArray();
        var stability = similarities.Average();
        var minSimilarity = similarities.Min();
        var adjacentStability = adjacent.Length == 0 ? stability : adjacent.Average();
        var extremeFrames = similarities.Count(x => x < .48);
        var anomalyFrames = features.Count(feature =>
            feature.Std < .025 || feature.Std > .32 || FeatureSimilarity(baseline, feature) < .55);
        var visualChanges = frames.Select((frame, index) => index == 0 ? 0 : FaceRegionDifference(frames[0], frame)).ToArray();
        var maxVisualChange = visualChanges.Max();
        var saturation = frames.Select(HighSaturationRatio).ToArray();
        var baselineSaturation = saturation[0];
        var colorArtifactFrames = saturation.Select((ratio, index) => new { ratio, index }).Count(x => x.index > 0 && x.ratio > .12 && x.ratio > baselineSaturation + .06);
        var visualArtifactFrames = visualChanges.Select((change, index) => new { change, index }).Count(x => x.index > 0 && x.change > .10);
        var drift = 1 - stability;
        var structuralArtifact = maxVisualChange > .10 && (drift > .10 || minSimilarity < .82);

        metrics["frameCount"] = frames.Count;
        metrics["faceSimilarityToFirstFrame"] = Math.Round(stability * 100, 2);
        metrics["minFaceSimilarityToFirstFrame"] = Math.Round(minSimilarity * 100, 2);
        metrics["adjacentFaceSimilarity"] = Math.Round(adjacentStability * 100, 2);
        metrics["identityDriftProxy"] = Math.Round(drift * 100, 2);
        metrics["facialAnomalyProxyPercent"] = Math.Round(anomalyFrames * 100d / frames.Count, 2);
        metrics["frameVisualArtifactProxyPercent"] = Math.Round(visualArtifactFrames * 100d / frames.Count, 2);
        metrics["maxFaceRegionVisualChange"] = Math.Round(maxVisualChange * 100, 2);
        metrics["highSaturationFaceRegionProxyPercent"] = Math.Round(saturation.Max() * 100, 2);
        metrics["colorArtifactFrameCount"] = colorArtifactFrames;
        metrics["extremeFrameCount"] = extremeFrames;
        metrics["sampleTimesSeconds"] = Enumerable.Range(0, frames.Count)
            .Select(index => probe?.DurationSeconds is > 0 ? Math.Round(probe.DurationSeconds.Value * index / Math.Max(1, frames.Count - 1), 3) : index / 2d)
            .ToArray();

        var aspectMismatch = false;
        if (TryAllowedFile(referencePath, out var referenceFullPath))
        {
            var referenceFrames = await DecodeFramesAsync(referenceFullPath, 1, ct);
            if (referenceFrames.Count > 0)
            {
                var referenceSimilarity = FeatureSimilarity(BuildFeature(referenceFrames[0]), baseline);
                metrics["referenceSimilarityProxy"] = Math.Round(referenceSimilarity * 100, 2);
                if (referenceSimilarity < .25) issues.Add("视频首帧与角色单脸锚点的相似度代理值偏低");
            }
            var referenceProbe = await _ffmpeg.ProbeAsync(referenceFullPath, ct);
            var videoAspect = probe?.Width is > 0 && probe.Height is > 0 ? (double)probe.Width.Value / probe.Height.Value : 0;
            var referenceAspect = referenceProbe?.Width is > 0 && referenceProbe.Height is > 0 ? (double)referenceProbe.Width.Value / referenceProbe.Height.Value : 0;
            if (videoAspect > 0 && referenceAspect > 0 && Math.Abs(Math.Log(videoAspect / referenceAspect)) > .1)
            {
                aspectMismatch = true;
                metrics["referenceAspect"] = Math.Round(referenceAspect, 4);
                metrics["videoAspect"] = Math.Round(videoAspect, 4);
                issues.Add("视频画幅与首帧/角色参考图不一致，存在裁切眼睛或下巴的高风险");
            }
        }

        if (stability < .55 || extremeFrames >= Math.Max(2, frames.Count / 4))
            issues.Add("多帧脸部稳定性严重不足，疑似脸部漂移、身份变化或极端变形");
        else if (stability < .72 || anomalyFrames * 100d / frames.Count >= 20)
            issues.Add("多帧脸部稳定性偏低，需要重点检查眼睛、嘴部和脸型");
        if (adjacentStability < .68)
            issues.Add("相邻帧脸部变化偏大，可能存在闪烁、鬼影或动作幅度过高");
        if (visualArtifactFrames > 0 || colorArtifactFrames > 0)
            issues.Add("检测到疑似局部彩色伪影、遮挡或大范围帧结构突变");
        if (structuralArtifact)
            issues.Add("脸部区域发生大范围结构突变，需拒绝该视频并降低动作/改用参考锁定重试");

        var score = Math.Clamp((decimal)(stability * 70 + minSimilarity * 20 + adjacentStability * 10), 0, 100);
        var rejected = aspectMismatch || structuralArtifact || colorArtifactFrames >= 1 || visualArtifactFrames >= 2 || stability < .48 || extremeFrames >= Math.Max(3, frames.Count / 3);
        metrics["score"] = Math.Round(score, 2);
        metrics["status"] = rejected ? "Rejected" : "NeedReview";
        metrics["issues"] = issues;
        return new FaceVideoQualityEvaluation(rejected, true, Math.Round(score, 2), metrics, issues);
    }

    private async Task<List<byte[]>> DecodeFramesAsync(string path, int fps, CancellationToken ct)
    {
        if (!File.Exists(_settings.FfmpegPath)) return [];
        var psi = new ProcessStartInfo
        {
            FileName = _settings.FfmpegPath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        var filter = fps == 1
            ? $"scale={SampleWidth}:{SampleHeight}:flags=bilinear,format=rgb24"
            : $"fps={fps.ToString(CultureInfo.InvariantCulture)},scale={SampleWidth}:{SampleHeight}:flags=bilinear,format=rgb24";
        foreach (var arg in new[]
        {
            "-hide_banner", "-loglevel", "error", "-i", path, "-an",
            "-vf", filter,
            "-frames:v", fps == 1 ? "1" : MaxVideoFrames.ToString(CultureInfo.InvariantCulture),
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"
        }) psi.ArgumentList.Add(arg);

        using var process = new Process { StartInfo = psi };
        if (!process.Start()) return [];
        using var buffer = new MemoryStream();
        var outputTask = process.StandardOutput.BaseStream.CopyToAsync(buffer, ct);
        var errorTask = process.StandardError.ReadToEndAsync(ct);
        await process.WaitForExitAsync(ct);
        await outputTask;
        var error = await errorTask;
        if (process.ExitCode != 0 && buffer.Length == 0)
        {
            _logger.LogDebug("Face frame sampling failed for asset {AssetName}: {Error}", Path.GetFileName(path), error.Trim());
            return [];
        }

        var bytes = buffer.ToArray();
        var count = bytes.Length / BytesPerFrame;
        var frames = new List<byte[]>(count);
        for (var index = 0; index < count; index++)
        {
            var frame = new byte[BytesPerFrame];
            Buffer.BlockCopy(bytes, index * BytesPerFrame, frame, 0, BytesPerFrame);
            frames.Add(frame);
        }
        return frames;
    }

    private static Feature BuildFeature(byte[] pixels)
    {
        var gray = new double[SampleWidth * SampleHeight];
        for (var index = 0; index < gray.Length; index++)
        {
            var offset = index * Channels;
            gray[index] = (pixels[offset] * .299 + pixels[offset + 1] * .587 + pixels[offset + 2] * .114) / 255d;
        }

        var roiLeft = 0.15; var roiTop = 0.05; var roiRight = .85; var roiBottom = .72;
        var vector = new double[FeatureWidth * FeatureHeight];
        var histogram = new double[16];
        var sum = 0d; var sumSquares = 0d; var edge = 0d; var count = 0;
        for (var y = 0; y < FeatureHeight; y++)
        for (var x = 0; x < FeatureWidth; x++)
        {
            var sourceX = Math.Clamp((int)Math.Round((roiLeft + (x + .5) / FeatureWidth * (roiRight - roiLeft)) * (SampleWidth - 1)), 0, SampleWidth - 1);
            var sourceY = Math.Clamp((int)Math.Round((roiTop + (y + .5) / FeatureHeight * (roiBottom - roiTop)) * (SampleHeight - 1)), 0, SampleHeight - 1);
            var value = gray[sourceY * SampleWidth + sourceX];
            vector[y * FeatureWidth + x] = value;
            sum += value; sumSquares += value * value; count++;
            histogram[Math.Clamp((int)(value * 16), 0, 15)]++;
            if (x > 0) edge += Math.Abs(value - vector[y * FeatureWidth + x - 1]);
            if (y > 0) edge += Math.Abs(value - vector[(y - 1) * FeatureWidth + x]);
        }

        var mean = sum / count;
        var variance = Math.Max(0, sumSquares / count - mean * mean);
        var std = Math.Sqrt(variance);
        for (var index = 0; index < vector.Length; index++) vector[index] = (vector[index] - mean) / Math.Max(.04, std);
        for (var index = 0; index < histogram.Length; index++) histogram[index] /= count;
        return new Feature(vector, histogram, mean, std, edge / (FeatureWidth * FeatureHeight * 2));
    }

    private static double FeatureSimilarity(Feature left, Feature right)
    {
        var pixelDistance = left.Vector.Zip(right.Vector, (a, b) => Math.Abs(a - b)).Average();
        var histogramDistance = left.Histogram.Zip(right.Histogram, (a, b) => Math.Abs(a - b)).Sum() / 2d;
        var brightnessDistance = Math.Abs(left.Mean - right.Mean);
        return Math.Clamp(1 - pixelDistance / 4d * .68 - histogramDistance * .22 - brightnessDistance * .10, 0, 1);
    }

    private static double FaceRegionDifference(byte[] left, byte[] right)
    {
        if (left.Length != right.Length || left.Length == 0) return 1;
        var total = 0d;
        var count = 0;
        var leftX = (int)(SampleWidth * .15); var rightX = (int)(SampleWidth * .85);
        var topY = (int)(SampleHeight * .05); var bottomY = (int)(SampleHeight * .72);
        for (var y = topY; y < bottomY; y++)
        for (var x = leftX; x < rightX; x++)
        {
            var offset = (y * SampleWidth + x) * Channels;
            total += Math.Abs(left[offset] - right[offset]) / 255d;
            total += Math.Abs(left[offset + 1] - right[offset + 1]) / 255d;
            total += Math.Abs(left[offset + 2] - right[offset + 2]) / 255d;
            count += Channels;
        }
        return count == 0 ? 1 : total / count;
    }

    private static double HighSaturationRatio(byte[] pixels)
    {
        var count = 0; var high = 0;
        var leftX = (int)(SampleWidth * .15); var rightX = (int)(SampleWidth * .85);
        var topY = (int)(SampleHeight * .05); var bottomY = (int)(SampleHeight * .72);
        for (var y = topY; y < bottomY; y++)
        for (var x = leftX; x < rightX; x++)
        {
            var offset = (y * SampleWidth + x) * Channels;
            var red = pixels[offset] / 255d; var green = pixels[offset + 1] / 255d; var blue = pixels[offset + 2] / 255d;
            if (Math.Max(red, Math.Max(green, blue)) - Math.Min(red, Math.Min(green, blue)) > .42 && Math.Max(red, Math.Max(green, blue)) > .55) high++;
            count++;
        }
        return count == 0 ? 0 : (double)high / count;
    }

    private static double PanelLayoutScore(byte[] pixels)
    {
        var gray = new double[SampleWidth * SampleHeight];
        for (var index = 0; index < gray.Length; index++)
        {
            var offset = index * Channels;
            gray[index] = (pixels[offset] * .299 + pixels[offset + 1] * .587 + pixels[offset + 2] * .114) / 255d;
        }

        var verticalPeak = 0d;
        for (var x = 1; x < SampleWidth - 1; x++)
        {
            var difference = 0d;
            for (var y = 0; y < SampleHeight; y++) difference += Math.Abs(gray[y * SampleWidth + x] - gray[y * SampleWidth + x - 1]);
            verticalPeak = Math.Max(verticalPeak, difference / SampleHeight);
        }
        var horizontalPeak = 0d;
        for (var y = 1; y < SampleHeight - 1; y++)
        {
            var difference = 0d;
            for (var x = 0; x < SampleWidth; x++) difference += Math.Abs(gray[y * SampleWidth + x] - gray[(y - 1) * SampleWidth + x]);
            horizontalPeak = Math.Max(horizontalPeak, difference / SampleWidth);
        }
        return Math.Clamp((Math.Max(0, verticalPeak - .17) + Math.Max(0, horizontalPeak - .17)) * 2.2, 0, 1);
    }

    private bool TryAllowedFile(string? path, out string full)
    {
        return _paths.TryResolveExisting(path, out full, out _);
    }

    private sealed record Feature(double[] Vector, double[] Histogram, double Mean, double Std, double EdgeEnergy);
}

public sealed record FaceImageQualityEvaluation(
    bool Rejected,
    bool ManualReviewRequired,
    decimal Score,
    Dictionary<string, object?> Metrics,
    IReadOnlyList<string> Issues);

public sealed record FaceVideoQualityEvaluation(
    bool Rejected,
    bool ManualReviewRequired,
    decimal Score,
    Dictionary<string, object?> Metrics,
    IReadOnlyList<string> Issues);
