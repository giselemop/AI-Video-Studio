using System.Text.Json;
using System.Text.Json.Serialization;

namespace VideoStudio.Server;

public sealed class ProjectInput
{
    public string Name { get; set; } = "";
    public string? Description { get; set; }
    public string Status { get; set; } = "Active";
    public string AspectRatio { get; set; } = "16:9";
    public string? Style { get; set; }
    public int DefaultFps { get; set; } = 30;
    public int DefaultWidth { get; set; } = 1920;
    public int DefaultHeight { get; set; } = 1080;
    public string? PromptStyle { get; set; }
    public string? BgmPath { get; set; }
    public decimal BgmVolume { get; set; } = .18m;
}

public sealed class LocalLoginInput
{
    public string Username { get; set; } = "";
    public string Password { get; set; } = "";
}

public sealed class LocalAdminSetupInput
{
    public string Username { get; set; } = "";
    public string Password { get; set; } = "";
}

public sealed class CharacterInput
{
    public long? ProjectId { get; set; }
    public string Name { get; set; } = "";
    public string? AgeSetting { get; set; }
    public string? FaceFeatures { get; set; }
    public string? Hair { get; set; }
    public string? Clothes { get; set; }
    public string? BodyRatio { get; set; }
    public string? FixedPrompt { get; set; }
    public string? NegativePrompt { get; set; }
    public string? EmbeddingPath { get; set; }
    public string? LoraPath { get; set; }
    public string? AnchorPath { get; set; }
    public string? VoiceId { get; set; }
    public decimal VoiceSpeed { get; set; } = 1m;
    public decimal VoicePitch { get; set; }
    public JsonElement? Metadata { get; set; }
}

public sealed class SceneInput
{
    public long? ProjectId { get; set; }
    public string Name { get; set; } = "";
    public string? Description { get; set; }
    public string? FixedPrompt { get; set; }
    public string? NegativePrompt { get; set; }
    public string? Style { get; set; }
    public string? AnchorPath { get; set; }
    public JsonElement? Metadata { get; set; }
}

public sealed class EpisodeInput
{
    public long ProjectId { get; set; }
    public int EpisodeNumber { get; set; } = 1;
    public string Name { get; set; } = "";
    public string? Description { get; set; }
    public decimal TargetSeconds { get; set; } = 60;
    public int OutputFps { get; set; } = 30;
    public int OutputWidth { get; set; } = 1920;
    public int OutputHeight { get; set; } = 1080;
}

public sealed class ShotInput
{
    public long ProjectId { get; set; }
    public long EpisodeId { get; set; }
    public int ShotNumber { get; set; }
    public string Title { get; set; } = "";
    public string? Description { get; set; }
    public long? SceneId { get; set; }
    public List<long>? CharacterIds { get; set; }
    public string? Prompt { get; set; }
    public string? NegativePrompt { get; set; }
    [JsonPropertyName("workflowId")]
    public long? WorkflowId { get; set; }
    public long? ModelId { get; set; }
    public List<long>? LoraIds { get; set; }
    public long? Seed { get; set; }
    public decimal? CfgScale { get; set; }
    public int? Steps { get; set; }
    public int? Width { get; set; }
    public int? Height { get; set; }
    public int? Frames { get; set; }
    public decimal? Fps { get; set; }
    public string? InputImagePath { get; set; }
    public string? MotionPreset { get; set; }
    public string? CameraPreset { get; set; }
    public string Status { get; set; } = "Draft";
    public string? Action { get; set; }
    public string? Dialogue { get; set; }
    public string? Narration { get; set; }
    public string? Emotion { get; set; }
    public string? CameraType { get; set; }
    public string? CameraMotion { get; set; }
    public decimal DurationSeconds { get; set; } = 5;
    public string? CharacterPrompt { get; set; }
    public string? ScenePrompt { get; set; }
    public string? ActionPrompt { get; set; }
    public string? CameraPrompt { get; set; }
    public string? LightingPrompt { get; set; }
    public string? StylePrompt { get; set; }
    public string? QualityPrompt { get; set; }
    public int PromptVersion { get; set; } = 1;
    public bool PromptLocked { get; set; }
    public string PromptSourceLanguage { get; set; } = "zh-CN";
    public string? SelectedKeyframePath { get; set; }
    public string? VideoPath { get; set; }
    public string? FinalVideoPath { get; set; }
    public decimal? QualityScore { get; set; }
    public int? UserRating { get; set; }
    public JsonElement? VideoQc { get; set; }
    public string AudioStatus { get; set; } = "Pending";
    public string SubtitleStatus { get; set; } = "Pending";
}

public sealed class ReorderInput
{
    public List<long> ShotIds { get; set; } = [];
}

public sealed class ReferenceInput
{
    public string Kind { get; set; } = "identity";
    public bool IsAnchor { get; set; }
    /// <summary>
    /// A stable story/production stage such as base, injured, battle-worn or
    /// night. It is metadata only and never selects a workflow implicitly.
    /// </summary>
    public string Stage { get; set; } = "base";
    /// <summary>What this reference is responsible for: identity, outfit, pose, environment, etc.</summary>
    public string Role { get; set; } = "identity";
    /// <summary>Human-readable reason for introducing a new stage/reference.</summary>
    public string? ChangeReason { get; set; }
}

public sealed class QualityExperimentInput
{
    public string Name { get; set; } = "";
    public string ExperimentType { get; set; } = "Baseline";
    public string? BaselineId { get; set; }
    public string? ControlledVariable { get; set; }
    public string Status { get; set; } = "Open";
    public string? Description { get; set; }
}

public sealed class QualityExperimentRunInput
{
    public string TestCase { get; set; } = "";
    public long? TaskId { get; set; }
    public long? ParentTaskId { get; set; }
    public string? WorkflowVersion { get; set; }
    public string? ModelName { get; set; }
    public string Status { get; set; } = "Recorded";
    public JsonElement? Parameters { get; set; }
    public JsonElement? Metrics { get; set; }
    public int? HumanRating { get; set; }
    public string? Notes { get; set; }
}

public sealed class QualityGoldenSampleInput
{
    public string SampleKey { get; set; } = "";
    public string SampleType { get; set; } = "image";
    public string Path { get; set; } = "";
    public long? TaskId { get; set; }
    public decimal? QualityScore { get; set; }
    public JsonElement? Metadata { get; set; }
    public bool IsActive { get; set; } = true;
}

public sealed class I2VPreflightInput
{
    public string? InputImagePath { get; set; }
    public JsonElement? Parameters { get; set; }
}

public class TaskInput
{
    public long? ProjectId { get; set; }
    public long? EpisodeId { get; set; }
    public long? ShotId { get; set; }
    public string TaskType { get; set; } = "Image";
    public int Priority { get; set; }
    public int MaxRetries { get; set; } = 2;
    [JsonPropertyName("workflowId")]
    public long? WorkflowId { get; set; }
    [JsonPropertyName("loraIds")]
    public List<long>? LoraIds { get; set; }
    public string? InputImagePath { get; set; }
    public string? OutputName { get; set; }
    public JsonElement? Parameters { get; set; }
    public string ResourceClass { get; set; } = "GPU";
    public string? Stage { get; set; }
    public long? DependencyTaskId { get; set; }
    public long? ProductionRunId { get; set; }
    public string? RequestId { get; set; }
    public string? IdempotencyKey { get; set; }
}

public sealed record LoraBinding(string Name, double StrengthModel = 1, double StrengthClip = 1);

public sealed class WorkflowScanInput
{
    public string? RootPath { get; set; }
}

public sealed class TaskExecutionContext
{
    public long TaskId { get; init; }
    public string TaskType { get; init; } = "";
    public string? WorkflowPath { get; init; }
    public JsonDocument Parameters { get; init; } = JsonDocument.Parse("{}");
    public long? ProjectId { get; init; }
    public long? EpisodeId { get; init; }
    public long? ShotId { get; init; }
}

public sealed record GpuSnapshot(string Name, long TotalMiB, long FreeMiB, double UtilizationPercent);

public sealed record ComfySnapshot(bool Online, string? Version, string? Message, GpuSnapshot? Gpu);

public sealed record FfmpegProbe(
    int? Width,
    int? Height,
    double? DurationSeconds,
    double? Fps,
    string? Codec,
    bool HasAudio = false,
    double? AudioDurationSeconds = null,
    long? SizeBytes = null,
    long? FrameCount = null);

public sealed record FfmpegDetailedProbe(
    int? Width,
    int? Height,
    double? DurationSeconds,
    double? Fps,
    string? Codec,
    bool HasAudio,
    double? AudioDurationSeconds,
    string? AudioCodec,
    bool HasSubtitle,
    string? SubtitleCodec,
    long? SizeBytes,
    long? FrameCount);

public sealed record FfmpegDecodeResult(bool Passed, int ErrorCount, string? Error);

public sealed record GenerationFile(string Path, string FileName, string Type, string? MimeType);

public sealed class ScriptInput
{
    public long ProjectId { get; set; }
    public long? EpisodeId { get; set; }
    public string Title { get; set; } = "未命名剧本";
    public string Content { get; set; } = "";
    public string Language { get; set; } = "zh-CN";
    public string Status { get; set; } = "Draft";
}

public sealed class ScriptVersionInput
{
    public string? ChangeNote { get; set; }
}

public sealed class ScriptAnalyzeInput
{
    public long ScriptId { get; set; }
    public long? EpisodeId { get; set; }
    public bool UseLlm { get; set; } = true;
    public bool ReplaceDraftShots { get; set; } = true;
}

public sealed class PromptUpdateInput
{
    public string Prompt { get; set; } = "";
    public string? NegativePrompt { get; set; }
    public bool? Locked { get; set; }
    public string Source { get; set; } = "user";
}

/// <summary>
/// Rejects a common irreversible encoding-loss signature before it reaches MySQL.
/// A single question mark can be intentional punctuation; a run of two or more in
/// editable text is treated as a likely replacement for lost UTF-8 characters.
/// </summary>
public static class TextEncodingGuard
{
    private static readonly System.Text.RegularExpressions.Regex ConsecutiveQuestionMarks =
        new(@"\?{2,}", System.Text.RegularExpressions.RegexOptions.CultureInvariant);

    public static string? FindError(object input)
    {
        foreach (var property in input.GetType().GetProperties(System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public))
        {
            if (property.PropertyType != typeof(string) || property.GetValue(input) is not string value || string.IsNullOrWhiteSpace(value))
            {
                continue;
            }

            if (ConsecutiveQuestionMarks.IsMatch(value))
            {
                return $"字段“{DisplayName(property.Name)}”包含连续问号，疑似文本编码损坏；请使用 UTF-8 文本重新填写。";
            }
        }

        return null;
    }

    private static string DisplayName(string propertyName) => propertyName switch
    {
        "Name" => "名称",
        "Title" => "标题",
        "Description" => "说明",
        "AgeSetting" => "年龄设定",
        "FaceFeatures" => "脸部特征",
        "FixedPrompt" => "固定提示词",
        "NegativePrompt" => "负面提示词",
        "Prompt" => "提示词",
        "Content" => "剧本内容",
        _ => propertyName
    };
}

public sealed class CandidateSelectInput
{
    public bool Selected { get; set; } = true;
}

public sealed class RatingInput
{
    public int Rating { get; set; }
}

public sealed class ProductionStartInput
{
    public long EpisodeId { get; set; }
    public string Mode { get; set; } = "ManualReview";
    public int CandidateCount { get; set; } = 2;
    public bool GenerateAudio { get; set; } = true;
    public bool GenerateSubtitles { get; set; } = true;
    public string? IdempotencyKey { get; set; }
}

public sealed class ProductionConfirmInput
{
    public bool Confirmed { get; set; }
}

public sealed class TtsInput
{
    public long? ProjectId { get; set; }
    public long? EpisodeId { get; set; }
    public long? ShotId { get; set; }
    public string Text { get; set; } = "";
    public string VoiceId { get; set; } = "";
    public decimal Speed { get; set; } = 1;
    public decimal Pitch { get; set; }
    public string Instruction { get; set; } = "";
    public string? EngineVersion { get; set; }
    public string? OutputName { get; set; }
}

public sealed class SubtitleGenerateInput
{
    public long EpisodeId { get; set; }
    public string? OutputName { get; set; }
}

public sealed class LlmSettingsInput
{
    public string Provider { get; set; } = "OpenAICompatible";
    public string? BaseUrl { get; set; }
    public string? ApiKey { get; set; }
    public string? Model { get; set; }
    public decimal Temperature { get; set; } = 0.2m;
    public int MaxTokens { get; set; } = 3000;
}

public sealed class AudioSettingsInput
{
    public string? DefaultVoiceId { get; set; }
    public string? NarratorVoiceId { get; set; }
    public decimal VoiceVolume { get; set; } = 1;
    public decimal BgmVolume { get; set; } = 0.18m;
    public decimal SfxVolume { get; set; } = 0.6m;
}

public sealed record TtsPreflightResult(bool Passed, string VoiceId, string? Message, double? DurationSeconds);

public sealed class SoundEffectInput
{
    public string Name { get; set; } = "";
    public string Category { get; set; } = "environment";
}

public sealed class ShotSoundEffectInput
{
    public long SoundEffectId { get; set; }
    public decimal StartSeconds { get; set; }
    public decimal Volume { get; set; } = .6m;
}

public sealed class ProjectTemplateInput
{
    public string Name { get; set; } = "";
    public string TemplateType { get; set; } = "AI_Drama";
    public string? Description { get; set; }
    public JsonElement? Config { get; set; }
}

public sealed class BgmInput
{
    public string Name { get; set; } = "";
    public decimal Volume { get; set; } = 0.18m;
}

public sealed class EpisodeRenderInput
{
    public long EpisodeId { get; set; }
    public string? OutputName { get; set; }
    public bool IncludeSubtitles { get; set; } = true;
    public List<string> AudioPaths { get; set; } = [];
    /// <summary>
    /// Preview renders may use playable, unapproved sources. They are never
    /// considered a formal episode release and are labelled in the UI/output API.
    /// </summary>
    public bool Preview { get; set; }
}

public sealed record ScriptShotDraft(
    int ShotNumber,
    string Title,
    string Description,
    string? SceneName,
    IReadOnlyList<string> CharacterNames,
    string Action,
    string? Dialogue,
    string? Narration,
    string CameraType,
    string CameraMotion,
    string Emotion,
    decimal DurationSeconds);

public sealed record ScriptAnalysisResult(
    IReadOnlyList<ScriptShotDraft> Shots,
    IReadOnlyList<string> MissingCharacters,
    IReadOnlyList<string> MissingScenes,
    string Provider,
    string? RawLlmResponse = null);

public sealed record PromptComposition(
    string CharacterPrompt,
    string ScenePrompt,
    string ActionPrompt,
    string CameraPrompt,
    string LightingPrompt,
    string StylePrompt,
    string QualityPrompt,
    string Prompt,
    string NegativePrompt);
