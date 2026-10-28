using System.Text.Json;

namespace VideoStudio.Server;

public sealed class QaTechnicalCheckInput
{
    public string Path { get; set; } = "";
    public int ExpectedWidth { get; set; } = 1920;
    public int ExpectedHeight { get; set; } = 1080;
    public decimal ExpectedFps { get; set; } = 30;
    public decimal? ExpectedDuration { get; set; }
    public string? SubtitlePath { get; set; }
    public bool RequireAudio { get; set; }
    public bool RequireSubtitle { get; set; }
    public decimal DurationTolerancePercent { get; set; } = 10;
    public decimal FpsTolerance { get; set; } = 1;
    public decimal BlackFrameMaxPercent { get; set; } = 2;
}

public sealed class FaceMediaCheckInput
{
    public string Path { get; set; } = "";
    public string? ReferenceImagePath { get; set; }
    public bool PortraitPreferred { get; set; }
}

public sealed class QaCheckInput
{
    public string Preset { get; set; } = "Standard";
    public bool AutoRetry { get; set; } = true;
}

public sealed class QaReviewInput
{
    public string Decision { get; set; } = "NeedReview";
    public string? Reviewer { get; set; }
    public string? Note { get; set; }
    /// <summary>
    /// Passing a shot that the automatic gate rejected is an explicit human
    /// override and must include a review note.
    /// </summary>
    public bool OverrideHardFailure { get; set; }
}

public sealed class QaExportInput
{
    public long? CandidateId { get; set; }
    public bool IncludeSubtitles { get; set; } = true;
    public bool IncludeCover { get; set; } = true;
}

public sealed class QaIssueResolveInput
{
    public string Status { get; set; } = "Ignored";
    public string? Note { get; set; }
}

public sealed record QaIssueDraft(string IssueType, string Severity, string Description, double? FrameTime = null, string? FramePath = null);

public sealed record QaFrameMetrics(
    int FrameCount,
    double BlackFramePercent,
    double AverageBrightness,
    double AverageMotion,
    double SuddenChangePercent,
    IReadOnlyList<double> BlackFrameTimes,
    string? Error = null);

public sealed record QaTechnicalEvaluation(
    string Status,
    decimal Score,
    bool HardFailure,
    Dictionary<string, object?> Result,
    List<QaIssueDraft> Issues,
    QaFrameMetrics Metrics)
{
    public string ResultJson => JsonSerializer.Serialize(Result);
}

public sealed record ShotQaEvaluation(
    string Status,
    decimal Score,
    Dictionary<string, decimal> ComponentScores,
    Dictionary<string, object?> Result,
    List<QaIssueDraft> Issues,
    bool ManualReviewRequired,
    bool ShouldRetry)
{
    public string ResultJson => JsonSerializer.Serialize(Result);
}

public sealed record EpisodeQaEvaluation(
    string Status,
    decimal Score,
    Dictionary<string, decimal> ComponentScores,
    Dictionary<string, object?> Result,
    List<QaIssueDraft> Issues,
    bool ManualReviewRequired)
{
    public string ResultJson => JsonSerializer.Serialize(Result);
}

public sealed record QaPresetOptions(
    string Name,
    decimal ShotPassScore,
    decimal ShotReviewScore,
    decimal EpisodePassScore,
    decimal BlackFrameMaxPercent,
    decimal DurationTolerancePercent,
    decimal FpsTolerance,
    int MaxAutoRetries);

public sealed record QaExportResult(
    string MasterPath,
    string? SubtitlePath,
    string? CoverPath,
    string ReportPath,
    string ReportJsonPath);
