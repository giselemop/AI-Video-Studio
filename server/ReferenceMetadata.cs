using System.Text.Json;

namespace VideoStudio.Server;

/// <summary>
/// Normalizes and reads stage-aware reference metadata. The metadata lives in
/// the existing JSON column so this first slice is additive and does not alter
/// or rewrite existing reference rows.
/// </summary>
public static class ReferenceMetadata
{
    public const string DefaultStage = "base";
    public const string DefaultRole = "identity";

    public static string NormalizeStage(string? value, string? fallback = null)
        => Normalize(value, fallback ?? DefaultStage, 64, "参考图阶段");

    public static string NormalizeRole(string? value, string? fallback = null)
        => Normalize(value, fallback ?? DefaultRole, 32, "参考图用途");

    public static string? NormalizeChangeReason(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var normalized = value.Trim();
        if (normalized.Length > 500 || normalized.Any(char.IsControl))
            throw new AssetValidationException("参考图阶段变更说明长度或字符不合法");
        return normalized;
    }

    public static string CreateJson(string sha256, string? stage, string? role, string? changeReason)
    {
        var metadata = new Dictionary<string, object?>
        {
            ["assetVersion"] = 1,
            ["assetSha256"] = sha256,
            ["humanReviewStatus"] = "NeedReview",
            ["reviewer"] = null,
            ["reviewedAt"] = null,
            ["reviewNote"] = null,
            ["stage"] = NormalizeStage(stage),
            ["role"] = NormalizeRole(role),
            ["changeReason"] = NormalizeChangeReason(changeReason)
        };
        return JsonSerializer.Serialize(metadata);
    }

    public static ReferenceMetadataSnapshot Read(string? json, string? fallbackRole = null)
    {
        var stage = DefaultStage;
        var role = NormalizeRole(fallbackRole, DefaultRole);
        var changeReason = (string?)null;
        var assetVersion = 1;
        string? sha256 = null;
        var reviewStatus = "NeedReview";
        string? reviewer = null;

        try
        {
            using var document = JsonDocument.Parse(string.IsNullOrWhiteSpace(json) ? "{}" : json);
            var root = document.RootElement;
            stage = ReadString(root, "stage") is { } stageValue ? NormalizeStage(stageValue) : stage;
            role = ReadString(root, "role") is { } roleValue ? NormalizeRole(roleValue, role) : role;
            changeReason = NormalizeChangeReason(ReadString(root, "changeReason"));
            if (root.TryGetProperty("assetVersion", out var version) && version.TryGetInt32(out var parsedVersion)) assetVersion = Math.Max(1, parsedVersion);
            sha256 = ReadString(root, "assetSha256");
            reviewStatus = ReadString(root, "humanReviewStatus") ?? reviewStatus;
            reviewer = ReadString(root, "reviewer");
        }
        catch (AssetValidationException) { throw; }
        catch (JsonException) { }

        return new ReferenceMetadataSnapshot(stage, role, changeReason, assetVersion, sha256, reviewStatus, reviewer);
    }

    private static string Normalize(string? value, string fallback, int maxLength, string label)
    {
        var normalized = string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
        if (normalized.Length == 0 || normalized.Length > maxLength || normalized.Any(char.IsControl)
            || normalized.Contains('\\') || normalized.Contains('/') || normalized.Contains("..", StringComparison.Ordinal))
            throw new AssetValidationException($"{label}不合法：只能使用短文本标签，不能包含路径字符");
        return normalized;
    }

    private static string? ReadString(JsonElement root, string name)
        => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
}

public sealed record ReferenceMetadataSnapshot(
    string Stage,
    string Role,
    string? ChangeReason,
    int AssetVersion,
    string? Sha256,
    string ReviewStatus,
    string? Reviewer);
