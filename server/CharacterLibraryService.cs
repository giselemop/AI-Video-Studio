using System.Text.Json;
using System.Text.Json.Nodes;
using System.Globalization;
using System.Text.Json.Serialization;
using MySqlConnector;

namespace VideoStudio.Server;

public sealed class LibraryVersionInput
{
    public string Label { get; set; } = "日常造型";
    public string Outfit { get; set; } = "";
    public string Profile { get; set; } = "baseline480";
    public long WorkflowId { get; set; }
    public List<LibraryReferenceInput> References { get; set; } = [];
    public string? Note { get; set; }
    public string? ReferencePack { get; set; }
    public string? BodyDescription { get; set; }
    public bool FreezeProvenance { get; set; }
    public bool RequireReviewed { get; set; }
}

public sealed record LibraryReferenceInput(long ReferenceId, string View, string? Framing = null);
public sealed record LibraryReference(long ReferenceId, string View, string AssetPath, string Sha256, int AssetVersion, string ReviewStatus,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Framing = null);
public sealed record LibraryWorkflow(long Id, string FileName, string Sha256, string Profile);
public sealed record LibraryVoice(string? Id, decimal Speed, decimal Pitch);
public sealed record LibraryFrozenSource(long ReferenceId, string ReferenceMetadataJson, long? TaskId, string? TaskInputJson);
public sealed record LibraryFacts(string? AgeSetting, string? Shoes, string? ImmutableTraits, IReadOnlyList<LibraryFrozenSource> Sources);
public sealed record LibraryPayload(string Schema, long CharacterId, string CharacterName, string Label, string Outfit,
    string FixedPrompt, string? NegativePrompt, string? FaceFeatures, string? Hair, string? BodyRatio,
    LibraryVoice Voice, LibraryWorkflow Workflow, IReadOnlyList<LibraryReference> References, string ContentReview,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? ReferencePack = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? ViewConvention = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] LibraryFacts? Facts = null);
public sealed record LibraryVersion(long Id, int Version, long OwnerProjectId, string Sha256, LibraryPayload Payload, object? CreatedAt);

public sealed class LibraryGenerateInput
{
    public long ProjectId { get; set; }
    public long VersionId { get; set; }
    public string View { get; set; } = "front";
    public string? Framing { get; set; }
    public string Prompt { get; set; } = "";
    public long Seed { get; set; } = 2026102601;
    public string IdempotencyKey { get; set; } = "";
}

public sealed record LibraryBinding(string Schema, long VersionId, int Version, long CharacterId, string VersionSha256,
    string View, long ReferenceId, string ReferenceAssetPath, string ReferenceSha256, int ReferenceVersion,
    long WorkflowId, string WorkflowSha256, string ScenePrompt, string Mode,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Framing = null);
public sealed record LibraryResolution(LibraryVersion Version, LibraryBinding Binding, string ResolvedPrompt, TaskInput Task);
public sealed record LibraryReferenceSlot(string View, string Framing);
public sealed record LibraryCoverage(int Present, int Expected, bool Complete, IReadOnlyList<LibraryReferenceSlot> Missing);

/// <summary>
/// Character library versions use the existing append-only entity_versions table.
/// A version is a complete snapshot, never a pointer to mutable character fields.
/// This first route is explicitly experimental and never grants production approval.
/// </summary>
public sealed class CharacterLibraryService
{
    public const string Schema = "character-library-v1";
    public const string CurrentSchema = "character-library-v2";
    public const string BasicPack = "basic-nine-v1";
    public const string ViewConvention = "image-facing-v1";
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    public static readonly string[] LegacyViews = ["front", "left", "right", "threeQuarterLeft", "threeQuarterRight", "fullBody", "back"];
    public static readonly string[] Views = ["front", "threeQuarterLeft", "left", "threeQuarterBackLeft", "back", "threeQuarterBackRight", "right", "threeQuarterRight"];
    public static readonly string[] Framings = ["closeUp", "medium", "fullBody"];
    public static readonly LibraryReferenceSlot[] BasicSlots =
    [
        new("front", "closeUp"), new("threeQuarterLeft", "closeUp"), new("threeQuarterRight", "closeUp"),
        new("front", "fullBody"), new("threeQuarterLeft", "fullBody"), new("left", "fullBody"),
        new("back", "fullBody"), new("right", "fullBody"), new("threeQuarterRight", "fullBody")
    ];
    private readonly StudioDb _db;
    private readonly StudioRepository _repository;
    private readonly AssetPathPolicy _paths;
    private readonly FfmpegService _ffmpeg;

    public CharacterLibraryService(StudioDb db, StudioRepository repository, AssetPathPolicy paths, FfmpegService ffmpeg)
    { _db = db; _repository = repository; _paths = paths; _ffmpeg = ffmpeg; }

    public Task<List<Dictionary<string, object?>>> RowsAsync(long? characterId = null, CancellationToken ct = default)
        => _db.QueryAsync(@"SELECT id,project_id,entity_id,version,payload_json,payload_sha256,created_at FROM entity_versions
            WHERE entity_type='Character' AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.schema')) IN (@schema,@current)
            AND (@character IS NULL OR entity_id=@character) ORDER BY entity_id,version DESC", c =>
            { StudioDb.Add(c, "@schema", Schema); StudioDb.Add(c, "@current", CurrentSchema); StudioDb.Add(c, "@character", characterId); }, ct);

    public async Task<IReadOnlyList<LibraryVersion>> ListAsync(CancellationToken ct = default)
        => (await RowsAsync(ct: ct)).Select(Read).ToArray();

    public async Task<bool> HasVersionsAsync(long characterId, CancellationToken ct = default)
        => (await RowsAsync(characterId, ct)).Count > 0;

    public Task<int> DeleteUnversionedCharacterAsync(long characterId, CancellationToken ct = default)
        => _db.InTransactionAsync(async (connection, transaction) =>
        {
            // Use the same row lock as CaptureAsync: delete/capture races cannot
            // remove the source reference records of a newly captured version.
            await using var source = new MySqlCommand("SELECT id FROM characters WHERE id=@id FOR UPDATE", connection, transaction);
            StudioDb.Add(source, "@id", characterId);
            if (await source.ExecuteScalarAsync(ct) is null) return 0;
            await using var versions = new MySqlCommand(@"SELECT COUNT(*) FROM entity_versions WHERE entity_type='Character'
                AND entity_id=@id AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.schema')) IN (@schema,@current)", connection, transaction);
            StudioDb.Add(versions, "@id", characterId); StudioDb.Add(versions, "@schema", Schema); StudioDb.Add(versions, "@current", CurrentSchema);
            if (Convert.ToInt32(await versions.ExecuteScalarAsync(ct)) > 0)
                throw new AssetValidationException("人物已有不可变库版本，请保留源角色；可编辑档案后保存新版本");
            await using var delete = new MySqlCommand("DELETE FROM characters WHERE id=@id", connection, transaction);
            StudioDb.Add(delete, "@id", characterId);
            return await delete.ExecuteNonQueryAsync(ct);
        }, ct);

    public Task<List<Dictionary<string, object?>>> HistoryAsync(CancellationToken ct = default)
        => _db.QueryAsync(@"SELECT t.id,t.project_id,t.status,t.progress,t.created_at,t.error_message,
            JSON_EXTRACT(t.input_json,'$.parameters.characterLibrary.versionId') AS version_id,
            JSON_UNQUOTE(JSON_EXTRACT(v.payload_json,'$.characterName')) AS character_name,
            JSON_UNQUOTE(JSON_EXTRACT(t.input_json,'$.parameters.characterLibrary.view')) AS view,
            JSON_UNQUOTE(JSON_EXTRACT(t.input_json,'$.parameters.characterLibrary.framing')) AS framing
            FROM generation_tasks t JOIN entity_versions v ON v.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(t.input_json,'$.parameters.characterLibrary.versionId')) AS UNSIGNED)
            WHERE JSON_UNQUOTE(JSON_EXTRACT(t.input_json,'$.parameters.characterLibrary.schema')) IN (@schema,@current)
            ORDER BY t.id DESC LIMIT 80", c => { StudioDb.Add(c, "@schema", Schema); StudioDb.Add(c, "@current", CurrentSchema); }, ct);

    public async Task<LibraryVersion> GetAsync(long id, CancellationToken ct = default)
    {
        var row = (await _db.QueryAsync(@"SELECT id,project_id,entity_id,version,payload_json,payload_sha256,created_at
            FROM entity_versions WHERE id=@id AND entity_type='Character'
            AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.schema')) IN (@schema,@current)", c =>
            { StudioDb.Add(c, "@id", id); StudioDb.Add(c, "@schema", Schema); StudioDb.Add(c, "@current", CurrentSchema); }, ct)).FirstOrDefault();
        return row is null ? throw new ArgumentException("人物库版本不存在，请明确选择库中的版本") : Read(row);
    }

    private static LibraryVersion Read(Dictionary<string, object?> row)
    {
        using var document = JsonDocument.Parse(row.Text("payloadJson") ?? "{}");
        var canonical = CanonicalPayload(document.RootElement);
        var actualHash = CanonicalJson.Sha256(canonical);
        if (!string.Equals(actualHash, row.Text("payloadSha256"), StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("人物库版本内容与冻结哈希不符");
        var payload = document.RootElement.Deserialize<LibraryPayload>(Json)
            ?? throw new AssetValidationException("人物库版本内容无效");
        if (payload.Schema is not (Schema or CurrentSchema) || payload.CharacterId != row.Long("entityId"))
            throw new AssetValidationException("人物库版本身份绑定无效");
        return new(row.Long("id"), row.Int("version"), row.Long("projectId"), actualHash, payload, row.GetValueOrDefault("createdAt"));
    }

    // MySQL JSON rewrites 1.00 to 1.0. Voice fields originate in DECIMAL(5,2),
    // so restore that exact numeric scale before hashing, without changing values.
    public static string CanonicalPayload(JsonElement payload)
    {
        var node = JsonNode.Parse(payload.GetRawText())!.AsObject();
        foreach (var name in new[] { "speed", "pitch" })
        {
            var value = payload.GetProperty("voice").GetProperty(name).GetDecimal();
            if (decimal.Round(value, 2) != value) throw new AssetValidationException("人物声音参数超出已支持的两位小数精度");
            node["voice"]![name] = decimal.Parse(value.ToString("F2", CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
        }
        return CanonicalJson.Serialize(node);
    }

    public static string EffectiveFraming(LibraryReference reference)
        => reference.Framing ?? (reference.View == "fullBody" ? "fullBody" : "medium");

    public static LibraryCoverage Coverage(IEnumerable<LibraryReference> references)
    {
        var available = references.Select(r => new LibraryReferenceSlot(r.View, EffectiveFraming(r))).ToHashSet();
        var missing = BasicSlots.Where(slot => !available.Contains(slot)).ToArray();
        return new(BasicSlots.Length - missing.Length, BasicSlots.Length, missing.Length == 0, missing);
    }

    public static bool ValidateReferenceSlots(LibraryVersionInput input)
    {
        if (input.References is null || input.References.Any(r => r is null)) throw new ArgumentException("请选择有效的人物参考图");
        var modern = input.ReferencePack is not null || input.References.Any(r => r.Framing is not null);
        if (input.ReferencePack is not (null or BasicPack)) throw new ArgumentException("参考包类型无效");
        if (input.References.Count < 1 || input.References.Count > (modern ? 24 : 7)) throw new ArgumentException("参考图数量无效，新版每个造型最多24张");
        if (input.References.Any(r => !(modern ? Views : LegacyViews).Contains(r.View, StringComparer.Ordinal))) throw new ArgumentException("参考视角无效");
        if (modern && input.References.Any(r => !Framings.Contains(r.Framing, StringComparer.Ordinal))) throw new ArgumentException("请为每张图片明确选择近景、半身或全身景别");
        if (input.References.Select(r => (r.View, r.Framing)).Distinct().Count() != input.References.Count)
            throw new ArgumentException("同一视角与景别只能绑定一张参考图；正面近景和正面全身可分别保存");
        if (input.ReferencePack == BasicPack && BasicSlots.Any(slot => !input.References.Any(r => r.View == slot.View && r.Framing == slot.Framing)))
            throw new ArgumentException("基础9图参考包尚不齐全，需要3张面部近景及6张全身图");
        return modern;
    }

    public static LibraryReference SelectReference(LibraryVersion version, string view, string? framing)
    {
        if (version.Payload.Schema == CurrentSchema && !Framings.Contains(framing, StringComparer.Ordinal))
            throw new ArgumentException("请选择明确的景别，系统不会自动在近景与全身之间换图");
        return version.Payload.References.SingleOrDefault(r => r.View == view && (framing is null || EffectiveFraming(r) == framing))
            ?? throw new ArgumentException("此版本没有所选视角与景别，请补图并保存新版本；不会自动换图");
    }

    private static LibraryBinding MakeBinding(LibraryVersion version, LibraryReference reference, string scenePrompt)
        => new(version.Payload.Schema, version.Id, version.Version, version.Payload.CharacterId, version.Sha256,
            reference.View, reference.ReferenceId, reference.AssetPath, reference.Sha256, reference.AssetVersion,
            version.Payload.Workflow.Id, version.Payload.Workflow.Sha256, scenePrompt, "Experimental", reference.Framing);

    public async Task<LibraryVersion> CaptureAsync(long characterId, LibraryVersionInput input, string actor, CancellationToken ct = default)
    {
        input.Outfit ??= "";
        var modern = ValidateReferenceSlots(input);
        if (input.FreezeProvenance && !modern) throw new ArgumentException("保存完整来源快照时须明确每张图片的景别");
        if (TextEncodingGuard.FindError(input) is { } encodingError) throw new ArgumentException(encodingError);
        if (string.IsNullOrWhiteSpace(input.Label) || input.Label.Length > 100 || input.Outfit.Length > 2000 || input.Note?.Length > 500)
            throw new ArgumentException("造型名称须为1–100字，造型说明最多2000字，备注最多500字");
        if (input.BodyDescription?.Length > 2000) throw new ArgumentException("体型与比例说明最多2000字");
        if (input.Profile is not ("baseline480" or "quality768"))
            throw new ArgumentException("人物库首版支持明确选择480p或768p本地试用路线");
        var workflow = (await _db.QueryAsync("SELECT * FROM workflows WHERE id=@id", c => StudioDb.Add(c, "@id", input.WorkflowId), ct)).FirstOrDefault()
            ?? throw new ArgumentException("请选择已登记的视频工作流");
        var profile = MiniMaxLocalService.ResolveProfile(input.Profile);
        if (!string.Equals(Path.GetFileName(workflow.Text("path")), profile.WorkflowFileName, StringComparison.OrdinalIgnoreCase)
            || !_paths.TryResolveExistingWorkflow(workflow.Text("path"), out var workflowPath, out _))
            throw new ArgumentException("所选工作流与明确指定的本地视频规格不匹配");
        var workflowHash = await _ffmpeg.Sha256Async(workflowPath, ct) ?? throw new AssetValidationException("工作流文件缺失");

        // Serialize version allocation with mutable character edits and concurrent captures.
        await using var connection = await _db.OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(ct);
        try
        {
            Dictionary<string, object?> character;
            await using (var command = new MySqlCommand("SELECT * FROM characters WHERE id=@id FOR UPDATE", connection, transaction))
            {
                StudioDb.Add(command, "@id", characterId);
                await using var reader = await command.ExecuteReaderAsync(ct);
                if (!await reader.ReadAsync(ct)) throw new ArgumentException("角色不存在，请先创建角色并上传参考图");
                character = new(StringComparer.OrdinalIgnoreCase);
                for (var i = 0; i < reader.FieldCount; i++)
                    character[string.Join("", reader.GetName(i).Split('_').Select((part, index) => index == 0 ? part : char.ToUpperInvariant(part[0]) + part[1..]))] = reader.IsDBNull(i) ? null : reader.GetValue(i);
            }
            var projectId = character.LongOrNull("projectId") ?? throw new ArgumentException("请先为角色选择归属项目；入库后可跨项目复用");
            if (!string.IsNullOrWhiteSpace(character.Text("embeddingPath")) || !string.IsNullOrWhiteSpace(character.Text("loraPath")))
                throw new ArgumentException("当前H3人物库路线未支持角色Embedding或LoRA，请使用经过对应工作流验证的独立版本");
            var references = new List<LibraryReference>();
            var frozenSources = new List<LibraryFrozenSource>();
            foreach (var selected in input.References.OrderBy(r => r.View, StringComparer.Ordinal).ThenBy(r => r.Framing, StringComparer.Ordinal))
            {
                var source = (await _repository.CharacterReferencesAsync(characterId, ct)).FirstOrDefault(r => r.Long("id") == selected.ReferenceId)
                    ?? throw new ArgumentException("参考图不属于当前人物");
                var metadata = ReferenceMetadata.Read(source.Text("metadataJson"));
                if (metadata.ReviewStatus == "Rejected") throw new ArgumentException("被拒绝的参考图不能入库");
                if (input.RequireReviewed && metadata.ReviewStatus != "Approved") throw new ArgumentException("仍有参考图待人工审核，可先保存待审版本或完成审核后再保存已审来源版本");
                if (!_paths.TryResolveExisting(source.Text("path"), out var imagePath, out var relative))
                    throw new AssetValidationException("参考图不存在或不在受控素材目录");
                var hash = await _ffmpeg.Sha256Async(imagePath, ct);
                if (metadata.AssetVersion <= 0 || !string.Equals(hash, metadata.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new AssetValidationException("参考图已变化或缺少版本，请重新登记参考图");
                var probe = await _ffmpeg.ProbeAsync(imagePath, ct);
                if (probe is null || probe.Width < 256 || probe.Height < 256 || Path.GetExtension(imagePath).ToLowerInvariant() is not (".png" or ".jpg" or ".jpeg" or ".webp"))
                    throw new AssetValidationException("人物参考须为可解码且至少256像素的图片");
                references.Add(new(selected.ReferenceId, selected.View, relative, hash!, metadata.AssetVersion, metadata.ReviewStatus, modern ? selected.Framing : null));
                if(input.FreezeProvenance)
                {
                    var origin=(await _db.QueryAsync(@"SELECT t.id,t.input_json FROM generation_tasks t JOIN generation_results r ON r.task_id=t.id JOIN assets a ON a.id=r.asset_id
                        WHERE a.sha256=@sha AND t.status='Succeeded' ORDER BY t.id LIMIT 1",c=>StudioDb.Add(c,"@sha",hash),ct)).FirstOrDefault();
                    frozenSources.Add(new(selected.ReferenceId,source.Text("metadataJson")??"{}",origin?.LongOrNull("id"),origin?.Text("inputJson")));
                }
            }
            var sourceMetadata=JsonNode.Parse(character.Text("metadataJson")??"{}");
            if(input.FreezeProvenance)
            {
                foreach(var field in new[]{"name","faceFeatures","hair","bodyRatio","clothes","fixedPrompt"})CharacterStoryStore.Required(character.Text(field),field);
                CharacterStoryStore.Required(input.Outfit,"本造型的完整服装");
                CharacterStoryStore.Required(character.Text("ageSetting"),"年龄设定");
                CharacterStoryStore.Required(sourceMetadata?["referenceStudio"]?["shoes"]?.GetValue<string>(),"鞋子");
                CharacterStoryStore.Required(sourceMetadata?["referenceStudio"]?["immutableTraits"]?.GetValue<string>(),"禁改特征");
            }
            var facts=input.FreezeProvenance ? new LibraryFacts(character.Text("ageSetting"),sourceMetadata?["referenceStudio"]?["shoes"]?.GetValue<string>(),sourceMetadata?["referenceStudio"]?["immutableTraits"]?.GetValue<string>(),frozenSources) : null;
            var payload = new LibraryPayload(modern ? CurrentSchema : Schema, characterId, character.Text("name") ?? "", input.Label.Trim(), input.Outfit.Trim(),
                character.Text("fixedPrompt") ?? "", character.Text("negativePrompt"), character.Text("faceFeatures"),
                character.Text("hair"), modern && !string.IsNullOrWhiteSpace(input.BodyDescription) ? input.BodyDescription.Trim() : character.Text("bodyRatio"),
                new(character.Text("voiceId"), character.Decimal("voiceSpeed", 1), character.Decimal("voicePitch", 0)),
                new(input.WorkflowId, profile.WorkflowFileName, workflowHash, profile.Id), references, "NeedReview",
                modern ? input.ReferencePack : null, modern ? ViewConvention : null, facts);
            if (string.IsNullOrWhiteSpace(payload.FixedPrompt)) throw new ArgumentException("请先填写人物固定提示词，以便每次调用复用外貌设定");
            var canonical = CanonicalPayload(JsonSerializer.SerializeToElement(payload, Json));
            var payloadHash = CanonicalJson.Sha256(canonical);
            long id;
            await using (var existing = new MySqlCommand("SELECT id FROM entity_versions WHERE entity_type='Character' AND entity_id=@character AND payload_sha256=@hash", connection, transaction))
            {
                StudioDb.Add(existing, "@character", characterId); StudioDb.Add(existing, "@hash", payloadHash);
                var found = await existing.ExecuteScalarAsync(ct);
                if (found is not null and not DBNull)
                {
                    id = Convert.ToInt64(found);
                    await transaction.CommitAsync(ct);
                    return await GetAsync(id, ct);
                }
            }
            await using (var insert = new MySqlCommand(@"INSERT INTO entity_versions(project_id,entity_type,entity_id,version,payload_json,source_asset_ids_json,payload_sha256,note,created_by)
                SELECT @project,'Character',@character,COALESCE(MAX(version),0)+1,@payload,'[]',@hash,@note,@actor
                FROM entity_versions WHERE entity_type='Character' AND entity_id=@character", connection, transaction))
            {
                StudioDb.Add(insert, "@project", projectId); StudioDb.Add(insert, "@character", characterId);
                StudioDb.Add(insert, "@payload", canonical); StudioDb.Add(insert, "@hash", payloadHash);
                StudioDb.Add(insert, "@note", input.Note); StudioDb.Add(insert, "@actor", actor);
                await insert.ExecuteNonQueryAsync(ct); id = insert.LastInsertedId;
            }
            await transaction.CommitAsync(ct);
            return await GetAsync(id, ct);
        }
        catch
        {
            // A read/serialization failure after commit must retain its original error.
            try { await transaction.RollbackAsync(CancellationToken.None); } catch (InvalidOperationException) { }
            throw;
        }
    }

    public async Task<LibraryResolution> ResolveAsync(LibraryGenerateInput input, CancellationToken ct = default)
    {
        if (input.ProjectId <= 0 || (await _repository.ProjectAsync(input.ProjectId, ct)).Count == 0)
            throw new ArgumentException("请选择有效的目标项目");
        if (string.IsNullOrWhiteSpace(input.Prompt) || input.Prompt.Length > 4000 || input.Seed < 0)
            throw new ArgumentException("请填写1–4000字的镜头动作描述，并使用非负种子");
        if (TextEncodingGuard.FindError(input) is { } error) throw new ArgumentException(error);
        var version = await GetAsync(input.VersionId, ct);
        await RequireNotRejectedAsync(version.Id, ct);
        var reference = SelectReference(version, input.View, input.Framing);
        var binding = MakeBinding(version, reference, input.Prompt.Trim());
        var prompt = ComposePrompt(version.Payload, binding.ScenePrompt);
        var task = MiniMaxLocalService.BuildTask(new MiniMaxLocalInput(input.ProjectId, prompt, reference.AssetPath,
            input.Seed, version.Payload.Workflow.Profile), version.Payload.Workflow.Id, "character-library:" + version.Id, input.IdempotencyKey);
        task.Stage = "Character-Library-Experiment";
        var parameters = JsonSerializer.SerializeToNode(task.Parameters!.Value)!.AsObject();
        parameters["characterLibrary"] = JsonSerializer.SerializeToNode(binding, Json);
        task.Parameters = JsonSerializer.SerializeToElement(parameters);
        await ValidateTaskAsync(task, ct);
        return new(version, binding, prompt, task);
    }

    public static string ComposePrompt(LibraryPayload payload, string scenePrompt)
        => string.Join("\n", new[] { payload.FixedPrompt.Trim(), string.IsNullOrWhiteSpace(payload.Outfit) ? null : "Wardrobe: " + payload.Outfit.Trim(),
            payload.Schema == CurrentSchema && !string.IsNullOrWhiteSpace(payload.BodyRatio) ? "Body proportions: " + payload.BodyRatio.Trim() : null,
            scenePrompt.Trim() }.Where(s => !string.IsNullOrWhiteSpace(s)));

    public async Task ValidateTaskAsync(TaskInput input, CancellationToken ct = default)
    {
        if (input.Parameters is not { ValueKind: JsonValueKind.Object } parameters || !parameters.TryGetProperty("characterLibrary", out var marker)) return;
        LibraryBinding binding;
        try { binding = marker.Deserialize<LibraryBinding>(Json) ?? throw new JsonException(); }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException or NotSupportedException)
        { throw new AssetValidationException("人物库调用快照无效"); }
        var version = await GetAsync(binding.VersionId, ct);
        await RequireNotRejectedAsync(version.Id, ct);
        var reference = SelectReference(version, binding.View, binding.Framing);
        var expected = MakeBinding(version, reference, binding.ScenePrompt);
        if (binding != expected || input.TaskType != "ImageToVideo" || input.WorkflowId != version.Payload.Workflow.Id
            || input.ShotId is not null || input.EpisodeId is not null || string.IsNullOrWhiteSpace(binding.ScenePrompt) || binding.ScenePrompt.Length > 4000)
            throw new AssetValidationException("人物库快照、人物、工作流或试用模式被改变");
        if (!_paths.TryResolveExisting(input.InputImagePath, out var firstFrame, out var firstRelative)
            || !string.Equals(firstRelative, reference.AssetPath, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(await _ffmpeg.Sha256Async(firstFrame, ct), reference.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("人物库首帧缺失、被替换或哈希已变化；任务未获准执行");
        var currentReference = (await _repository.CharacterReferencesAsync(binding.CharacterId, ct)).FirstOrDefault(r => r.Long("id") == binding.ReferenceId)
            ?? throw new AssetValidationException("人物库源参考记录已移除");
        var currentMetadata = ReferenceMetadata.Read(currentReference.Text("metadataJson"));
        if (currentMetadata.ReviewStatus == "Rejected" || currentMetadata.AssetVersion != reference.AssetVersion
            || !string.Equals(currentMetadata.Sha256, reference.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("人物库参考已被拒绝或版本发生变化");
        var workflow = (await _db.QueryAsync("SELECT * FROM workflows WHERE id=@id", c => StudioDb.Add(c, "@id", version.Payload.Workflow.Id), ct)).FirstOrDefault();
        if (workflow is null || !_paths.TryResolveExistingWorkflow(workflow.Text("path"), out var workflowPath, out _)
            || !string.Equals(Path.GetFileName(workflowPath), version.Payload.Workflow.FileName, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(await _ffmpeg.Sha256Async(workflowPath, ct), version.Payload.Workflow.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new AssetValidationException("人物库绑定的工作流已变化，请核查后保存新版本");
        if (!parameters.TryGetProperty("prompt", out var prompt) || prompt.GetString() != ComposePrompt(version.Payload, binding.ScenePrompt)
            || parameters.TryGetProperty("positive", out var positive) && positive.GetString() != prompt.GetString()
            || !parameters.TryGetProperty("contentReview", out var review) || review.GetString() != "NeedReview"
            || !parameters.TryGetProperty("qualityReferenceImagePath", out var qualityPath) || qualityPath.GetString() != reference.AssetPath)
            throw new AssetValidationException("人物固定设定、参考或审核状态被改变");
        MiniMaxLocalService.ValidateManagedParameters(parameters, workflowPath);
    }

    public async Task RequireNotRejectedAsync(long versionId,CancellationToken ct=default)
    {
        var row=(await _db.QueryAsync("SELECT payload_json FROM entity_versions WHERE entity_type='LibraryReview' AND entity_id=@id ORDER BY version DESC LIMIT 1",c=>StudioDb.Add(c,"@id",versionId),ct)).FirstOrDefault();
        if(row is not null && JsonNode.Parse(row.Text("payloadJson")??"{}")?["decision"]?.GetValue<string>()=="Rejected")
            throw new AssetValidationException("此人物库版本已被拒绝，请选择其他版本或保存修正版本");
    }
}
