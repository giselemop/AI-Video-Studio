using System.Globalization;
using System.Text.Json;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Append-only repository for production profiles, entity snapshots and shot
/// plans. No update/delete method is exposed for immutable rows.
/// </summary>
public sealed class ProductionCoreRepository
{
    private static readonly HashSet<string> EntityTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "Character", "Scene", "Prompt", "Workflow", "Voice"
    };

    private readonly StudioDb _db;

    public ProductionCoreRepository(StudioDb db) => _db = db;

    public async Task<bool> IsSchemaReadyAsync(CancellationToken ct = default)
    {
        try
        {
            var count = await _db.ScalarAsync("SELECT COUNT(*) FROM schema_migrations WHERE version=@version", command => StudioDb.Add(command, "@version", Stage12SchemaMigrator.Version), ct);
            return Convert.ToInt32(count ?? 0, CultureInfo.InvariantCulture) == 1;
        }
        catch (MySqlException) { return false; }
    }

    public Task<List<Dictionary<string, object?>>> ProfilesAsync(long projectId, CancellationToken ct = default)
        => _db.QueryAsync(@"SELECT p.*,(b.production_profile_id=p.id) AS is_active
            FROM production_profiles p
            LEFT JOIN project_production_profile_bindings b ON b.project_id=p.project_id
            WHERE p.project_id=@project ORDER BY p.profile_key,p.version DESC", command => StudioDb.Add(command, "@project", projectId), ct);

    public async Task<long> CreateProfileAsync(ProductionProfileInput input, CancellationToken ct = default)
    {
        if (input.ProjectId <= 0) throw new ArgumentException("ProjectId is required", nameof(input));
        var profileKey = NormalizeKey(input.ProfileKey, "default");
        var name = string.IsNullOrWhiteSpace(input.Name) ? profileKey : input.Name.Trim();
        if (input.OutputWidth is < 256 or > 7680 || input.OutputHeight is < 256 or > 4320 || input.OutputFps is < 1 or > 120)
            throw new ArgumentException("Production profile output dimensions or FPS are outside the supported range", nameof(input));
        await RequireProjectAsync(input.ProjectId, ct);

        var content = CanonicalJson.Serialize(new
        {
            input.OutputWidth,
            input.OutputHeight,
            input.OutputFps,
            videoCodec = NormalizeKey(input.VideoCodec, "h264"),
            audioCodec = NormalizeKey(input.AudioCodec, "aac"),
            input.AudioSampleRate,
            colorSpace = NormalizeKey(input.ColorSpace, "bt709"),
            settings = input.Settings
        });
        var hash = CanonicalJson.Sha256(content);
        var existing = await _db.ScalarAsync(@"SELECT id FROM production_profiles
            WHERE project_id=@project AND profile_key=@key AND content_sha256=@hash LIMIT 1", command =>
        {
            StudioDb.Add(command, "@project", input.ProjectId);
            StudioDb.Add(command, "@key", profileKey);
            StudioDb.Add(command, "@hash", hash);
        }, ct);
        if (existing is not null and not DBNull) return Convert.ToInt64(existing, CultureInfo.InvariantCulture);

        return await InsertWithVersionRetryAsync(async () => await _db.ExecuteInsertAsync(@"
            INSERT INTO production_profiles(project_id,profile_key,version,name,content_json,content_sha256,created_by)
            SELECT @project,@key,COALESCE(MAX(version),0)+1,@name,@content,@hash,@actor
            FROM production_profiles WHERE project_id=@project AND profile_key=@key", command =>
        {
            StudioDb.Add(command, "@project", input.ProjectId);
            StudioDb.Add(command, "@key", profileKey);
            StudioDb.Add(command, "@name", name);
            StudioDb.Add(command, "@content", content);
            StudioDb.Add(command, "@hash", hash);
            StudioDb.Add(command, "@actor", NormalizeActor(input.CreatedBy));
        }, ct), async () => await FindProfileByHashAsync(input.ProjectId, profileKey, hash, ct));
    }

    public async Task<int> BindProfileAsync(long projectId, long profileId, string actor, CancellationToken ct = default)
    {
        var profile = (await _db.QueryAsync("SELECT project_id FROM production_profiles WHERE id=@id", command => StudioDb.Add(command, "@id", profileId), ct)).FirstOrDefault();
        if (profile?.LongOrNull("projectId") != projectId) throw new InvalidOperationException("Production profile does not belong to the requested project");
        return await _db.ExecuteAsync(@"INSERT INTO project_production_profile_bindings(project_id,production_profile_id,bound_by,bound_at)
            VALUES(@project,@profile,@actor,NOW(3))
            ON DUPLICATE KEY UPDATE production_profile_id=VALUES(production_profile_id),bound_by=VALUES(bound_by),bound_at=NOW(3)", command =>
        {
            StudioDb.Add(command, "@project", projectId);
            StudioDb.Add(command, "@profile", profileId);
            StudioDb.Add(command, "@actor", NormalizeActor(actor));
        }, ct);
    }

    public Task<List<Dictionary<string, object?>>> EntityVersionsAsync(long projectId, string? entityType, long? entityId, CancellationToken ct = default)
        => _db.QueryAsync(@"SELECT * FROM entity_versions
            WHERE project_id=@project AND (@type IS NULL OR entity_type=@type) AND (@entity IS NULL OR entity_id=@entity)
            ORDER BY entity_type,entity_id,version DESC", command =>
        {
            StudioDb.Add(command, "@project", projectId);
            StudioDb.Add(command, "@type", string.IsNullOrWhiteSpace(entityType) ? null : NormalizeEntityType(entityType));
            StudioDb.Add(command, "@entity", entityId);
        }, ct);

    public async Task<long> CaptureEntityVersionAsync(EntityVersionCaptureInput input, CancellationToken ct = default)
    {
        var type = NormalizeEntityType(input.EntityType);
        await RequireProjectAsync(input.ProjectId, ct);
        await RequireAssetOwnershipAsync(input.ProjectId, input.SourceAssetIds, ct);
        var source = await LoadEntitySnapshotAsync(input.ProjectId, type, input.EntityId, ct)
            ?? throw new InvalidOperationException($"{type} source entity does not exist or belongs to another project");
        var payload = CanonicalJson.Serialize(source);
        var hash = CanonicalJson.Sha256(payload);
        var assetJson = JsonSerializer.Serialize(input.SourceAssetIds.Distinct().Order().ToArray());

        var existing = await _db.ScalarAsync(@"SELECT id FROM entity_versions
            WHERE entity_type=@type AND entity_id=@entity AND payload_sha256=@hash LIMIT 1", command =>
        {
            StudioDb.Add(command, "@type", type);
            StudioDb.Add(command, "@entity", input.EntityId);
            StudioDb.Add(command, "@hash", hash);
        }, ct);
        if (existing is not null and not DBNull) return Convert.ToInt64(existing, CultureInfo.InvariantCulture);

        return await InsertWithVersionRetryAsync(async () => await _db.ExecuteInsertAsync(@"
            INSERT INTO entity_versions(project_id,entity_type,entity_id,version,payload_json,source_asset_ids_json,payload_sha256,note,created_by)
            SELECT @project,@type,@entity,COALESCE(MAX(version),0)+1,@payload,@assets,@hash,@note,@actor
            FROM entity_versions WHERE entity_type=@type AND entity_id=@entity", command =>
        {
            StudioDb.Add(command, "@project", input.ProjectId);
            StudioDb.Add(command, "@type", type);
            StudioDb.Add(command, "@entity", input.EntityId);
            StudioDb.Add(command, "@payload", payload);
            StudioDb.Add(command, "@assets", assetJson);
            StudioDb.Add(command, "@hash", hash);
            StudioDb.Add(command, "@note", input.Note);
            StudioDb.Add(command, "@actor", NormalizeActor(input.CreatedBy));
        }, ct), async () => await FindEntityVersionByHashAsync(type, input.EntityId, hash, ct));
    }

    public Task<List<Dictionary<string, object?>>> ShotPlansAsync(long shotId, CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM shot_plans WHERE shot_id=@shot ORDER BY version DESC", command => StudioDb.Add(command, "@shot", shotId), ct);

    public async Task<long> CreateShotPlanAsync(ShotPlanInput input, CancellationToken ct = default)
    {
        var shot = (await _db.QueryAsync(@"SELECT s.project_id,s.episode_id FROM shots s
            JOIN episodes e ON e.id=s.episode_id AND e.project_id=s.project_id
            WHERE s.id=@shot", command => StudioDb.Add(command, "@shot", input.ShotId), ct)).FirstOrDefault();
        if (shot is null || shot.LongOrNull("projectId") != input.ProjectId || shot.LongOrNull("episodeId") != input.EpisodeId)
            throw new InvalidOperationException("Shot, Episode and Project ownership do not match");
        var profileProject = await _db.ScalarAsync("SELECT project_id FROM production_profiles WHERE id=@id", command => StudioDb.Add(command, "@id", input.ProductionProfileId), ct);
        if (profileProject is null || Convert.ToInt64(profileProject, CultureInfo.InvariantCulture) != input.ProjectId)
            throw new InvalidOperationException("Production profile does not belong to the shot project");

        var requiredVersions = input.CharacterVersionIds
            .Concat(new long?[] { input.SceneVersionId, input.PromptVersionId, input.WorkflowVersionId, input.VoiceVersionId }.Where(value => value is > 0).Select(value => value!.Value))
            .Distinct()
            .ToArray();
        var versions = await LoadVersionHeadersAsync(requiredVersions, ct);
        RequireVersionSet(input, versions);
        await RequireAssetOwnershipAsync(input.ProjectId, input.InputAssetIds, ct);

        var parameters = input.Parameters is { } parameterElement ? CanonicalJson.Serialize(parameterElement) : "{}";
        using var parametersDocument = JsonDocument.Parse(parameters);
        var content = CanonicalJson.Serialize(new
        {
            input.ProjectId,
            input.EpisodeId,
            input.ShotId,
            input.ProductionProfileId,
            characterVersionIds = input.CharacterVersionIds.Distinct().Order().ToArray(),
            input.SceneVersionId,
            input.PromptVersionId,
            input.WorkflowVersionId,
            input.VoiceVersionId,
            inputAssetIds = input.InputAssetIds.Distinct().Order().ToArray(),
            parameters = parametersDocument.RootElement.Clone()
        });
        var hash = CanonicalJson.Sha256(content);
        var existing = await _db.ScalarAsync("SELECT id FROM shot_plans WHERE shot_id=@shot AND content_sha256=@hash LIMIT 1", command =>
        {
            StudioDb.Add(command, "@shot", input.ShotId);
            StudioDb.Add(command, "@hash", hash);
        }, ct);
        if (existing is not null and not DBNull) return Convert.ToInt64(existing, CultureInfo.InvariantCulture);

        return await InsertWithVersionRetryAsync(async () => await _db.ExecuteInsertAsync(@"
            INSERT INTO shot_plans(project_id,episode_id,shot_id,version,production_profile_id,character_version_ids_json,scene_version_id,prompt_version_id,workflow_version_id,voice_version_id,input_asset_ids_json,parameters_json,content_sha256,created_by)
            SELECT @project,@episode,@shot,COALESCE(MAX(version),0)+1,@profile,@characters,@scene,@prompt,@workflow,@voice,@assets,@parameters,@hash,@actor
            FROM shot_plans WHERE shot_id=@shot", command =>
        {
            StudioDb.Add(command, "@project", input.ProjectId);
            StudioDb.Add(command, "@episode", input.EpisodeId);
            StudioDb.Add(command, "@shot", input.ShotId);
            StudioDb.Add(command, "@profile", input.ProductionProfileId);
            StudioDb.Add(command, "@characters", JsonSerializer.Serialize(input.CharacterVersionIds.Distinct().Order().ToArray()));
            StudioDb.Add(command, "@scene", input.SceneVersionId);
            StudioDb.Add(command, "@prompt", input.PromptVersionId);
            StudioDb.Add(command, "@workflow", input.WorkflowVersionId);
            StudioDb.Add(command, "@voice", input.VoiceVersionId);
            StudioDb.Add(command, "@assets", JsonSerializer.Serialize(input.InputAssetIds.Distinct().Order().ToArray()));
            StudioDb.Add(command, "@parameters", parameters);
            StudioDb.Add(command, "@hash", hash);
            StudioDb.Add(command, "@actor", NormalizeActor(input.CreatedBy));
        }, ct), async () => await FindShotPlanByHashAsync(input.ShotId, hash, ct));
    }

    private async Task RequireProjectAsync(long projectId, CancellationToken ct)
    {
        var count = await _db.ScalarAsync("SELECT COUNT(*) FROM projects WHERE id=@id", command => StudioDb.Add(command, "@id", projectId), ct);
        if (Convert.ToInt32(count ?? 0, CultureInfo.InvariantCulture) != 1) throw new InvalidOperationException("Project does not exist");
    }

    private async Task RequireAssetOwnershipAsync(long projectId, IEnumerable<long> ids, CancellationToken ct)
    {
        var distinct = ids.Where(id => id > 0).Distinct().ToArray();
        if (distinct.Length == 0) return;
        var rows = await QueryByIdsAsync("SELECT id,project_id,status,manifest_id FROM assets WHERE id IN ({0})", distinct, ct);
        if (rows.Count != distinct.Length || rows.Any(row => row.LongOrNull("projectId") != projectId || !string.Equals(row.Text("status"), "Ready", StringComparison.OrdinalIgnoreCase) || row.LongOrNull("manifestId") is null))
            throw new InvalidOperationException("Every formal input asset must be Ready, manifest-backed and owned by the requested project");
    }

    private async Task<Dictionary<string, object?>?> LoadEntitySnapshotAsync(long projectId, string type, long entityId, CancellationToken ct)
    {
        var sql = type switch
        {
            "Character" => "SELECT * FROM characters WHERE id=@id AND project_id=@project",
            "Scene" => "SELECT * FROM scenes WHERE id=@id AND project_id=@project",
            "Prompt" => "SELECT id,project_id,episode_id,prompt,negative_prompt,character_prompt,scene_prompt,action_prompt,camera_prompt,lighting_prompt,style_prompt,quality_prompt,prompt_version,prompt_locked,prompt_source_language FROM shots WHERE id=@id AND project_id=@project",
            "Workflow" => "SELECT w.*,@project AS project_id FROM workflows w WHERE w.id=@id AND w.enabled=1",
            "Voice" => "SELECT id,project_id,name,voice_id,voice_speed,voice_pitch FROM characters WHERE id=@id AND project_id=@project",
            _ => throw new InvalidOperationException("Unsupported entity type")
        };
        return (await _db.QueryAsync(sql, command =>
        {
            StudioDb.Add(command, "@id", entityId);
            StudioDb.Add(command, "@project", projectId);
        }, ct)).FirstOrDefault();
    }

    private async Task<List<Dictionary<string, object?>>> LoadVersionHeadersAsync(long[] ids, CancellationToken ct)
        => ids.Length == 0 ? [] : await QueryByIdsAsync("SELECT id,project_id,entity_type,entity_id,version FROM entity_versions WHERE id IN ({0})", ids, ct);

    private static void RequireVersionSet(ShotPlanInput input, IReadOnlyList<Dictionary<string, object?>> rows)
    {
        var map = rows.ToDictionary(row => row.Long("id"));
        void Require(long? id, string type, bool optional = false)
        {
            if (id is null or <= 0)
            {
                if (optional) return;
                throw new InvalidOperationException($"{type} version is required");
            }
            if (!map.TryGetValue(id.Value, out var row) || row.LongOrNull("projectId") != input.ProjectId || !string.Equals(row.Text("entityType"), type, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException($"{type} version {id} is missing or belongs to another project/type");
        }
        foreach (var id in input.CharacterVersionIds) Require(id, "Character");
        Require(input.SceneVersionId, "Scene", true);
        Require(input.PromptVersionId, "Prompt");
        Require(input.WorkflowVersionId, "Workflow");
        Require(input.VoiceVersionId, "Voice", true);
    }

    private async Task<List<Dictionary<string, object?>>> QueryByIdsAsync(string sqlTemplate, long[] ids, CancellationToken ct)
    {
        var placeholders = ids.Select((_, index) => $"@id{index}").ToArray();
        return await _db.QueryAsync(string.Format(CultureInfo.InvariantCulture, sqlTemplate, string.Join(',', placeholders)), command =>
        {
            for (var index = 0; index < ids.Length; index++) StudioDb.Add(command, placeholders[index], ids[index]);
        }, ct);
    }

    private static async Task<long> InsertWithVersionRetryAsync(Func<Task<long>> insert, Func<Task<long?>> findExisting)
    {
        for (var attempt = 0; attempt < 3; attempt++)
        {
            try { return await insert(); }
            catch (MySqlException ex) when (ex.Number == 1062)
            {
                if (await findExisting() is { } existing) return existing;
                if (attempt == 2) throw;
                await Task.Delay(20 * (attempt + 1));
            }
        }
        throw new InvalidOperationException("Unable to allocate an immutable version");
    }

    private async Task<long?> FindProfileByHashAsync(long projectId, string key, string hash, CancellationToken ct)
        => ToNullableLong(await _db.ScalarAsync("SELECT id FROM production_profiles WHERE project_id=@project AND profile_key=@key AND content_sha256=@hash LIMIT 1", command =>
        {
            StudioDb.Add(command, "@project", projectId); StudioDb.Add(command, "@key", key); StudioDb.Add(command, "@hash", hash);
        }, ct));

    private async Task<long?> FindEntityVersionByHashAsync(string type, long entityId, string hash, CancellationToken ct)
        => ToNullableLong(await _db.ScalarAsync("SELECT id FROM entity_versions WHERE entity_type=@type AND entity_id=@entity AND payload_sha256=@hash LIMIT 1", command =>
        {
            StudioDb.Add(command, "@type", type); StudioDb.Add(command, "@entity", entityId); StudioDb.Add(command, "@hash", hash);
        }, ct));

    private async Task<long?> FindShotPlanByHashAsync(long shotId, string hash, CancellationToken ct)
        => ToNullableLong(await _db.ScalarAsync("SELECT id FROM shot_plans WHERE shot_id=@shot AND content_sha256=@hash LIMIT 1", command =>
        {
            StudioDb.Add(command, "@shot", shotId); StudioDb.Add(command, "@hash", hash);
        }, ct));

    private static long? ToNullableLong(object? value)
        => value is null or DBNull ? null : Convert.ToInt64(value, CultureInfo.InvariantCulture);

    private static string NormalizeEntityType(string value)
    {
        var match = EntityTypes.FirstOrDefault(type => string.Equals(type, value?.Trim(), StringComparison.OrdinalIgnoreCase));
        return match ?? throw new ArgumentException("EntityType must be Character, Scene, Prompt, Workflow or Voice", nameof(value));
    }

    private static string NormalizeKey(string? value, string fallback)
    {
        var normalized = string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
        if (normalized.Length > 128 || normalized.Any(character => !(char.IsLetterOrDigit(character) || character is '-' or '_' or '.')))
            throw new ArgumentException("Version key contains unsupported characters", nameof(value));
        return normalized;
    }

    private static string NormalizeActor(string? actor)
        => string.IsNullOrWhiteSpace(actor) ? "system" : actor.Trim()[..Math.Min(actor.Trim().Length, 128)];
}
