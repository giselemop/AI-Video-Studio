using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

/// <summary>Fixed-camera composition snapshots reuse Scene and entity_versions.</summary>
public sealed class CharacterSceneService(StudioDb db,StudioRepository repository,CharacterStoryStore store,AssetPathPolicy paths,FfmpegService ffmpeg)
{
    public const string Schema="story-scene-v1";
    public const string WorkflowFile="character_scene_klein4b_five_locked_api.json";
    public const string WorkflowVersion="character-scene-klein4b-five-locked-1536-v1";
    public const string MaskedWorkflowFile="character_scene_klein4b_five_masked_locked_api.json";
    public const string MaskedWorkflowVersion="character-scene-klein4b-five-masked-locked-1536-v1";
    public static string WorkflowFor(JsonNode binding)=>CharacterStoryStore.Text(binding["payload"],"workflowVersion")==MaskedWorkflowVersion?MaskedWorkflowFile:WorkflowFile;
    public static string VersionFor(JsonNode binding)=>CharacterStoryStore.Text(binding["payload"],"workflowVersion")==MaskedWorkflowVersion?MaskedWorkflowVersion:WorkflowVersion;
    public const string Camera="Eye-level locked camera, identical framing and fixed screen positions. No camera motion, zoom, crop or scene cut.";
    public static void ValidateRegions(IReadOnlyList<SceneActorRegion> regions,int width=1536,int height=864)
    {
        if(width!=1536||height!=864||regions.Count!=2||!regions.Select(r=>r.Side).Order().SequenceEqual(new[]{"left","right"}))throw new ArgumentException("固定场景须为1536×864并分别定义左、右两个人物区域");
        foreach(var r in regions)
        {
            if(r.X<0||r.Y<0||r.Width<64||r.Height<64||r.X+r.Width>width||r.Y+r.Height>height||r.Feather<0||r.Feather>64||r.Feather*2>=Math.Min(r.Width,r.Height))throw new ArgumentException("人物区域超出原图或羽化范围无效");
            if(r.Side=="left"&&r.X+r.Width/2>=width/2||r.Side=="right"&&r.X+r.Width/2<=width/2)throw new ArgumentException("人物区域必须分别位于画面左、右");
        }
        var a=regions[0];var b=regions[1];
        if(a.X<b.X+b.Width&&b.X<a.X+a.Width&&a.Y<b.Y+b.Height&&b.Y<a.Y+a.Height)throw new ArgumentException("两个人物区域不能重叠，请保留独立站位");
        if(regions.Sum(r=>(long)r.Width*r.Height)*100>(long)width*height*65)throw new ArgumentException("人物区域过大，至少保留35%的固定背景供核验");
    }
    public async Task<object> ListAsync(long? projectId,CancellationToken ct)
    {
        var rows=await db.QueryAsync("SELECT id FROM entity_versions WHERE entity_type='Scene' AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.schema'))=@schema AND (@project IS NULL OR project_id=@project) ORDER BY id DESC",c=>{StudioDb.Add(c,"@schema",Schema);StudioDb.Add(c,"@project",projectId);},ct);
        var result=new List<CharacterStoryRecord>();foreach(var r in rows)result.Add(await store.GetAsync(r.Long("id"),"Scene",ct));return result;
    }
    private async Task<JsonObject> SourceAsync(long taskId,CancellationToken ct)
    {
        var task=(await repository.TaskAsync(taskId,ct)).FirstOrDefault()??throw new ArgumentException("场景来源任务不存在");
        if(task.Text("status")!="Succeeded")throw new AssetValidationException("场景来源任务尚未成功");
        var review=await store.LatestAsync("KeyframeReview",taskId,ct);
        if(CharacterStoryStore.Text(review?.Payload,"decision")!="Passed")throw new AssetValidationException("请先检查场景构图来源的实际关键帧；失败或待检查素材不能作为基准");
        var asset=(await db.QueryAsync("SELECT a.* FROM assets a JOIN generation_results r ON r.asset_id=a.id WHERE r.task_id=@task ORDER BY a.id",c=>StudioDb.Add(c,"@task",taskId),ct)).FirstOrDefault(a=>string.Equals(Path.GetExtension(a.Text("path")),".png",StringComparison.OrdinalIgnoreCase))??throw new AssetValidationException("场景来源须为实际PNG关键帧输出");
        if(!paths.TryResolveExisting(asset.Text("relativePath")??asset.Text("path"),out var full,out var relative))throw new AssetValidationException("场景基准文件缺失或不在受控目录");
        var hash=await ffmpeg.Sha256Async(full,ct);var probe=await ffmpeg.ProbeAsync(full,ct);
        if(hash!=asset.Text("sha256")||hash!=CharacterStoryStore.Text(review!.Payload,"sha256")||probe is null||probe.Width!=1536||probe.Height!=864)throw new AssetValidationException("场景基准SHA256或1536×864尺寸不符");
        return CharacterStoryStore.Object(new{taskId,assetId=asset.Long("id"),projectId=task.Long("projectId"),path=relative,sha256=hash,width=1536,height=864,taskInputJson=task.Text("inputJson"),reviewId=review.Id,reviewScope=CharacterStoryStore.Text(review.Payload,"scope")});
    }
    public async Task<CharacterStoryRecord> CaptureAsync(long sceneId,SceneCaptureInput input,string actor,CancellationToken ct)
    {
        var scene=(await repository.QuerySceneAsync(sceneId,ct)).FirstOrDefault()??throw new ArgumentException("场景不存在");
        if(ReferenceMetadata.Read(scene.Text("metadataJson")).ReviewStatus=="Rejected")throw new AssetValidationException("场景基准已被拒绝，不能冻结或自动换图");
        if(scene.LongOrNull("projectId") is not{} projectId)throw new ArgumentException("请先为场景指定归属项目");
        ValidateRegions(input.Regions);var source=await SourceAsync(input.SourceTaskId,ct);
        if(!paths.TryResolveExisting(scene.Text("anchorPath"),out _,out var anchor)||anchor!=CharacterStoryStore.Text(source,"path"))throw new AssetValidationException("当前场景锚点须明确指向所选来源任务输出");
        var sourceInput=JsonNode.Parse(CharacterStoryStore.Text(source,"taskInputJson"))!;
        var sourcePlan=await store.GetAsync(CharacterStoryStore.Number(sourceInput["parameters"]?[CharacterStoryService.Marker],"planId"),"ShotCast",ct);
        var actors=sourcePlan.Payload["actors"]!.AsArray();
        if(actors.Count!=2||actors.Any(a=>CharacterStoryStore.Text(a,"position") is not("left" or "right")))throw new ArgumentException("含人物的构图基准须已有左、右两人绑定；不把衣服槽当作第二身份");
        var boundActors=new JsonArray(actors.Select(a=>(JsonNode)CharacterStoryStore.Object(new{characterId=CharacterStoryStore.Number(a,"characterId"),versionId=CharacterStoryStore.Number(a,"versionId"),position=CharacterStoryStore.Text(a,"position")})).ToArray());
        if(input.WorkflowVersion is not(WorkflowVersion or MaskedWorkflowVersion))throw new ArgumentException("场景路线版本无效");
        var payload=new JsonObject{["schema"]=Schema,["requestId"]=CharacterStoryStore.RequestKey(input.IdempotencyKey),["sceneId"]=sceneId,["sceneName"]=scene.Text("name"),["sceneDescription"]=CharacterStoryStore.Required(input.Description,"固定场景说明"),["camera"]=Camera,["source"]=source,["actorVersions"]=boundActors,["regions"]=JsonSerializer.SerializeToNode(input.Regions,CharacterStoryStore.Json),["mode"]="FixedCameraBackgroundComposite",["contentReview"]="NeedReview",["publication"]="Blocked"};
        if(input.WorkflowVersion==MaskedWorkflowVersion)payload["workflowVersion"]=MaskedWorkflowVersion;
        return await store.AppendAsync("Scene",sceneId,projectId,payload,actor,ct);
    }
    public async Task<JsonObject> BindingAsync(long versionId,long projectId,CancellationToken ct)
    {
        var record=await store.GetAsync(versionId,"Scene",ct);
        if(record.ProjectId!=projectId||CharacterStoryStore.Text(record.Payload,"schema")!=Schema)throw new AssetValidationException("场景版本不属于当前项目或不支持当前路线");
        var scene=(await repository.QuerySceneAsync(record.EntityId,ct)).FirstOrDefault()??throw new AssetValidationException("场景归属已移除");
        if(ReferenceMetadata.Read(scene.Text("metadataJson")).ReviewStatus=="Rejected")throw new AssetValidationException("场景基准已被拒绝，不能继续调用旧快照");
        if(scene.Long("projectId")!=projectId)throw new AssetValidationException("场景项目归属已变化");
        var source=await SourceAsync(CharacterStoryStore.Number(record.Payload["source"],"taskId"),ct);
        foreach(var key in new[]{"path","sha256"})if(CharacterStoryStore.Text(source,key)!=CharacterStoryStore.Text(record.Payload["source"],key))throw new AssetValidationException("场景来源已变化，不能静默改用另一张图");
        var regions=record.Payload["regions"]!.Deserialize<List<SceneActorRegion>>(CharacterStoryStore.Json)!;ValidateRegions(regions);
        return new JsonObject{["versionId"]=record.Id,["versionSha256"]=record.Sha256,["payload"]=record.Payload.DeepClone()};
    }
    public static void RequireFixedComposition(JsonObject binding,JsonObject plan)
    {
        var fixedScene=binding["payload"]!;var actors=plan["actors"]!.AsArray();
        if(CharacterStoryStore.Text(plan,"shotFraming")!="twoShot"||actors.Count!=2||CharacterStoryStore.Text(plan,"camera")!=CharacterStoryStore.Text(fixedScene,"camera")||CharacterStoryStore.Text(plan,"scene")!=CharacterStoryStore.Text(fixedScene,"sceneDescription"))throw new ArgumentException("锁定背景路线仅支持同一机位的双人中景；场景和机位须沿用冻结基准，更换景别须建立新机位基准");
        foreach(var actor in actors)
            if(!fixedScene["actorVersions"]!.AsArray().Any(a=>CharacterStoryStore.Number(a,"characterId")==CharacterStoryStore.Number(actor,"characterId")&&CharacterStoryStore.Number(a,"versionId")==CharacterStoryStore.Number(actor,"versionId")&&CharacterStoryStore.Text(a,"position")==CharacterStoryStore.Text(actor,"position")))throw new ArgumentException("人物版本或站位与含人物的场景构图基准不符，请明确建立新基准");
    }
    public static void ApplyGeometry(JsonObject workflow,JsonElement parameters,WorkflowExecutionPlan? contract)
    {
        if(!parameters.TryGetProperty("sceneLock",out var scene))return;
        if(contract?.WorkflowFileName is not(WorkflowFile or MaskedWorkflowFile))throw new WorkflowContractException("SCENE_CONTRACT_REQUIRED","背景锁定参数只能用于已登记的五输入场景工作流");
        var regions=scene.GetProperty("payload").GetProperty("regions").Deserialize<List<SceneActorRegion>>(CharacterStoryStore.Json)!;ValidateRegions(regions);
        // Generic width/height patching touches all masks. Reapply only the
        // validated scene geometry after that patch; no arbitrary node overrides.
        foreach(var (side,solid,feather,composite) in new[]{("left","61","62","63"),("right","64","65","66")})
        {
            var r=regions.Single(r=>r.Side==side);var s=workflow[solid]!["inputs"]!.AsObject();s["width"]=r.Width;s["height"]=r.Height;
            var f=workflow[feather]!["inputs"]!.AsObject();foreach(var edge in new[]{"left","top","right"})f[edge]=r.Feather;f["bottom"]=0;
            var c=workflow[composite]!["inputs"]!.AsObject();c["x"]=r.X;c["y"]=r.Y;
        }
        if(contract.WorkflowFileName==MaskedWorkflowFile)
        {
            foreach(var (side,solid,composite) in new[]{("left","71","72"),("right","73","74")})
            {
                var r=regions.Single(r=>r.Side==side);var width=r.Width*7/10;var height=Math.Min(340,r.Height/2);
                var s=workflow[solid]!["inputs"]!.AsObject();s["width"]=width;s["height"]=height;
                var c=workflow[composite]!["inputs"]!.AsObject();c["x"]=r.X+(r.Width-width)/2;c["y"]=r.Y;
            }
        }
    }
}
public sealed class SceneActorRegion { public string Side {get;set;}="";public int X {get;set;}public int Y {get;set;}public int Width {get;set;}public int Height {get;set;}public int Feather {get;set;}=32; }
public sealed class SceneCaptureInput { public long SourceTaskId {get;set;}public string Description {get;set;}="";public List<SceneActorRegion> Regions {get;set;}=[];public string WorkflowVersion {get;set;}=CharacterSceneService.WorkflowVersion;public string IdempotencyKey {get;set;}=""; }
