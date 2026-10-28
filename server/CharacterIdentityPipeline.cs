using System.Diagnostics;
using System.Globalization;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed class CharacterQaBatchInput
{
    public string MasterPath { get; set; } = "";
    public List<CharacterQaCandidateInput> Candidates { get; set; } = [];
    public double IdentityThreshold { get; set; } = .85;
}

public sealed class CharacterQaCandidateInput
{
    public string Path { get; set; } = "";
    public string? CandidateId { get; set; }
    public string? RequestedView { get; set; }
    public string? SourcePrompt { get; set; }
    public long? Seed { get; set; }
}

public sealed record CharacterImageProbe(
    int Width,
    int Height,
    double FaceSymmetry,
    double FaceEdgeEnergy,
    double FaceContrast,
    double FeatureCentroidX,
    double BorderContact,
    double CentralOccupancy,
    string DetectorStatus);

public sealed record CharacterQualityEvaluation(
    string CandidateId,
    string Path,
    string? RequestedView,
    string DetectedView,
    double? ViewAngle,
    double ViewAngleConfidence,
    double IdentityScore,
    double FaceQualityScore,
    double PoseScore,
    double ClothingConsistencyScore,
    double HairConsistencyScore,
    double BodyQualityScore,
    double OcclusionScore,
    double OverallScore,
    bool Accepted,
    bool ManualReviewRequired,
    IReadOnlyList<string> HumanRejectFlags,
    IReadOnlyList<string> HardRejects,
    Dictionary<string, object?> Metrics,
    string ManualReview,
    string? SourcePrompt = null,
    long? Seed = null);

public sealed record GoldenReference(
    string Path,
    string View,
    double IdentityScore,
    double FaceQualityScore,
    double ViewAngle,
    double ClothingConsistencyScore,
    double HairConsistencyScore,
    double BodyQualityScore,
    bool Accepted,
    IReadOnlyList<string> HumanRejectFlags,
    string ManualReview);

public sealed record GoldenPackValidation(
    string Status,
    bool Passed,
    IReadOnlyList<string> MissingViews,
    IReadOnlyList<string> InvalidReferences,
    int AcceptedCount,
    int MinimumRequiredCount,
    bool ManualReviewRequired,
    string Reason);

public sealed record GoldenReferencePack(
    string CharacterId,
    string Master,
    string CreatedAt,
    string EmbeddingModel,
    string ScoreRange,
    double IdentityThreshold,
    IReadOnlyList<GoldenReference> References,
    GoldenPackValidation Validation,
    string LoraStatus);

/// <summary>
/// CPU-only character candidate QA. The installed workstation does not have
/// an ArcFace/InsightFace/landmark model, so the service deliberately reports
/// a face-region proxy and a low-confidence geometry classifier. It never
/// upgrades that proxy into a production identity pass.
/// </summary>
public sealed class CharacterQualityService
{
    private const int RasterWidth = 128;
    private const int RasterHeight = 160;
    private const int Channels = 3;
    private readonly StudioSettings _settings;
    private readonly FfmpegService _ffmpeg;
    private readonly FaceQualityService _faceQuality;
    private readonly AssetPathPolicy _paths;
    private readonly ILogger<CharacterQualityService> _logger;

    public CharacterQualityService(
        StudioSettings settings,
        FfmpegService ffmpeg,
        FaceQualityService faceQuality,
        AssetPathPolicy paths,
        ILogger<CharacterQualityService> logger)
    {
        _settings = settings;
        _ffmpeg = ffmpeg;
        _faceQuality = faceQuality;
        _paths = paths;
        _logger = logger;
    }

    public async Task<CharacterQualityEvaluation> EvaluateAsync(
        string masterPath,
        CharacterQaCandidateInput candidate,
        double identityThreshold = .85,
        CancellationToken ct = default)
    {
        var candidateId = string.IsNullOrWhiteSpace(candidate.CandidateId)
            ? Path.GetFileNameWithoutExtension(candidate.Path)
            : candidate.CandidateId!;
        var metrics = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["embeddingModel"] = "UNAVAILABLE",
            ["identityScoreMethod"] = "FaceQualityService.referenceSimilarityProxy-or-cpu-raster-proxy",
            ["viewDetector"] = "cpu-raster-symmetry-proxy-no-landmark-model",
            ["manualReviewRequired"] = true,
            ["identityThreshold"] = identityThreshold,
            ["scoreRange"] = "0..1"
        };
        var flags = new List<string>();
        var hardRejects = new List<string>();

        if (!_paths.TryResolveExisting(masterPath, out var masterFull, out var masterAsset))
        {
            flags.Add("MasterMissing");
            hardRejects.Add("MasterMissing");
            return Rejected(candidateId, candidate, metrics, flags, hardRejects, "角色 Master 不存在或不在受控媒体目录");
        }
        if (!_paths.TryResolveExisting(candidate.Path, out var candidateFull, out var candidateAsset))
        {
            flags.Add("FaceMissing");
            hardRejects.Add("FaceMissing");
            metrics["master"] = masterAsset;
            return Rejected(candidateId, candidate, metrics, flags, hardRejects, "候选图片不存在或不在受控媒体目录");
        }

        var masterProbe = await ProbeAsync(masterFull, ct);
        var candidateProbe = await ProbeAsync(candidateFull, ct);
        if (masterProbe is null || candidateProbe is null)
        {
            flags.Add("FaceMissing");
            hardRejects.Add("FaceMissing");
            return Rejected(candidateId, candidate, metrics, flags, hardRejects, "候选图片无法解码");
        }

        var face = await _faceQuality.AnalyzeImageAsync(candidateFull, masterFull, portraitPreferred: true, ct);
        var faceQuality = Math.Clamp((double)face.Score / 100d, 0, 1);
        var faceProxy = TryDouble(face.Metrics, "referenceSimilarityProxy") is { } proxy
            ? Math.Clamp(proxy / 100d, 0, 1)
            : RegionSimilarity(masterProbe, candidateProbe, .12, .64, .18, .84);
        var identity = Math.Clamp(faceProxy * .72 + RegionSimilarity(masterProbe, candidateProbe, .17, .58, .16, .78) * .28, 0, 1);
        if (string.Equals(masterFull, candidateFull, StringComparison.OrdinalIgnoreCase)) identity = 1;

        var clothing = RegionSimilarity(masterProbe, candidateProbe, .02, .98, .62, .99);
        var hair = RegionSimilarity(masterProbe, candidateProbe, .04, .96, .01, .25);
        var body = Math.Clamp(.55 + RegionSimilarity(masterProbe, candidateProbe, .03, .97, .35, .98) * .45, 0, 1);
        var occlusion = Math.Clamp(1 - candidateProbe.BorderContact * .9, 0, 1);
        var detected = ClassifyView(masterProbe, candidateProbe, out var angle, out var viewConfidence);
        var expected = NormalizeView(candidate.RequestedView);
        var viewMatch = expected is null || string.Equals(expected, detected, StringComparison.OrdinalIgnoreCase);
        var viewScore = expected is null ? viewConfidence : viewMatch ? Math.Max(viewConfidence, .75) : 0;
        var overall = Math.Clamp(
            identity * .40 + faceQuality * .20 + viewScore * .15 + clothing * .10 + hair * .10 + body * .05,
            0, 1);

        metrics["master"] = masterAsset;
        metrics["candidate"] = candidateAsset;
        metrics["faceQualityMetrics"] = face.Metrics;
        metrics["masterProbe"] = masterProbe;
        metrics["candidateProbe"] = candidateProbe;
        metrics["identityScoreProxy"] = Math.Round(identity, 4);
        metrics["faceQualityScore"] = Math.Round(faceQuality, 4);
        metrics["viewScore"] = Math.Round(viewScore, 4);
        metrics["viewMatch"] = viewMatch;
        metrics["viewDetectorConfidence"] = Math.Round(viewConfidence, 4);
        metrics["clothingSimilarityProxy"] = Math.Round(clothing, 4);
        metrics["hairSimilarityProxy"] = Math.Round(hair, 4);
        metrics["bodyQualityProxy"] = Math.Round(body, 4);

        foreach (var issue in face.Issues)
        {
            if (issue.Contains("拼图", StringComparison.OrdinalIgnoreCase)) flags.Add("MultipleFaces");
            if (issue.Contains("细节过低", StringComparison.OrdinalIgnoreCase)) flags.Add("FaceBlur");
            if (issue.Contains("对比度异常", StringComparison.OrdinalIgnoreCase)) flags.Add("FaceDistortion");
        }
        if (identity < identityThreshold) flags.Add("WrongIdentity");
        if (expected is not null && !viewMatch)
            flags.Add(string.Equals(detected, "Unknown", StringComparison.OrdinalIgnoreCase) ? "ViewAngleUnverified" : "WrongViewAngle");
        if (clothing < .62) flags.Add("ClothingMismatch");
        if (hair < .62) flags.Add("HairMismatch");
        if (candidateProbe.BorderContact > .42) flags.Add("HeadCropped");
        if (occlusion < .45) flags.Add("SevereOcclusion");
        if (body < .40) flags.Add("SevereBodyDistortion");

        foreach (var flag in flags.Distinct(StringComparer.OrdinalIgnoreCase))
            if (IsHardReject(flag)) hardRejects.Add(flag);

        var manualReview = "自动分数仅为 CPU 视觉代理；必须由人工确认身份、真实视角、服装/发型和身体完整性。";
        var accepted = hardRejects.Count == 0
            && identity >= identityThreshold
            && faceQuality >= .70
            && (expected is null || viewMatch)
            && viewConfidence >= .50;
        return new CharacterQualityEvaluation(
            candidateId,
            candidateAsset,
            expected,
            detected,
            angle,
            Math.Round(viewConfidence, 4),
            Math.Round(identity, 4),
            Math.Round(faceQuality, 4),
            Math.Round(viewScore, 4),
            Math.Round(clothing, 4),
            Math.Round(hair, 4),
            Math.Round(body, 4),
            Math.Round(occlusion, 4),
            Math.Round(overall, 4),
            accepted,
            true,
            flags.Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
            hardRejects.Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
            metrics,
            manualReview,
            candidate.SourcePrompt,
            candidate.Seed);
    }

    public async Task<IReadOnlyList<CharacterQualityEvaluation>> EvaluateBatchAsync(
        CharacterQaBatchInput input,
        CancellationToken ct = default)
    {
        var results = new List<CharacterQualityEvaluation>(input.Candidates.Count);
        foreach (var candidate in input.Candidates)
            results.Add(await EvaluateAsync(input.MasterPath, candidate, input.IdentityThreshold, ct));
        return results;
    }

    public static GoldenReferencePack BuildGoldenPack(
        string characterId,
        string master,
        double identityThreshold,
        IReadOnlyList<CharacterQualityEvaluation> results)
    {
        var references = results
            .Where(result => result.Accepted && result.ViewAngle is not null)
            .GroupBy(result => result.DetectedView, StringComparer.OrdinalIgnoreCase)
            .Select(group => group.OrderByDescending(result => result.OverallScore).First())
            .Select(result => new GoldenReference(
                result.Path,
                result.DetectedView,
                result.IdentityScore,
                result.FaceQualityScore,
                result.ViewAngle ?? 0,
                result.ClothingConsistencyScore,
                result.HairConsistencyScore,
                result.BodyQualityScore,
                result.Accepted,
                result.HumanRejectFlags,
                result.ManualReview))
            .ToArray();
        var validation = ValidateGoldenPack(references);
        return new GoldenReferencePack(
            characterId,
            master,
            DateTimeOffset.Now.ToString("O", CultureInfo.InvariantCulture),
            "UNAVAILABLE (InsightFace/ArcFace/landmark model not installed)",
            "0..1; identity is a CPU proxy, not an embedding distance",
            identityThreshold,
            references,
            validation,
            validation.Passed ? "Conditional-until-human-review" : "BLOCKED_DATASET_QUALITY");
    }

    public static GoldenPackValidation ValidateGoldenPack(IReadOnlyList<GoldenReference> references)
    {
        var required = new[] { "Front", "FrontLeft30", "FrontRight30", "Left45", "Right45", "HalfBody", "FullBody" };
        var missing = required.Where(view => !references.Any(reference => string.Equals(reference.View, view, StringComparison.OrdinalIgnoreCase) && reference.Accepted)).ToArray();
        var invalid = references
            .Where(reference => !reference.Accepted || reference.HumanRejectFlags.Count > 0)
            .Select(reference => $"{reference.View}:{string.Join(',', reference.HumanRejectFlags)}")
            .ToArray();
        var manual = references.Any(reference => !string.IsNullOrWhiteSpace(reference.ManualReview));
        var passed = missing.Length == 0 && invalid.Length == 0 && references.Count >= 10 && !manual;
        var status = passed ? "Passed" : missing.Length > 0 ? "BLOCKED_GOLDEN_PACK_INCOMPLETE" : "Conditional-manual-review-required";
        var reason = passed
            ? "Golden Pack 覆盖核心视角且已完成人工确认"
            : $"缺少视角 {string.Join(',', missing)}；数量 {references.Count}/10；人工复核={manual}";
        return new GoldenPackValidation(status, passed, missing, invalid, references.Count, 10, manual, reason);
    }

    private async Task<CharacterImageProbe?> ProbeAsync(string path, CancellationToken ct)
    {
        var probe = await _ffmpeg.ProbeAsync(path, ct);
        if (probe?.Width is not > 0 || probe.Height is not > 0 || !File.Exists(_settings.FfmpegPath)) return null;
        var psi = new ProcessStartInfo
        {
            FileName = _settings.FfmpegPath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (var arg in new[]
        {
            "-hide_banner", "-loglevel", "error", "-i", path, "-frames:v", "1",
            "-vf", $"scale={RasterWidth}:{RasterHeight}:force_original_aspect_ratio=decrease,pad={RasterWidth}:{RasterHeight}:(ow-iw)/2:(oh-ih)/2:color=black",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"
        }) psi.ArgumentList.Add(arg);
        using var process = new Process { StartInfo = psi };
        if (!process.Start()) return null;
        using var buffer = new MemoryStream();
        var outputTask = process.StandardOutput.BaseStream.CopyToAsync(buffer, ct);
        var errorTask = process.StandardError.ReadToEndAsync(ct);
        await process.WaitForExitAsync(ct);
        await outputTask;
        var error = await errorTask;
        var expectedBytes = RasterWidth * RasterHeight * Channels;
        if (process.ExitCode != 0 || buffer.Length < expectedBytes)
        {
            _logger.LogDebug("Character raster probe failed for {Path}: {Error}", path, error.Trim());
            return null;
        }
        var bytes = buffer.ToArray();
        var luminance = new double[RasterWidth * RasterHeight];
        for (var i = 0; i < luminance.Length; i++)
        {
            var offset = i * Channels;
            luminance[i] = (bytes[offset] * .299 + bytes[offset + 1] * .587 + bytes[offset + 2] * .114) / 255d;
        }
        var faceLeft = (int)(RasterWidth * .13); var faceRight = (int)(RasterWidth * .87);
        var faceTop = (int)(RasterHeight * .02); var faceBottom = (int)(RasterHeight * .62);
        var symmetryTotal = 0d; var contrastTotal = 0d; var edgeTotal = 0d; var weightTotal = 0d; var xWeight = 0d; var border = 0d; var central = 0d;
        for (var y = 0; y < RasterHeight; y++)
        for (var x = 0; x < RasterWidth; x++)
        {
            var value = luminance[y * RasterWidth + x];
            var weight = Math.Abs(value - .5) + .05;
            if (x >= faceLeft && x < faceRight && y >= faceTop && y < faceBottom)
            {
                var mirror = luminance[y * RasterWidth + (RasterWidth - 1 - x)];
                symmetryTotal += Math.Abs(value - mirror);
                contrastTotal += weight;
                if (x > faceLeft) edgeTotal += Math.Abs(value - luminance[y * RasterWidth + x - 1]);
                weightTotal += weight;
                xWeight += x * weight;
            }
            if ((x < 4 || x >= RasterWidth - 4 || y < 4 || y >= RasterHeight - 4) && value < .08) border++;
            if (x >= RasterWidth * .18 && x < RasterWidth * .82 && y >= RasterHeight * .05 && y < RasterHeight * .90 && value > .12) central++;
        }
        var facePixels = Math.Max(1, (faceRight - faceLeft) * (faceBottom - faceTop));
        return new CharacterImageProbe(
            probe.Width!.Value,
            probe.Height!.Value,
            Math.Clamp(1 - symmetryTotal / facePixels * 2.2, 0, 1),
            Math.Clamp(edgeTotal / Math.Max(1, (faceRight - faceLeft) * (faceBottom - faceTop)), 0, 1),
            Math.Clamp(contrastTotal / Math.Max(1, weightTotal), 0, 1),
            xWeight / Math.Max(.001, weightTotal) / RasterWidth,
            Math.Clamp(border / (double)(RasterWidth * RasterHeight), 0, 1),
            Math.Clamp(central / (double)(RasterWidth * RasterHeight), 0, 1),
            "ffmpeg-rgb-raster; no face detector/landmark model");
    }

    private static double RegionSimilarity(CharacterImageProbe master, CharacterImageProbe candidate, double left, double right, double top, double bottom)
    {
        var symmetryDistance = Math.Abs(master.FaceSymmetry - candidate.FaceSymmetry);
        var edgeDistance = Math.Abs(master.FaceEdgeEnergy - candidate.FaceEdgeEnergy);
        var contrastDistance = Math.Abs(master.FaceContrast - candidate.FaceContrast);
        var centerDistance = Math.Abs(master.FeatureCentroidX - candidate.FeatureCentroidX);
        var cropDistance = Math.Abs(master.BorderContact - candidate.BorderContact);
        return Math.Clamp(1 - symmetryDistance * .34 - edgeDistance * .26 - contrastDistance * .20 - centerDistance * .12 - cropDistance * .08, 0, 1);
    }

    private static string ClassifyView(CharacterImageProbe master, CharacterImageProbe probe, out double? angle, out double confidence)
    {
        var symmetryDelta = Math.Abs(probe.FaceSymmetry - master.FaceSymmetry);
        var centerDelta = Math.Abs(probe.FeatureCentroidX - master.FeatureCentroidX);
        if (symmetryDelta <= .035 && centerDelta <= .018)
        {
            angle = 0;
            confidence = Math.Clamp(.70 - symmetryDelta * 2 + (.018 - centerDelta) * 4, .60, .95);
            return "Front";
        }
        angle = Math.Round(Math.Clamp(symmetryDelta * 180 + centerDelta * 120, 0, 90), 2);
        confidence = Math.Clamp(.25 + (probe.FaceContrast - .20) * .35, .10, .55);
        return "Unknown";
    }

    private static string? NormalizeView(string? view)
    {
        if (string.IsNullOrWhiteSpace(view)) return null;
        var value = view.Trim().Replace(" ", "", StringComparison.Ordinal).Replace("-", "", StringComparison.Ordinal).ToLowerInvariant();
        return value switch
        {
            "front" or "正面" => "Front",
            "frontleft30" or "left30" or "左30" => "FrontLeft30",
            "frontright30" or "right30" or "右30" => "FrontRight30",
            "left45" or "左45" => "Left45",
            "right45" or "右45" => "Right45",
            "leftprofile" or "左侧面" => "LeftProfile",
            "rightprofile" or "右侧面" => "RightProfile",
            "halfbody" or "half" or "半身" => "HalfBody",
            "fullbody" or "full" or "全身" => "FullBody",
            _ => view.Trim()
        };
    }

    private static double? TryDouble(Dictionary<string, object?> metrics, string key)
    {
        if (!metrics.TryGetValue(key, out var value) || value is null) return null;
        return value switch
        {
            double number => number,
            float number => number,
            decimal number => (double)number,
            int number => number,
            long number => number,
            _ when double.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed) => parsed,
            _ => null
        };
    }

    private static bool IsHardReject(string flag) => flag is
        "FaceMissing" or "FaceTooSmall" or "FaceBlur" or "FaceDistortion" or "MultipleFaces" or
        "WrongIdentity" or "WrongViewAngle" or "HairMismatch" or "ClothingMismatch" or
        "SevereBodyDistortion" or "ExtraLimb" or "MissingLimb" or "HeadCropped" or
        "BodyCroppedUnexpectedly" or "SevereOcclusion" or "WrongGenderPresentation" or
        "SevereAgeDrift" or "PropContamination" or "MasterMissing";

    private static CharacterQualityEvaluation Rejected(
        string candidateId,
        CharacterQaCandidateInput candidate,
        Dictionary<string, object?> metrics,
        IReadOnlyList<string> flags,
        IReadOnlyList<string> hardRejects,
        string review)
        => new(
            candidateId,
            candidate.Path,
            candidate.RequestedView,
            "Unknown",
            null,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            false,
            true,
            flags,
            hardRejects,
            metrics,
            review,
            candidate.SourcePrompt,
            candidate.Seed);
}

public sealed record ReferenceSelectorRequest(
    string CameraAngle = "Front",
    string ShotSize = "CloseUp",
    string? CharacterId = null,
    string? Action = null);

public sealed record ReferenceCandidateScore(
    string Path,
    string View,
    double Score,
    bool Qualified,
    string? DisqualificationReason);

public sealed record ReferenceSelection(
    string? SelectedReference,
    string? SelectedView,
    double SelectionScore,
    bool Fallback,
    string? FallbackReason,
    IReadOnlyList<ReferenceCandidateScore> CandidateScores,
    string Policy);

public static class ReferenceSelectorV2
{
    public static ReferenceSelection Select(ReferenceSelectorRequest request, IReadOnlyList<GoldenReference> references)
    {
        var requested = Normalize(request.CameraAngle, request.ShotSize);
        var priorities = Priorities(requested);
        var scores = references.Select(reference =>
        {
            var qualified = reference.Accepted
                && reference.HumanRejectFlags.Count == 0
                && reference.IdentityScore >= .85
                && reference.FaceQualityScore >= .70
                && reference.ClothingConsistencyScore >= .62
                && reference.HairConsistencyScore >= .62;
            var index = Array.FindIndex(priorities, value => string.Equals(value, reference.View, StringComparison.OrdinalIgnoreCase));
            var priorityScore = index < 0 ? 0 : 1d - index / (double)Math.Max(1, priorities.Length);
            var score = qualified ? Math.Clamp(priorityScore * .55 + reference.IdentityScore * .20 + reference.FaceQualityScore * .10 + reference.ClothingConsistencyScore * .075 + reference.HairConsistencyScore * .075, 0, 1) : 0;
            var reason = qualified ? null : reference.HumanRejectFlags.Count > 0 ? string.Join(',', reference.HumanRejectFlags) : "NotQualifiedGoldenReference";
            return new ReferenceCandidateScore(reference.Path, reference.View, Math.Round(score, 4), qualified, reason);
        }).OrderByDescending(candidate => candidate.Score).ToArray();
        var selected = scores.FirstOrDefault(candidate => candidate.Qualified && priorities.Contains(candidate.View, StringComparer.OrdinalIgnoreCase));
        if (selected is not null)
        {
            var selectedIndex = Array.FindIndex(priorities, value => string.Equals(value, selected.View, StringComparison.OrdinalIgnoreCase));
            var fallback = selectedIndex > 0;
            var fallbackReason = fallback ? $"NoQualified{SanitizeReason(request.CameraAngle)};SelectedAdjacent{selected.View}" : null;
            return new ReferenceSelection(selected.Path, selected.View, selected.Score, fallback, fallbackReason, scores, "Prefer requested view, then explicitly ranked adjacent view; never silent fallback.");
        }

        var front = scores.FirstOrDefault(candidate => candidate.Qualified && string.Equals(candidate.View, "Front", StringComparison.OrdinalIgnoreCase));
        var wantedLabel = string.IsNullOrWhiteSpace(request.CameraAngle) ? request.ShotSize : request.CameraAngle;
        return front is null
            ? new ReferenceSelection(null, null, 0, true, $"NoQualified{SanitizeReason(wantedLabel)};NoQualifiedFront", scores, "Fallback is explicit and blocks if no qualified front anchor exists.")
            : new ReferenceSelection(front.Path, front.View, front.Score, true, $"NoQualified{SanitizeReason(wantedLabel)}", scores, "Fallback is explicit and recorded.");
    }

    private static string[] Priorities(string requested) => requested switch
    {
        "Left45" => ["Left45", "FrontLeft30", "Front"],
        "Right45" => ["Right45", "FrontRight30", "Front"],
        "FrontLeft30" => ["FrontLeft30", "Left45", "Front"],
        "FrontRight30" => ["FrontRight30", "Right45", "Front"],
        "HalfBody" => ["HalfBody", "FrontLeft30", "FrontRight30", "Front"],
        "FullBody" => ["FullBody", "HalfBody", "Front"],
        "LeftProfile" => ["LeftProfile", "Left45", "FrontLeft30", "Front"],
        "RightProfile" => ["RightProfile", "Right45", "FrontRight30", "Front"],
        _ => ["Front", "FrontLeft30", "FrontRight30", "Left45", "Right45", "HalfBody", "FullBody"]
    };

    private static string Normalize(string? cameraAngle, string? shotSize)
    {
        var value = (cameraAngle ?? "").Replace(" ", "", StringComparison.Ordinal).Replace("-", "", StringComparison.Ordinal).ToLowerInvariant();
        if (value.Length == 0) value = (shotSize ?? "").Replace(" ", "", StringComparison.Ordinal).ToLowerInvariant();
        return value switch
        {
            "left45" or "左45" => "Left45",
            "right45" or "右45" => "Right45",
            "left30" or "frontleft30" or "左30" => "FrontLeft30",
            "right30" or "frontright30" or "右30" => "FrontRight30",
            "half" or "halfbody" or "半身" => "HalfBody",
            "full" or "fullbody" or "全身" => "FullBody",
            "leftprofile" or "左侧面" => "LeftProfile",
            "rightprofile" or "右侧面" => "RightProfile",
            _ => "Front"
        };
    }

    private static string SanitizeReason(string value)
        => new(value.Where(char.IsLetterOrDigit).ToArray());
}

public sealed record MotionSubShot(
    string Id,
    string Action,
    string SuggestedDuration,
    string RecommendedWorkflow,
    string Reason);

public sealed record MotionComplexityAnalysis(
    string OriginalAction,
    IReadOnlyList<string> DetectedActions,
    string Complexity,
    bool NeedSplit,
    IReadOnlyList<MotionSubShot> SuggestedSubShots,
    string RecommendedWorkflow,
    string? BlockingReason);

public static class MotionComplexityAnalyzer
{
    private static readonly (string Canonical, string[] Terms)[] ActionTerms =
    [
        ("blink", ["blink", "blinks", "眨眼"]),
        ("smile", ["smile", "smiles", "微笑", "笑"]),
        ("look", ["look", "looks", "看向", "注视", "抬头", "低头"]),
        ("turn", ["turn", "turning", "转身", "转头", "转向"]),
        ("raise-hand", ["raise hand", "raises hand", "抬手", "举手"]),
        ("walk", ["walk", "walking", "step", "steps", "走", "走路", "走一步", "走两步"]),
        ("sit", ["sit", "sitting", "坐下", "坐", "下坐"]),
        ("stand", ["stand", "standing", "起身", "站起", "站立"]),
        ("bend", ["bend", "bending", "弯腰", "俯身"]),
        ("pick", ["pick", "pickup", "pick-up", "拿起", "捡起", "拿杯", "取物"]),
        ("drive", ["drive", "driving", "驾驶", "开车", "方向盘"]),
        ("run", ["run", "running", "奔跑"]),
        ("dance", ["dance", "dancing", "跳舞"]),
        ("fight", ["fight", "fighting", "打斗"])
    ];

    public static MotionComplexityAnalysis Analyze(string? action)
    {
        var original = action?.Trim() ?? "";
        var normalized = original.ToLowerInvariant();
        var detected = ActionTerms
            .Where(pair => pair.Terms.Any(term => normalized.Contains(term, StringComparison.OrdinalIgnoreCase)))
            .Select(pair => pair.Canonical)
            .ToArray();
        var driving = detected.Contains("drive", StringComparer.OrdinalIgnoreCase);
        var highRisk = detected.Any(value => value is "walk" or "sit" or "pick" or "bend" or "drive" or "run" or "dance" or "fight");
        var multiple = detected.Length >= 2 || (detected.Length > 1 && (normalized.Contains(" and ", StringComparison.OrdinalIgnoreCase) || normalized.Contains("然后", StringComparison.OrdinalIgnoreCase) || normalized.Contains("再", StringComparison.OrdinalIgnoreCase)));
        var simpleOnly = detected.Length == 0 || detected.All(value => value is "blink" or "smile" or "look" or "turn" or "raise-hand");
        var complexity = driving || multiple ? "Complex" : highRisk ? "Medium" : simpleOnly ? "Simple" : "Medium";
        var needSplit = highRisk || multiple;
        var workflow = driving ? "wan2.2-animate" : needSplit ? "split-shot-gated" : "12_ltx_face_stable_v3";
        var blocking = driving
            ? "BLOCKED_MODEL_ASSET/BLOCKED_WORKFLOW：本机没有 Wan2.2 Animate 目标权重与完整 Retarget 工作流。"
            : needSplit
                ? "当前小动作 I2V 没有证明该动作语义；必须拆成 1.0–2.5 秒子镜头并逐镜人工验收。"
                : null;
        var subshots = BuildSubShots(detected, multiple);
        return new MotionComplexityAnalysis(original, detected, complexity, needSplit, subshots, workflow, blocking);
    }

    private static IReadOnlyList<MotionSubShot> BuildSubShots(IReadOnlyList<string> detected, bool multiple)
    {
        var list = new List<MotionSubShot>();
        foreach (var action in detected)
        {
            switch (action)
            {
                case "walk":
                    list.Add(new MotionSubShot("walk-step-1", "走第一步", "1.0–2.0s", "Pose/Driving or split-shot I2V", "单步、全身、脚落地可检查"));
                    list.Add(new MotionSubShot("walk-step-2", "走第二步/到达", "1.0–2.0s", "Pose/Driving or split-shot I2V", "保持重心和身份连续"));
                    break;
                case "sit":
                    list.Add(new MotionSubShot("sit-prepare", "站立转身并准备坐下", "1.0–2.0s", "Pose/Driving or split-shot I2V", "先锁定椅子/落座方向"));
                    list.Add(new MotionSubShot("sit-lower", "下坐", "1.0–2.5s", "Pose/Driving or split-shot I2V", "检查膝盖、腿数和接触面"));
                    list.Add(new MotionSubShot("sit-hold", "坐稳停住", "1.0–1.5s", "12_ltx_face_stable_v3", "用短镜头收住身份"));
                    break;
                case "pick":
                    list.Add(new MotionSubShot("pick-reach", "手靠近物体", "1.0–1.5s", "Pose/Driving or split-shot I2V", "手掌与物体保持可见"));
                    list.Add(new MotionSubShot("pick-contact", "手接触物体", "1.0–1.5s", "Pose/Driving or split-shot I2V", "验证手物接触"));
                    list.Add(new MotionSubShot("pick-lift", "物体离开桌面", "1.0–2.0s", "Pose/Driving or split-shot I2V", "验证杯子数量和位置连续"));
                    list.Add(new MotionSubShot("pick-chest", "抬到胸口并停住", "1.0–1.5s", "12_ltx_face_stable_v3", "短镜头稳定身份"));
                    break;
                case "drive":
                    list.Add(new MotionSubShot("drive-seat", "坐入驾驶位", "1.0–2.0s", "wan2.2-animate", "需要真实 Driving/Retarget 输入"));
                    list.Add(new MotionSubShot("drive-hands", "双手接触方向盘", "1.0–2.0s", "wan2.2-animate", "需要手物与车辆内饰控制"));
                    break;
                default:
                    list.Add(new MotionSubShot($"{action}-single", action, multiple ? "1.0–2.5s" : "3.0s", "12_ltx_face_stable_v3", "单一动作短镜头"));
                    break;
            }
        }
        if (list.Count == 0)
            list.Add(new MotionSubShot("simple-single", "小幅单动作", "3.0s", "12_ltx_face_stable_v3", "当前已验证的小动作范围"));
        return list;
    }
}
