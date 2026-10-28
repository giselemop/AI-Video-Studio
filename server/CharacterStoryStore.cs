using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using MySqlConnector;

namespace VideoStudio.Server;

public sealed record CharacterStoryRecord(long Id, long ProjectId, string Type, long EntityId, int Version, string Sha256, JsonObject Payload, object? CreatedAt);

/// <summary>Typed additions to the existing immutable ledger; no second Episode/Shot system.</summary>
public sealed class CharacterStoryStore(StudioDb db)
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly Dictionary<string,string> Parents = new(StringComparer.Ordinal)
    { ["ProjectCast"]="projects", ["EpisodeCast"]="episodes", ["ShotCast"]="shots", ["KeyframeReview"]="generation_tasks", ["LibraryReview"]="entity_versions", ["CharacterWorkflow"]="characters", ["Scene"]="scenes" };
    public static JsonObject Object(object value) => JsonSerializer.SerializeToNode(value,Json)!.AsObject();
    public static TaskInput RestoreTask(JsonElement input,IReadOnlyDictionary<string,object?> row)
    {
        var task=input.Deserialize<TaskInput>(Json)??throw new AssetValidationException("持久化任务输入无效");
        // CreateTaskAsync intentionally stores scheduling fields in columns,
        // not input_json. Rehydrate them before applying the business contract.
        task.ProjectId=row.LongOrNull("projectId");task.EpisodeId=row.LongOrNull("episodeId");task.ShotId=row.LongOrNull("shotId");task.ProductionRunId=row.LongOrNull("productionRunId");task.WorkflowId=row.LongOrNull("workflowId");
        task.TaskType=row.Text("taskType")??task.TaskType;task.ResourceClass=row.Text("resourceClass")??task.ResourceClass;task.MaxRetries=row.Int("maxRetries");task.Stage=row.Text("stage");task.DependencyTaskId=row.LongOrNull("dependencyTaskId");task.IdempotencyKey=row.Text("idempotencyKey");
        return task;
    }
    public static string Text(JsonNode? value, string key, string fallback="") => value?[key]?.GetValue<string>() ?? fallback;
    public static long Number(JsonNode? value, string key, long fallback=0) => value?[key]?.GetValue<long>() ?? fallback;
    public static string Required(string? value, string name, int max=2000)
    { if(string.IsNullOrWhiteSpace(value) || value.Length>max) throw new ArgumentException($"{name}不能为空且最多{max}字"); return value.Trim(); }
    public static string RequestKey(string? value)
    { value=Required(value,"请求标识",128); if(value.Length<8 || value.Any(char.IsControl)) throw new ArgumentException("请求标识须8–128字符，重试时复用"); return value; }
    public static bool Equal(JsonElement a, JsonElement b)
    {
        if(a.ValueKind==JsonValueKind.Number && b.ValueKind==JsonValueKind.Number)
        { if(a.TryGetInt64(out var x) && b.TryGetInt64(out var y)) return x==y; return Math.Abs(a.GetDouble()-b.GetDouble())<=1e-11*Math.Max(1,Math.Abs(a.GetDouble())); }
        if(a.ValueKind!=b.ValueKind) return false;
        if(a.ValueKind==JsonValueKind.Object)
        { var aa=a.EnumerateObject().ToArray(); var bb=b.EnumerateObject().ToArray(); return aa.Length==bb.Length && aa.All(p=>b.TryGetProperty(p.Name,out var v)&&Equal(p.Value,v)); }
        if(a.ValueKind==JsonValueKind.Array) { var aa=a.EnumerateArray().ToArray();var bb=b.EnumerateArray().ToArray();return aa.Length==bb.Length&&aa.Zip(bb).All(p=>Equal(p.First,p.Second)); }
        return a.ToString()==b.ToString();
    }
    public async Task<CharacterStoryRecord?> LatestAsync(string type,long entityId,CancellationToken ct=default)
        => (await RowsAsync(type,entityId,ct)).FirstOrDefault();
    public async Task<IReadOnlyList<CharacterStoryRecord>> RowsAsync(string type,long entityId,CancellationToken ct=default)
        => (await db.QueryAsync("SELECT * FROM entity_versions WHERE entity_type=@type AND entity_id=@entity ORDER BY version DESC",c=>{StudioDb.Add(c,"@type",type);StudioDb.Add(c,"@entity",entityId);},ct)).Select(Read).ToArray();
    public async Task<CharacterStoryRecord> GetAsync(long id,string type,CancellationToken ct=default)
    {
        var row=(await db.QueryAsync("SELECT * FROM entity_versions WHERE id=@id AND entity_type=@type",c=>{StudioDb.Add(c,"@id",id);StudioDb.Add(c,"@type",type);},ct)).FirstOrDefault();
        return row is null ? throw new ArgumentException("所选记录不存在或类型不符") : Read(row);
    }
    private static CharacterStoryRecord Read(Dictionary<string,object?> row)
    {
        var payload=JsonNode.Parse(row.Text("payloadJson")??"{}")!.AsObject();var hash=CanonicalJson.Sha256(CanonicalJson.Serialize(payload));
        if(hash!=row.Text("payloadSha256"))throw new AssetValidationException("不可变记录哈希不符");
        return new(row.Long("id"),row.Long("projectId"),row.Text("entityType")!,row.Long("entityId"),row.Int("version"),hash,payload,row.GetValueOrDefault("createdAt"));
    }
    public async Task<CharacterStoryRecord> AppendAsync(string type,long entityId,long projectId,JsonObject payload,string actor,CancellationToken ct=default)
    {
        if(!Parents.TryGetValue(type,out var table))throw new ArgumentException("记录类型无效");
        var key=RequestKey(Text(payload,"requestId"));var canonical=CanonicalJson.Serialize(payload);var hash=CanonicalJson.Sha256(canonical);
        await using var connection=await db.OpenAsync(ct);await using var tx=await connection.BeginTransactionAsync(ct);
        long id;
        try
        {
            await using(var parent=new MySqlCommand($"SELECT id FROM {table} WHERE id=@id FOR UPDATE",connection,tx))
            { StudioDb.Add(parent,"@id",entityId);if(await parent.ExecuteScalarAsync(ct) is null)throw new ArgumentException("归属记录不存在"); }
            await using(var existing=new MySqlCommand("SELECT id,payload_sha256 FROM entity_versions WHERE entity_type=@type AND entity_id=@entity AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.requestId'))=@key",connection,tx))
            {
                StudioDb.Add(existing,"@type",type);StudioDb.Add(existing,"@entity",entityId);StudioDb.Add(existing,"@key",key);
                await using var reader=await existing.ExecuteReaderAsync(ct);
                if(await reader.ReadAsync(ct))
                { id=reader.GetInt64(0);if(reader.GetString(1)!=hash)throw new IdempotencyConflictException("请求标识已绑定其他内容");await reader.DisposeAsync();await tx.CommitAsync(ct);return await GetAsync(id,type,ct); }
            }
            await using(var insert=new MySqlCommand(@"INSERT INTO entity_versions(project_id,entity_type,entity_id,version,payload_json,source_asset_ids_json,payload_sha256,note,created_by)
                SELECT @project,@type,@entity,COALESCE(MAX(version),0)+1,@payload,'[]',@hash,'Character reference and story workflow',@actor FROM entity_versions WHERE entity_type=@type AND entity_id=@entity",connection,tx))
            {
                StudioDb.Add(insert,"@project",projectId);StudioDb.Add(insert,"@type",type);StudioDb.Add(insert,"@entity",entityId);StudioDb.Add(insert,"@payload",canonical);StudioDb.Add(insert,"@hash",hash);StudioDb.Add(insert,"@actor",actor);
                await insert.ExecuteNonQueryAsync(ct);id=insert.LastInsertedId;
            }
            await tx.CommitAsync(ct);
        }
        catch {try{await tx.RollbackAsync(CancellationToken.None);}catch(InvalidOperationException){}throw;}
        return await GetAsync(id,type,ct);
    }
}

public sealed class StoryRoleInput { public string Role {get;set;}=""; public long VersionId {get;set;} }
public sealed class StoryCastInput { public List<StoryRoleInput> Roles {get;set;}=[]; public string AudioStrategy {get;set;}="PostDubbing"; public string IdempotencyKey {get;set;}=""; }
public sealed class StoryActorInput { public string Role {get;set;}=""; public string View {get;set;}="front"; public string Framing {get;set;}="closeUp"; public string Position {get;set;}="center"; public string Action {get;set;}=""; public long? LegacyHeadshotReferenceId {get;set;} }
public sealed class StoryShotInput
{
    public long EpisodeCastId {get;set;}
    public List<StoryActorInput> Actors {get;set;}=[];
    public string ShotFraming {get;set;}="medium";
    public string Scene {get;set;}="";
    public string Action {get;set;}="";
    public string Camera {get;set;}="Locked camera";
    public string Props {get;set;}="None";
    public bool KeyframeStartOnly {get;set;}
    public long? SceneVersionId {get;set;}
    public string IdempotencyKey {get;set;}="";
}
public sealed class StoryRenderInput
{
    public long PlanId {get;set;}
    public long KeyframeTaskId {get;set;}
    public long ReviewId {get;set;}
    public string Profile {get;set;}="baseline480";
    public long Seed {get;set;}=2026102701;
    public long? RepairOfTaskId {get;set;}
    public string? ChangeReason {get;set;}
    public string? PromptAdjustment {get;set;}
    public string IdempotencyKey {get;set;}="";
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public long? ContinuationSourceTaskId {get;set;}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public long? ContinuationReviewId {get;set;}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public string? ContinuationFramePath {get;set;}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public string? ContinuationFrameSha256 {get;set;}
}
public sealed class StoryReviewInput { public long TaskId {get;set;} public string Decision {get;set;}="NeedReview"; public string Scope {get;set;}="PreviewInspection"; public bool HumanConfirmed {get;set;} public string Note {get;set;}=""; public string IdempotencyKey {get;set;}=""; }
public sealed class StoryPreviewInput { public long EpisodeId {get;set;} public List<long> TaskIds {get;set;}=[]; public string? AudioPath {get;set;} public string IdempotencyKey {get;set;}=""; }
