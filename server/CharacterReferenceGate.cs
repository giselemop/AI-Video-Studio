using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed record CharacterReferenceBinding(
    long CharacterId,
    long ReferenceId,
    string FullPath,
    string RelativePath,
    int AssetVersion,
    string AssetSha256,
    string ReviewStatus,
    string Reviewer);

public sealed record CharacterReferenceGateResult(
    bool Passed,
    IReadOnlyList<CharacterReferenceBinding> References,
    IReadOnlyList<string> Issues);

/// <summary>
/// Character identity is a production input, not a descriptive label. Every
/// referenced anchor must have an append-only human decision tied to the exact
/// bytes and version currently on disk.
/// </summary>
public sealed class CharacterReferenceGateService
{
    private readonly StudioRepository _repository;
    private readonly FfmpegService _ffmpeg;
    private readonly AssetPathPolicy _paths;

    public CharacterReferenceGateService(StudioRepository repository, FfmpegService ffmpeg, AssetPathPolicy paths)
    {
        _repository = repository;
        _ffmpeg = ffmpeg;
        _paths = paths;
    }

    public async Task<CharacterReferenceGateResult> CheckShotAsync(long shotId, CancellationToken ct = default)
    {
        var shot = (await _repository.QueryShotAsync(shotId, ct)).FirstOrDefault();
        if (shot is null) return new(false, [], ["镜头不存在，无法核验角色参考图"]);
        var characterIds = ReadCharacterIds(shot.Text("characterIdsJson"));
        if (characterIds.Count == 0) return new(true, [], []);

        var bindings = new List<CharacterReferenceBinding>();
        var issues = new List<string>();
        foreach (var characterId in characterIds)
        {
            var references = await _repository.CharacterReferencesAsync(characterId, ct);
            var reference = references.FirstOrDefault(row => row.Bool("isAnchor")) ?? references.FirstOrDefault();
            if (reference is null)
            {
                issues.Add($"角色 {characterId} 没有可用的主参考图");
                continue;
            }

            var metadata = ReadMetadata(reference.Text("metadataJson"));
            var status = GetString(metadata, "humanReviewStatus") ?? "NeedReview";
            var reviewer = GetString(metadata, "reviewer");
            var expectedHash = GetString(metadata, "assetSha256");
            var version = GetInt(metadata, "assetVersion");
            var referencePath = reference.Text("path");
            if (!string.Equals(status, "Approved", StringComparison.OrdinalIgnoreCase))
                issues.Add($"角色 {characterId} 参考图 {reference.Long("id")} 未获人工批准（当前 {status}）");
            if (version <= 0 || !IsSha256(expectedHash) || string.IsNullOrWhiteSpace(reviewer))
                issues.Add($"角色 {characterId} 参考图 {reference.Long("id")} 缺少完整的审核版本、哈希或审核人");
            if (!_paths.TryResolveExisting(referencePath, out var fullPath, out var relativePath))
            {
                issues.Add($"角色 {characterId} 参考图 {reference.Long("id")} 不存在或不在受控媒体目录");
                continue;
            }
            var actualHash = await _ffmpeg.Sha256Async(fullPath, ct);
            if (!IsSha256(actualHash) || !string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
            {
                issues.Add($"角色 {characterId} 参考图 {reference.Long("id")} 文件已变化，必须重新审核");
                continue;
            }
            bindings.Add(new CharacterReferenceBinding(characterId, reference.Long("id"), fullPath, relativePath, version, actualHash!, status, reviewer!));
        }
        return new(issues.Count == 0, bindings, issues);
    }

    public static IReadOnlyList<long> ReadCharacterIds(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return [];
        try
        {
            using var document = JsonDocument.Parse(json);
            return document.RootElement.ValueKind == JsonValueKind.Array
                ? document.RootElement.EnumerateArray().Where(item => item.TryGetInt64(out var id) && id > 0).Select(item => item.GetInt64()).Distinct().ToArray()
                : [];
        }
        catch (JsonException) { return []; }
    }

    private static Dictionary<string, object?> ReadMetadata(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return new(StringComparer.OrdinalIgnoreCase);
        try { return JsonSerializer.Deserialize<Dictionary<string, object?>>(json) ?? new(StringComparer.OrdinalIgnoreCase); }
        catch (JsonException) { return new(StringComparer.OrdinalIgnoreCase); }
    }

    private static string? GetString(IReadOnlyDictionary<string, object?> values, string key)
        => values.TryGetValue(key, out var value) ? Convert.ToString(value, CultureInfo.InvariantCulture) : null;

    private static int GetInt(IReadOnlyDictionary<string, object?> values, string key)
        => values.TryGetValue(key, out var value) && int.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Integer, CultureInfo.InvariantCulture, out var result) ? result : 0;

    private static bool IsSha256(string? value)
        => !string.IsNullOrWhiteSpace(value) && value.Length == 64 && value.All(Uri.IsHexDigit);
}
