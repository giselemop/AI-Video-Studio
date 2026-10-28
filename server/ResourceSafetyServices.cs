using System.Globalization;

namespace VideoStudio.Server;

public sealed record DiskSpaceCheck(
    bool Allowed,
    string Root,
    long AvailableBytes,
    long RequiredBytes,
    string Reason);

/// <summary>
/// Rejects expensive work before media/model execution when the target volume
/// is below the configured free-space floor. It never deletes files.
/// </summary>
public sealed class DiskSpaceGuard
{
    private readonly StudioSettings _settings;

    public DiskSpaceGuard(StudioSettings settings) => _settings = settings;

    public DiskSpaceCheck Check(string? targetPath = null, long additionalBytes = 0)
    {
        var requested = string.IsNullOrWhiteSpace(targetPath) ? _settings.DataPath : targetPath;
        try
        {
            var full = Path.GetFullPath(requested);
            var root = Path.GetPathRoot(full);
            if (string.IsNullOrWhiteSpace(root)) return new(false, "", 0, _settings.MinimumFreeDiskBytes, "目标路径没有可检查的卷根");
            var drive = new DriveInfo(root);
            var required = Math.Max(_settings.MinimumFreeDiskBytes, Math.Max(0, additionalBytes));
            var available = drive.AvailableFreeSpace;
            return new(available >= required, root, available, required,
                available >= required ? "free-space floor satisfied" : "free-space floor not satisfied");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return new(false, requested, 0, _settings.MinimumFreeDiskBytes, $"无法读取目标卷空间：{ex.Message}");
        }
    }

    public static bool IsHighCostTask(string? taskType, string? resourceClass)
    {
        if (string.Equals(resourceClass, "GPU", StringComparison.OrdinalIgnoreCase)) return true;
        return taskType?.Trim() switch
        {
            "Image" or "Keyframe" or "ImageToVideo" or "Video" or "Enhance" or "VideoEnhancement"
                or "Audio" or "TTS" or "Subtitles" or "Concat" or "VideoConcat"
                  or "EpisodeRender" or "EpisodeBuild" or "Master" or "SkinComposite" => true,
            _ => false
        };
    }

    public static string Diagnostic(DiskSpaceCheck check)
        => $"{check.Reason}; root={check.Root}; available={check.AvailableBytes.ToString(CultureInfo.InvariantCulture)}; required={check.RequiredBytes.ToString(CultureInfo.InvariantCulture)}";
}

public sealed record CacheCleanupCandidate(string RelativePath, long SizeBytes, DateTime LastWriteTimeUtc, string Reason);

public sealed record CacheCleanupPreview(
    bool DryRun,
    int CandidateCount,
    long CandidateBytes,
    IReadOnlyList<CacheCleanupCandidate> Candidates,
    string[] ScannedRoots);

/// <summary>
/// Read-only cache cleanup preview. The service intentionally has no delete
/// method; production cleanup must be separately reviewed and implemented.
/// </summary>
public sealed class CacheCleanupService
{
    private readonly StudioSettings _settings;
    private readonly StudioDb _db;

    public CacheCleanupService(StudioSettings settings, StudioDb db)
    {
        _settings = settings;
        _db = db;
    }

    public async Task<CacheCleanupPreview> PreviewAsync(TimeSpan? minimumAge = null, CancellationToken ct = default)
    {
        var threshold = DateTime.UtcNow - (minimumAge ?? TimeSpan.FromHours(24));
        var roots = new[]
        {
            Path.Combine(_settings.DataPath, "Cache"),
            Path.Combine(_settings.DataPath, "AudioCache")
        };
        var referenced = await ReferencedPathsAsync(ct);
        var candidates = new List<CacheCleanupCandidate>();
        foreach (var root in roots)
        {
            if (!Directory.Exists(root)) continue;
            foreach (var file in EnumerateSafeFiles(root))
            {
                var info = new FileInfo(file);
                if (info.LastWriteTimeUtc > threshold) continue;
                var relative = Path.GetRelativePath(_settings.DataPath, file).Replace(Path.DirectorySeparatorChar, '/');
                var normalizedFull = Path.GetFullPath(file);
                if (referenced.Contains(relative) || referenced.Contains(normalizedFull)) continue;
                candidates.Add(new CacheCleanupCandidate(relative, info.Length, info.LastWriteTimeUtc, "unreferenced cache older than retention threshold"));
            }
        }
        return new(true, candidates.Count, candidates.Sum(candidate => candidate.SizeBytes), candidates, roots);
    }

    private async Task<HashSet<string>> ReferencedPathsAsync(CancellationToken ct)
    {
        var values = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (var row in await _db.QueryAsync("SELECT path,relative_path FROM assets WHERE path IS NOT NULL OR relative_path IS NOT NULL", cancellationToken: ct))
            {
                Add(row.Text("path"));
                Add(row.Text("relativePath"));
            }
            foreach (var row in await _db.QueryAsync("SELECT path FROM audio_cache WHERE path IS NOT NULL", cancellationToken: ct)) Add(row.Text("path"));
        }
        catch (MySqlConnector.MySqlException)
        {
            // A preview must fail closed rather than propose deletion when the
            // reference query is unavailable.
            values.Add("__DATABASE_REFERENCE_LOOKUP_FAILED__");
        }
        return values;

        void Add(string? value)
        {
            if (string.IsNullOrWhiteSpace(value)) return;
            values.Add(value.Replace('\\', '/'));
            if (Path.IsPathRooted(value)) values.Add(Path.GetFullPath(value));
        }
    }

    private static IEnumerable<string> EnumerateSafeFiles(string root)
    {
        var rootInfo = new DirectoryInfo(root);
        if ((rootInfo.Attributes & FileAttributes.ReparsePoint) != 0) yield break;
        var pending = new Stack<DirectoryInfo>();
        pending.Push(rootInfo);
        while (pending.Count > 0)
        {
            var current = pending.Pop();
            FileInfo[] files;
            DirectoryInfo[] directories;
            try
            {
                files = current.GetFiles();
                directories = current.GetDirectories();
            }
            catch (IOException) { continue; }
            catch (UnauthorizedAccessException) { continue; }
            foreach (var file in files)
            {
                if ((file.Attributes & FileAttributes.ReparsePoint) == 0) yield return file.FullName;
            }
            foreach (var directory in directories)
            {
                if ((directory.Attributes & FileAttributes.ReparsePoint) == 0) pending.Push(directory);
            }
        }
    }
}

public sealed class AssetRetentionException : InvalidOperationException
{
    public AssetRetentionException(string message) : base(message) { }
}
