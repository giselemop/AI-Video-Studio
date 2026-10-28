using System.Data;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MySqlConnector;

namespace VideoStudio.Server;

public static class ArtifactPurposePolicy
{
    private static readonly IReadOnlyDictionary<ArtifactPurpose, HashSet<string>> Extensions =
        new Dictionary<ArtifactPurpose, HashSet<string>>
        {
            [ArtifactPurpose.Image] = Set(".png", ".jpg", ".jpeg", ".webp"),
            [ArtifactPurpose.Cover] = Set(".png", ".jpg", ".jpeg", ".webp"),
            [ArtifactPurpose.Video] = Set(".mp4"),
            [ArtifactPurpose.Episode] = Set(".mp4"),
            [ArtifactPurpose.EpisodePreview] = Set(".mp4"),
            [ArtifactPurpose.Master] = Set(".mp4"),
            [ArtifactPurpose.Audio] = Set(".wav", ".mp3", ".ogg", ".flac"),
            [ArtifactPurpose.Subtitle] = Set(".srt", ".vtt"),
            [ArtifactPurpose.QaReport] = Set(".json", ".md")
        };

    public static bool Allows(ArtifactPurpose purpose, string? extension)
        => extension is not null && Extensions.TryGetValue(purpose, out var allowed) && allowed.Contains(extension);

    public static string MimeType(ArtifactPurpose purpose, string extension) => extension.ToLowerInvariant() switch
    {
        ".png" => "image/png",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".webp" => "image/webp",
        ".mp4" => "video/mp4",
        ".wav" => "audio/wav",
        ".mp3" => "audio/mpeg",
        ".ogg" => "audio/ogg",
        ".flac" => "audio/flac",
        ".srt" => "application/x-subrip",
        ".vtt" => "text/vtt",
        ".json" when purpose == ArtifactPurpose.QaReport => "application/json",
        ".md" when purpose == ArtifactPurpose.QaReport => "text/markdown",
        _ => "application/octet-stream"
    };

    public static string AssetType(ArtifactPurpose purpose) => purpose switch
    {
        ArtifactPurpose.Image or ArtifactPurpose.Cover => "image",
        ArtifactPurpose.Audio => "audio",
        ArtifactPurpose.Subtitle => "subtitle",
        ArtifactPurpose.QaReport => "report",
        _ => "video"
    };

    public static string ResultType(ArtifactPurpose purpose) => purpose switch
    {
        ArtifactPurpose.EpisodePreview => "episode_preview",
        ArtifactPurpose.Episode => "episode",
        ArtifactPurpose.QaReport => "qa_report",
        _ => purpose.ToString().ToLowerInvariant()
    };

    private static HashSet<string> Set(params string[] values) => new(values, StringComparer.OrdinalIgnoreCase);
}

/// <summary>
/// Creates attempt-local workspaces and publishes validated files through an
/// append-only manifest. Final file names are versioned and are never replaced.
/// </summary>
public sealed class TaskArtifactService
{
    private readonly StudioSettings _settings;
    private readonly FfmpegService _ffmpeg;
    private readonly string _dataRoot;
    private readonly string _dataRootPrefix;

    public TaskArtifactService(StudioSettings settings, FfmpegService ffmpeg)
    {
        _settings = settings;
        _ffmpeg = ffmpeg;
        _dataRoot = Path.GetFullPath(settings.DataPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        _dataRootPrefix = _dataRoot + Path.DirectorySeparatorChar;
    }

    public TaskWorkspace CreateWorkspace(TaskLease lease)
    {
        var relative = lease.TempRelativePath.Replace('/', Path.DirectorySeparatorChar);
        var full = Path.GetFullPath(Path.Combine(_dataRoot, relative));
        RequireUnderDataRoot(full);
        if (!full.StartsWith(Path.Combine(_dataRoot, "Temp", "Tasks") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("Task workspace must be below Data/Temp/Tasks");
        EnsureNoReparsePoint(full);
        Directory.CreateDirectory(full);
        EnsureNoReparsePoint(full);
        return new TaskWorkspace(lease, full, Path.GetRelativePath(_dataRoot, full).Replace(Path.DirectorySeparatorChar, '/'));
    }

    public string CreateStagedPath(TaskWorkspace workspace, string requestedName, string fallbackName)
    {
        var name = AssetPathPolicy.SanitizeFileName(requestedName, fallbackName);
        if (name.EndsWith(".part", StringComparison.OrdinalIgnoreCase) || name.Contains(".part-", StringComparison.OrdinalIgnoreCase)
            || name.Contains(".tmp-", StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("Partial-file names cannot be published");
        var full = Path.GetFullPath(Path.Combine(workspace.FullPath, name));
        RequireInside(full, workspace.FullPath);
        EnsureNoReparsePoint(full);
        if (File.Exists(full)) throw new AssetValidationException("Task staged output already exists");
        return full;
    }

    public Task ValidateStagedAsync(string stagedPath, ArtifactPurpose purpose, CancellationToken ct = default)
        => ValidateAsync(Path.GetFullPath(stagedPath), purpose, ct);

    public async Task<PublishedArtifact> PublishAsync(TaskWorkspace workspace, ArtifactPublishSpec spec, string stagedPath, CancellationToken ct = default)
    {
        if (spec.ProjectId <= 0) throw new AssetValidationException("A project-owned task is required for formal publication");
        var source = Path.GetFullPath(stagedPath);
        RequireInside(source, workspace.FullPath);
        EnsureNoReparsePoint(source);
        if (!File.Exists(source)) throw new AssetValidationException("Staged artifact does not exist");
        if (source.EndsWith(".part", StringComparison.OrdinalIgnoreCase) || Path.GetFileName(source).Contains(".part-", StringComparison.OrdinalIgnoreCase)
            || Path.GetFileName(source).Contains(".tmp-", StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("Partial artifacts cannot be published");

        var extension = Path.GetExtension(source).ToLowerInvariant();
        if (!ArtifactPurposePolicy.Allows(spec.Purpose, extension))
            throw new AssetValidationException($"Extension {extension} is not allowed for {spec.Purpose}");
        var validation = await ValidateAsync(source, spec.Purpose, ct);
        var hash = await Sha256Async(source, ct);
        var size = new FileInfo(source).Length;
        var version = await NextVersionAsync(workspace.Lease, spec.Purpose, ct);
        var finalName = BuildImmutableName(spec.FileName, extension, version, hash);
        var finalRelative = $"Artifacts/project-{spec.ProjectId}/{spec.Purpose.ToString().ToLowerInvariant()}/task-{workspace.Lease.TaskId}/v{version:0000}/{finalName}";
        var finalPath = Path.GetFullPath(Path.Combine(_dataRoot, finalRelative.Replace('/', Path.DirectorySeparatorChar)));
        RequireUnderDataRoot(finalPath);
        EnsureNoReparsePoint(finalPath);
        Directory.CreateDirectory(Path.GetDirectoryName(finalPath)!);
        EnsureNoReparsePoint(Path.GetDirectoryName(finalPath)!);
        if (File.Exists(finalPath)) throw new IOException("Immutable artifact target already exists");

        var intentId = await CreatePublishIntentAsync(workspace.Lease, spec, workspace.RelativePathFor(source), finalRelative, ct);
        var moved = false;
        try
        {
            IOException? moveError = null;
            for (var moveAttempt = 1; moveAttempt <= 4 && !moved; moveAttempt++)
            {
                try
                {
                    File.Move(source, finalPath, false);
                    moved = true;
                }
                catch (IOException ex) when (moveAttempt < 4)
                {
                    moveError = ex;
                    await Task.Delay(TimeSpan.FromMilliseconds(250 * moveAttempt), ct);
                }
            }
            if (!moved)
            {
                try
                {
                    // Some Windows file scanners briefly hold the staged file
                    // after validation. The destination is unique and the
                    // source has already passed the size/decode checks, so a
                    // verified copy is a safe publication fallback.
                    File.Copy(source, finalPath, false);
                    moved = true;
                    try { File.Delete(source); } catch (IOException) { }
                }
                catch (IOException ex)
                {
                    throw moveError ?? ex;
                }
            }
            return await RecordPublishedAsync(workspace.Lease, spec, intentId, finalPath, finalRelative, finalName, extension, hash, size, validation, version, ct);
        }
        catch (Exception ex)
        {
            await MarkNeedsReconcileAsync(intentId, moved ? "final file moved but database finalization failed" : "atomic move failed", ex, CancellationToken.None);
            throw;
        }
    }

    private async Task<(FfmpegProbe? Probe, string ProbeJson)> ValidateAsync(string path, ArtifactPurpose purpose, CancellationToken ct)
    {
        var firstLength = new FileInfo(path).Length;
        if (firstLength <= 0) throw new AssetValidationException("Artifact is empty");
        await Task.Delay(100, ct);
        var secondLength = new FileInfo(path).Length;
        if (firstLength != secondLength) throw new AssetValidationException("Artifact is still being written");
        await using (var exclusiveRead = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            if (exclusiveRead.Length != secondLength) throw new AssetValidationException("Artifact length changed during validation");
        }

        if (purpose == ArtifactPurpose.Subtitle)
        {
            if (secondLength < 8 || secondLength > 20 * 1024 * 1024) throw new AssetValidationException("Subtitle size is invalid");
            var text = await File.ReadAllTextAsync(path, Encoding.UTF8, ct);
            if (text.Contains('\0') || !HasCompleteSubtitleCue(text)) throw new AssetValidationException("Subtitle content is incomplete or malformed");
            return (null, JsonSerializer.Serialize(new { kind = "subtitle", chars = text.Length }));
        }
        if (purpose == ArtifactPurpose.QaReport)
        {
            if (secondLength > 20 * 1024 * 1024) throw new AssetValidationException("QA report is too large");
            if (Path.GetExtension(path).Equals(".json", StringComparison.OrdinalIgnoreCase))
            {
                await using var report = File.OpenRead(path);
                using var document = await JsonDocument.ParseAsync(report, cancellationToken: ct);
                if (document.RootElement.ValueKind is not (JsonValueKind.Object or JsonValueKind.Array)) throw new AssetValidationException("QA report must be JSON");
                return (null, JsonSerializer.Serialize(new { kind = "json", bytes = secondLength }));
            }
            var markdown = await File.ReadAllTextAsync(path, Encoding.UTF8, ct);
            if (string.IsNullOrWhiteSpace(markdown) || markdown.Contains('\0')) throw new AssetValidationException("QA Markdown report is empty or malformed");
            return (null, JsonSerializer.Serialize(new { kind = "markdown", chars = markdown.Length }));
        }

        if (secondLength < 32) throw new AssetValidationException("Media artifact is too small to be complete");
        var probe = await _ffmpeg.ProbeAsync(path, ct) ?? throw new AssetValidationException("Artifact cannot be decoded by ffprobe");
        switch (purpose)
        {
            case ArtifactPurpose.Image:
            case ArtifactPurpose.Cover:
                if (probe.Width is not > 0 || probe.Height is not > 0) throw new AssetValidationException("Image dimensions are invalid");
                break;
            case ArtifactPurpose.Audio:
                if (!probe.HasAudio || probe.AudioDurationSeconds is not > 0.05) throw new AssetValidationException("Audio stream is missing or too short");
                break;
            default:
                if (probe.Width is not > 0 || probe.Height is not > 0 || probe.DurationSeconds is not > 0.05)
                    throw new AssetValidationException("Video stream is missing or too short");
                var decode = await _ffmpeg.CheckDecodeAsync(path, ct);
                if (!decode.Passed) throw new AssetValidationException($"Video decode validation failed: {decode.Error}");
                break;
        }
        return (probe, JsonSerializer.Serialize(probe));
    }

    private static bool HasCompleteSubtitleCue(string text)
    {
        var lines = text.Replace("\r", string.Empty, StringComparison.Ordinal).Split('\n');
        var cues = 0;
        for (var i = 0; i < lines.Length;)
        {
            while (i < lines.Length && string.IsNullOrWhiteSpace(lines[i])) i++;
            if (i >= lines.Length) break;
            if (lines[i].Trim().Equals("WEBVTT", StringComparison.OrdinalIgnoreCase)) { i++; continue; }
            if (!lines[i].Contains("-->", StringComparison.Ordinal)) i++;
            if (i >= lines.Length || !lines[i].Contains("-->", StringComparison.Ordinal)) return false;
            var timing = lines[i].Split("-->", 2, StringSplitOptions.TrimEntries);
            if (timing.Length != 2 || !TryParseSubtitleTimestamp(timing[0], out var start) || !TryParseSubtitleTimestamp(timing[1], out var end) || end <= start)
                return false;
            i++;
            var hasText = false;
            while (i < lines.Length && !string.IsNullOrWhiteSpace(lines[i])) { hasText = true; i++; }
            if (!hasText) return false;
            cues++;
        }
        return cues > 0;
    }

    private static bool TryParseSubtitleTimestamp(string value, out int milliseconds)
    {
        milliseconds = 0;
        var parts = value.Trim().Split(':', StringSplitOptions.TrimEntries);
        if (parts.Length is not (2 or 3)) return false;
        var hour = 0;
        var minuteIndex = 0;
        if (parts.Length == 3)
        {
            if (!int.TryParse(parts[0], out hour)) return false;
            minuteIndex = 1;
        }
        if (!int.TryParse(parts[minuteIndex], out var minute) || minute is < 0 or > 59) return false;
        var secondParts = parts[minuteIndex + 1].Replace('.', ',').Split(',', 2, StringSplitOptions.TrimEntries);
        if (secondParts.Length != 2 || !int.TryParse(secondParts[0], out var second) || !int.TryParse(secondParts[1], out var fraction)
            || second is < 0 or > 59 || fraction is < 0 or > 999) return false;
        milliseconds = checked(((hour * 60 + minute) * 60 + second) * 1000 + fraction);
        return true;
    }

    private async Task<int> NextVersionAsync(TaskLease lease, ArtifactPurpose purpose, CancellationToken ct)
    {
        await using var connection = await OpenAsync(ct);
        await using var command = new MySqlCommand("SELECT COALESCE(MAX(version),0)+1 FROM asset_manifests WHERE task_id=@task AND purpose=@purpose", connection);
        Add(command, "@task", lease.TaskId); Add(command, "@purpose", purpose.ToString());
        return Convert.ToInt32(await command.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture);
    }

    private async Task<long> CreatePublishIntentAsync(TaskLease lease, ArtifactPublishSpec spec, string tempRelative, string finalRelative, CancellationToken ct)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            await RequireActiveLeaseAndOwnershipAsync(connection, transaction, lease, spec, ct);
            await using var command = new MySqlCommand(@"INSERT INTO artifact_publish_intents(task_id,attempt_id,lease_token,project_id,episode_id,shot_id,purpose,temp_relative_path,final_relative_path,status)
                VALUES(@task,@attempt,@token,@project,@episode,@shot,@purpose,@temp,@final,'Staging')", connection, transaction);
            BindLease(command, lease); Add(command, "@project", spec.ProjectId); Add(command, "@episode", spec.EpisodeId); Add(command, "@shot", spec.ShotId);
            Add(command, "@purpose", spec.Purpose.ToString()); Add(command, "@temp", tempRelative); Add(command, "@final", finalRelative);
            await command.ExecuteNonQueryAsync(ct);
            var id = command.LastInsertedId;
            await transaction.CommitAsync(ct);
            return id;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    private async Task<PublishedArtifact> RecordPublishedAsync(TaskLease lease, ArtifactPublishSpec spec, long intentId, string finalPath, string finalRelative,
        string finalName, string extension, string hash, long size, (FfmpegProbe? Probe, string ProbeJson) validation, int version, CancellationToken ct)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            await RequireActiveLeaseAndOwnershipAsync(connection, transaction, lease, spec, ct);
            long manifestId;
            await using (var manifest = new MySqlCommand(@"INSERT INTO asset_manifests(project_id,episode_id,shot_id,task_id,attempt_id,source_kind,production_profile_id,shot_plan_id,
                purpose,version,relative_path,file_name,extension,mime_type,size_bytes,sha256,probe_json,input_manifest_json,status)
                VALUES(@project,@episode,@shot,@task,@attempt,'Task',@profile,@plan,@purpose,@version,@relative,@name,@extension,@mime,@size,@sha,@probe,@inputs,'Staged')", connection, transaction))
            {
                BindLease(manifest, lease); BindSpec(manifest, spec); Add(manifest, "@version", version); Add(manifest, "@relative", finalRelative); Add(manifest, "@name", finalName);
                Add(manifest, "@extension", extension); Add(manifest, "@mime", ArtifactPurposePolicy.MimeType(spec.Purpose, extension)); Add(manifest, "@size", size); Add(manifest, "@sha", hash);
                Add(manifest, "@probe", validation.ProbeJson); Add(manifest, "@inputs", spec.InputManifest is { } inputs ? CanonicalJson.Serialize(inputs) : null);
                await manifest.ExecuteNonQueryAsync(ct); manifestId = manifest.LastInsertedId;
            }
            long assetId;
            await using (var asset = new MySqlCommand(@"INSERT INTO assets(project_id,episode_id,shot_id,asset_type,name,path,relative_path,mime_type,size_bytes,width,height,duration_seconds,fps,sha256,metadata_json,
                manifest_id,purpose,version,status,source_attempt_id,immutable_path)
                VALUES(@project,@episode,@shot,@type,@name,@path,@relative,@mime,@size,@width,@height,@duration,@fps,@sha,@metadata,@manifest,@purpose,@version,'Staged',@attempt,1)", connection, transaction))
            {
                Add(asset, "@project", spec.ProjectId); Add(asset, "@episode", spec.EpisodeId); Add(asset, "@shot", spec.ShotId); Add(asset, "@type", ArtifactPurposePolicy.AssetType(spec.Purpose));
                Add(asset, "@name", finalName); Add(asset, "@path", finalPath); Add(asset, "@relative", finalRelative); Add(asset, "@mime", ArtifactPurposePolicy.MimeType(spec.Purpose, extension));
                Add(asset, "@size", size); Add(asset, "@width", validation.Probe?.Width); Add(asset, "@height", validation.Probe?.Height); Add(asset, "@duration", validation.Probe?.DurationSeconds ?? validation.Probe?.AudioDurationSeconds);
                Add(asset, "@fps", validation.Probe?.Fps); Add(asset, "@sha", hash); Add(asset, "@metadata", validation.ProbeJson); Add(asset, "@manifest", manifestId);
                Add(asset, "@purpose", spec.Purpose.ToString()); Add(asset, "@version", version); Add(asset, "@attempt", lease.AttemptId);
                await asset.ExecuteNonQueryAsync(ct); assetId = asset.LastInsertedId;
            }
            long resultId;
            await using (var result = new MySqlCommand(@"INSERT INTO generation_results(task_id,asset_id,result_type,path,attempt_id,manifest_id,metadata_json)
                VALUES(@task,@asset,@type,@path,@attempt,@manifest,@metadata)", connection, transaction))
            {
                Add(result, "@task", lease.TaskId); Add(result, "@asset", assetId); Add(result, "@type", ArtifactPurposePolicy.ResultType(spec.Purpose)); Add(result, "@path", finalPath);
                Add(result, "@attempt", lease.AttemptId); Add(result, "@manifest", manifestId); Add(result, "@metadata", validation.ProbeJson);
                await result.ExecuteNonQueryAsync(ct); resultId = result.LastInsertedId;
            }
            await using (var intent = new MySqlCommand("UPDATE artifact_publish_intents SET sha256=@sha,size_bytes=@size,manifest_id=@manifest WHERE id=@id AND status='Staging'", connection, transaction))
            {
                Add(intent, "@sha", hash); Add(intent, "@size", size); Add(intent, "@manifest", manifestId); Add(intent, "@id", intentId);
                if (await intent.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Publish intent was changed before manifest recording");
            }
            await transaction.CommitAsync(ct);
            return new PublishedArtifact(manifestId, assetId, resultId, spec.Purpose, finalPath, finalRelative, hash, size);
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    private static async Task RequireActiveLeaseAndOwnershipAsync(MySqlConnection connection, MySqlTransaction transaction, TaskLease lease, ArtifactPublishSpec spec, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT project_id,episode_id,shot_id FROM generation_tasks
            WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker FOR UPDATE", connection, transaction);
        BindLease(command, lease);
        await using var reader = await command.ExecuteReaderAsync(ct);
        if (!await reader.ReadAsync(ct)) throw new StaleTaskLeaseException("Task lease is no longer active; artifact cannot be published");
        long? projectId = reader.IsDBNull(0) ? null : reader.GetInt64(0);
        long? episodeId = reader.IsDBNull(1) ? null : reader.GetInt64(1);
        long? shotId = reader.IsDBNull(2) ? null : reader.GetInt64(2);
        if (projectId != spec.ProjectId || spec.EpisodeId is { } expectedEpisode && episodeId != expectedEpisode || spec.ShotId is { } expectedShot && shotId != expectedShot)
            throw new AssetValidationException("Artifact ownership does not match its task project/episode/shot");
    }

    private async Task MarkNeedsReconcileAsync(long intentId, string message, Exception exception, CancellationToken ct)
    {
        try
        {
            await using var connection = await OpenAsync(ct);
            await using var command = new MySqlCommand("UPDATE artifact_publish_intents SET status='NeedsReconcile',error_message=@error WHERE id=@id AND status='Staging'", connection);
            Add(command, "@error", $"{message}: {Limit(exception.Message, 1500)}"); Add(command, "@id", intentId);
            await command.ExecuteNonQueryAsync(ct);
        }
        catch { /* recovery SOP scans both intents and the immutable folder */ }
    }

    private async Task<MySqlConnection> OpenAsync(CancellationToken ct)
    {
        var connection = new MySqlConnection(_settings.DatabaseConnectionString);
        await connection.OpenAsync(ct);
        return connection;
    }

    private static string BuildImmutableName(string requested, string extension, int version, string hash)
    {
        var safe = AssetPathPolicy.SanitizeFileName(requested, $"artifact{extension}");
        var stem = Path.GetFileNameWithoutExtension(safe);
        return $"v{version:0000}_{stem}_{hash[..12]}{extension}";
    }

    private async Task<string> Sha256Async(string path, CancellationToken ct)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, ct)).ToLowerInvariant();
    }

    private void RequireUnderDataRoot(string fullPath)
    {
        if (!fullPath.StartsWith(_dataRootPrefix, StringComparison.OrdinalIgnoreCase)) throw new AssetValidationException("Path is outside the governed Data root");
        if (fullPath.StartsWith("\\\\", StringComparison.Ordinal) || fullPath.StartsWith("\\\\?\\", StringComparison.Ordinal)) throw new AssetValidationException("UNC and device paths are not allowed");
    }

    private void RequireInside(string fullPath, string parent)
    {
        RequireUnderDataRoot(fullPath);
        var prefix = Path.GetFullPath(parent).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!fullPath.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new AssetValidationException("Path escapes its task workspace");
    }

    private static void EnsureNoReparsePoint(string path)
    {
        var current = File.Exists(path) ? new FileInfo(path).Directory : Directory.Exists(path) ? new DirectoryInfo(path) : new FileInfo(path).Directory;
        if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new AssetValidationException("Reparse-point files are not allowed");
        while (current is not null)
        {
            if (current.Exists && (current.Attributes & FileAttributes.ReparsePoint) != 0) throw new AssetValidationException("Reparse-point directories are not allowed");
            current = current.Parent;
        }
    }

    private static void BindLease(MySqlCommand command, TaskLease lease)
    {
        Add(command, "@task", lease.TaskId); Add(command, "@attempt", lease.AttemptId); Add(command, "@token", lease.LeaseToken); Add(command, "@worker", lease.WorkerId);
    }

    private static void BindSpec(MySqlCommand command, ArtifactPublishSpec spec)
    {
        Add(command, "@project", spec.ProjectId); Add(command, "@episode", spec.EpisodeId); Add(command, "@shot", spec.ShotId); Add(command, "@profile", spec.ProductionProfileId);
        Add(command, "@plan", spec.ShotPlanId); Add(command, "@purpose", spec.Purpose.ToString());
    }

    private static void Add(MySqlCommand command, string name, object? value) => command.Parameters.AddWithValue(name, value ?? DBNull.Value);
    private static string Limit(string value, int length) => value.Length <= length ? value : value[..length];
}

public sealed class AssetReferenceResolver
{
    private readonly StudioDb _db;
    private readonly AssetPathPolicy _paths;

    public AssetReferenceResolver(StudioDb db, AssetPathPolicy paths)
    {
        _db = db;
        _paths = paths;
    }

    public async Task<ResolvedAssetReference> ResolveAsync(long assetId, long projectId, IEnumerable<ArtifactPurpose> purposes, CancellationToken ct = default)
    {
        if (assetId <= 0 || projectId <= 0) throw new AssetValidationException("AssetId and ProjectId are required");
        var row = (await _db.QueryAsync(@"SELECT a.id,a.project_id,a.episode_id,a.shot_id,a.path,a.relative_path,a.status,a.immutable_path,a.manifest_id,a.version,
            COALESCE(a.purpose,m.purpose) AS purpose,m.extension,m.status AS manifest_status,m.relative_path AS manifest_relative_path
            FROM assets a JOIN asset_manifests m ON m.id=a.manifest_id WHERE a.id=@id LIMIT 1", command => StudioDb.Add(command, "@id", assetId), ct)).FirstOrDefault()
            ?? throw new AssetValidationException("AssetId does not exist or has no manifest");
        var allowed = purposes.Select(purpose => purpose.ToString()).ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (row.LongOrNull("projectId") != projectId) throw new AssetValidationException("Asset does not belong to the requested project");
        if (!string.Equals(row.Text("status"), "Ready", StringComparison.OrdinalIgnoreCase) || !string.Equals(row.Text("manifestStatus"), "Ready", StringComparison.OrdinalIgnoreCase) || !row.Bool("immutablePath"))
            throw new AssetValidationException("Asset is not an immutable Ready artifact");
        var purpose = row.Text("purpose") ?? "";
        if (!allowed.Contains(purpose)) throw new AssetValidationException("Asset purpose is not allowed for this input");
        var extension = (row.Text("extension") ?? Path.GetExtension(row.Text("relativePath") ?? string.Empty)).ToLowerInvariant();
        if (!Enum.TryParse<ArtifactPurpose>(purpose, true, out var parsedPurpose) || !ArtifactPurposePolicy.Allows(parsedPurpose, extension))
            throw new AssetValidationException("Asset extension does not match its declared purpose");
        var stored = row.Text("relativePath") ?? row.Text("path");
        if (!_paths.TryResolveExisting(stored, out var full, out var relative)) throw new AssetValidationException("Asset path is missing, outside Data, UNC, or crosses a reparse point");
        if (!string.Equals(relative.Replace('\\', '/'), row.Text("manifestRelativePath")?.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("Asset path does not match its manifest");
        return new ResolvedAssetReference(assetId, projectId, row.LongOrNull("episodeId"), row.LongOrNull("shotId"), purpose, full, relative, extension, "Ready", row.LongOrNull("manifestId"), Math.Max(1, row.Int("version", 1)));
    }
}

internal static class TaskWorkspaceExtensions
{
    public static string RelativePathFor(this TaskWorkspace workspace, string fullPath)
        => $"{workspace.RelativePath.TrimEnd('/')}/{Path.GetFileName(fullPath)}";
}
