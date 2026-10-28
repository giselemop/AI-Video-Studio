using System.Data;
using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

public sealed class StudioSettings
{
    public string RootPath { get; init; } = @"C:\install\AI\VideoStudio";
    public string DataPath { get; init; } = @"C:\install\AI\Data";
    public string ModelsPath { get; init; } = @"C:\install\AI\Models";
    public string WorkflowsPath { get; init; } = @"C:\install\AI\Workflows";
    public string ComfyUrl { get; init; } = "http://127.0.0.1:8188";
    public string ComfyRoot { get; init; } = @"C:\install\AI\ComfyUI";
    public string ComfyInputPath { get; init; } = @"C:\install\AI\ComfyUI\input";
    public string ComfyOutputPath { get; init; } = @"C:\install\AI\ComfyUI\output";
    public string FfmpegPath { get; init; } = @"C:\install\FFmpeg\bin\ffmpeg.exe";
    public string FfprobePath { get; init; } = @"C:\install\FFmpeg\bin\ffprobe.exe";
    public int QueuePollMilliseconds { get; init; } = 1500;
    public int MinFreeVramMiB { get; init; } = 1024;
    public bool WorkerEnabled { get; init; }
    public string DatabaseHost { get; init; } = "127.0.0.1";
    public int DatabasePort { get; init; } = 3306;
    public string DatabaseName { get; init; } = "ai_video_studio";
    public string DatabaseUser { get; init; } = "root";
    public string DatabasePassword { get; init; } = "";
    public bool AutoApplySchema { get; init; }
    public bool AllowDatabaseCreate { get; init; }
    public long MinimumFreeDiskBytes { get; init; } = 1L * 1024 * 1024 * 1024;
    public string AdminUsername { get; init; } = "";
    public string AdminPassword { get; init; } = "";
    public string AdminPasswordHash { get; init; } = "";
    public bool RequireLocalLogin { get; init; } = true;
    public string DatabaseConnectionString
    {
        get
        {
            var builder = new MySqlConnectionStringBuilder
            {
                Server = DatabaseHost,
                Port = (uint)DatabasePort,
                Database = DatabaseName,
                UserID = DatabaseUser,
                Password = DatabasePassword,
                CharacterSet = "utf8mb4",
                ConnectionTimeout = 4,
                DefaultCommandTimeout = 60,
                Pooling = true,
                AllowUserVariables = true
            };
            return builder.ConnectionString;
        }
    }

    public string ServerConnectionString
    {
        get
        {
            var builder = new MySqlConnectionStringBuilder(DatabaseConnectionString) { Database = "" };
            return builder.ConnectionString;
        }
    }
}

public static class StudioPaths
{
    public static string FindRoot()
    {
        var configured = Environment.GetEnvironmentVariable("VIDEO_STUDIO_ROOT");
        if (!string.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);

        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (string.Equals(current.Name, "VideoStudio", StringComparison.OrdinalIgnoreCase)) return current.FullName;
            current = current.Parent;
        }
        return @"C:\install\AI\VideoStudio";
    }

    public static Dictionary<string, string> ReadLocalEnv(string path)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(path)) return values;
        foreach (var raw in File.ReadAllLines(path))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith('#')) continue;
            var separator = line.IndexOf('=');
            if (separator <= 0) continue;
            var key = line[..separator].Trim();
            var value = line[(separator + 1)..].Trim().Trim('"').Trim('\'');
            values[key] = value;
        }
        return values;
    }

    public static StudioSettings Load(IConfiguration configuration, string root)
    {
        var env = ReadLocalEnv(Path.Combine(root, "config", "local.env"));
        var preferExternal = string.Equals(Environment.GetEnvironmentVariable("AI_VIDEO_STUDIO_PREFER_ENV"), "1", StringComparison.OrdinalIgnoreCase)
            || string.Equals(Environment.GetEnvironmentVariable("AI_VIDEO_STUDIO_PREFER_ENV"), "true", StringComparison.OrdinalIgnoreCase);
        string Read(string key, string fallback)
        {
            var external = Environment.GetEnvironmentVariable(key);
            if (preferExternal && !string.IsNullOrWhiteSpace(external)) return external;
            if (env.TryGetValue(key, out var local) && !string.IsNullOrWhiteSpace(local)) return local;
            return !string.IsNullOrWhiteSpace(external) ? external : fallback;
        }
        int ReadInt(string key, int fallback) => int.TryParse(Read(key, fallback.ToString(CultureInfo.InvariantCulture)), out var value) ? value : fallback;
        long ReadLong(string key, long fallback) => long.TryParse(Read(key, fallback.ToString(CultureInfo.InvariantCulture)), out var value) ? Math.Max(0, value) : fallback;
        bool ReadBool(string key, bool fallback)
        {
            var value = Read(key, fallback ? "1" : "0");
            return value.Equals("1", StringComparison.OrdinalIgnoreCase)
                || bool.TryParse(value, out var parsed) && parsed;
        }
        var database = configuration.GetSection("Database");
        var comfy = configuration.GetSection("ComfyUI");
        var paths = configuration.GetSection("Paths");
        var queue = configuration.GetSection("Queue");
        var ffmpeg = configuration.GetSection("Ffmpeg");
        return new StudioSettings
        {
            RootPath = root,
            DataPath = paths["Data"] ?? @"C:\install\AI\Data",
            ModelsPath = paths["Models"] ?? @"C:\install\AI\Models",
            WorkflowsPath = paths["Workflows"] ?? @"C:\install\AI\Workflows",
            ComfyUrl = NormalizeLoopbackHttpUrl(comfy["BaseUrl"] ?? "http://127.0.0.1:8188"),
            ComfyRoot = comfy["Root"] ?? @"C:\install\AI\ComfyUI",
            ComfyInputPath = comfy["Input"] ?? @"C:\install\AI\ComfyUI\input",
            ComfyOutputPath = comfy["Output"] ?? @"C:\install\AI\ComfyUI\output",
            FfmpegPath = ffmpeg["Ffmpeg"] ?? @"C:\install\FFmpeg\bin\ffmpeg.exe",
            FfprobePath = ffmpeg["Ffprobe"] ?? @"C:\install\FFmpeg\bin\ffprobe.exe",
            QueuePollMilliseconds = int.TryParse(queue["PollMilliseconds"], out var poll) ? poll : 1500,
            MinFreeVramMiB = int.TryParse(queue["MinFreeVramMiB"], out var minVram) ? minVram : 1024,
            WorkerEnabled = ReadBool("AI_VIDEO_STUDIO_WORKER_ENABLED", bool.TryParse(queue["Enabled"], out var workerEnabled) && workerEnabled),
            DatabaseHost = Read("AI_VIDEO_STUDIO_DB_HOST", database["Host"] ?? "127.0.0.1"),
            DatabasePort = ReadInt("AI_VIDEO_STUDIO_DB_PORT", int.TryParse(database["Port"], out var dbPort) ? dbPort : 3306),
            DatabaseName = Read("AI_VIDEO_STUDIO_DB_NAME", database["Name"] ?? "ai_video_studio"),
            DatabaseUser = Read("AI_VIDEO_STUDIO_DB_USER", database["User"] ?? "root"),
            DatabasePassword = Read("AI_VIDEO_STUDIO_DB_PASSWORD", ""),
            AutoApplySchema = ReadBool("AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA", false),
            AllowDatabaseCreate = ReadBool("AI_VIDEO_STUDIO_ALLOW_DATABASE_CREATE", false),
            MinimumFreeDiskBytes = ReadLong("AI_VIDEO_STUDIO_MIN_FREE_DISK_BYTES", 1L * 1024 * 1024 * 1024),
            AdminUsername = Read("AI_VIDEO_STUDIO_ADMIN_USERNAME", ""),
            AdminPassword = Read("AI_VIDEO_STUDIO_ADMIN_PASSWORD", ""),
            AdminPasswordHash = Read("AI_VIDEO_STUDIO_ADMIN_PASSWORD_HASH", ""),
            RequireLocalLogin = ReadBool("AI_VIDEO_STUDIO_REQUIRE_LOGIN", configuration.GetValue("LocalAccess:RequireLogin", true))
        };
    }

    public static string NormalizeLoopbackHttpUrl(string value)
    {
        if (!Uri.TryCreate(value?.Trim(), UriKind.Absolute, out var uri)
            || uri is null
            || uri.Scheme is not ("http" or "https")
            || !string.IsNullOrWhiteSpace(uri.UserInfo)
            || !string.IsNullOrWhiteSpace(uri.Query)
            || !string.IsNullOrWhiteSpace(uri.Fragment))
            throw new InvalidOperationException("ComfyUI BaseUrl 必须是无凭据、无查询参数的 HTTP(S) 地址");
        var host = uri.DnsSafeHost.TrimEnd('.');
        var loopback = string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)
            || IPAddress.TryParse(host, out var address) && IPAddress.IsLoopback(address);
        if (!loopback) throw new InvalidOperationException("ComfyUI BaseUrl 仅允许 loopback 地址");
        return uri.GetLeftPart(UriPartial.Path).TrimEnd('/');
    }
}

public sealed class StudioDb
{
    private readonly StudioSettings _settings;
    private readonly ILogger<StudioDb> _logger;

    public StudioDb(StudioSettings settings, ILogger<StudioDb> logger)
    {
        _settings = settings;
        _logger = logger;
    }

    public async Task<MySqlConnection> OpenAsync(CancellationToken cancellationToken = default)
    {
        var connection = new MySqlConnection(_settings.DatabaseConnectionString);
        await connection.OpenAsync(cancellationToken);
        return connection;
    }

    public async Task<bool> CanConnectAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            await using var connection = await OpenAsync(cancellationToken);
            await using var command = new MySqlCommand("SELECT 1", connection);
            await command.ExecuteScalarAsync(cancellationToken);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Video Studio database is not reachable");
            return false;
        }
    }

    public async Task<long> ExecuteInsertAsync(string sql, Action<MySqlCommand>? bind = null, CancellationToken cancellationToken = default)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var command = new MySqlCommand(sql, connection);
        bind?.Invoke(command);
        await command.ExecuteNonQueryAsync(cancellationToken);
        return Convert.ToInt64(await new MySqlCommand("SELECT LAST_INSERT_ID()", connection).ExecuteScalarAsync(cancellationToken), CultureInfo.InvariantCulture);
    }

    public async Task<int> ExecuteAsync(string sql, Action<MySqlCommand>? bind = null, CancellationToken cancellationToken = default)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var command = new MySqlCommand(sql, connection);
        bind?.Invoke(command);
        return await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<List<Dictionary<string, object?>>> QueryAsync(string sql, Action<MySqlCommand>? bind = null, CancellationToken cancellationToken = default)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var command = new MySqlCommand(sql, connection);
        bind?.Invoke(command);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var rows = new List<Dictionary<string, object?>>();
        while (await reader.ReadAsync(cancellationToken))
        {
            var row = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
            for (var i = 0; i < reader.FieldCount; i++)
            {
                var name = ToCamelCase(reader.GetName(i));
                object? value = await reader.IsDBNullAsync(i, cancellationToken) ? null : reader.GetValue(i);
                if (value is byte[] bytes) value = Convert.ToBase64String(bytes);
                row[name] = value;
            }
            rows.Add(row);
        }
        return rows;
    }

    public async Task<object?> ScalarAsync(string sql, Action<MySqlCommand>? bind = null, CancellationToken cancellationToken = default)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var command = new MySqlCommand(sql, connection);
        bind?.Invoke(command);
        return await command.ExecuteScalarAsync(cancellationToken);
    }

    public async Task<T> InTransactionAsync<T>(Func<MySqlConnection, MySqlTransaction, Task<T>> action, CancellationToken cancellationToken = default)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, cancellationToken);
        try
        {
            var result = await action(connection, transaction);
            await transaction.CommitAsync(cancellationToken);
            return result;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    public static void Add(MySqlCommand command, string name, object? value)
        => command.Parameters.AddWithValue(name, value ?? DBNull.Value);

    public static string JsonOrNull(JsonElement? value)
        => value is { } element && element.ValueKind != JsonValueKind.Null ? element.GetRawText() : "{}";

    public static string JsonOrEmpty<T>(T? value)
        => value is null ? "[]" : JsonSerializer.Serialize(value);

    public static string NewSlug(string name)
    {
        var normalized = Regex.Replace(name.Trim().ToLowerInvariant(), @"[^\p{L}\p{N}]+", "-").Trim('-');
        var suffix = Guid.NewGuid().ToString("N");
        return string.IsNullOrWhiteSpace(normalized) ? $"project-{suffix}" : $"{normalized}-{suffix[..8]}";
    }

    private static string ToCamelCase(string value)
    {
        var parts = value.Split('_', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 1) return char.ToLowerInvariant(value[0]) + value[1..];
        var builder = new StringBuilder(parts[0].ToLowerInvariant());
        foreach (var part in parts.Skip(1)) builder.Append(char.ToUpperInvariant(part[0])).Append(part[1..].ToLowerInvariant());
        return builder.ToString();
    }
}

public sealed partial class StudioRepository
{
    private readonly StudioDb _db;
    private readonly ILogger<StudioRepository> _logger;

    public StudioRepository(StudioDb db, ILogger<StudioRepository> logger)
    {
        _db = db;
        _logger = logger;
    }

    public Task<List<Dictionary<string, object?>>> ProjectsAsync(CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT p.*, (SELECT COUNT(*) FROM episodes e WHERE e.project_id=p.id) AS episode_count,
               (SELECT COUNT(*) FROM shots s WHERE s.project_id=p.id) AS shot_count,
               (SELECT COUNT(*) FROM assets a WHERE a.project_id=p.id) AS asset_count
        FROM projects p ORDER BY p.updated_at DESC", cancellationToken: ct);

    public Task<List<Dictionary<string, object?>>> ProjectAsync(long id, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM projects WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public Task<long> CreateProjectAsync(ProjectInput input, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO projects(name,slug,description,status,root_path,aspect_ratio,style,default_fps,default_width,default_height,prompt_style,bgm_path,bgm_volume) VALUES(@name,@slug,@description,@status,@root,@aspect,@style,@fps,@width,@height,@prompt_style,@bgm_path,@bgm_volume)", c =>
    {
        StudioDb.Add(c, "@name", input.Name.Trim()); StudioDb.Add(c, "@slug", StudioDb.NewSlug(input.Name));
        StudioDb.Add(c, "@description", input.Description); StudioDb.Add(c, "@status", input.Status); StudioDb.Add(c, "@root", null); BindProjectOptions(c, input);
    }, ct);

    public Task<int> UpdateProjectAsync(long id, ProjectInput input, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE projects SET name=@name,description=@description,status=@status,aspect_ratio=@aspect,style=@style,default_fps=@fps,default_width=@width,default_height=@height,prompt_style=@prompt_style,bgm_path=@bgm_path,bgm_volume=@bgm_volume WHERE id=@id", c =>
    { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@name", input.Name.Trim()); StudioDb.Add(c, "@description", input.Description); StudioDb.Add(c, "@status", input.Status); BindProjectOptions(c, input); }, ct);

    public Task<int> DeleteProjectAsync(long id, CancellationToken ct = default) => _db.ExecuteAsync("DELETE FROM projects WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public Task<List<Dictionary<string, object?>>> CharactersAsync(long? projectId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT c.*, (SELECT COUNT(*) FROM character_references r WHERE r.character_id=c.id) AS reference_count,
               (SELECT r.path FROM character_references r WHERE r.character_id=c.id ORDER BY r.is_anchor DESC,r.created_at DESC LIMIT 1) AS reference_path
        FROM characters c WHERE (@project_id IS NULL OR c.project_id=@project_id) ORDER BY c.updated_at DESC", c => StudioDb.Add(c, "@project_id", projectId), ct);

    public Task<long> CreateCharacterAsync(CharacterInput input, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO characters(project_id,name,age_setting,face_features,hair,clothes,body_ratio,fixed_prompt,negative_prompt,embedding_path,lora_path,anchor_path,voice_id,voice_speed,voice_pitch,metadata_json)
        VALUES(@project_id,@name,@age,@face,@hair,@clothes,@body,@fixed,@negative,@embedding,@lora,@anchor,@voice_id,@voice_speed,@voice_pitch,@metadata)", c => BindCharacter(c, input), ct);

    public Task<int> UpdateCharacterAsync(long id, CharacterInput input, CancellationToken ct = default) => _db.ExecuteAsync(@"
        UPDATE characters SET project_id=@project_id,name=@name,age_setting=@age,face_features=@face,hair=@hair,clothes=@clothes,body_ratio=@body,fixed_prompt=@fixed,negative_prompt=@negative,embedding_path=@embedding,lora_path=@lora,anchor_path=@anchor,voice_id=@voice_id,voice_speed=@voice_speed,voice_pitch=@voice_pitch,metadata_json=@metadata WHERE id=@id", c => { StudioDb.Add(c, "@id", id); BindCharacter(c, input); }, ct);

    public Task<int> DeleteCharacterAsync(long id, CancellationToken ct = default) => _db.ExecuteAsync("DELETE FROM characters WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public Task<List<Dictionary<string, object?>>> QueryCharacterAsync(long id, CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM characters WHERE id=@id LIMIT 1", c => StudioDb.Add(c, "@id", id), ct);

    public async Task<long> AddCharacterReferenceAsync(long characterId, string path, ReferenceInput input, CancellationToken ct = default)
    {
        var hash = await Sha256Async(path, ct) ?? throw new AssetValidationException("角色参考图不存在，无法登记资产版本");
        var metadata = ReferenceMetadata.CreateJson(hash, input.Stage, input.Role, input.ChangeReason);
        var id = await _db.ExecuteInsertAsync(@"
            INSERT INTO character_references(character_id,path,kind,is_anchor,metadata_json) VALUES(@character_id,@path,@kind,@anchor,@metadata)", c => { StudioDb.Add(c, "@character_id", characterId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@kind", input.Kind); StudioDb.Add(c, "@anchor", input.IsAnchor); StudioDb.Add(c, "@metadata", metadata); }, ct);
        if (input.IsAnchor)
        {
            await _db.ExecuteAsync("UPDATE character_references SET is_anchor=0 WHERE character_id=@character_id AND id<>@id", c => { StudioDb.Add(c, "@character_id", characterId); StudioDb.Add(c, "@id", id); }, ct);
            await _db.ExecuteAsync("UPDATE characters SET anchor_path=@path WHERE id=@character_id", c => { StudioDb.Add(c, "@character_id", characterId); StudioDb.Add(c, "@path", path); }, ct);
        }
        return id;
    }

    public Task<List<Dictionary<string, object?>>> CharacterReferencesAsync(long characterId, CancellationToken ct = default)
        => _db.QueryAsync("SELECT id,character_id,path,kind,is_anchor,width,height,metadata_json,created_at FROM character_references WHERE character_id=@character ORDER BY is_anchor DESC,created_at DESC", c => StudioDb.Add(c, "@character", characterId), ct);

    public async Task<int> ReviewCharacterReferenceAsync(long characterId, long referenceId, string decision, string? reviewer, string? note, CancellationToken ct = default)
    {
        var row = (await CharacterReferencesAsync(characterId, ct)).FirstOrDefault(x => x.Long("id") == referenceId);
        if (row is null) return 0;
        if (string.IsNullOrWhiteSpace(reviewer)) throw new InvalidOperationException("角色参考图审核必须来自已登录身份");
        var path = row.Text("path");
        var hash = await Sha256Async(path ?? "", ct);
        if (string.IsNullOrWhiteSpace(hash)) throw new AssetValidationException("角色参考图不存在，无法完成审核");
        var metadata = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        try
        {
            if (!string.IsNullOrWhiteSpace(row.Text("metadataJson")))
                metadata = JsonSerializer.Deserialize<Dictionary<string, object?>>(row.Text("metadataJson")!) ?? metadata;
        }
        catch { }
        var previousHash = metadata.TryGetValue("assetSha256", out var previousHashValue) ? Convert.ToString(previousHashValue, CultureInfo.InvariantCulture) : null;
        var previousStatus = metadata.TryGetValue("humanReviewStatus", out var previousStatusValue) ? Convert.ToString(previousStatusValue, CultureInfo.InvariantCulture) : null;
        var previousVersion = metadata.TryGetValue("assetVersion", out var previousVersionValue) && int.TryParse(Convert.ToString(previousVersionValue, CultureInfo.InvariantCulture), out var parsedVersion) ? parsedVersion : 0;
        var assetVersion = Math.Max(1, previousVersion + (string.Equals(previousHash, hash, StringComparison.OrdinalIgnoreCase) ? 0 : 1));
        metadata["assetVersion"] = assetVersion;
        metadata["assetSha256"] = hash;
        metadata["humanReviewStatus"] = decision;
        metadata["reviewer"] = reviewer.Trim();
        metadata["reviewedAt"] = DateTimeOffset.UtcNow;
        metadata["reviewNote"] = note?.Trim();
        var metadataJson = JsonSerializer.Serialize(metadata);
        return await _db.InTransactionAsync(async (connection, transaction) =>
        {
            await using var update = new MySqlCommand("UPDATE character_references SET metadata_json=@metadata WHERE id=@id AND character_id=@character", connection, transaction);
            StudioDb.Add(update, "@metadata", metadataJson); StudioDb.Add(update, "@id", referenceId); StudioDb.Add(update, "@character", characterId);
            var updated = await update.ExecuteNonQueryAsync(ct);
            if (updated == 0) return 0;
            await using var history = new MySqlCommand(@"
                INSERT INTO character_reference_reviews(character_id,reference_id,decision,asset_version,asset_sha256,reviewer,note)
                VALUES(@character,@reference,@decision,@version,@sha,@reviewer,@note)", connection, transaction);
            StudioDb.Add(history, "@character", characterId); StudioDb.Add(history, "@reference", referenceId); StudioDb.Add(history, "@decision", decision);
            StudioDb.Add(history, "@version", assetVersion); StudioDb.Add(history, "@sha", hash); StudioDb.Add(history, "@reviewer", reviewer.Trim()); StudioDb.Add(history, "@note", note?.Trim());
            await history.ExecuteNonQueryAsync(ct);
            var requiresReReview = !string.Equals(previousHash, hash, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(previousStatus, "Approved", StringComparison.OrdinalIgnoreCase)
                || !string.Equals(decision, "Approved", StringComparison.OrdinalIgnoreCase);
            if (requiresReReview)
            {
                await using var invalidateShots = new MySqlCommand(@"
                    UPDATE shots
                    SET qa_status='NeedReview',
                        qa_result=JSON_SET(COALESCE(qa_result,JSON_OBJECT()),
                            '$.characterReferenceReviewRequired',true,
                            '$.characterReferenceId',@reference,
                            '$.characterReferenceAssetVersion',@version,
                            '$.characterReferenceAssetSha256',@sha,
                            '$.characterReferenceDecision',@decision)
                    WHERE JSON_CONTAINS(COALESCE(character_ids_json,JSON_ARRAY()),JSON_ARRAY(@character),'$')", connection, transaction);
                StudioDb.Add(invalidateShots, "@character", characterId); StudioDb.Add(invalidateShots, "@reference", referenceId);
                StudioDb.Add(invalidateShots, "@version", assetVersion); StudioDb.Add(invalidateShots, "@sha", hash); StudioDb.Add(invalidateShots, "@decision", decision);
                await invalidateShots.ExecuteNonQueryAsync(ct);

                await using var invalidateEpisodes = new MySqlCommand(@"
                    UPDATE episodes e
                    JOIN shots s ON s.episode_id=e.id
                    SET e.qa_locked=0,
                        e.qa_status='NeedReview',
                        e.qa_approved_at=NULL,
                        e.status=CASE WHEN e.status='Approved' THEN 'Completed' ELSE e.status END,
                        e.qa_result=JSON_SET(COALESCE(e.qa_result,JSON_OBJECT()),
                            '$.characterReferenceReviewRequired',true,
                            '$.characterReferenceId',@reference,
                            '$.characterReferenceAssetVersion',@version,
                            '$.characterReferenceAssetSha256',@sha,
                            '$.characterReferenceDecision',@decision)
                    WHERE JSON_CONTAINS(COALESCE(s.character_ids_json,JSON_ARRAY()),JSON_ARRAY(@character),'$')", connection, transaction);
                StudioDb.Add(invalidateEpisodes, "@character", characterId); StudioDb.Add(invalidateEpisodes, "@reference", referenceId);
                StudioDb.Add(invalidateEpisodes, "@version", assetVersion); StudioDb.Add(invalidateEpisodes, "@sha", hash); StudioDb.Add(invalidateEpisodes, "@decision", decision);
                await invalidateEpisodes.ExecuteNonQueryAsync(ct);
            }
            return updated;
        }, ct);
    }

    public Task<List<Dictionary<string, object?>>> ScenesAsync(long? projectId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT s.*, (SELECT COUNT(*) FROM scene_references r WHERE r.scene_id=s.id) AS reference_count,
               (SELECT r.path FROM scene_references r WHERE r.scene_id=s.id ORDER BY r.is_anchor DESC,r.created_at LIMIT 1) AS reference_path
        FROM scenes s WHERE (@project_id IS NULL OR s.project_id=@project_id) ORDER BY s.updated_at DESC", c => StudioDb.Add(c, "@project_id", projectId), ct);

    public Task<long> CreateSceneAsync(SceneInput input, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO scenes(project_id,name,description,fixed_prompt,negative_prompt,style,anchor_path,metadata_json)
        VALUES(@project_id,@name,@description,@fixed,@negative,@style,@anchor,@metadata)", c => BindScene(c, input), ct);

    public Task<int> UpdateSceneAsync(long id, SceneInput input, CancellationToken ct = default) => _db.ExecuteAsync(@"
        UPDATE scenes SET project_id=@project_id,name=@name,description=@description,fixed_prompt=@fixed,negative_prompt=@negative,style=@style,anchor_path=@anchor,metadata_json=@metadata WHERE id=@id", c => { StudioDb.Add(c, "@id", id); BindScene(c, input); }, ct);

    public Task<int> DeleteSceneAsync(long id, CancellationToken ct = default) => _db.ExecuteAsync("DELETE FROM scenes WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public async Task<long> AddSceneReferenceAsync(long sceneId, string path, ReferenceInput input, CancellationToken ct = default)
    {
        var hash = await Sha256Async(path, ct) ?? throw new AssetValidationException("场景参考图不存在，无法登记资产版本");
        var metadata = ReferenceMetadata.CreateJson(hash, input.Stage, input.Role, input.ChangeReason);
        return await _db.ExecuteInsertAsync(@"
            INSERT INTO scene_references(scene_id,path,kind,is_anchor,metadata_json) VALUES(@scene_id,@path,@kind,@anchor,@metadata)", c =>
        {
            StudioDb.Add(c, "@scene_id", sceneId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@kind", input.Kind);
            StudioDb.Add(c, "@anchor", input.IsAnchor); StudioDb.Add(c, "@metadata", metadata);
        }, ct);
    }

    public Task<List<Dictionary<string, object?>>> SceneReferencesAsync(long sceneId, CancellationToken ct = default)
        => _db.QueryAsync("SELECT id,scene_id,path,kind,is_anchor,width,height,metadata_json,created_at FROM scene_references WHERE scene_id=@scene ORDER BY is_anchor DESC,created_at DESC", c => StudioDb.Add(c, "@scene", sceneId), ct);

    public Task<List<Dictionary<string, object?>>> EpisodesAsync(long projectId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT e.*, (SELECT COUNT(*) FROM shots s WHERE s.episode_id=e.id) AS shot_count,
               (SELECT COUNT(*) FROM generation_tasks t WHERE t.episode_id=e.id AND t.status='Succeeded') AS completed_task_count
        FROM episodes e WHERE e.project_id=@project_id ORDER BY e.episode_number", c => StudioDb.Add(c, "@project_id", projectId), ct);

    public Task<List<Dictionary<string, object?>>> EpisodeAsync(long id, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM episodes WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public Task<long> CreateEpisodeAsync(EpisodeInput input, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO episodes(project_id,episode_number,name,description,target_seconds,output_fps,output_width,output_height) VALUES(@project,@number,@name,@description,@seconds,@fps,@width,@height)", c => BindEpisode(c, input), ct);

    public Task<int> UpdateEpisodeAsync(long id, EpisodeInput input, CancellationToken ct = default) => _db.ExecuteAsync(@"
        UPDATE episodes SET episode_number=@number,name=@name,description=@description,target_seconds=@seconds,output_fps=@fps,output_width=@width,output_height=@height WHERE id=@id", c => { StudioDb.Add(c, "@id", id); BindEpisode(c, input); }, ct);

    public Task<List<Dictionary<string, object?>>> ShotsAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT s.*, sc.name AS scene_name,
               COALESCE(s.final_video_path,s.video_path,s.selected_keyframe_path,
                 (SELECT a.path FROM assets a WHERE a.shot_id=s.id ORDER BY a.created_at DESC LIMIT 1)) AS result_path
        FROM shots s LEFT JOIN scenes sc ON sc.id=s.scene_id WHERE s.episode_id=@episode_id ORDER BY s.sort_order,s.shot_number", c => StudioDb.Add(c, "@episode_id", episodeId), ct);

    public async Task<List<string>> ShotReferencePathsAsync(long shotId, CancellationToken ct = default)
    {
        var shot = (await QueryShotAsync(shotId, ct)).FirstOrDefault();
        if (shot is null) return [];
        var projectId = shot.LongOrNull("projectId");
        var characters = await CharactersAsync(projectId, ct);
        var scenes = await ScenesAsync(projectId, ct);
        var characterPaths = new List<string>();
        try
        {
            using var ids = JsonDocument.Parse(shot.Text("characterIdsJson") ?? "[]");
            if (ids.RootElement.ValueKind == JsonValueKind.Array)
                foreach (var id in ids.RootElement.EnumerateArray().Where(x => x.TryGetInt64(out _)).Select(x => x.GetInt64()))
                {
                    var path = characters.FirstOrDefault(x => x.LongOrNull("id") == id)?.Text("referencePath");
                    if (!string.IsNullOrWhiteSpace(path) && File.Exists(path)) characterPaths.Add(path);
                }
        }
        catch (JsonException) { }
        // The face-stability LTX workflow has one effective guide-image slot.
        // Prioritize the character anchor over a scene board; the scene remains
        // represented by the shot prompt and can be added when no character exists.
        var paths = characterPaths;
        if (paths.Count == 0 && shot.LongOrNull("sceneId") is { } sceneId)
        {
            var scenePath = scenes.FirstOrDefault(x => x.LongOrNull("id") == sceneId)?.Text("referencePath");
            if (!string.IsNullOrWhiteSpace(scenePath) && File.Exists(scenePath)) paths.Add(scenePath);
        }
        return paths.Distinct(StringComparer.OrdinalIgnoreCase).Take(4).ToList();
    }

    public Task<long> CreateShotAsync(ShotInput input, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO shots(project_id,episode_id,shot_number,title,description,scene_id,character_ids_json,prompt,negative_prompt,workflow_id,model_id,lora_ids_json,seed,cfg_scale,steps,width,height,frames,fps,input_image_path,motion_preset,camera_preset,status,sort_order,action,dialogue,narration,emotion,camera_type,camera_motion,duration_seconds,character_prompt,scene_prompt,action_prompt,camera_prompt,lighting_prompt,style_prompt,quality_prompt,prompt_version,prompt_locked,prompt_source_language,selected_keyframe_path,video_path,final_video_path,quality_score,user_rating,video_qc_json,audio_status,subtitle_status)
        VALUES(@project,@episode,@number,@title,@description,@scene,@characters,@prompt,@negative,@workflow,@model,@loras,@seed,@cfg,@steps,@width,@height,@frames,@fps,@input,@motion,@camera,@status,@sort,@action,@dialogue,@narration,@emotion,@camera_type,@camera_motion,@duration,@character_prompt,@scene_prompt,@action_prompt,@camera_prompt,@lighting_prompt,@style_prompt,@quality_prompt,@prompt_version,@prompt_locked,@prompt_language,@selected_keyframe,@video,@final_video,@quality_score,@user_rating,@video_qc,@audio_status,@subtitle_status)", c => BindShot(c, input), ct);

    public Task<int> UpdateShotAsync(long id, ShotInput input, CancellationToken ct = default) => _db.ExecuteAsync(@"
        UPDATE shots SET project_id=@project,episode_id=@episode,shot_number=@number,title=@title,description=@description,scene_id=@scene,character_ids_json=@characters,prompt=@prompt,negative_prompt=@negative,workflow_id=@workflow,model_id=@model,lora_ids_json=@loras,seed=@seed,cfg_scale=@cfg,steps=@steps,width=@width,height=@height,frames=@frames,fps=@fps,input_image_path=@input,motion_preset=@motion,camera_preset=@camera,status=@status,action=@action,dialogue=@dialogue,narration=@narration,emotion=@emotion,camera_type=@camera_type,camera_motion=@camera_motion,duration_seconds=@duration,character_prompt=@character_prompt,scene_prompt=@scene_prompt,action_prompt=@action_prompt,camera_prompt=@camera_prompt,lighting_prompt=@lighting_prompt,style_prompt=@style_prompt,quality_prompt=@quality_prompt,prompt_version=@prompt_version,prompt_locked=@prompt_locked,prompt_source_language=@prompt_language,selected_keyframe_path=@selected_keyframe,video_path=@video,final_video_path=@final_video,quality_score=@quality_score,user_rating=@user_rating,video_qc_json=@video_qc,audio_status=@audio_status,subtitle_status=@subtitle_status WHERE id=@id", c => { StudioDb.Add(c, "@id", id); BindShot(c, input); }, ct);

    public Task<int> DeleteShotAsync(long id, CancellationToken ct = default) => _db.ExecuteAsync("DELETE FROM shots WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public async Task ReorderShotsAsync(long episodeId, IReadOnlyList<long> shotIds, CancellationToken ct = default)
    {
        for (var i = 0; i < shotIds.Count; i++)
        {
            await _db.ExecuteAsync("UPDATE shots SET sort_order=@sort WHERE id=@id AND episode_id=@episode", c => { StudioDb.Add(c, "@sort", i); StudioDb.Add(c, "@id", shotIds[i]); StudioDb.Add(c, "@episode", episodeId); }, ct);
        }
    }

    public Task<List<Dictionary<string, object?>>> WorkflowsAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM workflows ORDER BY workflow_type,name", cancellationToken: ct);
    public Task<List<Dictionary<string, object?>>> ModelsAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM models ORDER BY model_type,name", cancellationToken: ct);
    public Task<List<Dictionary<string, object?>>> LorasAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM loras ORDER BY name", cancellationToken: ct);
    public Task<List<Dictionary<string, object?>>> AssetsAsync(long? projectId, string? assetType, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT * FROM assets WHERE (@project IS NULL OR project_id=@project) AND (@type IS NULL OR asset_type=@type) ORDER BY created_at DESC LIMIT 300", c => { StudioDb.Add(c, "@project", projectId); StudioDb.Add(c, "@type", assetType); }, ct);
    public Task<List<Dictionary<string, object?>>> AssetAsync(long id, CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM assets WHERE id=@id LIMIT 1", c => StudioDb.Add(c, "@id", id), ct);
    public Task<List<Dictionary<string, object?>>> TrackedAssetAsync(long? projectId, string relativePath, string sha256, CancellationToken ct = default)
        => _db.QueryAsync(@"
            SELECT a.id,a.project_id,a.episode_id,a.shot_id,a.manifest_id,a.version,a.sha256,a.status,m.status AS manifest_status
            FROM assets a JOIN asset_manifests m ON m.id=a.manifest_id
            WHERE a.relative_path=@relative AND a.sha256=@sha AND (@project IS NULL OR a.project_id=@project)
              AND a.status='Ready' AND m.status='Ready'
            ORDER BY a.id DESC LIMIT 1",
            c => { StudioDb.Add(c, "@project", projectId); StudioDb.Add(c, "@relative", relativePath); StudioDb.Add(c, "@sha", sha256); }, ct);

    public async Task<int> DeleteAssetAsync(long id, CancellationToken ct = default)
    {
        var asset = (await AssetAsync(id, ct)).FirstOrDefault();
        if (asset is null) return 0;
        var manifestId = asset.LongOrNull("manifestId");
        var attemptId = asset.LongOrNull("sourceAttemptId");
        if (manifestId is not null || attemptId is not null)
            throw new AssetRetentionException("带有Manifest或Attempt血缘的资产不可直接删除；请走版本化隔离/归档流程");

        var resultRefs = await _db.ScalarAsync("SELECT COUNT(*) FROM generation_results WHERE asset_id=@asset", c => StudioDb.Add(c, "@asset", id), ct);
        if (Convert.ToInt32(resultRefs ?? 0, CultureInfo.InvariantCulture) > 0)
            throw new AssetRetentionException("已有生成结果引用该资产，不可直接删除");
        return await _db.ExecuteAsync("DELETE FROM assets WHERE id=@id AND manifest_id IS NULL AND source_attempt_id IS NULL", c => StudioDb.Add(c, "@id", id), ct);
    }

    public async Task<long> AddAssetAsync(long? projectId, long? episodeId, long? shotId, string type, string name, string path, string? relativePath, FfmpegProbe? probe, CancellationToken ct = default)
    {
        var hash = await Sha256Async(path, ct);
        // Episode versions are immutable history records. Even when two previews
        // contain identical bytes, each version must retain its own path/name so
        // the result row never points at an asset with stale metadata.
        var dedupeByHash = !string.Equals(type, "episode", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(type, "episode_preview", StringComparison.OrdinalIgnoreCase);
        if (dedupeByHash && !string.IsNullOrWhiteSpace(hash))
        {
            var existing = await _db.ScalarAsync("SELECT id FROM assets WHERE sha256=@hash ORDER BY id LIMIT 1", c => StudioDb.Add(c, "@hash", hash), ct);
            if (existing is not null && existing is not DBNull) return Convert.ToInt64(existing, CultureInfo.InvariantCulture);
        }
        return await _db.ExecuteInsertAsync(@"
            INSERT INTO assets(project_id,episode_id,shot_id,asset_type,name,path,relative_path,mime_type,size_bytes,width,height,duration_seconds,fps,sha256,metadata_json)
            VALUES(@project,@episode,@shot,@type,@name,@path,@relative,@mime,@size,@width,@height,@duration,@fps,@sha256,@metadata)", c =>
        {
            StudioDb.Add(c, "@project", projectId); StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@type", type); StudioDb.Add(c, "@name", name); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@relative", relativePath); StudioDb.Add(c, "@mime", MimeFor(path));
            StudioDb.Add(c, "@size", File.Exists(path) ? new FileInfo(path).Length : null); StudioDb.Add(c, "@width", probe?.Width); StudioDb.Add(c, "@height", probe?.Height); StudioDb.Add(c, "@duration", probe?.DurationSeconds); StudioDb.Add(c, "@fps", probe?.Fps); StudioDb.Add(c, "@sha256", hash); StudioDb.Add(c, "@metadata", JsonSerializer.Serialize(new { codec = probe?.Codec, hasAudio = probe?.HasAudio, audioDurationSeconds = probe?.AudioDurationSeconds }));
        }, ct);
    }

    public async Task<long> CreateTaskAsync(TaskInput input, CancellationToken ct = default)
    {
        var payload = JsonSerializer.Serialize(new
        {
            input.ProjectId,
            input.EpisodeId,
            input.ShotId,
            input.TaskType,
            input.WorkflowId,
            input.ResourceClass,
            input.Stage,
            input.DependencyTaskId,
            loraIds = input.LoraIds,
            inputImagePath = input.InputImagePath,
            outputName = input.OutputName,
            parameters = input.Parameters
        });
        var fingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(payload))).ToLowerInvariant();
        var key = string.IsNullOrWhiteSpace(input.IdempotencyKey) ? null : input.IdempotencyKey.Trim();
        if (key is not null)
        {
            var existing = await TaskByIdempotencyKeyAsync(key, ct);
            if (existing is not null)
            {
                if (!string.Equals(existing.Text("inputFingerprint"), fingerprint, StringComparison.OrdinalIgnoreCase))
                    throw new IdempotencyConflictException("相同幂等键对应了不同的任务参数");
                return existing.Long("id");
            }
        }

        var id = await _db.ExecuteInsertAsync(@"
            INSERT INTO generation_tasks(project_id,episode_id,shot_id,production_run_id,task_type,status,priority,max_retries,workflow_id,input_json,resource_class,stage,dependency_task_id,request_id,idempotency_key,input_fingerprint,queued_at)
            VALUES(@project,@episode,@shot,@run,@type,'Pending',@priority,@retries,@workflow,@input,@resource,@stage,@dependency,@request,@idempotency,@fingerprint,NOW(3))
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)", c =>
        {
            StudioDb.Add(c, "@project", input.ProjectId); StudioDb.Add(c, "@episode", input.EpisodeId); StudioDb.Add(c, "@shot", input.ShotId); StudioDb.Add(c, "@run", input.ProductionRunId); StudioDb.Add(c, "@type", input.TaskType); StudioDb.Add(c, "@priority", input.Priority); StudioDb.Add(c, "@retries", Math.Clamp(input.MaxRetries, 0, 5)); StudioDb.Add(c, "@workflow", input.WorkflowId);
            StudioDb.Add(c, "@input", payload); StudioDb.Add(c, "@resource", string.Equals(input.ResourceClass, "CPU", StringComparison.OrdinalIgnoreCase) ? "CPU" : "GPU"); StudioDb.Add(c, "@stage", input.Stage); StudioDb.Add(c, "@dependency", input.DependencyTaskId); StudioDb.Add(c, "@request", input.RequestId); StudioDb.Add(c, "@idempotency", key); StudioDb.Add(c, "@fingerprint", fingerprint);
        }, ct);
        var persisted = key is null ? null : await TaskByIdempotencyKeyAsync(key, ct);
        if (persisted is not null && !string.Equals(persisted.Text("inputFingerprint"), fingerprint, StringComparison.OrdinalIgnoreCase))
            throw new IdempotencyConflictException("相同幂等键对应了不同的任务参数");
        return persisted?.Long("id") ?? id;
    }

    public Task<Dictionary<string, object?>?> TaskByIdempotencyKeyAsync(string key, CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM generation_tasks WHERE idempotency_key=@key LIMIT 1", c => StudioDb.Add(c, "@key", key), ct).ContinueWith(t => t.Result.FirstOrDefault(), ct);

    public async Task<List<Dictionary<string, object?>>> TasksAsync(int limit = 100, CancellationToken ct = default, bool recentFirst = false)
    {
        // Sort only narrow task IDs. Large immutable source snapshots in
        // input_json otherwise exhaust MySQL's filesort buffer even at LIMIT 5.
        var order=recentFirst?"t.created_at DESC,t.id DESC":"FIELD(t.status,'Running','Pending','Failed','Succeeded','Cancelled'),t.priority DESC,t.created_at DESC,t.id DESC";
        var keys=(await _db.QueryAsync($"SELECT t.id FROM generation_tasks t ORDER BY {order} LIMIT {Math.Clamp(limit,1,500)}",cancellationToken:ct)).Select(r=>r.Long("id")).ToArray();
        if(keys.Length==0)return [];
        var names=keys.Select((_,i)=>"@task"+i).ToArray();
        var rows=await _db.QueryAsync($@"SELECT t.*,p.name AS project_name,e.name AS episode_name,s.title AS shot_title,w.name AS workflow_name
            FROM generation_tasks t LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN episodes e ON e.id=t.episode_id LEFT JOIN shots s ON s.id=t.shot_id LEFT JOIN workflows w ON w.id=t.workflow_id
            WHERE t.id IN ({string.Join(',',names)})",c=>{for(var i=0;i<keys.Length;i++)StudioDb.Add(c,names[i],keys[i]);},ct);
        var byId=rows.ToDictionary(r=>r.Long("id"));return keys.Where(byId.ContainsKey).Select(id=>byId[id]).ToList();
    }

    public Task<List<Dictionary<string, object?>>> AudioTasksAsync(int limit = 20, CancellationToken ct = default) => _db.QueryAsync($@"
        SELECT t.*,p.name AS project_name FROM generation_tasks t LEFT JOIN projects p ON p.id=t.project_id
        WHERE t.task_type IN ('Audio','TTS') ORDER BY t.created_at DESC,t.id DESC LIMIT {Math.Clamp(limit, 1, 100)}", cancellationToken: ct);

    public Task<List<Dictionary<string, object?>>> TaskAsync(long id, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT t.*,e.production_mode AS episode_production_mode,e.narrator_voice_id AS episode_narrator_voice_id,w.path AS workflow_path,w.workflow_type AS workflow_type,s.input_image_path AS shot_input_image,s.prompt AS shot_prompt,s.negative_prompt AS shot_negative_prompt,s.action AS shot_action,
               s.seed AS shot_seed,s.width AS shot_width,s.height AS shot_height,s.frames AS shot_frames,s.fps AS shot_fps,s.duration_seconds AS shot_duration_seconds
        FROM generation_tasks t LEFT JOIN workflows w ON w.id=t.workflow_id LEFT JOIN shots s ON s.id=t.shot_id LEFT JOIN episodes e ON e.id=t.episode_id WHERE t.id=@id", c => StudioDb.Add(c, "@id", id), ct);
    public async Task<Dictionary<string, object?>?> LatestVideoTaskForShotAsync(long shotId, CancellationToken ct = default)
        => (await _db.QueryAsync(@"
            SELECT t.*,w.path AS workflow_path,w.workflow_type AS workflow_type,s.action AS shot_action
            FROM generation_tasks t LEFT JOIN workflows w ON w.id=t.workflow_id
                LEFT JOIN shots s ON s.id=t.shot_id
                WHERE t.shot_id=@shot AND t.task_type IN ('ImageToVideo','Video')
            ORDER BY t.id DESC LIMIT 1", c => StudioDb.Add(c, "@shot", shotId), ct)).FirstOrDefault();
    public Task<List<Dictionary<string, object?>>> ShotTakesAsync(long shotId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT r.*,t.shot_id,t.task_type,t.status AS status,t.workflow_id,
               t.created_at AS task_created_at,t.started_at AS task_started_at,t.finished_at AS task_finished_at,
               a.name AS asset_name,a.relative_path AS asset_relative_path,a.mime_type,a.width,a.height,a.duration_seconds,a.fps
        FROM generation_results r
        INNER JOIN generation_tasks t ON t.id=r.task_id
        LEFT JOIN assets a ON a.id=r.asset_id
        WHERE t.shot_id=@shot AND t.task_type IN ('ImageToVideo','Video','Enhance')
        ORDER BY r.created_at DESC,r.id DESC", c => StudioDb.Add(c, "@shot", shotId), ct);
    public Task<List<Dictionary<string, object?>>> ResultsAsync(long taskId, CancellationToken ct = default) => _db.QueryAsync("SELECT r.*,a.name AS asset_name,a.relative_path AS asset_relative_path,a.mime_type,a.width,a.height,a.duration_seconds,a.fps FROM generation_results r LEFT JOIN assets a ON a.id=r.asset_id WHERE r.task_id=@task ORDER BY r.created_at", c => StudioDb.Add(c, "@task", taskId), ct);
    public Task<List<Dictionary<string, object?>>> EpisodeRenderHistoryAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT t.id AS task_id,t.status,t.progress,t.error_message,t.created_at,t.started_at,t.finished_at,t.duration_ms,t.input_json,
               r.path AS output_path,a.name AS asset_name,a.width AS asset_width,a.height AS asset_height,a.duration_seconds AS asset_duration_seconds,a.fps AS asset_fps,a.size_bytes AS asset_size_bytes
        FROM generation_tasks t
         LEFT JOIN generation_results r ON r.task_id=t.id AND r.result_type IN ('episode','episode_preview')
        LEFT JOIN assets a ON a.id=r.asset_id
        WHERE t.episode_id=@episode AND t.task_type='EpisodeRender'
        ORDER BY t.created_at DESC,t.id DESC
        LIMIT 30", c => StudioDb.Add(c, "@episode", episodeId), ct);
    public Task<List<Dictionary<string, object?>>> PendingTasksAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT id FROM generation_tasks WHERE status='Pending' ORDER BY priority DESC,created_at", cancellationToken: ct);

    private async Task<int> RecoverRunningTasksAsync(CancellationToken ct = default)
    {
        var rows = await _db.QueryAsync("SELECT id FROM generation_tasks WHERE status='Running' AND (lease_expires_at IS NULL OR lease_expires_at<NOW(3))", cancellationToken: ct);
        var count = 0;
        foreach (var row in rows)
        {
            var id = row.Long("id");
            var changed = await _db.ExecuteAsync("UPDATE generation_tasks SET status='Pending',error_message='任务租约过期，重新排队',state_version=state_version+1,queued_at=NOW(3),lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL WHERE id=@id AND status='Running' AND (lease_expires_at IS NULL OR lease_expires_at<NOW(3))", c => StudioDb.Add(c, "@id", id), ct);
            if (changed == 1) { count++; await AddTaskEventAsync(id, "Running", "Pending", "recovery", null, "任务租约过期", ct: ct); }
        }
        return count;
    }

    private async Task<bool> ClaimTaskAsync(long id, string worker, TimeSpan lease, TimeSpan? deadline = null, CancellationToken ct = default)
    {
        var leaseSeconds = Math.Max(1, (int)Math.Ceiling(lease.TotalSeconds));
        var deadlineSeconds = deadline is { } value ? Math.Max(1, (int)Math.Ceiling(value.TotalSeconds)) : (int?)null;
        var changed = await _db.ExecuteAsync(@"UPDATE generation_tasks SET status='Running',attempts=attempts+1,state_version=state_version+1,lease_owner=@worker,lease_expires_at=DATE_ADD(NOW(3), INTERVAL @lease_seconds SECOND),heartbeat_at=NOW(3),deadline_at=IF(@deadline_seconds IS NULL,NULL,DATE_ADD(NOW(3), INTERVAL @deadline_seconds SECOND)),timed_out_at=NULL,started_at=NOW(3),progress=0,error_message=NULL,cancel_requested_at=NULL
            WHERE id=@id AND status='Pending' AND paused=0", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@worker", worker); StudioDb.Add(c, "@lease_seconds", leaseSeconds); StudioDb.Add(c, "@deadline_seconds", deadlineSeconds); }, ct);
        if (changed == 1) await AddTaskEventAsync(id, "Pending", "Running", "queue", worker, "任务领取", ct: ct);
        return changed == 1;
    }

    private Task<int> TouchTaskLeaseAsync(long id, string worker, TimeSpan lease, CancellationToken ct = default)
    {
        var leaseSeconds = Math.Max(1, (int)Math.Ceiling(lease.TotalSeconds));
        return _db.ExecuteAsync("UPDATE generation_tasks SET lease_expires_at=DATE_ADD(NOW(3), INTERVAL @lease_seconds SECOND),heartbeat_at=NOW(3) WHERE id=@id AND status='Running' AND lease_owner=@worker", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@worker", worker); StudioDb.Add(c, "@lease_seconds", leaseSeconds); }, ct);
    }

    private async Task<int> CompleteTaskAsync(long id, string worker, string status, string? error = null, decimal progress = 0, CancellationToken ct = default)
    {
        if (status is not ("Succeeded" or "Failed" or "Cancelled")) throw new ArgumentOutOfRangeException(nameof(status), "Only terminal task states may be completed");
        var current = (await TaskAsync(id, ct)).FirstOrDefault();
        var changed = await _db.ExecuteAsync(@"UPDATE generation_tasks SET status=@status,error_message=@error,progress=@progress,state_version=state_version+1,finished_at=IF(@status IN ('Succeeded','Failed','Cancelled'),NOW(3),finished_at),duration_ms=IF(@status IN ('Succeeded','Failed','Cancelled'),TIMESTAMPDIFF(MICROSECOND,started_at,NOW(3))/1000,duration_ms),lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=@id AND status='Running' AND lease_owner=@worker", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@worker", worker); StudioDb.Add(c, "@status", status); StudioDb.Add(c, "@error", error); StudioDb.Add(c, "@progress", progress); }, ct);
        if (changed == 1) await AddTaskEventAsync(id, current?.Text("status"), status, "queue", worker, error, ct: ct);
        return changed;
    }

    private async Task<int> MarkTaskTimedOutAsync(long id, string worker, string message, CancellationToken ct = default)
    {
        var current = (await TaskAsync(id, ct)).FirstOrDefault();
        var changed = await _db.ExecuteAsync("UPDATE generation_tasks SET status='Failed',failure_code='TASK_TIMEOUT',error_type='TASK_TIMEOUT',error_message=@message,timed_out_at=NOW(3),state_version=state_version+1,finished_at=NOW(3),duration_ms=IF(started_at IS NULL,NULL,TIMESTAMPDIFF(MICROSECOND,started_at,NOW(3))/1000),lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL WHERE id=@id AND status='Running' AND lease_owner=@worker", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@worker", worker); StudioDb.Add(c, "@message", message); }, ct);
        if (changed == 1) await AddTaskEventAsync(id, current?.Text("status"), "Failed", "queue", worker, message, ct: ct);
        return changed;
    }

    private async Task<int> RequeueTaskAsync(long id, string worker, string failureCode, string message, CancellationToken ct = default)
    {
        var current = (await TaskAsync(id, ct)).FirstOrDefault();
        var changed = await _db.ExecuteAsync(@"UPDATE generation_tasks SET status='Pending',failure_code=@code,error_type=@code,error_message=@message,state_version=state_version+1,queued_at=NOW(3),finished_at=NULL,lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=@id AND status='Running' AND lease_owner=@worker", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@worker", worker); StudioDb.Add(c, "@code", failureCode); StudioDb.Add(c, "@message", message); }, ct);
        if (changed == 1) await AddTaskEventAsync(id, current?.Text("status"), "Pending", "queue", worker, message, ct: ct);
        return changed;
    }

    private async Task<int> CancelTaskAsync(long id, string reason = "用户取消", CancellationToken ct = default)
    {
        var current = (await TaskAsync(id, ct)).FirstOrDefault();
        var changed = await _db.ExecuteAsync(@"UPDATE generation_tasks SET status='Cancelled',cancel_requested_at=NOW(3),state_version=state_version+1,error_message=@reason,finished_at=NOW(3),lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=@id AND status IN ('Pending','Running')", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@reason", reason); }, ct);
        if (changed == 1) await AddTaskEventAsync(id, current?.Text("status"), "Cancelled", "user", null, reason, ct: ct);
        return changed;
    }

    private async Task<int> FailPendingTaskAsync(long id, string errorType, string message, CancellationToken ct = default)
    {
        var current = (await TaskAsync(id, ct)).FirstOrDefault();
        var changed = await _db.ExecuteAsync("UPDATE generation_tasks SET status='Failed',failure_code=@type,error_type=@type,error_message=@message,state_version=state_version+1,finished_at=NOW(3) WHERE id=@id AND status='Pending'", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@type", errorType); StudioDb.Add(c, "@message", message); }, ct);
        if (changed == 1) await AddTaskEventAsync(id, current?.Text("status"), "Failed", "queue", null, message, ct: ct);
        return changed;
    }

    public Task<int> UpdateResultQualityAsync(long taskId, string path, decimal score, string qcJson, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE generation_results SET quality_score=@score,qc_json=@qc WHERE task_id=@task AND path=@path", c => { StudioDb.Add(c, "@task", taskId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@score", score); StudioDb.Add(c, "@qc", qcJson); }, ct);
    public Task<int> AddTaskEventAsync(long taskId, string? fromStatus, string toStatus, string actor, string? worker, string? reason, string? promptId = null, string? metadataJson = null, CancellationToken ct = default)
        => _db.ExecuteAsync("INSERT INTO task_events(task_id,from_status,to_status,actor,worker,reason,state_version,comfy_prompt_id,metadata_json) SELECT id,@from,@to,@actor,@worker,@reason,state_version,COALESCE(@prompt,comfy_prompt_id),@metadata FROM generation_tasks WHERE id=@id", c => { StudioDb.Add(c, "@id", taskId); StudioDb.Add(c, "@from", fromStatus); StudioDb.Add(c, "@to", toStatus); StudioDb.Add(c, "@actor", actor); StudioDb.Add(c, "@worker", worker); StudioDb.Add(c, "@reason", reason); StudioDb.Add(c, "@prompt", promptId); StudioDb.Add(c, "@metadata", metadataJson); }, ct);
    public Task<int> LogAsync(string operation, string message, long? taskId = null, string level = "Info", CancellationToken ct = default) => _db.ExecuteAsync("INSERT INTO operation_logs(level,operation,message,task_id) VALUES(@level,@operation,@message,@task)", c => { StudioDb.Add(c, "@level", level); StudioDb.Add(c, "@operation", operation); StudioDb.Add(c, "@message", message); StudioDb.Add(c, "@task", taskId); }, ct);

    public Task<long> CreateAdminSessionAsync(string tokenHash, string csrfHash, string username, string role, DateTime expiresAt, string? clientIp, string? userAgent, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO admin_sessions(token_hash,csrf_hash,username,role,expires_at,client_ip,user_agent)
        VALUES(@token_hash,@csrf_hash,@username,@role,@expires_at,@client_ip,@user_agent)", c =>
    {
        StudioDb.Add(c, "@token_hash", tokenHash); StudioDb.Add(c, "@csrf_hash", csrfHash); StudioDb.Add(c, "@username", username); StudioDb.Add(c, "@role", role);
        StudioDb.Add(c, "@expires_at", expiresAt); StudioDb.Add(c, "@client_ip", clientIp); StudioDb.Add(c, "@user_agent", userAgent);
    }, ct);

    public async Task<Dictionary<string, object?>?> AdminSessionByTokenHashAsync(string tokenHash, CancellationToken ct = default)
        => (await _db.QueryAsync(@"SELECT id,token_hash,csrf_hash,username,role,expires_at,revoked_at,last_seen_at FROM admin_sessions WHERE token_hash=@token_hash LIMIT 1", c => StudioDb.Add(c, "@token_hash", tokenHash), ct)).FirstOrDefault();

    public Task<int> RotateAdminSessionCsrfAsync(long sessionId, string csrfHash, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE admin_sessions SET csrf_hash=@csrf_hash,last_seen_at=NOW(3) WHERE id=@id AND revoked_at IS NULL AND expires_at>NOW(3)", c => { StudioDb.Add(c, "@id", sessionId); StudioDb.Add(c, "@csrf_hash", csrfHash); }, ct);
    public Task<int> TouchAdminSessionAsync(long sessionId, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE admin_sessions SET last_seen_at=NOW(3) WHERE id=@id AND revoked_at IS NULL AND expires_at>NOW(3)", c => StudioDb.Add(c, "@id", sessionId), ct);
    public Task<int> RevokeAdminSessionAsync(long sessionId, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE admin_sessions SET revoked_at=NOW(3),last_seen_at=NOW(3) WHERE id=@id AND revoked_at IS NULL", c => StudioDb.Add(c, "@id", sessionId), ct);

    public Task<int> AddSecurityAuditEventAsync(long? sessionId, string? actor, string? role, string action, string method, string path, string requestId, string? clientIp, string outcome, string? detailsJson, CancellationToken ct = default) => _db.ExecuteAsync(@"
        INSERT INTO security_audit_events(session_id,actor,role,action,method,path,request_id,client_ip,outcome,details_json)
        VALUES(@session_id,@actor,@role,@action,@method,@path,@request_id,@client_ip,@outcome,@details_json)", c =>
    {
        StudioDb.Add(c, "@session_id", sessionId); StudioDb.Add(c, "@actor", actor); StudioDb.Add(c, "@role", role); StudioDb.Add(c, "@action", action);
        StudioDb.Add(c, "@method", method); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@request_id", requestId); StudioDb.Add(c, "@client_ip", clientIp);
        StudioDb.Add(c, "@outcome", outcome); StudioDb.Add(c, "@details_json", detailsJson);
    }, ct);

    public Task<List<Dictionary<string, object?>>> SecurityAuditEventsAsync(int limit, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT id,session_id,actor,role,action,method,path,request_id,client_ip,outcome,details_json,created_at
        FROM security_audit_events ORDER BY id DESC LIMIT @limit", c => StudioDb.Add(c, "@limit", Math.Clamp(limit, 1, 200)), ct);

    public Task<int> UpsertWorkflowAsync(string name, string type, string path, string? model, string mapping, CancellationToken ct = default) => _db.ExecuteAsync(@"
        INSERT INTO workflows(name,workflow_type,path,model_name,parameter_mapping_json) VALUES(@name,@type,@path,@model,@mapping)
        ON DUPLICATE KEY UPDATE name=VALUES(name),workflow_type=VALUES(workflow_type),model_name=VALUES(model_name),parameter_mapping_json=VALUES(parameter_mapping_json),updated_at=NOW(3)", c => { StudioDb.Add(c, "@name", name); StudioDb.Add(c, "@type", type); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@model", model); StudioDb.Add(c, "@mapping", mapping); }, ct);

    public Task<int> UpsertModelAsync(string name, string type, string path, long size, CancellationToken ct = default) => _db.ExecuteAsync(@"
        INSERT INTO models(name,model_type,path,file_size_bytes) VALUES(@name,@type,@path,@size)
        ON DUPLICATE KEY UPDATE name=VALUES(name),model_type=VALUES(model_type),file_size_bytes=VALUES(file_size_bytes),updated_at=NOW(3)", c => { StudioDb.Add(c, "@name", name); StudioDb.Add(c, "@type", type); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@size", size); }, ct);

    public Task<int> UpsertLoraAsync(string name, string path, CancellationToken ct = default) => _db.ExecuteAsync(@"
        INSERT INTO loras(name,path) VALUES(@name,@path)
        ON DUPLICATE KEY UPDATE name=VALUES(name),updated_at=NOW(3)", c => { StudioDb.Add(c, "@name", name); StudioDb.Add(c, "@path", path); }, ct);

    public async Task<Dictionary<string, long>> DashboardCountsAsync(CancellationToken ct = default)
    {
        var rows = await _db.QueryAsync(@"SELECT
            (SELECT COUNT(*) FROM projects) projects,
            (SELECT COUNT(*) FROM episodes) episodes,
            (SELECT COUNT(*) FROM shots) shots,
            (SELECT COUNT(*) FROM characters) characters,
            (SELECT COUNT(*) FROM scenes) scenes,
            (SELECT COUNT(*) FROM assets) assets,
            (SELECT COUNT(*) FROM generation_tasks WHERE status='Running') running_tasks,
            (SELECT COUNT(*) FROM generation_tasks WHERE status='Succeeded') succeeded_tasks", cancellationToken: ct);
        return rows.FirstOrDefault()?.ToDictionary(k => k.Key, v => Convert.ToInt64(v.Value ?? 0, CultureInfo.InvariantCulture)) ?? [];
    }

    public Task<List<Dictionary<string, object?>>> ScriptsAsync(long? projectId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT s.*, p.name AS project_name, e.name AS episode_name
        FROM scripts s LEFT JOIN projects p ON p.id=s.project_id LEFT JOIN episodes e ON e.id=s.episode_id
        WHERE (@project IS NULL OR s.project_id=@project) ORDER BY s.updated_at DESC", c => StudioDb.Add(c, "@project", projectId), ct);

    public Task<List<Dictionary<string, object?>>> ScriptAsync(long id, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM scripts WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct);

    public async Task<long> CreateScriptAsync(ScriptInput input, CancellationToken ct = default)
    {
        var id = await _db.ExecuteInsertAsync(@"
            INSERT INTO scripts(project_id,episode_id,title,content,version,status,language) VALUES(@project,@episode,@title,@content,1,@status,@language)", c =>
        {
            StudioDb.Add(c, "@project", input.ProjectId); StudioDb.Add(c, "@episode", input.EpisodeId); StudioDb.Add(c, "@title", input.Title.Trim()); StudioDb.Add(c, "@content", input.Content); StudioDb.Add(c, "@status", input.Status); StudioDb.Add(c, "@language", input.Language);
        }, ct);
        await _db.ExecuteAsync("INSERT INTO script_versions(script_id,version,title,content,change_note) VALUES(@id,1,@title,@content,'初始版本')", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@title", input.Title.Trim()); StudioDb.Add(c, "@content", input.Content); }, ct);
        return id;
    }

    public async Task<int> UpdateScriptAsync(long id, ScriptInput input, string? changeNote, CancellationToken ct = default)
    {
        var version = Convert.ToInt32(await _db.ScalarAsync("SELECT COALESCE(version,1) FROM scripts WHERE id=@id", c => StudioDb.Add(c, "@id", id), ct) ?? 0, CultureInfo.InvariantCulture) + 1;
        var changed = await _db.ExecuteAsync("UPDATE scripts SET project_id=@project,episode_id=@episode,title=@title,content=@content,version=@version,status=@status,language=@language WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@project", input.ProjectId); StudioDb.Add(c, "@episode", input.EpisodeId); StudioDb.Add(c, "@title", input.Title.Trim()); StudioDb.Add(c, "@content", input.Content); StudioDb.Add(c, "@version", version); StudioDb.Add(c, "@status", input.Status); StudioDb.Add(c, "@language", input.Language);
        }, ct);
        if (changed > 0) await _db.ExecuteAsync("INSERT INTO script_versions(script_id,version,title,content,change_note) VALUES(@id,@version,@title,@content,@note)", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@version", version); StudioDb.Add(c, "@title", input.Title.Trim()); StudioDb.Add(c, "@content", input.Content); StudioDb.Add(c, "@note", changeNote ?? "编辑剧本"); }, ct);
        return changed;
    }

    public Task<List<Dictionary<string, object?>>> ScriptVersionsAsync(long scriptId, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM script_versions WHERE script_id=@id ORDER BY version DESC", c => StudioDb.Add(c, "@id", scriptId), ct);
    public Task<int> SaveScriptAnalysisAsync(long scriptId, string analysisJson, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE scripts SET analysis_json=@analysis,status='Analyzed' WHERE id=@id", c => { StudioDb.Add(c, "@id", scriptId); StudioDb.Add(c, "@analysis", analysisJson); }, ct);

    public Task<List<Dictionary<string, object?>>> ShotByNumberAsync(long episodeId, int shotNumber, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM shots WHERE episode_id=@episode AND shot_number=@number LIMIT 1", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@number", shotNumber); }, ct);
    public Task<List<Dictionary<string, object?>>> QueryShotAsync(long id, CancellationToken ct = default) => _db.QueryAsync("SELECT s.*,sc.name AS scene_name FROM shots s LEFT JOIN scenes sc ON sc.id=s.scene_id WHERE s.id=@id LIMIT 1", c => StudioDb.Add(c, "@id", id), ct);
    public Task<List<Dictionary<string, object?>>> QuerySceneAsync(long id, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM scenes WHERE id=@id LIMIT 1", c => StudioDb.Add(c, "@id", id), ct);

    public Task<int> UpdateAnalyzedShotAsync(long id, ScriptShotDraft draft, long? sceneId, IReadOnlyList<long> characterIds, CancellationToken ct = default) => _db.ExecuteAsync(@"
        UPDATE shots SET title=@title,description=@description,scene_id=@scene,character_ids_json=@characters,action=@action,dialogue=@dialogue,narration=@narration,emotion=@emotion,camera_type=@camera_type,camera_motion=@camera_motion,duration_seconds=@duration,status=IF(status IN ('Draft','Ready','Failed'),'Ready',status) WHERE id=@id", c =>
    {
        StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@title", draft.Title); StudioDb.Add(c, "@description", draft.Description); StudioDb.Add(c, "@scene", sceneId); StudioDb.Add(c, "@characters", JsonSerializer.Serialize(characterIds)); StudioDb.Add(c, "@action", draft.Action); StudioDb.Add(c, "@dialogue", draft.Dialogue); StudioDb.Add(c, "@narration", draft.Narration); StudioDb.Add(c, "@emotion", draft.Emotion); StudioDb.Add(c, "@camera_type", draft.CameraType); StudioDb.Add(c, "@camera_motion", draft.CameraMotion); StudioDb.Add(c, "@duration", draft.DurationSeconds);
    }, ct);

    public Task<int> SavePromptAsync(long shotId, PromptComposition composition, bool locked, string source, CancellationToken ct = default) => SavePromptInternalAsync(shotId, composition, locked, source, ct);

    private async Task<int> SavePromptInternalAsync(long shotId, PromptComposition composition, bool locked, string source, CancellationToken ct)
    {
        var current = (await _db.QueryAsync("SELECT prompt_version FROM shots WHERE id=@id", c => StudioDb.Add(c, "@id", shotId), ct)).FirstOrDefault();
        var version = Math.Max(1, current?.Int("promptVersion", 0) ?? 0) + 1;
        var components = JsonSerializer.Serialize(new { composition.CharacterPrompt, composition.ScenePrompt, composition.ActionPrompt, composition.CameraPrompt, composition.LightingPrompt, composition.StylePrompt, composition.QualityPrompt });
        await _db.ExecuteAsync("INSERT INTO prompt_history(shot_id,version,prompt,negative_prompt,components_json,source) VALUES(@shot,@version,@prompt,@negative,@components,@source)", c => { StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@version", version); StudioDb.Add(c, "@prompt", composition.Prompt); StudioDb.Add(c, "@negative", composition.NegativePrompt); StudioDb.Add(c, "@components", components); StudioDb.Add(c, "@source", source); }, ct);
        return await _db.ExecuteAsync(@"UPDATE shots SET prompt=@prompt,negative_prompt=@negative,character_prompt=@character,scene_prompt=@scene,action_prompt=@action,camera_prompt=@camera,lighting_prompt=@lighting,style_prompt=@style,quality_prompt=@quality,prompt_version=@version,prompt_locked=@locked,prompt_source_language='zh-CN',status=IF(status='Draft','Ready',status) WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@prompt", composition.Prompt); StudioDb.Add(c, "@negative", composition.NegativePrompt); StudioDb.Add(c, "@character", composition.CharacterPrompt); StudioDb.Add(c, "@scene", composition.ScenePrompt); StudioDb.Add(c, "@action", composition.ActionPrompt); StudioDb.Add(c, "@camera", composition.CameraPrompt); StudioDb.Add(c, "@lighting", composition.LightingPrompt); StudioDb.Add(c, "@style", composition.StylePrompt); StudioDb.Add(c, "@quality", composition.QualityPrompt); StudioDb.Add(c, "@version", version); StudioDb.Add(c, "@locked", locked);
        }, ct);
    }

    public Task<List<Dictionary<string, object?>>> PromptHistoryAsync(long shotId, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM prompt_history WHERE shot_id=@shot ORDER BY version DESC", c => StudioDb.Add(c, "@shot", shotId), ct);

    public async Task<int> RollbackPromptAsync(long shotId, int version, CancellationToken ct = default)
    {
        var history = (await _db.QueryAsync("SELECT * FROM prompt_history WHERE shot_id=@shot AND version=@version LIMIT 1", c => { StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@version", version); }, ct)).FirstOrDefault();
        if (history is null) return 0;
        var character = ""; var scene = ""; var action = ""; var camera = ""; var lighting = ""; var style = ""; var quality = "";
        try
        {
            using var components = JsonDocument.Parse(history.Text("componentsJson") ?? "{}");
            character = components.RootElement.TryGetProperty("CharacterPrompt", out var characterValue) ? characterValue.GetString() ?? "" : components.RootElement.TryGetProperty("characterPrompt", out characterValue) ? characterValue.GetString() ?? "" : "";
            scene = components.RootElement.TryGetProperty("ScenePrompt", out var sceneValue) ? sceneValue.GetString() ?? "" : components.RootElement.TryGetProperty("scenePrompt", out sceneValue) ? sceneValue.GetString() ?? "" : "";
            action = components.RootElement.TryGetProperty("ActionPrompt", out var actionValue) ? actionValue.GetString() ?? "" : components.RootElement.TryGetProperty("actionPrompt", out actionValue) ? actionValue.GetString() ?? "" : "";
            camera = components.RootElement.TryGetProperty("CameraPrompt", out var cameraValue) ? cameraValue.GetString() ?? "" : components.RootElement.TryGetProperty("cameraPrompt", out cameraValue) ? cameraValue.GetString() ?? "" : "";
            lighting = components.RootElement.TryGetProperty("LightingPrompt", out var lightingValue) ? lightingValue.GetString() ?? "" : components.RootElement.TryGetProperty("lightingPrompt", out lightingValue) ? lightingValue.GetString() ?? "" : "";
            style = components.RootElement.TryGetProperty("StylePrompt", out var styleValue) ? styleValue.GetString() ?? "" : components.RootElement.TryGetProperty("stylePrompt", out styleValue) ? styleValue.GetString() ?? "" : "";
            quality = components.RootElement.TryGetProperty("QualityPrompt", out var qualityValue) ? qualityValue.GetString() ?? "" : components.RootElement.TryGetProperty("qualityPrompt", out qualityValue) ? qualityValue.GetString() ?? "" : "";
        }
        catch { }
        var composition = new PromptComposition(character, scene, action, camera, lighting, style, quality, history.Text("prompt") ?? "", history.Text("negativePrompt") ?? "");
        return await SavePromptInternalAsync(shotId, composition, false, "rollback", ct);
    }

    public Task<List<Dictionary<string, object?>>> CandidatesAsync(long shotId, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM shot_candidates WHERE shot_id=@shot ORDER BY is_selected DESC,created_at", c => StudioDb.Add(c, "@shot", shotId), ct);

    public Task<long> AddCandidateAsync(long shotId, long? taskId, string path, int index, long? seed, string qcStatus, decimal? score, string? qcJson, CancellationToken ct = default) => _db.ExecuteInsertAsync(@"
        INSERT INTO shot_candidates(shot_id,task_id,path,candidate_index,seed,qc_status,quality_score,qc_json) VALUES(@shot,@task,@path,@index,@seed,@status,@score,@qc)", c => { StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@task", taskId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@index", index); StudioDb.Add(c, "@seed", seed); StudioDb.Add(c, "@status", qcStatus); StudioDb.Add(c, "@score", score); StudioDb.Add(c, "@qc", qcJson); }, ct);

    public async Task<string?> SelectCandidateAsync(long shotId, long candidateId, CancellationToken ct = default)
    {
        var candidate = (await _db.QueryAsync("SELECT path,qc_status FROM shot_candidates WHERE id=@id AND shot_id=@shot", c => { StudioDb.Add(c, "@id", candidateId); StudioDb.Add(c, "@shot", shotId); }, ct)).FirstOrDefault();
        if (candidate is null || string.Equals(candidate.Text("qcStatus"), "Rejected", StringComparison.OrdinalIgnoreCase)) return null;
        await _db.ExecuteAsync("UPDATE shot_candidates SET is_selected=0 WHERE shot_id=@shot", c => StudioDb.Add(c, "@shot", shotId), ct);
        await _db.ExecuteAsync("UPDATE shot_candidates SET is_selected=1 WHERE id=@id AND shot_id=@shot", c => { StudioDb.Add(c, "@id", candidateId); StudioDb.Add(c, "@shot", shotId); }, ct);
        await _db.ExecuteAsync("UPDATE shots SET selected_keyframe_path=@path,input_image_path=@path,status='ImageReview' WHERE id=@shot", c => { StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@path", candidate.Text("path")); }, ct);
        return candidate.Text("path");
    }

    public Task<int> UpdateShotStatusAsync(long shotId, string status, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE shots SET status=@status WHERE id=@id", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@status", status); }, ct);
    public Task<int> UpdateShotAudioStatusAsync(long shotId, string status, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE shots SET audio_status=@status WHERE id=@id", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@status", status); }, ct);
    public async Task<bool> TryCompleteShotAudioAsync(long shotId, CancellationToken ct = default)
    {
        var total = Convert.ToInt32(await _db.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE shot_id=@shot AND task_type IN ('Audio','TTS')", c => StudioDb.Add(c, "@shot", shotId), ct) ?? 0, CultureInfo.InvariantCulture);
        var remaining = Convert.ToInt32(await _db.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE shot_id=@shot AND task_type IN ('Audio','TTS') AND status<>'Succeeded'", c => StudioDb.Add(c, "@shot", shotId), ct) ?? 0, CultureInfo.InvariantCulture);
        if (total == 0 || remaining > 0) return false;
        await _db.ExecuteAsync("UPDATE shots SET audio_status='Completed',status='Completed' WHERE id=@shot", c => StudioDb.Add(c, "@shot", shotId), ct);
        return true;
    }
    public Task<int> UpdateShotVideoAsync(long shotId, string path, FfmpegProbe? probe, string? qcJson, decimal score, string status = "VideoReview", CancellationToken ct = default) => _db.ExecuteAsync("UPDATE shots SET video_path=@path,final_video_path=@path,quality_score=@score,video_qc_json=@qc,status=@status WHERE id=@id", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@score", score); StudioDb.Add(c, "@qc", qcJson); StudioDb.Add(c, "@status", status); }, ct);
    public Task<int> UpdateShotFinalVideoAsync(long shotId, string path, string? qcJson, decimal score, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE shots SET final_video_path=@path,quality_score=@score,video_qc_json=@qc,status='Completed' WHERE id=@id", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@score", score); StudioDb.Add(c, "@qc", qcJson); }, ct);
    public Task<int> RateShotAsync(long shotId, int rating, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE shots SET user_rating=@rating WHERE id=@id", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@rating", Math.Clamp(rating, 1, 5)); }, ct);

    public async Task<Dictionary<string, object?>?> HighestPendingTaskAsync(string resourceClass = "GPU", CancellationToken ct = default) => (await _db.QueryAsync("SELECT id FROM generation_tasks WHERE status='Pending' AND paused=0 AND COALESCE(resource_class,'GPU')=@resource ORDER BY priority DESC,created_at LIMIT 1", c => StudioDb.Add(c, "@resource", string.Equals(resourceClass, "CPU", StringComparison.OrdinalIgnoreCase) ? "CPU" : "GPU"), ct)).FirstOrDefault();
    public async Task<bool> HasActiveTaskForShotAsync(long shotId, string taskType, CancellationToken ct = default)
        => (await _db.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE shot_id=@shot AND task_type=@type AND status IN ('Pending','Running')", c => { StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@type", taskType); }, ct)) is { } value && Convert.ToInt32(value, CultureInfo.InvariantCulture) > 0;
    public async Task<bool> HasActiveTaskForEpisodeAsync(long episodeId, string taskType, CancellationToken ct = default)
        => (await _db.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE episode_id=@episode AND task_type=@type AND status IN ('Pending','Running')", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@type", taskType); }, ct)) is { } value && Convert.ToInt32(value, CultureInfo.InvariantCulture) > 0;
    public async Task<bool> HasSucceededTaskForEpisodeAsync(long episodeId, string taskType, CancellationToken ct = default)
        => (await _db.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE episode_id=@episode AND task_type=@type AND status='Succeeded'", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@type", taskType); }, ct)) is { } value && Convert.ToInt32(value, CultureInfo.InvariantCulture) > 0;

    public async Task<(bool Ready, bool Blocked)> TaskDependencyStateAsync(long taskId, CancellationToken ct = default)
    {
        var rows = await _db.QueryAsync(@"SELECT d.depends_on_task_id AS dependency_id,t.status AS dependency_status
            FROM task_dependencies d JOIN generation_tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=@id", c => StudioDb.Add(c, "@id", taskId), ct);
        if (rows.Any(x => string.Equals(x.Text("dependencyStatus"), "Failed", StringComparison.OrdinalIgnoreCase) || string.Equals(x.Text("dependencyStatus"), "Cancelled", StringComparison.OrdinalIgnoreCase))) return (false, true);
        return (!rows.Any(x => !string.Equals(x.Text("dependencyStatus"), "Succeeded", StringComparison.OrdinalIgnoreCase)), false);
    }

    public Task<int> AddTaskDependencyAsync(long taskId, long dependsOnTaskId, CancellationToken ct = default) => _db.ExecuteAsync("INSERT IGNORE INTO task_dependencies(task_id,depends_on_task_id) VALUES(@task,@dependency)", c => { StudioDb.Add(c, "@task", taskId); StudioDb.Add(c, "@dependency", dependsOnTaskId); }, ct);

    public async Task<long> CreateProductionRunAsync(long projectId, long episodeId, string mode, int totalShots, string? idempotencyKey = null, CancellationToken ct = default)
    {
        var key = string.IsNullOrWhiteSpace(idempotencyKey) ? null : idempotencyKey.Trim();
        var id = await _db.ExecuteInsertAsync("INSERT INTO production_runs(project_id,episode_id,mode,status,total_shots,idempotency_key,started_at) VALUES(@project,@episode,@mode,'Running',@total,@key,NOW(3)) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)", c => { StudioDb.Add(c, "@project", projectId); StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@mode", mode); StudioDb.Add(c, "@total", totalShots); StudioDb.Add(c, "@key", key); }, ct);
        if (key is not null)
        {
            var existing = await ProductionRunByIdempotencyKeyAsync(key, ct);
            if (existing is not null && (existing.LongOrNull("projectId") != projectId || existing.LongOrNull("episodeId") != episodeId || !string.Equals(existing.Text("mode"), mode, StringComparison.OrdinalIgnoreCase) || existing.Int("totalShots", -1) != totalShots))
                throw new IdempotencyConflictException("相同幂等键对应了不同的生产批次");
            return existing?.Long("id") ?? id;
        }
        return id;
    }
    public Task<List<Dictionary<string, object?>>> ProductionRunAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM production_runs WHERE episode_id=@episode ORDER BY created_at DESC LIMIT 1", c => StudioDb.Add(c, "@episode", episodeId), ct);
    public Task<Dictionary<string, object?>?> ProductionRunByIdempotencyKeyAsync(string key, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM production_runs WHERE idempotency_key=@key LIMIT 1", c => StudioDb.Add(c, "@key", key), ct).ContinueWith(t => t.Result.FirstOrDefault(), ct);
    public Task<Dictionary<string, object?>?> ActiveProductionRunAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM production_runs WHERE episode_id=@episode AND status IN ('Queued','Running') ORDER BY created_at DESC LIMIT 1", c => StudioDb.Add(c, "@episode", episodeId), ct).ContinueWith(t => t.Result.FirstOrDefault(), ct);
    public Task<List<Dictionary<string, object?>>> ProductionRunTasksAsync(long runId, CancellationToken ct = default) => _db.QueryAsync("SELECT id,status FROM generation_tasks WHERE production_run_id=@run ORDER BY id", c => StudioDb.Add(c, "@run", runId), ct);
    public Task<int> UpdateProductionRunAsync(long id, string status, int? completed = null, int? failed = null, string? error = null, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE production_runs SET status=@status,completed_shots=COALESCE(@completed,completed_shots),failed_shots=COALESCE(@failed,failed_shots),last_error=@error,finished_at=IF(@status IN ('Completed','Failed','Cancelled'),NOW(3),finished_at) WHERE id=@id", c => { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@status", status); StudioDb.Add(c, "@completed", completed); StudioDb.Add(c, "@failed", failed); StudioDb.Add(c, "@error", error); }, ct);

    public Task<List<Dictionary<string, object?>>> GetSettingsAsync(string? category = null, CancellationToken ct = default) => _db.QueryAsync("SELECT setting_key,setting_value,category,is_secret FROM system_settings WHERE (@category IS NULL OR category=@category) ORDER BY setting_key", c => StudioDb.Add(c, "@category", category), ct);
    public Task<string?> GetSettingAsync(string key, CancellationToken ct = default) => _db.QueryAsync("SELECT setting_value FROM system_settings WHERE setting_key=@key LIMIT 1", c => StudioDb.Add(c, "@key", key), ct).ContinueWith(t => t.Result.FirstOrDefault()?.Text("settingValue"), ct);
    public Task<int> SetSettingAsync(string key, string? value, string category, bool secret, CancellationToken ct = default) => _db.ExecuteAsync("INSERT INTO system_settings(setting_key,setting_value,category,is_secret) VALUES(@key,@value,@category,@secret) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value),category=VALUES(category),is_secret=VALUES(is_secret),updated_at=NOW(3)", c => { StudioDb.Add(c, "@key", key); StudioDb.Add(c, "@value", value); StudioDb.Add(c, "@category", category); StudioDb.Add(c, "@secret", secret); }, ct);

    public Task<Dictionary<string, object?>?> AudioCacheAsync(string key, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM audio_cache WHERE cache_key=@key LIMIT 1", c => StudioDb.Add(c, "@key", key), ct).ContinueWith(t => t.Result.FirstOrDefault(), ct);
    public Task<long> AddAudioCacheAsync(string key, string text, string voice, decimal speed, decimal pitch, string path, double? duration, CancellationToken ct = default) => _db.ExecuteInsertAsync("INSERT INTO audio_cache(cache_key,text_content,voice_id,speed,pitch,path,duration_seconds) VALUES(@key,@text,@voice,@speed,@pitch,@path,@duration) ON DUPLICATE KEY UPDATE path=VALUES(path),duration_seconds=VALUES(duration_seconds)", c => { StudioDb.Add(c, "@key", key); StudioDb.Add(c, "@text", text); StudioDb.Add(c, "@voice", voice); StudioDb.Add(c, "@speed", speed); StudioDb.Add(c, "@pitch", pitch); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@duration", duration); }, ct);

    public async Task ReplaceSubtitlesAsync(long episodeId, IReadOnlyList<(long? ShotId, int Sequence, double Start, double End, string? Speaker, string Content)> items, string path, CancellationToken ct = default)
    {
        await _db.ExecuteAsync("DELETE FROM subtitles WHERE episode_id=@episode", c => StudioDb.Add(c, "@episode", episodeId), ct);
        foreach (var item in items) await _db.ExecuteAsync("INSERT INTO subtitles(episode_id,shot_id,sequence_no,start_seconds,end_seconds,speaker,content,path) VALUES(@episode,@shot,@sequence,@start,@end,@speaker,@content,@path)", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@shot", item.ShotId); StudioDb.Add(c, "@sequence", item.Sequence); StudioDb.Add(c, "@start", item.Start); StudioDb.Add(c, "@end", item.End); StudioDb.Add(c, "@speaker", item.Speaker); StudioDb.Add(c, "@content", item.Content); StudioDb.Add(c, "@path", path); }, ct);
        await _db.ExecuteAsync("UPDATE episodes SET subtitle_path=@path WHERE id=@episode", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@path", path); }, ct);
    }

    public Task<List<Dictionary<string, object?>>> SubtitlesAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM subtitles WHERE episode_id=@episode ORDER BY sequence_no", c => StudioDb.Add(c, "@episode", episodeId), ct);

    public Task<List<Dictionary<string, object?>>> SoundEffectsAsync(string? category, CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM sound_effects WHERE (@category IS NULL OR category=@category) ORDER BY category,name", c => StudioDb.Add(c, "@category", category), ct);
    public Task<long> AddSoundEffectAsync(string name, string category, string path, string? sha256, double? duration, CancellationToken ct = default) => _db.ExecuteInsertAsync("INSERT INTO sound_effects(name,category,path,sha256,duration_seconds) VALUES(@name,@category,@path,@sha256,@duration) ON DUPLICATE KEY UPDATE name=VALUES(name),category=VALUES(category),sha256=VALUES(sha256),duration_seconds=VALUES(duration_seconds)", c => { StudioDb.Add(c, "@name", name); StudioDb.Add(c, "@category", category); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@sha256", sha256); StudioDb.Add(c, "@duration", duration); }, ct);
    public Task<List<Dictionary<string, object?>>> BgmTracksAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM bgm_tracks ORDER BY name", cancellationToken: ct);
    public Task<long> AddBgmAsync(string name, string path, string? sha256, double? duration, decimal volume, CancellationToken ct = default) => _db.ExecuteInsertAsync("INSERT INTO bgm_tracks(name,path,sha256,duration_seconds,default_volume) VALUES(@name,@path,@sha256,@duration,@volume) ON DUPLICATE KEY UPDATE name=VALUES(name),sha256=VALUES(sha256),duration_seconds=VALUES(duration_seconds),default_volume=VALUES(default_volume)", c => { StudioDb.Add(c, "@name", name); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@sha256", sha256); StudioDb.Add(c, "@duration", duration); StudioDb.Add(c, "@volume", volume); }, ct);
    public Task<int> BindEpisodeBgmAsync(long episodeId, long bgmId, decimal volume, CancellationToken ct = default) => _db.ExecuteAsync("INSERT INTO episode_bgm(episode_id,bgm_id,volume) VALUES(@episode,@bgm,@volume) ON DUPLICATE KEY UPDATE volume=VALUES(volume)", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@bgm", bgmId); StudioDb.Add(c, "@volume", volume); }, ct);
    public Task<List<Dictionary<string, object?>>> EpisodeBgmAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync("SELECT b.*,eb.volume FROM episode_bgm eb JOIN bgm_tracks b ON b.id=eb.bgm_id WHERE eb.episode_id=@episode", c => StudioDb.Add(c, "@episode", episodeId), ct);
    public Task<List<Dictionary<string, object?>>> EpisodeAudioResultsAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT r.path,r.created_at,t.shot_id,s.sort_order,s.duration_seconds
        FROM generation_results r JOIN generation_tasks t ON t.id=r.task_id
        LEFT JOIN shots s ON s.id=t.shot_id
        WHERE t.episode_id=@episode AND t.status='Succeeded' AND r.result_type='audio' AND r.path IS NOT NULL
        ORDER BY COALESCE(s.sort_order,s.id),r.created_at", c => StudioDb.Add(c, "@episode", episodeId), ct);
    public Task<List<Dictionary<string, object?>>> EpisodeSoundEffectsAsync(long episodeId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT se.path,ss.shot_id,ss.start_seconds,ss.volume,s.sort_order
        FROM shot_sound_effects ss JOIN sound_effects se ON se.id=ss.sound_effect_id
        JOIN shots s ON s.id=ss.shot_id WHERE s.episode_id=@episode ORDER BY s.sort_order,ss.start_seconds", c => StudioDb.Add(c, "@episode", episodeId), ct);
    public Task<int> UpdateEpisodeProductionAsync(long episodeId, string mode, string? narratorVoiceId, decimal voiceVolume, decimal bgmVolume, decimal sfxVolume, CancellationToken ct = default) => _db.ExecuteAsync("UPDATE episodes SET production_mode=@mode,narrator_voice_id=@narrator,voice_volume=@voice,bgm_volume=@bgm,sfx_volume=@sfx WHERE id=@id", c => { StudioDb.Add(c, "@id", episodeId); StudioDb.Add(c, "@mode", mode); StudioDb.Add(c, "@narrator", narratorVoiceId); StudioDb.Add(c, "@voice", voiceVolume); StudioDb.Add(c, "@bgm", bgmVolume); StudioDb.Add(c, "@sfx", sfxVolume); }, ct);
    public Task<int> UpdateEpisodeOutputAsync(long episodeId, string path, FfmpegProbe? probe, CancellationToken ct = default)
    {
        var fps = probe?.Fps is { } rate ? (int?)Math.Round(rate) : null;
        return _db.ExecuteAsync("UPDATE episodes SET output_path=@path,total_duration_seconds=@duration,output_width=COALESCE(@width,output_width),output_height=COALESCE(@height,output_height),output_fps=COALESCE(@fps,output_fps),status=IF(qa_locked=1 AND qa_status='Approved','Approved','Completed') WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", episodeId); StudioDb.Add(c, "@path", path); StudioDb.Add(c, "@duration", probe?.DurationSeconds); StudioDb.Add(c, "@width", probe?.Width); StudioDb.Add(c, "@height", probe?.Height); StudioDb.Add(c, "@fps", fps);
        }, ct);
    }
    public Task<int> BindShotSoundEffectAsync(long shotId, ShotSoundEffectInput input, CancellationToken ct = default) => _db.ExecuteAsync("INSERT INTO shot_sound_effects(shot_id,sound_effect_id,start_seconds,volume) VALUES(@shot,@effect,@start,@volume) ON DUPLICATE KEY UPDATE start_seconds=VALUES(start_seconds),volume=VALUES(volume)", c => { StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@effect", input.SoundEffectId); StudioDb.Add(c, "@start", Math.Max(0, input.StartSeconds)); StudioDb.Add(c, "@volume", Math.Clamp(input.Volume, 0, 1)); }, ct);
    public Task<List<Dictionary<string, object?>>> ShotSoundEffectsAsync(long shotId, CancellationToken ct = default) => _db.QueryAsync("SELECT se.*,s.start_seconds,s.volume FROM shot_sound_effects s JOIN sound_effects se ON se.id=s.sound_effect_id WHERE s.shot_id=@shot ORDER BY s.start_seconds", c => StudioDb.Add(c, "@shot", shotId), ct);
    public Task<List<Dictionary<string, object?>>> ProjectTemplatesAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM project_templates ORDER BY template_type,name", cancellationToken: ct);
    public Task<long> CreateProjectTemplateAsync(ProjectTemplateInput input, CancellationToken ct = default) => _db.ExecuteInsertAsync("INSERT INTO project_templates(name,template_type,description,config_json) VALUES(@name,@type,@description,@config) ON DUPLICATE KEY UPDATE description=VALUES(description),config_json=VALUES(config_json)", c => { StudioDb.Add(c, "@name", input.Name.Trim()); StudioDb.Add(c, "@type", input.TemplateType); StudioDb.Add(c, "@description", input.Description); StudioDb.Add(c, "@config", StudioDb.JsonOrNull(input.Config)); }, ct);
    public async Task<int> ApplyProjectTemplateAsync(long projectId, long templateId, CancellationToken ct = default)
    {
        var template = (await _db.QueryAsync("SELECT config_json FROM project_templates WHERE id=@id", c => StudioDb.Add(c, "@id", templateId), ct)).FirstOrDefault(); if (template is null) return 0;
        using var config = JsonDocument.Parse(template.Text("configJson") ?? "{}"); var root = config.RootElement;
        return await _db.ExecuteAsync("UPDATE projects SET aspect_ratio=COALESCE(@aspect,aspect_ratio),style=COALESCE(@style,style),default_fps=COALESCE(@fps,default_fps),default_width=COALESCE(@width,default_width),default_height=COALESCE(@height,default_height),prompt_style=COALESCE(@prompt_style,prompt_style),bgm_path=COALESCE(@bgm_path,bgm_path),bgm_volume=COALESCE(@bgm_volume,bgm_volume) WHERE id=@id", c => { StudioDb.Add(c, "@id", projectId); StudioDb.Add(c, "@aspect", JsonString(root, "aspectRatio")); StudioDb.Add(c, "@style", JsonString(root, "style")); StudioDb.Add(c, "@fps", JsonInt(root, "fps")); StudioDb.Add(c, "@width", JsonInt(root, "width")); StudioDb.Add(c, "@height", JsonInt(root, "height")); StudioDb.Add(c, "@prompt_style", JsonString(root, "promptStyle")); StudioDb.Add(c, "@bgm_path", JsonString(root, "bgmPath")); StudioDb.Add(c, "@bgm_volume", JsonDecimal(root, "bgmVolume")); }, ct);
    }
    public Task<List<Dictionary<string, object?>>> PresetsAsync(CancellationToken ct = default) => _db.QueryAsync("SELECT * FROM generation_presets ORDER BY preset_type,name", cancellationToken: ct);
    public Task<List<Dictionary<string, object?>>> ParameterRecommendationsAsync(CancellationToken ct = default) => _db.QueryAsync(@"SELECT COALESCE(w.name,'Default') AS workflow_name,COUNT(*) AS sample_count,AVG(COALESCE(r.quality_score,0)) AS average_quality,AVG(COALESCE(s.user_rating,0)) AS average_rating,AVG(COALESCE(t.duration_ms,0)) AS average_duration_ms
        FROM generation_results r JOIN generation_tasks t ON t.id=r.task_id LEFT JOIN workflows w ON w.id=t.workflow_id LEFT JOIN shots s ON s.id=t.shot_id
        GROUP BY COALESCE(w.name,'Default') ORDER BY average_rating DESC,average_quality DESC,sample_count DESC LIMIT 20", cancellationToken: ct);

    private static void BindCharacter(MySqlCommand c, CharacterInput input)
    {
        StudioDb.Add(c, "@project_id", input.ProjectId); StudioDb.Add(c, "@name", input.Name.Trim()); StudioDb.Add(c, "@age", input.AgeSetting); StudioDb.Add(c, "@face", input.FaceFeatures); StudioDb.Add(c, "@hair", input.Hair); StudioDb.Add(c, "@clothes", input.Clothes); StudioDb.Add(c, "@body", input.BodyRatio); StudioDb.Add(c, "@fixed", input.FixedPrompt); StudioDb.Add(c, "@negative", input.NegativePrompt); StudioDb.Add(c, "@embedding", input.EmbeddingPath); StudioDb.Add(c, "@lora", input.LoraPath); StudioDb.Add(c, "@anchor", input.AnchorPath); StudioDb.Add(c, "@voice_id", input.VoiceId); StudioDb.Add(c, "@voice_speed", Math.Clamp(input.VoiceSpeed, .5m, 2m)); StudioDb.Add(c, "@voice_pitch", Math.Clamp(input.VoicePitch, -10m, 10m)); StudioDb.Add(c, "@metadata", StudioDb.JsonOrNull(input.Metadata));
    }
    private static void BindProjectOptions(MySqlCommand c, ProjectInput input)
    {
        var ratio = input.AspectRatio is "9:16" or "1:1" or "16:9" ? input.AspectRatio : "16:9";
        StudioDb.Add(c, "@aspect", ratio); StudioDb.Add(c, "@style", input.Style); StudioDb.Add(c, "@fps", Math.Clamp(input.DefaultFps, 24, 60)); StudioDb.Add(c, "@width", Math.Clamp(input.DefaultWidth, 256, 3840)); StudioDb.Add(c, "@height", Math.Clamp(input.DefaultHeight, 256, 3840)); StudioDb.Add(c, "@prompt_style", input.PromptStyle); StudioDb.Add(c, "@bgm_path", input.BgmPath); StudioDb.Add(c, "@bgm_volume", Math.Clamp(input.BgmVolume, 0, 1));
    }
    private static string? JsonString(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
    private static int? JsonInt(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.TryGetInt32(out var result) ? result : null;
    private static decimal? JsonDecimal(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.TryGetDecimal(out var result) ? result : null;
    private static void BindScene(MySqlCommand c, SceneInput input)
    {
        StudioDb.Add(c, "@project_id", input.ProjectId); StudioDb.Add(c, "@name", input.Name.Trim()); StudioDb.Add(c, "@description", input.Description); StudioDb.Add(c, "@fixed", input.FixedPrompt); StudioDb.Add(c, "@negative", input.NegativePrompt); StudioDb.Add(c, "@style", input.Style); StudioDb.Add(c, "@anchor", input.AnchorPath); StudioDb.Add(c, "@metadata", StudioDb.JsonOrNull(input.Metadata));
    }
    private static void BindEpisode(MySqlCommand c, EpisodeInput input)
    {
        StudioDb.Add(c, "@project", input.ProjectId); StudioDb.Add(c, "@number", input.EpisodeNumber); StudioDb.Add(c, "@name", input.Name.Trim()); StudioDb.Add(c, "@description", input.Description); StudioDb.Add(c, "@seconds", input.TargetSeconds); StudioDb.Add(c, "@fps", input.OutputFps); StudioDb.Add(c, "@width", input.OutputWidth); StudioDb.Add(c, "@height", input.OutputHeight);
    }
    private static void BindShot(MySqlCommand c, ShotInput input)
    {
        StudioDb.Add(c, "@project", input.ProjectId); StudioDb.Add(c, "@episode", input.EpisodeId); StudioDb.Add(c, "@number", input.ShotNumber); StudioDb.Add(c, "@title", input.Title.Trim()); StudioDb.Add(c, "@description", input.Description); StudioDb.Add(c, "@scene", input.SceneId); StudioDb.Add(c, "@characters", StudioDb.JsonOrEmpty(input.CharacterIds)); StudioDb.Add(c, "@prompt", input.Prompt); StudioDb.Add(c, "@negative", input.NegativePrompt); StudioDb.Add(c, "@workflow", input.WorkflowId); StudioDb.Add(c, "@model", input.ModelId); StudioDb.Add(c, "@loras", StudioDb.JsonOrEmpty(input.LoraIds)); StudioDb.Add(c, "@seed", input.Seed); StudioDb.Add(c, "@cfg", input.CfgScale); StudioDb.Add(c, "@steps", input.Steps); StudioDb.Add(c, "@width", input.Width); StudioDb.Add(c, "@height", input.Height); StudioDb.Add(c, "@frames", input.Frames); StudioDb.Add(c, "@fps", input.Fps); StudioDb.Add(c, "@input", input.InputImagePath); StudioDb.Add(c, "@motion", input.MotionPreset); StudioDb.Add(c, "@camera", input.CameraPreset); StudioDb.Add(c, "@status", input.Status); StudioDb.Add(c, "@sort", input.ShotNumber);
        StudioDb.Add(c, "@action", input.Action); StudioDb.Add(c, "@dialogue", input.Dialogue); StudioDb.Add(c, "@narration", input.Narration); StudioDb.Add(c, "@emotion", input.Emotion); StudioDb.Add(c, "@camera_type", input.CameraType); StudioDb.Add(c, "@camera_motion", input.CameraMotion); StudioDb.Add(c, "@duration", input.DurationSeconds); StudioDb.Add(c, "@character_prompt", input.CharacterPrompt); StudioDb.Add(c, "@scene_prompt", input.ScenePrompt); StudioDb.Add(c, "@action_prompt", input.ActionPrompt); StudioDb.Add(c, "@camera_prompt", input.CameraPrompt); StudioDb.Add(c, "@lighting_prompt", input.LightingPrompt); StudioDb.Add(c, "@style_prompt", input.StylePrompt); StudioDb.Add(c, "@quality_prompt", input.QualityPrompt); StudioDb.Add(c, "@prompt_version", Math.Max(1, input.PromptVersion)); StudioDb.Add(c, "@prompt_locked", input.PromptLocked); StudioDb.Add(c, "@prompt_language", input.PromptSourceLanguage); StudioDb.Add(c, "@selected_keyframe", input.SelectedKeyframePath); StudioDb.Add(c, "@video", input.VideoPath); StudioDb.Add(c, "@final_video", input.FinalVideoPath); StudioDb.Add(c, "@quality_score", input.QualityScore); StudioDb.Add(c, "@user_rating", input.UserRating); StudioDb.Add(c, "@video_qc", StudioDb.JsonOrNull(input.VideoQc)); StudioDb.Add(c, "@audio_status", input.AudioStatus); StudioDb.Add(c, "@subtitle_status", input.SubtitleStatus);
    }
    private static async Task<string?> Sha256Async(string path, CancellationToken ct)
    {
        if (!File.Exists(path)) return null;
        await using var stream = File.OpenRead(path);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, ct)).ToLowerInvariant();
    }

    private static string MimeFor(string path) => Path.GetExtension(path).ToLowerInvariant() switch { ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp", ".mp4" => "video/mp4", ".mov" => "video/quicktime", ".wav" => "audio/wav", ".mp3" => "audio/mpeg", ".srt" => "application/x-subrip", _ => "application/octet-stream" };
}

public sealed class DatabaseInitializer
{
    private readonly StudioSettings _settings;
    private readonly StudioDb _db;
    private readonly ILogger<DatabaseInitializer> _logger;

    public DatabaseInitializer(StudioSettings settings, StudioDb db, ILogger<DatabaseInitializer> logger)
    {
        _settings = settings;
        _db = db;
        _logger = logger;
    }

    public async Task<bool> TryInitializeAsync(CancellationToken ct = default)
    {
        if (!_settings.AutoApplySchema)
        {
            _logger.LogWarning("Database schema auto-apply is disabled; no schema-creation or migration statements will be executed by the initializer");
            return false;
        }

        try
        {
            if (_settings.AllowDatabaseCreate)
            {
                await using var server = new MySqlConnection(_settings.ServerConnectionString);
                await server.OpenAsync(ct);
                await using var create = new MySqlCommand($"CREATE DATABASE IF NOT EXISTS `{_settings.DatabaseName}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci", server);
                await create.ExecuteNonQueryAsync(ct);
            }
            await ApplyExistingSchemaAsync(ct);
            _logger.LogInformation("Video Studio database schema is ready");
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Database initialization deferred: {Message}", ex.Message);
            return false;
        }
    }

    /// <summary>
    /// Applies the baseline schema and additive migrations to an already-created
    /// database. Database creation is deliberately separate so the runtime
    /// migrator never needs a global CREATE DATABASE privilege.
    /// </summary>
    public async Task ApplyExistingSchemaAsync(CancellationToken ct = default)
    {
        var schemaPath = Path.Combine(_settings.RootPath, "database", "database.sql");
        if (!File.Exists(schemaPath)) throw new FileNotFoundException("database.sql not found", schemaPath);
        var sql = File.ReadAllText(schemaPath);
        await using var connection = new MySqlConnection(_settings.DatabaseConnectionString);
        await connection.OpenAsync(ct);
        foreach (var statement in SplitSql(sql))
        {
            var executable = RemoveLeadingSqlComments(statement).Trim();
            if (string.IsNullOrWhiteSpace(executable) || Regex.IsMatch(executable, "^(CREATE DATABASE|USE\\b)", RegexOptions.IgnoreCase)) continue;
            await using var command = new MySqlCommand(executable, connection) { CommandTimeout = 120 };
            await command.ExecuteNonQueryAsync(ct);
        }
        await MarkBaselineSchemaVersionAsync(connection, ct);
        await ProductionSchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "002_production_pipeline.sql"), ct);
        await VideoQaSchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "003_video_qa.sql"), ct);
        await ReliabilitySchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "004_reliability_references_audio.sql"), ct);
        await QualityOptimizationSchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "005_quality_optimization.sql"), ct);
        await LocalAuthSchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "007_local_auth_audit.sql"), ct);
        await Stage12SchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "008_stage12_production_core.sql"), ct);
        await ReleaseCandidateSchemaMigrator.ApplyAsync(connection, Path.Combine(_settings.RootPath, "database", "migrations", "009_release_candidate_packages.sql"), ct);
    }

    private static async Task MarkBaselineSchemaVersionAsync(MySqlConnection connection, CancellationToken ct)
    {
        await using var command = new MySqlCommand("INSERT IGNORE INTO schema_migrations(version) VALUES('001_database_sql')", connection);
        await command.ExecuteNonQueryAsync(ct);
    }

    private static IEnumerable<string> SplitSql(string sql)
    {
        var current = new StringBuilder();
        var inString = false;
        var quote = '\0';
        for (var i = 0; i < sql.Length; i++)
        {
            var ch = sql[i];
            if ((ch == '\'' || ch == '"') && (i == 0 || sql[i - 1] != '\\'))
            {
                if (!inString) { inString = true; quote = ch; }
                else if (quote == ch) inString = false;
            }
            if (ch == ';' && !inString) { yield return current.ToString(); current.Clear(); }
            else current.Append(ch);
        }
        if (current.Length > 0) yield return current.ToString();
    }

    private static string RemoveLeadingSqlComments(string statement)
    {
        var remaining = statement.TrimStart();
        while (remaining.StartsWith("--", StringComparison.Ordinal))
        {
            var newline = remaining.IndexOf('\n');
            if (newline < 0) return string.Empty;
            remaining = remaining[(newline + 1)..].TrimStart();
        }
        while (remaining.StartsWith("/*", StringComparison.Ordinal))
        {
            var end = remaining.IndexOf("*/", StringComparison.Ordinal);
            if (end < 0) return string.Empty;
            remaining = remaining[(end + 2)..].TrimStart();
        }
        return remaining;
    }
}
