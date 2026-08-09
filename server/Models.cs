using System.Text.Json;

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
}

public sealed class TaskInput
{
    public long? ProjectId { get; set; }
    public long? EpisodeId { get; set; }
    public long? ShotId { get; set; }
    public string TaskType { get; set; } = "Image";
    public int Priority { get; set; }
    public int MaxRetries { get; set; } = 2;
    public long? WorkflowId { get; set; }
    public string? InputImagePath { get; set; }
    public string? OutputName { get; set; }
    public JsonElement? Parameters { get; set; }
    public string ResourceClass { get; set; } = "GPU";
    public string? Stage { get; set; }
    public long? DependencyTaskId { get; set; }
}

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

public sealed record FfmpegProbe(int? Width, int? Height, double? DurationSeconds, double? Fps, string? Codec, bool HasAudio = false);

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
    long? SizeBytes);

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
