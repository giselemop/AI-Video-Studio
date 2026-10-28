using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

public sealed class WorkshopGenerateInput
{
    public long CharacterId {get;set;}
    public string Kind {get;set;}="identity";
    public string View {get;set;}="front";
    public string Framing {get;set;}="closeUp";
    public long Seed {get;set;}=2026102701;
    public long? RepairOfTaskId {get;set;}
    public string? ChangeReason {get;set;}
    public string? PromptAdjustment {get;set;}
    public string IdempotencyKey {get;set;}="";
}
public sealed class WorkshopAnchorInput {public long IdentityId {get;set;} public long OutfitId {get;set;} public string IdempotencyKey {get;set;}="";}
public sealed class WorkshopCollectInput {public long TaskId {get;set;} public string View {get;set;}="front";public string Framing {get;set;}="closeUp";public string? ChangeReason {get;set;}}

/// <summary>Draft candidates and explicitly approved anchors. No image generation outside GenerationQueue.</summary>
public sealed class CharacterWorkshopService(StudioDb db,StudioRepository repository,CharacterStoryStore store,AssetPathPolicy paths,FfmpegService ffmpeg,StudioSettings settings)
{
    public const string Marker="characterWorkbench";
    static readonly JsonSerializerOptions Json=CharacterStoryStore.Json;
    public async Task<object> SummariesAsync(CancellationToken ct)
    {
        var output=new List<object>();
        foreach(var character in await repository.CharactersAsync(null,ct))
        {
            var refs=(await repository.CharacterReferencesAsync(character.Long("id"),ct)).Where(r=>JsonNode.Parse(r.Text("metadataJson")??"{}")?["workbench"] is not null&&ReferenceMetadata.Read(r.Text("metadataJson")).ReviewStatus!="Rejected"&&paths.TryResolveExisting(r.Text("path"),out _,out _)).ToArray();
            if(refs.Length==0)continue;
            var slots=refs.Select(r=>r.Text("kind")).ToHashSet();var missing=CharacterLibraryService.BasicSlots.Where(s=>!slots.Contains(s.View+"-"+s.Framing)).ToArray();
            var cover=refs.FirstOrDefault(r=>r.Text("kind")=="front-closeUp")??refs[0];var available=paths.TryResolveExisting(cover.Text("path"),out _,out var relative);
            output.Add(new{characterId=character.Long("id"),name=character.Text("name"),ageSetting=character.Text("ageSetting"),outfit=character.Text("clothes"),candidateCount=refs.Length,present=9-missing.Length,expected=9,missing,cover=available?relative:null,reviewStatus="NeedReview",versionStatus="Draft",explanation="候选图用途标注待逐图审核，未冻结为库版本"});
        }
        return output;
    }
    public async Task<Dictionary<string,object?>> Character(long id,CancellationToken ct)
        =>(await repository.QueryCharacterAsync(id,ct)).FirstOrDefault()??throw new ArgumentException("人物不存在");
    public async Task<JsonObject> Reference(long characterId,long id,bool approved,CancellationToken ct)
    {
        var row=(await repository.CharacterReferencesAsync(characterId,ct)).FirstOrDefault(r=>r.Long("id")==id)??throw new ArgumentException("候选图不属于该人物");
        var meta=ReferenceMetadata.Read(row.Text("metadataJson"));
        if(meta.ReviewStatus=="Rejected"||approved&&meta.ReviewStatus!="Approved")throw new AssetValidationException("身份/造型基准必须先人工检查并批准，不能使用待审或被拒绝素材");
        if(!paths.TryResolveExisting(row.Text("path"),out var full,out var relative)||await ffmpeg.Sha256Async(full,ct)!=meta.Sha256)throw new AssetValidationException("候选图缺失或SHA256变化");
        return new JsonObject{["id"]=id,["path"]=relative,["sha256"]=meta.Sha256,["assetVersion"]=meta.AssetVersion};
    }
    public async Task<object> StateAsync(long characterId,CancellationToken ct)
    {
        var character=await Character(characterId,ct);var anchors=await store.LatestAsync("CharacterWorkflow",characterId,ct);
        var refs=new List<object>();
        foreach(var row in await repository.CharacterReferencesAsync(characterId,ct))
        {var available=paths.TryResolveExisting(row.Text("path"),out _,out var relative);refs.Add(new{id=row.Long("id"),kind=row.Text("kind"),metadata=JsonNode.Parse(row.Text("metadataJson")??"{}"),available,assetPath=available?relative:null,width=row.Int("width"),height=row.Int("height")});}
        var tasks=await db.QueryAsync("SELECT id,status,error_message,input_json FROM generation_tasks WHERE JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.parameters.characterWorkbench.request.characterId'))=@id ORDER BY id DESC LIMIT 50",c=>StudioDb.Add(c,"@id",characterId.ToString()),ct);
        return new{character,anchors,references=refs,tasks=tasks.Select(t=>new{id=t.Long("id"),status=t.Text("status"),error=t.Text("errorMessage"),input=JsonNode.Parse(t.Text("inputJson")??"{}")}),promptPolicy=CharacterReferencePrompts.Policy()["version"]!.GetValue<string>(),prompts=PromptPreviews(character),contentReview="NeedReview"};
    }
    public static object[] PromptPreviews(Dictionary<string,object?> character)
    {
        var metadata=JsonNode.Parse(character.Text("metadataJson")??"{}");
        var shoes=CharacterStoryStore.Text(metadata?["referenceStudio"],"shoes","match established shoes");
        var identity=$"{character.Text("fixedPrompt")}. Face: {character.Text("faceFeatures")}. Hair: {character.Text("hair")}. Age: {character.Text("ageSetting")}.";
        return CharacterLibraryService.BasicSlots.Select(s=>(object)new{view=s.View,framing=s.Framing,
            prompt=CharacterReferencePrompts.Compose(s.View,s.Framing,s.View=="front"?(s.Framing=="closeUp"?0:1):2,identity,character.Text("clothes")+(s.Framing=="fullBody"?". Shoes: "+shoes:""),character.Text("bodyRatio")??"natural adult proportions")}).ToArray();
    }
    public async Task<CharacterStoryRecord> AnchorsAsync(long characterId,WorkshopAnchorInput input,string actor,CancellationToken ct)
    {
        var character=await Character(characterId,ct);var identity=await Reference(characterId,input.IdentityId,true,ct);
        var identityRow=(await repository.CharacterReferencesAsync(characterId,ct)).First(r=>r.Long("id")==input.IdentityId);
        if(identityRow.Text("kind")!="front-closeUp")throw new ArgumentException("身份锚点须标注为正面近景");
        JsonObject? outfit=null;
        if(input.OutfitId>0)
        { outfit=await Reference(characterId,input.OutfitId,true,ct);var r=(await repository.CharacterReferencesAsync(characterId,ct)).First(r=>r.Long("id")==input.OutfitId);if(r.Text("kind")!="front-fullBody")throw new ArgumentException("造型基准须为正面全身"); }
        return await store.AppendAsync("CharacterWorkflow",characterId,character.Long("projectId"),new JsonObject{["schema"]="character-anchors-v1",["requestId"]=CharacterStoryStore.RequestKey(input.IdempotencyKey),["identity"]=identity,["outfit"]=outfit},actor,ct);
    }
    public async Task<TaskInput> BuildAsync(WorkshopGenerateInput input,CancellationToken ct,bool legacyPrompt=false)
    {
        var character=await Character(input.CharacterId,ct);var key=CharacterStoryStore.RequestKey(input.IdempotencyKey);
        if(input.Seed<0||input.Kind is not("identity" or "outfit" or "slot"))throw new ArgumentException("候选阶段或种子无效");
        if(!CharacterLibraryService.BasicSlots.Any(s=>s.View==input.View&&s.Framing==input.Framing))throw new ArgumentException("请使用九图标准方向及景别");
        if(input.Kind=="identity"&&(input.View!="front"||input.Framing!="closeUp")||input.Kind=="outfit"&&(input.View!="front"||input.Framing!="fullBody"))throw new ArgumentException("身份候选为正面近景，造型基准为正面全身");
        foreach(var name in new[]{"name","ageSetting","faceFeatures","hair","bodyRatio","clothes","fixedPrompt"})CharacterStoryStore.Required(character.Text(name),name);
        var metadata=JsonNode.Parse(character.Text("metadataJson")??"{}");
        var shoes=CharacterStoryStore.Required(CharacterStoryStore.Text(metadata?["referenceStudio"],"shoes"),"鞋子");
        var invariants=CharacterStoryStore.Required(CharacterStoryStore.Text(metadata?["referenceStudio"],"immutableTraits"),"禁改特征");
        JsonObject? identity=null,outfit=null;long? anchorId=null;
        if(input.Kind!="identity")
        {
            var anchors=await store.LatestAsync("CharacterWorkflow",input.CharacterId,ct)??throw new ArgumentException("请先确认身份锚点");anchorId=anchors.Id;
            identity=await Reference(input.CharacterId,CharacterStoryStore.Number(anchors.Payload["identity"],"id"),true,ct);
            if(!CharacterStoryStore.Equal(JsonSerializer.SerializeToElement(identity),JsonSerializer.SerializeToElement(anchors.Payload["identity"])))throw new AssetValidationException("身份基准已变化，请重新确认");
            if(input.Kind=="slot")
            {outfit=await Reference(input.CharacterId,CharacterStoryStore.Number(anchors.Payload["outfit"],"id"),true,ct);if(!CharacterStoryStore.Equal(JsonSerializer.SerializeToElement(outfit),JsonSerializer.SerializeToElement(anchors.Payload["outfit"])))throw new AssetValidationException("造型基准已变化");}
        }
        JsonObject? directionalIdentity=null;
        if(!legacyPrompt&&input.Kind=="slot"&&input.Framing=="fullBody"&&input.View is "threeQuarterLeft" or "threeQuarterRight")
        {
            var pose=(await repository.CharacterReferencesAsync(input.CharacterId,ct)).FirstOrDefault(r=>r.Text("kind")==input.View+"-closeUp"&&ReferenceMetadata.Read(r.Text("metadataJson")).ReviewStatus=="Approved");
            if(pose is not null)directionalIdentity=await Reference(input.CharacterId,pose.Long("id"),true,ct);
        }
        var slots=new JsonObject();if(identity is not null)slots["firstFrame"]=(directionalIdentity??identity)["path"]!.DeepClone();if(outfit is not null&&directionalIdentity is null)slots["wardrobeReference"]=outfit["path"]!.DeepClone();
        var file=input.Kind=="identity"?"realvisxl_reference_api.json":slots.Count==1?"character_pack_klein4b_single_api.json":"character_pack_klein4b_dual_api.json";
        var workflow=(await repository.WorkflowsAsync(ct)).FirstOrDefault(w=>Path.GetFileName(w.Text("path"))==file)??throw new ArgumentException("既有工作流未登记");
        if(!paths.TryResolveExistingWorkflow(workflow.Text("path"),out var full,out _))throw new AssetValidationException("工作流缺失");
        var fixedAppearance=character.Text("fixedPrompt")!;
        if(input.Framing=="closeUp"&&System.Text.RegularExpressions.Regex.IsMatch(fixedAppearance+" "+invariants,@"\b(pants|trousers|shoes|sneakers|boots|loafers)\b|裤|鞋",System.Text.RegularExpressions.RegexOptions.IgnoreCase))throw new ArgumentException("近景的固定外貌描述/禁改特征混入裤装或鞋子；请把完整穿搭移到服装、鞋子字段，保留脸、发型、年龄等身份特征");
        var face=$"{fixedAppearance}. Face: {character.Text("faceFeatures")}. Hair: {character.Text("hair")}. Age: {character.Text("ageSetting")}. Preserve face and hair traits: {invariants}.";
        var framing=input.Framing=="closeUp"?"Tight head and shoulders portrait, complete crown visible, crop at collarbone. No pants or shoes in this close-up.":$"Complete full-body standing photograph, entire crown, both hands and both complete shoes with floor and comfortable margins. Body: {character.Text("bodyRatio")}. Outfit: {character.Text("clothes")}. Shoes: {shoes}.";
        var prompt=$"ONE photographic adult person only. {face} {framing} {Direction(input.View)} Plain light-gray studio, uniform soft light, neutral closed mouth. No collage, inset, text or additional person.";
        if(input.Kind!="identity")prompt="Preserve EXACT person from image1. "+(outfit is not null?"Image2 fixes the SAME person's outfit; in close-ups only reproduce the visible collar and upper garment, never another identity. ":"")+prompt;
        if(!legacyPrompt)prompt=CharacterReferencePrompts.Compose(input.View,input.Framing,slots.Count,face,character.Text("clothes")+(input.Framing=="fullBody"?". Shoes: "+shoes:""),character.Text("bodyRatio")??"");
        prompt+=CharacterStoryService.Adjustment(input.PromptAdjustment);
        var p=new JsonObject{["workflowVersion"]=input.Kind=="identity"?"realvisxl-reference-1536-v1":"character-pack-klein4b-"+(slots.Count==2?"dual":"single")+"-1536-v1",["positive"]=prompt,["negative"]=input.Kind=="identity"?"child, collage, inset, deformed face, extra people, text, watermark":"",["seed"]=input.Seed,["width"]=1536,["height"]=864,["steps"]=input.Kind=="identity"?35:4,["cfg"]=input.Kind=="identity"?5.5:1};
        if(slots.Count>0)p["inputSlots"]=slots;
        if(!legacyPrompt)p["promptPolicy"]=CharacterReferencePrompts.Policy()["version"]!.DeepClone();
        if(!legacyPrompt&&input.Kind=="identity")p["negative"]=CharacterReferencePrompts.Policy()["negative"]!.DeepClone();
        if(directionalIdentity is not null)p["directionalIdentity"]=directionalIdentity.DeepClone();
        var inputHashes=new JsonObject();foreach(var r in new[]{identity,outfit,directionalIdentity})if(r is not null)inputHashes[r["path"]!.GetValue<string>()]=r["sha256"]!.DeepClone();
        p[Marker]=CharacterStoryStore.Object(new{schema="character-workbench-v1",request=input,anchorId,identity,outfit,characterSha256=CanonicalJson.Sha256(CanonicalJson.Serialize(new{face,framing,fixedPrompt=character.Text("fixedPrompt"),clothes=character.Text("clothes"),shoes,body=character.Text("bodyRatio")})),workflowSha256=await ffmpeg.Sha256Async(full,ct),inputSha256=(directionalIdentity??identity)?["sha256"]?.GetValue<string>(),inputHashes});
        return new TaskInput{ProjectId=character.Long("projectId"),TaskType="Image",WorkflowId=workflow.Long("id"),InputImagePath=(directionalIdentity??identity)?["path"]?.GetValue<string>(),ResourceClass="GPU",MaxRetries=0,Stage="Character-Workbench-Candidate",IdempotencyKey=key,Parameters=JsonSerializer.SerializeToElement(p,Json)};
    }
    // Story plans and persisted v1 task validators retain their original wording.
    public static string Direction(string view)=>view switch{"front"=>"Exactly frontal with equal shoulders and eyes.","threeQuarterLeft"=>"Front three-quarter about35 degrees toward picture LEFT, both eyes and wide front of chest visible, not a profile.","threeQuarterRight"=>"Front three-quarter about35 degrees toward picture RIGHT, both eyes and wide front of chest visible, not a profile.","left"=>"Strict left profile, nose toward picture LEFT, far eye hidden.","right"=>"Strict right profile, nose toward picture RIGHT, far eye hidden.","back"=>"Exact back view, no face visible. Inspect hairstyle back, outfit and body; this cannot verify front identity.",_=>throw new ArgumentException("方向无效")};
    public async Task ValidateTaskAsync(TaskInput input,CancellationToken ct)
    {
        if(input.Parameters is not {ValueKind:JsonValueKind.Object} p||!p.TryGetProperty(Marker,out var m))return;
        var expected=await BuildAsync(m.GetProperty("request").Deserialize<WorkshopGenerateInput>(Json)!,ct,legacyPrompt:!p.TryGetProperty("promptPolicy",out _));
        if(input.ProjectId!=expected.ProjectId||input.EpisodeId is not null||input.ShotId is not null||input.ProductionRunId is not null||input.WorkflowId!=expected.WorkflowId||input.TaskType!="Image"||input.ResourceClass!="GPU"||input.MaxRetries!=0||input.InputImagePath!=expected.InputImagePath||input.Stage!=expected.Stage||input.LoraIds is {Count:>0}||!CharacterStoryStore.Equal(p,expected.Parameters!.Value))throw new AssetValidationException("人物设定、已确认基准、来源哈希或候选工作流发生变化");
    }
    public async Task<object> SubmitAsync(WorkshopGenerateInput input,TaskSubmissionPreflightService preflight,GenerationQueue queue,CancellationToken ct)
    {
        await using var connection=await db.OpenAsync(ct);await using var tx=await connection.BeginTransactionAsync(System.Data.IsolationLevel.ReadCommitted,ct);
        await using(var guard=new MySqlConnector.MySqlCommand("SELECT id FROM characters WHERE id=@id FOR UPDATE",connection,tx)){StudioDb.Add(guard,"@id",input.CharacterId);if(await guard.ExecuteScalarAsync(ct)is null)throw new ArgumentException("人物不存在");}
        var task=await BuildAsync(input,ct);var existing=await repository.TaskByIdempotencyKeyAsync(input.IdempotencyKey,ct);
        if(existing is null)
        {
            var records=await db.QueryAsync("SELECT id,status,input_json FROM generation_tasks WHERE JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.parameters.characterWorkbench.request.characterId'))=@id",c=>StudioDb.Add(c,"@id",input.CharacterId.ToString()),ct);
            var current=JsonSerializer.SerializeToNode(task.Parameters!.Value)![Marker];
            var same=records.Where(r=>{var marker=JsonNode.Parse(r.Text("inputJson")!)?["parameters"]?[Marker];var request=marker?["request"];return CharacterStoryStore.Text(marker,"characterSha256")==CharacterStoryStore.Text(current,"characterSha256")&&CharacterStoryStore.Number(marker,"anchorId")==CharacterStoryStore.Number(current,"anchorId")&&CharacterStoryStore.Text(request,"kind")==input.Kind&&CharacterStoryStore.Text(request,"view")==input.View&&CharacterStoryStore.Text(request,"framing")==input.Framing;}).ToList();
            if(input.Kind=="identity"&&same.Count>=3)throw new ArgumentException("本阶段先比较现有三张身份候选，避免无界批量生成");
            if(input.Kind!="identity"&&same.Count>0)
            {
                if(same.Count>=3)throw new ArgumentException("该槽位已达到初次加两次定向修复上限");
                var old=same.FirstOrDefault(r=>r.Long("id")==input.RepairOfTaskId)??throw new ArgumentException("提供本槽位失败来源任务");
                var refs=await repository.CharacterReferencesAsync(input.CharacterId,ct);
                if(old.Text("status")!="Failed"&&!refs.Any(r=>CharacterStoryStore.Number(JsonNode.Parse(r.Text("metadataJson")??"{}")?["workbench"],"taskId")==input.RepairOfTaskId&&ReferenceMetadata.Read(r.Text("metadataJson")).ReviewStatus=="Rejected"))throw new ArgumentException("先明确拒绝失败候选，再定向修复");
                CharacterStoryStore.Required(input.ChangeReason,"具体修复改变");var oldReq=JsonNode.Parse(old.Text("inputJson")!)?["parameters"]?[Marker]?["request"];if(CharacterStoryStore.Number(oldReq,"seed")==input.Seed&&CharacterStoryStore.Text(oldReq,"promptAdjustment").Trim()== (input.PromptAdjustment??"").Trim())throw new ArgumentException("修复须改变种子或定向提示词，并记录改变原因");
            }
        }
        var check=await preflight.CheckAsync(task,ct,businessSubmission:true);if(!check.Passed)throw new AssetValidationException(string.Join("；",check.Issues));
        var id=await repository.CreateTaskAsync(task,ct);await tx.CommitAsync(ct);if(existing is null||existing.Text("status")=="Pending")queue.Enqueue(id);return new{id,created=existing is null,contentReview="NeedReview"};
    }
    public async Task<object> CollectAsync(long characterId,WorkshopCollectInput input,CancellationToken ct)
    {
        var character=await Character(characterId,ct);
        if(!CharacterLibraryService.BasicSlots.Any(s=>s.View==input.View&&s.Framing==input.Framing))throw new ArgumentException("只允许九图标准槽位");
        var task=(await db.QueryAsync("SELECT * FROM generation_tasks WHERE id=@id",c=>StudioDb.Add(c,"@id",input.TaskId),ct)).FirstOrDefault()??throw new ArgumentException("来源任务不存在");
        if(task.Text("status")!="Succeeded"||task.Long("projectId")!=character.Long("projectId"))throw new ArgumentException("只收集该人物项目的真实成功输出");
        var root=JsonNode.Parse(task.Text("inputJson")!);var request=root?["parameters"]?[Marker]?["request"];string? originalKey=null;
        // Candidate-only repairs use the same contracted Studio queue without claiming approved anchors.
        // Collection records their real task, owner and frozen request; it never approves or freezes them.
        var repair=root?["parameters"]?["characterReferenceRepair"];
        if(request is null&&CharacterStoryStore.Number(repair,"characterId")==characterId)request=repair;
        if(CharacterStoryStore.Number(request,"characterId")!=characterId)
        {
            // Previous real checkpoints are read only: task-to-character mapping,
            // output hash and original requests are verified before adoption.
            var checkpoint=Path.Combine(settings.DataPath,"CharacterExpansionFive20261026","run.json");
            if(!File.Exists(checkpoint))throw new ArgumentException("来源任务没有人物归属记录");
            var legacy=JsonNode.Parse(await File.ReadAllTextAsync(checkpoint,ct))!;
            var person=legacy["people"]!.AsObject().FirstOrDefault(p=>CharacterStoryStore.Number(p.Value,"id")==characterId||CharacterStoryStore.Number(p.Value,"characterId")==characterId);
            if(person.Key is null)throw new ArgumentException("原检查点未将任务绑定到该人物");
            var entry=legacy["tasks"]!.AsObject().FirstOrDefault(t=>t.Key.StartsWith(person.Key+"-",StringComparison.Ordinal)&&CharacterStoryStore.Number(t.Value,"id")==input.TaskId);
            if(entry.Key is null)throw new ArgumentException("原检查点未将任务绑定到该人物");originalKey=entry.Key;
            var parts=entry.Key[(person.Key.Length+1)..].Split('-');
            request=new JsonObject{["view"]=parts[0],["framing"]=parts[1]};
        }
        var output=(await db.QueryAsync("SELECT a.* FROM assets a JOIN generation_results r ON r.asset_id=a.id WHERE r.task_id=@id",c=>StudioDb.Add(c,"@id",input.TaskId),ct)).FirstOrDefault(r=>Path.GetExtension(r.Text("path"))==".png")??throw new ArgumentException("没有PNG输出");
        if(!paths.TryResolveExisting(output.Text("path"),out var full,out _)||await ffmpeg.Sha256Async(full,ct)!=output.Text("sha256"))throw new AssetValidationException("输出文件缺失或变化");
        var existing=(await repository.CharacterReferencesAsync(characterId,ct)).FirstOrDefault(r=>r.Text("kind")==input.View+"-"+input.Framing&&CharacterStoryStore.Number(JsonNode.Parse(r.Text("metadataJson")??"{}")?["workbench"],"taskId")==input.TaskId);
        if(existing is not null)return new{id=existing.Long("id"),created=false};
        var originalView=CharacterStoryStore.Text(request,"view",input.View);var originalFraming=CharacterStoryStore.Text(request,"framing",input.Framing);
        if((originalView!=input.View||originalFraming!=input.Framing)&&string.IsNullOrWhiteSpace(input.ChangeReason))throw new ArgumentException("纠正用途标注必须保留原因");
        var id=await repository.AddCharacterReferenceAsync(characterId,full,new ReferenceInput{Kind=input.View+"-"+input.Framing,Role=input.Framing=="closeUp"?"identity":"outfit",Stage="candidate",ChangeReason=input.ChangeReason},ct);
        var probe=await ffmpeg.ProbeAsync(full,ct)??throw new AssetValidationException("候选输出无法读取尺寸");
        var provenance=CharacterStoryStore.Object(new{taskId=input.TaskId,originalKey,originalView,originalFraming,view=input.View,framing=input.Framing,changeReason=input.ChangeReason,originalRequestJson=task.Text("inputJson"),contentReview="NeedReview",directionReview="NeedReview",identityScore=(double?)null});
        await db.ExecuteAsync("UPDATE character_references SET width=@w,height=@h,metadata_json=JSON_SET(metadata_json,'$.workbench',CAST(@p AS JSON)) WHERE id=@id",c=>{StudioDb.Add(c,"@w",probe.Width);StudioDb.Add(c,"@h",probe.Height);StudioDb.Add(c,"@p",provenance.ToJsonString());StudioDb.Add(c,"@id",id);},ct);
        return new{id,created=true};
    }
}
