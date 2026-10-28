using System.Security.Cryptography;

namespace VideoStudio.Server;

/// <summary>
/// Resolves media paths against the Studio data root and owns every external
/// upload write.  Callers never receive a general-purpose filesystem escape:
/// absolute paths are accepted only for compatible records already rooted in
/// Data, while new client input is converted to a relative, normalized path.
/// </summary>
public sealed class AssetPathPolicy
{
    private static readonly HashSet<string> ImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".png", ".jpg", ".jpeg", ".webp"
    };

    private static readonly HashSet<string> AudioExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".wav", ".mp3", ".ogg", ".flac"
    };

    private static readonly HashSet<string> VideoExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".mp4", ".mov", ".webm", ".mkv"
    };

    private readonly StudioSettings _settings;
    private readonly FfmpegService _ffmpeg;
    private readonly ILogger<AssetPathPolicy> _logger;
    private readonly string _dataRoot;
    private readonly string _dataRootWithSeparator;
    private readonly string _modelsRoot;
    private readonly string _modelsRootWithSeparator;
    private readonly string _workflowsRoot;
    private readonly string _workflowsRootWithSeparator;

    public AssetPathPolicy(StudioSettings settings, FfmpegService ffmpeg, ILogger<AssetPathPolicy> logger)
    {
        _settings = settings;
        _ffmpeg = ffmpeg;
        _logger = logger;
        _dataRoot = Path.GetFullPath(settings.DataPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        _dataRootWithSeparator = _dataRoot + Path.DirectorySeparatorChar;
        _modelsRoot = Path.GetFullPath(settings.ModelsPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        _modelsRootWithSeparator = _modelsRoot + Path.DirectorySeparatorChar;
        _workflowsRoot = Path.GetFullPath(settings.WorkflowsPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        _workflowsRootWithSeparator = _workflowsRoot + Path.DirectorySeparatorChar;
    }

    public bool TryResolveExisting(string? storedPath, out string fullPath, out string relativePath)
    {
        fullPath = string.Empty;
        relativePath = string.Empty;
        if (string.IsNullOrWhiteSpace(storedPath)) return false;

        try
        {
            var candidate = storedPath.Trim();
            if (LooksLikeUnsafeExternalPath(candidate)) return false;
            var full = Path.IsPathRooted(candidate)
                ? Path.GetFullPath(candidate)
                : Path.GetFullPath(Path.Combine(_dataRoot, candidate));
            if (!IsUnderDataRoot(full) || !File.Exists(full) || HasReparsePointInPath(full)) return false;
            fullPath = full;
            relativePath = Path.GetRelativePath(_dataRoot, full).Replace(Path.DirectorySeparatorChar, '/');
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Rejected invalid media path");
            return false;
        }
    }

    public bool IsAllowedExistingFile(string? storedPath)
        => TryResolveExisting(storedPath, out _, out _);

    public bool IsAllowedExistingModelFile(string? storedPath)
        => TryResolveExistingModel(storedPath, out _, out _);

    public bool IsAllowedExistingWorkflowFile(string? storedPath)
        => TryResolveExistingWorkflow(storedPath, out _, out _);

    public bool TryResolveExistingModel(string? storedPath, out string fullPath, out string relativePath)
    {
        fullPath = string.Empty;
        relativePath = string.Empty;
        if (string.IsNullOrWhiteSpace(storedPath)) return false;
        try
        {
            var candidate = storedPath.Trim();
            if (LooksLikeUnsafeExternalPath(candidate)) return false;
            var full = Path.IsPathRooted(candidate)
                ? Path.GetFullPath(candidate)
                : Path.GetFullPath(Path.Combine(_modelsRoot, candidate));
            if (!IsUnderModelsRoot(full) || !File.Exists(full) || HasReparsePointInPath(full)) return false;
            fullPath = full;
            relativePath = Path.GetRelativePath(_modelsRoot, full).Replace(Path.DirectorySeparatorChar, '/');
            return true;
        }
        catch { return false; }
    }

    public bool TryResolveExistingWorkflow(string? storedPath, out string fullPath, out string relativePath)
    {
        fullPath = string.Empty;
        relativePath = string.Empty;
        if (string.IsNullOrWhiteSpace(storedPath)) return false;
        try
        {
            var candidate = storedPath.Trim();
            if (LooksLikeUnsafeExternalPath(candidate)) return false;
            var full = Path.IsPathRooted(candidate)
                ? Path.GetFullPath(candidate)
                : Path.GetFullPath(Path.Combine(_workflowsRoot, candidate));
            if (!IsUnderWorkflowsRoot(full) || !string.Equals(Path.GetExtension(full), ".json", StringComparison.OrdinalIgnoreCase) || !File.Exists(full) || HasReparsePointInPath(full)) return false;
            fullPath = full;
            relativePath = Path.GetRelativePath(_workflowsRoot, full).Replace(Path.DirectorySeparatorChar, '/');
            return true;
        }
        catch { return false; }
    }

    public bool TryResolveExternalAssetPath(string? relativePath, out string fullPath, out string normalizedRelativePath)
    {
        fullPath = string.Empty;
        normalizedRelativePath = string.Empty;
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath) || LooksLikeUnsafeExternalPath(relativePath)) return false;
        return TryResolveExisting(relativePath, out fullPath, out normalizedRelativePath);
    }

    public string RequireExisting(string? storedPath, string errorMessage)
    {
        if (!TryResolveExisting(storedPath, out var full, out _)) throw new InvalidOperationException(errorMessage);
        return full;
    }

    public string RelativePathForExisting(string storedPath)
        => TryResolveExisting(storedPath, out _, out var relative) ? relative : throw new InvalidOperationException("媒体文件不存在或不在受控数据目录");

    public string BuildOutputPath(string folder, string requestedName, string fallbackName)
    {
        var safeFolder = NormalizeFolder(folder);
        var safeName = SanitizeFileName(requestedName, fallbackName);
        var directory = Path.Combine(_dataRoot, safeFolder);
        if (HasReparsePointInPath(directory)) throw new InvalidOperationException("输出目录包含不允许的重解析点");
        Directory.CreateDirectory(directory);
        var target = Path.GetFullPath(Path.Combine(directory, safeName));
        if (!IsUnderDataRoot(target) || HasReparsePointInPath(target)) throw new InvalidOperationException("输出目录不在受控数据范围内");
        return target;
    }

    public async Task<StoredUpload> StoreUploadAsync(
        IFormFile file,
        string folder,
        UploadKind kind,
        long maxBytes,
        CancellationToken ct = default)
    {
        if (file is null || file.Length <= 0) throw new AssetValidationException("上传文件不能为空");
        if (file.Length > maxBytes) throw new AssetValidationException($"上传文件不能超过 {FormatSize(maxBytes)}");

        var extension = Path.GetExtension(file.FileName).ToLowerInvariant();
        if (!IsExtensionAllowed(extension, kind)) throw new AssetValidationException(AllowedExtensionMessage(kind));
        if (!ContentTypeMatches(file.ContentType, kind)) throw new AssetValidationException("上传文件的 MIME 类型与媒体类型不匹配");

        var safeFolder = NormalizeFolder(folder);
        var directory = Path.Combine(_dataRoot, safeFolder);
        Directory.CreateDirectory(directory);
        if (HasReparsePointInPath(directory)) throw new AssetValidationException("上传目录包含不允许的重解析点");

        var safeStem = SanitizeStem(Path.GetFileNameWithoutExtension(file.FileName), "upload");
        var finalName = $"{DateTime.UtcNow:yyyyMMddHHmmss}_{Guid.NewGuid():N}_{safeStem}{extension}";
        var finalPath = Path.GetFullPath(Path.Combine(directory, finalName));
        if (!IsUnderDataRoot(finalPath)) throw new AssetValidationException("上传目标不在受控数据目录");
        var temporaryPath = Path.Combine(Path.Combine(_dataRoot, "Temp", "Uploads"), $"{Guid.NewGuid():N}.part");
        var temporaryDirectory = Path.GetDirectoryName(temporaryPath)!;
        if (HasReparsePointInPath(temporaryDirectory)) throw new AssetValidationException("上传临时目录包含不允许的重解析点");
        Directory.CreateDirectory(temporaryDirectory);
        if (HasReparsePointInPath(temporaryDirectory)) throw new AssetValidationException("上传临时目录包含不允许的重解析点");

        try
        {
            await using (var target = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan))
            await using (var source = file.OpenReadStream())
            {
                await source.CopyToAsync(target, ct);
                await target.FlushAsync(ct);
            }

            var bytes = new FileInfo(temporaryPath).Length;
            if (bytes <= 0 || bytes > maxBytes) throw new AssetValidationException("上传文件大小校验失败");
            await ValidateUploadContentAsync(temporaryPath, kind, ct);

            string hash;
            // End the read handle before the atomic move. File.Move on Windows can
            // fail with a sharing violation while this stream is still in scope.
            await using (var read = File.OpenRead(temporaryPath))
            {
                hash = Convert.ToHexString(await SHA256.HashDataAsync(read, ct)).ToLowerInvariant();
            }
            File.Move(temporaryPath, finalPath, false);
            return new StoredUpload(finalPath, Path.GetRelativePath(_dataRoot, finalPath).Replace(Path.DirectorySeparatorChar, '/'), Path.GetFileName(finalPath), hash, bytes);
        }
        finally
        {
            try { if (File.Exists(temporaryPath)) File.Delete(temporaryPath); } catch { }
        }
    }

    private async Task ValidateUploadContentAsync(string temporaryPath, UploadKind kind, CancellationToken ct)
    {
        if (kind == UploadKind.Image)
        {
            await using var stream = File.OpenRead(temporaryPath);
            var header = new byte[32];
            var count = await stream.ReadAsync(header.AsMemory(0, header.Length), ct);
            if (!LooksLikeImage(header.AsSpan(0, count))) throw new AssetValidationException("上传内容不是可识别的 PNG、JPEG 或 WebP 图像");
            var imageProbe = await _ffmpeg.ProbeAsync(temporaryPath, ct);
            if (imageProbe is not { Width: > 0, Height: > 0 }) throw new AssetValidationException("上传图像无法解码或尺寸无效");
            return;
        }

        var probe = await _ffmpeg.ProbeAsync(temporaryPath, ct);
        if (probe?.DurationSeconds is not > 0.05) throw new AssetValidationException("上传媒体无法解码或时长无效");
        if (kind == UploadKind.Audio && probe.HasAudio != true) throw new AssetValidationException("上传文件不包含可解码的音频流");
        if (kind == UploadKind.Video && (probe.Width is not > 0 || probe.Height is not > 0)) throw new AssetValidationException("上传文件不包含可解码的视频流");
    }

    private bool IsUnderDataRoot(string fullPath)
        => fullPath.StartsWith(_dataRootWithSeparator, StringComparison.OrdinalIgnoreCase);

    private bool IsUnderModelsRoot(string fullPath)
        => fullPath.StartsWith(_modelsRootWithSeparator, StringComparison.OrdinalIgnoreCase);

    private bool IsUnderWorkflowsRoot(string fullPath)
        => fullPath.StartsWith(_workflowsRootWithSeparator, StringComparison.OrdinalIgnoreCase);

    private static bool LooksLikeUnsafeExternalPath(string value)
    {
        if (value.StartsWith("\\\\", StringComparison.Ordinal)
            || value.StartsWith("\\\\?\\", StringComparison.Ordinal)
            || value.StartsWith("\\\\.\\", StringComparison.Ordinal)
            || value.Contains('\0')) return true;

        // A colon is valid only as the second character of a fully qualified
        // Windows drive path.  Reject ADS (file.txt:stream), drive-relative
        // paths (C:foo), URI-like values and other alternate path syntaxes.
        var colon = value.IndexOf(':');
        return colon >= 0 && !(colon == 1
            && char.IsLetter(value[0])
            && value.Length > 2
            && value[2] is '\\' or '/');
    }

    private static bool HasReparsePointInPath(string fullPath)
    {
        try
        {
            var file = new FileInfo(fullPath);
            if (file.Exists && (file.Attributes & FileAttributes.ReparsePoint) != 0) return true;
            var current = file.Directory;
            while (current is not null)
            {
                // A destination directory may legitimately not exist yet (for
                // example the first upload into Temp/Uploads). Inspect only
                // existing ancestors; nonexistent paths cannot themselves be
                // reparse points, but an existing reparse-point parent still
                // remains a rejection.
                if (current.Exists && (current.Attributes & FileAttributes.ReparsePoint) != 0) return true;
                current = current.Parent;
            }
        }
        catch { return true; }
        return false;
    }

    private static string NormalizeFolder(string folder)
    {
        var normalized = (folder ?? string.Empty).Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar).Trim(Path.DirectorySeparatorChar);
        if (string.IsNullOrWhiteSpace(normalized) || normalized.Contains("..", StringComparison.Ordinal) || Path.IsPathRooted(normalized) || LooksLikeUnsafeExternalPath(normalized))
            throw new AssetValidationException("上传目录无效");
        return normalized;
    }

    public static string SanitizeFileName(string? value, string fallback)
    {
        var extension = Path.GetExtension(value ?? string.Empty);
        var stem = SanitizeStem(Path.GetFileNameWithoutExtension(value ?? string.Empty), Path.GetFileNameWithoutExtension(fallback));
        extension = string.IsNullOrWhiteSpace(extension) ? Path.GetExtension(fallback) : extension.ToLowerInvariant();
        return $"{stem}{extension}";
    }

    private static string SanitizeStem(string? value, string fallback)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var stem = new string((value ?? string.Empty).Select(character => invalid.Contains(character) || char.IsControl(character) ? '_' : character).ToArray())
            .Trim()
            .TrimEnd('.');
        if (string.IsNullOrWhiteSpace(stem) || stem is "." or "..") stem = fallback;
        return stem.Length > 120 ? stem[..120] : stem;
    }

    private static bool IsExtensionAllowed(string extension, UploadKind kind)
        => kind switch
        {
            UploadKind.Image => ImageExtensions.Contains(extension),
            UploadKind.Audio => AudioExtensions.Contains(extension),
            UploadKind.Video => VideoExtensions.Contains(extension),
            _ => false
        };

    private static bool ContentTypeMatches(string? contentType, UploadKind kind)
    {
        if (string.IsNullOrWhiteSpace(contentType) || contentType.Equals("application/octet-stream", StringComparison.OrdinalIgnoreCase)) return true;
        return kind switch
        {
            UploadKind.Image => contentType.StartsWith("image/", StringComparison.OrdinalIgnoreCase),
            UploadKind.Audio => contentType.StartsWith("audio/", StringComparison.OrdinalIgnoreCase),
            UploadKind.Video => contentType.StartsWith("video/", StringComparison.OrdinalIgnoreCase),
            _ => false
        };
    }

    private static string AllowedExtensionMessage(UploadKind kind) => kind switch
    {
        UploadKind.Image => "只允许 PNG、JPG、JPEG、WebP 图像",
        UploadKind.Audio => "只允许 WAV、MP3、OGG、FLAC 音频",
        UploadKind.Video => "只允许 MP4、MOV、WEBM、MKV 视频",
        _ => "上传媒体类型不受支持"
    };

    private static bool LooksLikeImage(ReadOnlySpan<byte> header)
        => header.Length >= 8 && header[..8].SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 })
           || header.Length >= 3 && header[..3].SequenceEqual(new byte[] { 255, 216, 255 })
           || header.Length >= 12 && header[..4].SequenceEqual("RIFF"u8) && header[8..12].SequenceEqual("WEBP"u8);

    private static string FormatSize(long bytes)
        => bytes >= 1024L * 1024L ? $"{bytes / 1024d / 1024d:0}MB" : $"{bytes / 1024d:0}KB";
}

public enum UploadKind { Image, Audio, Video }

public sealed record StoredUpload(string FullPath, string RelativePath, string FileName, string Sha256, long SizeBytes);

public sealed class AssetValidationException : InvalidOperationException
{
    public AssetValidationException(string message) : base(message) { }
}
