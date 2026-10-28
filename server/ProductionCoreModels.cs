using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed class ProductionProfileInput
{
    public long ProjectId { get; set; }
    public string ProfileKey { get; set; } = "default";
    public string Name { get; set; } = "Default Production Profile";
    public int OutputWidth { get; set; } = 1920;
    public int OutputHeight { get; set; } = 1080;
    public int OutputFps { get; set; } = 30;
    public string VideoCodec { get; set; } = "h264";
    public string AudioCodec { get; set; } = "aac";
    public int AudioSampleRate { get; set; } = 48000;
    public string ColorSpace { get; set; } = "bt709";
    public JsonElement? Settings { get; set; }
    public string CreatedBy { get; set; } = "administrator";
}

public sealed class EntityVersionCaptureInput
{
    public long ProjectId { get; set; }
    public string EntityType { get; set; } = "Character";
    public long EntityId { get; set; }
    public List<long> SourceAssetIds { get; set; } = [];
    public string? Note { get; set; }
    public string CreatedBy { get; set; } = "administrator";
}

public sealed class ShotPlanInput
{
    public long ProjectId { get; set; }
    public long EpisodeId { get; set; }
    public long ShotId { get; set; }
    public long ProductionProfileId { get; set; }
    public List<long> CharacterVersionIds { get; set; } = [];
    public long? SceneVersionId { get; set; }
    public long PromptVersionId { get; set; }
    public long WorkflowVersionId { get; set; }
    public long? VoiceVersionId { get; set; }
    public List<long> InputAssetIds { get; set; } = [];
    public JsonElement? Parameters { get; set; }
    public string CreatedBy { get; set; } = "administrator";
}

public sealed record TaskLease(
    long TaskId,
    long AttemptId,
    int AttemptNo,
    int StateVersion,
    string WorkerId,
    string LeaseToken,
    string TempRelativePath);

public enum TaskLifecycleState
{
    Pending,
    Running,
    Succeeded,
    Failed,
    Cancelled
}

public static class TaskStateMachine
{
    private static readonly IReadOnlyDictionary<TaskLifecycleState, HashSet<TaskLifecycleState>> Allowed =
        new Dictionary<TaskLifecycleState, HashSet<TaskLifecycleState>>
        {
            [TaskLifecycleState.Pending] = [TaskLifecycleState.Running, TaskLifecycleState.Failed, TaskLifecycleState.Cancelled],
            [TaskLifecycleState.Running] = [TaskLifecycleState.Pending, TaskLifecycleState.Succeeded, TaskLifecycleState.Failed, TaskLifecycleState.Cancelled],
            [TaskLifecycleState.Succeeded] = [],
            [TaskLifecycleState.Failed] = [TaskLifecycleState.Pending],
            [TaskLifecycleState.Cancelled] = [TaskLifecycleState.Pending]
        };

    public static bool CanTransition(TaskLifecycleState from, TaskLifecycleState to)
        => Allowed.TryGetValue(from, out var destinations) && destinations.Contains(to);

    public static void Require(TaskLifecycleState from, TaskLifecycleState to)
    {
        if (!CanTransition(from, to))
            throw new InvalidOperationException($"Illegal task transition: {from} -> {to}");
    }

    public static TaskLifecycleState Parse(string value)
        => Enum.TryParse<TaskLifecycleState>(value, true, out var parsed)
            ? parsed
            : throw new InvalidOperationException($"Unknown task state: {value}");
}

public enum ArtifactPurpose
{
    Image,
    Video,
    Audio,
    Subtitle,
    Episode,
    EpisodePreview,
    Master,
    Cover,
    QaReport
}

public sealed record ArtifactPublishSpec(
    long ProjectId,
    long? EpisodeId,
    long? ShotId,
    ArtifactPurpose Purpose,
    string FileName,
    long? ProductionProfileId = null,
    long? ShotPlanId = null,
    JsonElement? InputManifest = null);

public sealed record PublishedArtifact(
    long ManifestId,
    long AssetId,
    long ResultId,
    ArtifactPurpose Purpose,
    string FullPath,
    string RelativePath,
    string Sha256,
    long SizeBytes);

public sealed record TaskWorkspace(TaskLease Lease, string FullPath, string RelativePath);

public sealed record ResolvedAssetReference(
    long AssetId,
    long ProjectId,
    long? EpisodeId,
    long? ShotId,
    string Purpose,
    string FullPath,
    string RelativePath,
    string Extension,
    string Status,
    long? ManifestId,
    int AssetVersion = 1);

public sealed class FormalTaskInput : TaskInput
{
    public long ProductionProfileId { get; set; }
    public long? ShotPlanId { get; set; }
    public long? InputAssetId { get; set; }
    public List<long> InputAssetIds { get; set; } = [];
}

public sealed record FormalTaskSubmission(long TaskId, bool Created, string IdempotencyKey, string Fingerprint);

public static class CanonicalJson
{
    public static string Serialize<T>(T value)
    {
        using var document = JsonDocument.Parse(JsonSerializer.Serialize(value));
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream)) Write(writer, document.RootElement);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    public static string Sha256(string canonicalJson)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonicalJson))).ToLowerInvariant();

    private static void Write(Utf8JsonWriter writer, JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (var property in element.EnumerateObject().OrderBy(property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    Write(writer, property.Value);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var item in element.EnumerateArray()) Write(writer, item);
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText());
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
            case JsonValueKind.Undefined:
                writer.WriteNullValue();
                break;
        }
    }
}
