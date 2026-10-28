using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

/// <summary>
/// Cast and Shot context use the existing immutable ledger. H3 work remains
/// isolated review-preview work, with validated links to real Episode/Shot ids.
/// Existing formal H3 and publication gates are deliberately unchanged.
/// </summary>
public sealed class CharacterStoryService(StudioDb db, StudioRepository repository, CharacterStoryStore store,
    CharacterLibraryService library, AssetPathPolicy paths, FfmpegService ffmpeg,CharacterSceneService? sceneReferences=null)
{
    public const string Marker="storyPipeline";
    public const string FourWorkflow="character_story_klein4b_four_api.json";
    public const string PreviewMarker="storyPreview";
    private static readonly JsonSerializerOptions Json=CharacterStoryStore.Json;
    public static object Capabilities => new
    {
        meaning="人物设定、参考图与不可变造型版本；不是已训练的专属模型或三维人物",
        videoRoute="ReviewedStoryKeyframeToH3FirstFrame", checkedTailContinuation=true, h3Ref2VA=false, h3MultipleIdentityInputs=false,
        multiActorKeyframe="独立身份/服装四槽静态候选，须逐张检查后才可试片",
        formalProduction=false, publication="Blocked", gpuConcurrency=1,
        videoProfiles=new[]{"baseline480","quality768","native1080"}, frames=124,fps=24,
        referenceDirection="image-facing-v1：鼻尖朝画面左/右；前侧保留斜前方，背面不验证正脸身份"
    };
    public async Task<object> ReadinessAsync(CancellationToken ct)
    {
        var clause=await db.ScalarAsync("SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='ck_entity_versions_type'",c=>{},ct);
        var versionRecordsReady=new[]{"ProjectCast","EpisodeCast","ShotCast","KeyframeReview","LibraryReview","CharacterWorkflow"}.All(t=>Convert.ToString(clause)?.Contains(t,StringComparison.Ordinal)==true);
        var referenceReviewAuditReady=Convert.ToInt32(await db.ScalarAsync("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='character_reference_reviews'",c=>{},ct))==1;
        var ready=versionRecordsReady&&referenceReviewAuditReady;
        var missingMigrations=new List<string>();if(!versionRecordsReady)missingMigrations.Add("010_character_story_records.sql");if(!referenceReviewAuditReady)missingMigrations.Add("011_character_reference_review_audit.sql");
        return new{ready,versionRecordsReady,referenceReviewAuditReady,status=ready?"Passed":"Blocked",code=ready?"READY":"STORY_MIGRATION_REQUIRED",missingMigrations,message=ready?"版本记录与素材审核日志已就绪":"请管理员执行缺失迁移："+string.Join("、",missingMigrations)+"；业务账号无ALTER/CREATE权限，不提交依赖这些表的任务"};
    }
    public async Task<TaskInput> BuildPreviewAsync(StoryPreviewInput input,CancellationToken ct)
    {
        var episode=await Parent("episodes",input.EpisodeId,ct);
        if(input.TaskIds is null||input.TaskIds.Count is <1 or >24||input.TaskIds.Distinct().Count()!=input.TaskIds.Count)throw new ArgumentException("按顺序选取1–24个不同的已检查视频任务");
        var clips=new JsonArray();string? strategy=null;int? width=null,height=null;
        foreach(var id in input.TaskIds)
        {
            var (task,result)=await TaskOutput(id,ct);var marker=task["input"]?["parameters"]?[Marker];
            if(CharacterStoryStore.Text(marker,"kind")!="Video"||CharacterStoryStore.Number(marker,"episodeId")!=input.EpisodeId||CharacterStoryStore.Number(task,"projectId")!=episode.Long("projectId"))throw new ArgumentException("预览只能合成本集剧情视频输出");
            var plan=await Plan(CharacterStoryStore.Number(marker,"planId"),ct);var review=await store.LatestAsync("KeyframeReview",id,ct);
            if(CharacterStoryStore.Text(review?.Payload,"decision")!="Passed"||CharacterStoryStore.Text(review?.Payload,"sha256")!=CharacterStoryStore.Text(result,"sha256"))throw new AssetValidationException("只合成已检查且哈希一致的视频，内容失败项须定向修复");
            var audio=CharacterStoryStore.Text(plan.Payload,"audioStrategy");if(strategy is not null&&strategy!=audio)throw new ArgumentException("同一预览不能混用音频策略");strategy=audio;
            paths.TryResolveExisting(CharacterStoryStore.Text(result,"path"),out var full,out _);var probe=await ffmpeg.ProbeAsync(full,ct)??throw new AssetValidationException("视频无法读取");
            if(probe.FrameCount!=124||probe.Fps!=24)throw new AssetValidationException("实际视频不符合已验证的24FPS/124帧契约，请检查源片，不改变帧数掩盖问题");
            if(audio=="NativeH3"&&probe.HasAudio!=true)throw new AssetValidationException("选定原生声音策略但源视频没有音轨；不能静默换成其他策略");
            if(width is not null&&(width!=probe.Width||height!=probe.Height))throw new ArgumentException("视频规格不同，请明确后处理规格，不能静默降低画质");width=probe.Width;height=probe.Height;
            clips.Add(new JsonObject{["taskId"]=id,["reviewId"]=review!.Id,["path"]=result["path"]!.DeepClone(),["sha256"]=result["sha256"]!.DeepClone()});
        }
        string? audioPath=null,audioSha=null;
        if(strategy=="ExistingDubbing")
        {if(!paths.TryResolveExisting(input.AudioPath,out var full,out audioPath))throw new ArgumentException("已有配音策略必须选择受控音轨");var probe=await ffmpeg.ProbeAsync(full,ct);if(probe?.HasAudio!=true)throw new ArgumentException("配音来源没有音轨");audioSha=await ffmpeg.Sha256Async(full,ct);}
        else if(!string.IsNullOrEmpty(input.AudioPath))throw new ArgumentException("当前音频策略不接收替换音轨");
        return new TaskInput{ProjectId=episode.Long("projectId"),TaskType="Concat",ResourceClass="CPU",MaxRetries=0,Stage="Story-Episode-Review-Preview",IdempotencyKey=CharacterStoryStore.RequestKey(input.IdempotencyKey),DependencyTaskId=input.TaskIds[^1],Parameters=JsonSerializer.SerializeToElement(new{files=clips.Select(c=>CharacterStoryStore.Text(c,"path")),targetFps=24,outputName="story_review_preview.mp4",storyPreview=new{schema="story-preview-v1",request=input,clips,audioStrategy=strategy,audioPath,audioSha256=audioSha,contentReview="NeedReview",publication="Blocked"}},Json)};
    }
    public async Task ValidatePreviewAsync(TaskInput input,CancellationToken ct)
    {
        if(input.Parameters is not{ValueKind:JsonValueKind.Object} p||!p.TryGetProperty(PreviewMarker,out var m))return;
        var expected=await BuildPreviewAsync(m.GetProperty("request").Deserialize<StoryPreviewInput>(Json)!,ct);
        if(input.ProjectId!=expected.ProjectId||input.TaskType!="Concat"||input.ResourceClass!="CPU"||input.ShotId is not null||input.EpisodeId is not null||input.ProductionRunId is not null||input.MaxRetries!=0||!CharacterStoryStore.Equal(p,expected.Parameters!.Value))throw new AssetValidationException("剧情预览源、审核或音轨快照发生变化");
    }
    private async Task<Dictionary<string,object?>> Parent(string table,long id,CancellationToken ct)
        => (await db.QueryAsync($"SELECT * FROM {table} WHERE id=@id",c=>StudioDb.Add(c,"@id",id),ct)).FirstOrDefault()??throw new ArgumentException("项目、集或镜头不存在");
    public async Task<Dictionary<string,object?>> CheckReferenceAsync(long characterId,LibraryReference reference,CancellationToken ct=default)
    {
        var row=(await repository.CharacterReferencesAsync(characterId,ct)).FirstOrDefault(r=>r.Long("id")==reference.ReferenceId)??throw new AssetValidationException("人物来源参考记录已移除");
        var metadata=ReferenceMetadata.Read(row.Text("metadataJson"));
        if(metadata.ReviewStatus=="Rejected")throw new AssetValidationException("所选参考已被拒绝，不能换用其他图代替");
        if(metadata.AssetVersion!=reference.AssetVersion || metadata.Sha256!=reference.Sha256 || !paths.TryResolveExisting(reference.AssetPath,out var full,out _)
            || !paths.TryResolveExisting(row.Text("path"),out var original,out _) || !string.Equals(full,original,StringComparison.OrdinalIgnoreCase)
            || await ffmpeg.Sha256Async(full,ct)!=reference.Sha256)throw new AssetValidationException("所选参考缺失、版本或文件SHA256已变化");
        return row;
    }
    public async Task<object> LibraryReviewStatesAsync(CancellationToken ct=default)
    {
        var states=new List<object>();
        foreach(var version in await library.ListAsync(ct))
        {
            var approved=0;var rejected=0;var unavailable=0;
            foreach(var reference in version.Payload.References)
            {
                try { var row=await CheckReferenceAsync(version.Payload.CharacterId,reference,ct);if(ReferenceMetadata.Read(row.Text("metadataJson")).ReviewStatus=="Approved")approved++; }
                catch(AssetValidationException ex){if(ex.Message.Contains("拒绝"))rejected++;else unavailable++;}
            }
            var review=await store.LatestAsync("LibraryReview",version.Id,ct);
            var decision=CharacterStoryStore.Text(review?.Payload,"decision","NeedReview");
            states.Add(new{versionId=version.Id,approved,total=version.Payload.References.Count,rejected,unavailable,decision,
                complete=CharacterLibraryService.Coverage(version.Payload.References).Complete,
                contentStatus=rejected>0||unavailable>0||decision=="Rejected"?"Rejected":decision=="Approved"&&approved==version.Payload.References.Count?"Approved":"NeedReview"});
        }
        return states;
    }
    public async Task<CharacterStoryRecord> ReviewVersionAsync(long versionId,StoryReviewInput input,string actor,CancellationToken ct)
    {
        if(input.Decision is not("Approved" or "Rejected" or "NeedReview"))throw new ArgumentException("版本审核决定无效");
        if(input.Decision!="NeedReview"&&!input.HumanConfirmed)throw new ArgumentException("版本批准或拒绝须由有权限的操作员明确确认人工检查");
        var version=await library.GetAsync(versionId,ct);
        if(input.Decision=="Approved")
        {
            foreach(var reference in version.Payload.References)
            { var row=await CheckReferenceAsync(version.Payload.CharacterId,reference,ct);if(ReferenceMetadata.Read(row.Text("metadataJson")).ReviewStatus!="Approved")throw new ArgumentException("素材仍待人工审核，不能仅凭九图齐全批准版本"); }
        }
        return await store.AppendAsync("LibraryReview",versionId,version.OwnerProjectId,CharacterStoryStore.Object(new{schema="library-review-v1",requestId=CharacterStoryStore.RequestKey(input.IdempotencyKey),versionId,versionSha256=version.Sha256,decision=input.Decision,note=CharacterStoryStore.Required(input.Note,"审核说明"),reviewer=actor}),actor,ct);
    }
    public async Task<object> CastStateAsync(long projectId,long? episodeId,CancellationToken ct)
    {
        _=await Parent("projects",projectId,ct);
        var project=await store.LatestAsync("ProjectCast",projectId,ct);
        CharacterStoryRecord? episode=null;
        if(episodeId is{} eid)
        { var row=await Parent("episodes",eid,ct);if(row.Long("projectId")!=projectId)throw new ArgumentException("集不属于所选项目");episode=await store.LatestAsync("EpisodeCast",eid,ct); }
        return new{project,episode,requiresEpisodeSnapshot=episodeId is not null&&episode is null,projectChanged=episode is not null&&project is not null&&CharacterStoryStore.Number(episode.Payload,"sourceCastId")!=project.Id,
            explanation="本集与镜头固定选定版本，人物库或项目选角更新不会自动替换历史绑定"};
    }
    public async Task<CharacterStoryRecord> SaveProjectCastAsync(long projectId,StoryCastInput input,string actor,CancellationToken ct)
    {
        _=await Parent("projects",projectId,ct);
        if(input.Roles is null || input.Roles.Count is <1 or >12 || input.Roles.Any(r=>r is null||string.IsNullOrWhiteSpace(r.Role)) || input.Roles.Select(r=>r.Role.Trim()).Distinct(StringComparer.OrdinalIgnoreCase).Count()!=input.Roles.Count)throw new ArgumentException("选择1–12个不同剧情角色名");
        if(input.AudioStrategy is not("NativeH3" or "ExistingDubbing" or "PostDubbing"))throw new ArgumentException("请选择原生声音、已有配音或后期配音策略");
        var roles=new JsonArray();
        foreach(var role in input.Roles)
        {
            var name=CharacterStoryStore.Required(role.Role,"剧情角色名",100);var version=await library.GetAsync(role.VersionId,ct);await library.RequireNotRejectedAsync(version.Id,ct);
            roles.Add(CharacterStoryStore.Object(new{role=name,versionId=version.Id,versionSha256=version.Sha256,characterId=version.Payload.CharacterId,name=version.Payload.CharacterName,outfitLabel=version.Payload.Label}));
        }
        return await store.AppendAsync("ProjectCast",projectId,projectId,new JsonObject{["schema"]="project-cast-v1",["requestId"]=CharacterStoryStore.RequestKey(input.IdempotencyKey),["roles"]=roles,["audioStrategy"]=input.AudioStrategy},actor,ct);
    }
    public async Task<CharacterStoryRecord> SnapshotEpisodeAsync(long episodeId,string requestId,string actor,CancellationToken ct)
    {
        var episode=await Parent("episodes",episodeId,ct);var projectId=episode.Long("projectId");var cast=await store.LatestAsync("ProjectCast",projectId,ct)??throw new ArgumentException("请先保存项目选角");
        return await store.AppendAsync("EpisodeCast",episodeId,projectId,new JsonObject{["schema"]="episode-cast-v1",["requestId"]=CharacterStoryStore.RequestKey(requestId),["sourceCastId"]=cast.Id,["sourceCastSha256"]=cast.Sha256,["roles"]=cast.Payload["roles"]!.DeepClone(),["audioStrategy"]=cast.Payload["audioStrategy"]!.DeepClone()},actor,ct);
    }
    private static LibraryReference Reference(JsonNode node)=>node.Deserialize<LibraryReference>(Json)??throw new AssetValidationException("参考快照无效");
    public const string LegacyHeadshotMode="ApprovedLegacyHeadshotV1";
    // Old library records did not record a framing. A caller may explicitly
    // select an approved FRONT portrait for a single close-up; it never stands
    // in for a full-body or wardrobe reference, or for a two-person scene.
    public static LibraryReference SelectExplicitLegacyHeadshot(LibraryVersion version,StoryShotInput input,StoryActorInput actor)
    {
        if(actor.LegacyHeadshotReferenceId is not >0 || version.Payload.Schema!=CharacterLibraryService.Schema || input.ShotFraming!="closeUp" || input.Actors.Count!=1 || input.SceneVersionId is not null || actor.View!="front" || actor.Framing!="closeUp")
            throw new ArgumentException("旧版正面参考只能明确用于单人面部近景；全身、多人及固定场景仍需对应的完整参考");
        return version.Payload.References.SingleOrDefault(r=>r.ReferenceId==actor.LegacyHeadshotReferenceId && r.View=="front" && r.Framing is null)
            ?? throw new ArgumentException("明确指定的旧版正面参考不属于当前人物版本，不能自动换图");
    }
    private static IEnumerable<LibraryReference> BoundReferences(JsonNode actor)
    {
        var names=CharacterStoryStore.Text(actor,"referenceMode")==LegacyHeadshotMode?new[]{"reference","identity"}:new[]{"reference","identity","outfitReference"};
        foreach(var name in names)yield return Reference(actor[name]??throw new AssetValidationException("人物参考快照缺失："+name));
    }
    private async Task RequireApprovedLegacyReferenceAsync(long characterId,LibraryReference reference,CancellationToken ct)
    {
        var row=await CheckReferenceAsync(characterId,reference,ct);
        if(ReferenceMetadata.Read(row.Text("metadataJson")).ReviewStatus!="Approved")throw new AssetValidationException("旧版正面参考须已明确审核通过；不能将待审图片当作已批准");
    }
    public async Task<CharacterStoryRecord> SaveShotAsync(long shotId,StoryShotInput input,string actor,CancellationToken ct)
    {
        var shot=await Parent("shots",shotId,ct);var cast=await store.GetAsync(input.EpisodeCastId,"EpisodeCast",ct);
        if(cast.EntityId!=shot.Long("episodeId")||cast.ProjectId!=shot.Long("projectId"))throw new ArgumentException("集选角与镜头归属不符");
        if(input.Actors is null || input.Actors.Count is <1 or >2 || input.Actors.Any(a=>a is null||string.IsNullOrWhiteSpace(a.Role)) || input.Actors.Select(a=>a.Role).Distinct().Count()!=input.Actors.Count)throw new ArgumentException("本路线支持一人或两个不同角色，须分别绑定");
        if(input.ShotFraming is not("closeUp" or "medium" or "fullBody" or "twoShot"))throw new ArgumentException("镜头景别无效");
        var actors=new JsonArray();
        foreach(var selected in input.Actors)
        {
            if(input.ShotFraming=="closeUp"&&selected.Framing!="closeUp"||input.ShotFraming is "fullBody" or "twoShot"&&selected.Framing!="fullBody")throw new ArgumentException("面部近景须明确选择近景参考；全身/双人镜头须选择全身参考，不自动替换其他景别");
            var role=cast.Payload["roles"]!.AsArray().FirstOrDefault(r=>CharacterStoryStore.Text(r,"role")==selected.Role)??throw new ArgumentException("角色不在本集已固定选角中");
            var version=await library.GetAsync(CharacterStoryStore.Number(role,"versionId"),ct);
            if(version.Sha256!=CharacterStoryStore.Text(role,"versionSha256"))throw new AssetValidationException("选角版本SHA不符");
            await library.RequireNotRejectedAsync(version.Id,ct);
            var legacy=selected.LegacyHeadshotReferenceId is not null;
            var reference=legacy?SelectExplicitLegacyHeadshot(version,input,selected):CharacterLibraryService.SelectReference(version,selected.View,selected.Framing);
            var identity=legacy?reference:CharacterLibraryService.SelectReference(version,"front","closeUp");
            var outfit=legacy?null:CharacterLibraryService.SelectReference(version,"front","fullBody");
            if(legacy)await RequireApprovedLegacyReferenceAsync(version.Payload.CharacterId,reference,ct);
            else foreach(var r in new[]{reference,identity,outfit!}.Distinct())await CheckReferenceAsync(version.Payload.CharacterId,r,ct);
            var position=selected.Position;
            if(position is not("left" or "center" or "right"))throw new ArgumentException("站位须为画面左、中或右");
            var actorRecord=new JsonObject{["role"]=selected.Role,["versionId"]=version.Id,["versionSha256"]=version.Sha256,["characterId"]=version.Payload.CharacterId,["name"]=version.Payload.CharacterName,
                ["outfit"]=version.Payload.Outfit,["fixedPrompt"]=version.Payload.FixedPrompt,["view"]=selected.View,["framing"]=selected.Framing,["position"]=position,["action"]=selected.Action,
                ["reference"]=JsonSerializer.SerializeToNode(reference,Json),["identity"]=JsonSerializer.SerializeToNode(identity,Json)};
            if(legacy){actorRecord["referenceMode"]=LegacyHeadshotMode;actorRecord["legacyHeadshotReferenceId"]=reference.ReferenceId;}
            else actorRecord["outfitReference"]=JsonSerializer.SerializeToNode(outfit,Json);
            actors.Add(actorRecord);
        }
        if(actors.Count==2&&(actors.Select(a=>CharacterStoryStore.Number(a,"characterId")).Distinct().Count()!=2||actors.Select(a=>CharacterStoryStore.Text(a,"position")).Distinct().Count()!=2))throw new ArgumentException("双人镜头须绑定两个人物和不同站位");
        var payload=new JsonObject{["schema"]="story-shot-v1",["requestId"]=CharacterStoryStore.RequestKey(input.IdempotencyKey),["shotId"]=shotId,["episodeId"]=shot.Long("episodeId"),["episodeCastId"]=cast.Id,["episodeCastSha256"]=cast.Sha256,
            ["actors"]=actors,["shotFraming"]=input.ShotFraming,["scene"]=CharacterStoryStore.Required(input.Scene,"剧情场景"),["action"]=CharacterStoryStore.Required(input.Action,"镜头动作"),["camera"]=CharacterStoryStore.Required(input.Camera,"机位与镜头"),["props"]=input.Props,["audioStrategy"]=cast.Payload["audioStrategy"]!.DeepClone()};
        if(input.KeyframeStartOnly)payload["keyframeStartOnly"]=true;
        if(input.SceneVersionId is{} sceneId)
        {var binding=await (sceneReferences??throw new AssetValidationException("场景绑定服务未就绪")).BindingAsync(sceneId,cast.ProjectId,ct);CharacterSceneService.RequireFixedComposition(binding,payload);payload["sceneBinding"]=binding;}
        var saved=await store.AppendAsync("ShotCast",shotId,cast.ProjectId,payload,actor,ct);
        // Existing Shot fields remain the editable story surface; the ledger is
        // the pinned actor/reference context used by this explicit preview mode.
        await db.ExecuteAsync("UPDATE shots SET character_ids_json=@ids,action=@action,camera_type=@camera WHERE id=@id",c=>{StudioDb.Add(c,"@ids",JsonSerializer.Serialize(actors.Select(a=>CharacterStoryStore.Number(a,"characterId"))));StudioDb.Add(c,"@action",input.Action);StudioDb.Add(c,"@camera",input.Camera);StudioDb.Add(c,"@id",shotId);},ct);
        return saved;
    }
    public async Task<object> ShotStateAsync(long shotId,CancellationToken ct)
    {
        _=await Parent("shots",shotId,ct);var plans=await store.RowsAsync("ShotCast",shotId,ct);
        var tasks=await db.QueryAsync(@"SELECT t.id,t.status,t.task_type,t.error_message,t.created_at,t.input_json FROM generation_tasks t
            WHERE JSON_UNQUOTE(JSON_EXTRACT(t.input_json,'$.parameters.storyPipeline.shotId'))=@shot ORDER BY t.id DESC LIMIT 60",c=>StudioDb.Add(c,"@shot",shotId.ToString()),ct);
        var rows=new List<object>();
        foreach(var task in tasks)
        { var review=await store.LatestAsync("KeyframeReview",task.Long("id"),ct);rows.Add(new{id=task.Long("id"),status=task.Text("status"),taskType=task.Text("taskType"),error=task.Text("errorMessage"),createdAt=task.GetValueOrDefault("createdAt"),review,parameters=JsonNode.Parse(task.Text("inputJson")??"{}")?["parameters"]}); }
        return new{plans,tasks=rows,mode="ReviewPreview",contentReview="NeedReview",publication="Blocked"};
    }
    private async Task<CharacterStoryRecord> Plan(long id,CancellationToken ct)
    {
        var plan=await store.GetAsync(id,"ShotCast",ct);var shot=await Parent("shots",plan.EntityId,ct);
        if(shot.Long("projectId")!=plan.ProjectId||shot.Long("episodeId")!=CharacterStoryStore.Number(plan.Payload,"episodeId"))throw new AssetValidationException("镜头归属已变化");
        var cast=await store.GetAsync(CharacterStoryStore.Number(plan.Payload,"episodeCastId"),"EpisodeCast",ct);
        if(cast.Sha256!=CharacterStoryStore.Text(plan.Payload,"episodeCastSha256"))throw new AssetValidationException("集选角快照已变化");
        if(plan.Payload["sceneBinding"] is JsonObject scene)
        {
            var current=await (sceneReferences??throw new AssetValidationException("场景绑定服务未就绪")).BindingAsync(CharacterStoryStore.Number(scene,"versionId"),plan.ProjectId,ct);
            if(!CharacterStoryStore.Equal(JsonSerializer.SerializeToElement(scene),JsonSerializer.SerializeToElement(current)))throw new AssetValidationException("场景快照、基准文件或人物区域发生变化");
            CharacterSceneService.RequireFixedComposition(scene,plan.Payload);
        }
        foreach(var a in plan.Payload["actors"]!.AsArray())
        {
            var version=await library.GetAsync(CharacterStoryStore.Number(a,"versionId"),ct);await library.RequireNotRejectedAsync(version.Id,ct);
            if(version.Sha256!=CharacterStoryStore.Text(a,"versionSha256"))throw new AssetValidationException("人物版本SHA已变化");
            if(CharacterStoryStore.Text(a,"referenceMode")==LegacyHeadshotMode)
            {
                var legacyId=CharacterStoryStore.Number(a,"legacyHeadshotReferenceId");
                var input=new StoryShotInput{ShotFraming=CharacterStoryStore.Text(plan.Payload,"shotFraming"),SceneVersionId=plan.Payload["sceneBinding"] is null?null:1,Actors=[new StoryActorInput{View=CharacterStoryStore.Text(a,"view"),Framing=CharacterStoryStore.Text(a,"framing"),LegacyHeadshotReferenceId=legacyId}]};
                if(plan.Payload["actors"]!.AsArray().Count!=1 || a!["outfitReference"] is not null || a["reference"] is null || a["identity"] is null)throw new AssetValidationException("旧版近景计划不得伪造全身参考、遗漏身份参考或用于多人");
                var expected=SelectExplicitLegacyHeadshot(version,input,input.Actors[0]);
                if(Reference(a["reference"]!)!=expected||Reference(a["identity"]!)!=expected)throw new AssetValidationException("旧版近景参考与冻结版本不一致");
                await RequireApprovedLegacyReferenceAsync(version.Payload.CharacterId,expected,ct);
            }
            else
            {
                if(a!["referenceMode"] is not null || a["legacyHeadshotReferenceId"] is not null)throw new AssetValidationException("未知或不完整的旧版参考模式");
                foreach(var reference in BoundReferences(a))await CheckReferenceAsync(version.Payload.CharacterId,reference,ct);
            }
        }
        return plan;
    }
    private async Task<(long Id,string Path,string Hash)> Workflow(string file,CancellationToken ct)
    {
        var row=(await repository.WorkflowsAsync(ct)).FirstOrDefault(r=>Path.GetFileName(r.Text("path"))==file)??throw new AssetValidationException("明确的剧情工作流未登记，请先扫描");
        if(!paths.TryResolveExistingWorkflow(row.Text("path"),out var full,out _))throw new AssetValidationException("剧情工作流不存在");
        return(row.Long("id"),full,(await ffmpeg.Sha256Async(full,ct))!);
    }
    private async Task<(JsonObject Task,JsonObject Result)> TaskOutput(long taskId,CancellationToken ct)
    {
        var row=(await db.QueryAsync("SELECT * FROM generation_tasks WHERE id=@id",c=>StudioDb.Add(c,"@id",taskId),ct)).FirstOrDefault()??throw new ArgumentException("来源任务不存在");
        if(row.Text("status")!="Succeeded")throw new AssetValidationException("来源任务尚未成功，保留检查点后继续等待");
        var sourceInput=JsonNode.Parse(row.Text("inputJson")??"{}");var extension=CharacterStoryStore.Text(sourceInput?["parameters"]?[Marker],"kind")=="Video"?".mp4":".png";
        var output=(await db.QueryAsync("SELECT a.* FROM assets a JOIN generation_results r ON r.asset_id=a.id WHERE r.task_id=@id ORDER BY a.id",c=>StudioDb.Add(c,"@id",taskId),ct))
            .FirstOrDefault(r=>Path.GetExtension(r.Text("path"))==extension)??throw new AssetValidationException("来源任务没有受控媒体输出");
        if(!paths.TryResolveExisting(output.Text("relativePath")??output.Text("path"),out var full,out var relative))throw new AssetValidationException("来源输出已丢失");
        var hash=await ffmpeg.Sha256Async(full,ct);
        if(hash!=output.Text("sha256"))throw new AssetValidationException("来源输出SHA已变化");
        return(new JsonObject{["id"]=taskId,["projectId"]=row.Long("projectId"),["input"]=JsonNode.Parse(row.Text("inputJson")??"{}")},new JsonObject{["path"]=relative,["sha256"]=hash,["assetId"]=output.Long("id")});
    }
    public async Task<TaskInput> BuildAsync(string kind,StoryRenderInput input,CancellationToken ct=default)
    {
        var plan=await Plan(input.PlanId,ct);var key=CharacterStoryStore.RequestKey(input.IdempotencyKey);
        if(input.Seed<0)throw new ArgumentException("种子须为非负整数");
        TaskInput task;string workflowHash;string firstHash;var inputHashes=new JsonObject();JsonObject? continuation=null;
        if(kind=="Keyframe")
        {
            var actors=plan.Payload["actors"]!.AsArray();var close=CharacterStoryStore.Text(plan.Payload,"shotFraming")=="closeUp";var lockedScene=plan.Payload["sceneBinding"] is JsonObject;var file=lockedScene?CharacterSceneService.WorkflowFor(plan.Payload["sceneBinding"]!):actors.Count==2?FourWorkflow:close?"character_pack_klein4b_single_api.json":"character_pack_klein4b_dual_api.json";
            foreach(var a in actors)foreach(var r in BoundReferences(a!))inputHashes[r.AssetPath]=r.Sha256;
            var workflow=await Workflow(file,ct);workflowHash=workflow.Hash;
            var first=actors[0]!;var primary=Reference(first[CharacterStoryStore.Text(first,"framing")=="closeUp"?"reference":"identity"]!);
            var slots=new JsonObject{["firstFrame"]=primary.AssetPath};firstHash=primary.Sha256;
            if(!close||actors.Count==2)slots["wardrobeReference"]=Reference(first[CharacterStoryStore.Text(first,"framing")=="fullBody"?"reference":"outfitReference"]!).AssetPath;
            if(actors.Count==2)
            { var second=actors[1]!;slots["secondIdentity"]=Reference(second[CharacterStoryStore.Text(second,"framing")=="closeUp"?"reference":"identity"]!).AssetPath;slots["secondWardrobe"]=Reference(second[CharacterStoryStore.Text(second,"framing")=="fullBody"?"reference":"outfitReference"]!).AssetPath; }
            if(lockedScene){var source=plan.Payload["sceneBinding"]!["payload"]!["source"]!;slots["sceneReference"]=CharacterStoryStore.Text(source,"path");inputHashes[CharacterStoryStore.Text(source,"path")]=CharacterStoryStore.Text(source,"sha256");}
            var prompt=KeyframePrompt(plan.Payload)+Adjustment(input.PromptAdjustment);
            task=new TaskInput{ProjectId=plan.ProjectId,TaskType="Keyframe",WorkflowId=workflow.Id,InputImagePath=primary.AssetPath,ResourceClass="GPU",MaxRetries=0,Stage="Story-Keyframe-Preview",IdempotencyKey=key,
                Parameters=JsonSerializer.SerializeToElement(new{workflowVersion=lockedScene?CharacterSceneService.VersionFor(plan.Payload["sceneBinding"]!):actors.Count==2?"character-story-klein4b-four-1536-v1":"character-pack-klein4b-"+(close?"single":"dual")+"-1536-v1",positive=prompt,negative="",inputSlots=slots,seed=input.Seed,width=1536,height=864,steps=4,cfg=1,contentReview="NeedReview"},Json)};
        }
        else if(kind=="Video")
        {
            if(input.Profile is not("baseline480" or "quality768" or "native1080"))throw new ArgumentException("剧情试片请选择已验证的480p、768p或原生1080p规格");
            var profile=MiniMaxLocalService.ResolveProfile(input.Profile);var workflow=await Workflow(profile.WorkflowFileName,ct);workflowHash=workflow.Hash;
            var isContinuation=input.ContinuationSourceTaskId is not null||input.ContinuationReviewId is not null||input.ContinuationFramePath is not null||input.ContinuationFrameSha256 is not null;
            string firstPath;long dependency;
            if(!isContinuation)
            {
                var (source,result)=await TaskOutput(input.KeyframeTaskId,ct);
                var marker=source["input"]?["parameters"]?[Marker];
                if(CharacterStoryStore.Number(source,"projectId")!=plan.ProjectId || CharacterStoryStore.Number(marker,"planId")!=plan.Id || CharacterStoryStore.Text(marker,"kind")!="Keyframe" || !CharacterStoryStore.Text(result,"path").EndsWith(".png"))throw new AssetValidationException("必须使用本镜头计划实际生成的剧情关键帧，不能替换人物参考图路径");
                var review=await store.GetAsync(input.ReviewId,"KeyframeReview",ct);var latest=await store.LatestAsync("KeyframeReview",input.KeyframeTaskId,ct);
                if(review.EntityId!=input.KeyframeTaskId || latest?.Id!=review.Id || CharacterStoryStore.Text(review.Payload,"decision")!="Passed" || CharacterStoryStore.Text(review.Payload,"sha256")!=CharacterStoryStore.Text(result,"sha256"))throw new AssetValidationException("静态关键帧尚未检查通过或已被后续审核撤回，不能进入视频");
                firstPath=CharacterStoryStore.Text(result,"path");firstHash=CharacterStoryStore.Text(result,"sha256");dependency=input.KeyframeTaskId;
            }
            else
            {
                if(input.ContinuationSourceTaskId is not >0||input.ContinuationReviewId is not >0||string.IsNullOrWhiteSpace(input.ContinuationFramePath)||string.IsNullOrWhiteSpace(input.ContinuationFrameSha256)||input.KeyframeTaskId!=0||input.ReviewId!=0)throw new ArgumentException("尾帧续接须明确指定前一视频、检查记录、尾帧路径和哈希，不与关键帧入口混用");
                var (source,result)=await TaskOutput(input.ContinuationSourceTaskId.Value,ct);var marker=source["input"]?["parameters"]?[Marker];
                if(CharacterStoryStore.Text(marker,"kind")!="Video"||CharacterStoryStore.Number(source,"projectId")!=plan.ProjectId||CharacterStoryStore.Number(marker,"episodeId")!=CharacterStoryStore.Number(plan.Payload,"episodeId"))throw new AssetValidationException("续接来源须是同一集实际剧情视频");
                var previous=await Plan(CharacterStoryStore.Number(marker,"planId"),ct);
                var previousShot=await Parent("shots",previous.EntityId,ct);var currentShot=await Parent("shots",plan.EntityId,ct);
                if(previous.EntityId==plan.EntityId||previousShot.Int("shotNumber")+1!=currentShot.Int("shotNumber"))throw new AssetValidationException("仅允许接续同一集的上一顺序镜头");
                RequireContinuousComposition(previous.Payload,plan.Payload);
                var review=await store.GetAsync(input.ContinuationReviewId.Value,"KeyframeReview",ct);var latest=await store.LatestAsync("KeyframeReview",input.ContinuationSourceTaskId.Value,ct);
                if(review.EntityId!=input.ContinuationSourceTaskId.Value||latest?.Id!=review.Id||CharacterStoryStore.Text(review.Payload,"decision")!="Passed"||CharacterStoryStore.Text(review.Payload,"sha256")!=CharacterStoryStore.Text(result,"sha256"))throw new AssetValidationException("前一视频未检查通过或检查已撤回，不能续接");
                if(!paths.TryResolveExisting(CharacterStoryStore.Text(result,"path"),out var videoFull,out _)||!paths.TryResolveExisting(input.ContinuationFramePath,out var frameFull,out firstPath)||!Path.GetExtension(frameFull).Equals(".png",StringComparison.OrdinalIgnoreCase))throw new AssetValidationException("续接视频或尾帧缺失");
                var probe=await ffmpeg.ProbeAsync(videoFull,ct);var frameProbe=await ffmpeg.ProbeAsync(frameFull,ct);
                if(probe?.FrameCount!=124||probe.Fps!=24||probe.Width!=profile.Width||probe.Height!=profile.Height||frameProbe?.Width!=profile.Width||frameProbe.Height!=profile.Height)throw new AssetValidationException("续接视频、尾帧和选择的H3规格不一致");
                firstHash=(await ffmpeg.Sha256Async(frameFull,ct))!;
                if(!string.Equals(firstHash,input.ContinuationFrameSha256,StringComparison.OrdinalIgnoreCase)||!await ffmpeg.MatchesDecodedLastFrameAsync(videoFull,frameFull,probe.FrameCount.Value,ct))throw new AssetValidationException("指定图片不是前一视频的实际最后一帧或文件SHA已变化");
                var sourceHash=CharacterStoryStore.Text(result,"sha256");inputHashes[CharacterStoryStore.Text(result,"path")]=sourceHash;dependency=input.ContinuationSourceTaskId.Value;
                continuation=CharacterStoryStore.Object(new{sourceTaskId=dependency,sourcePlanId=previous.Id,sourceVideoPath=CharacterStoryStore.Text(result,"path"),sourceVideoSha256=sourceHash,sourceReviewId=review.Id,frameIndex=probe.FrameCount.Value-1,framePath=firstPath,frameSha256=firstHash});
            }
            inputHashes[firstPath]=firstHash;
            var prompt=(isContinuation?VideoPrompt(plan.Payload).Replace("Animate the CONFIRMED story keyframe.","Continue from the CHECKED FINAL FRAME of the previous shot; start with the exact pose, expression and composition.",StringComparison.Ordinal):VideoPrompt(plan.Payload))+Adjustment(input.PromptAdjustment);
            task=MiniMaxLocalService.BuildTask(new MiniMaxLocalInput(plan.ProjectId,prompt,firstPath,input.Seed,input.Profile),workflow.Id,"story-plan:"+plan.Id,key);
            task.DependencyTaskId=dependency;task.Stage=isContinuation?"Story-H3-Continuous-Preview":"Story-H3-Review-Preview";
        }
        else throw new ArgumentException("剧情阶段无效");
        var parameters=JsonSerializer.SerializeToNode(task.Parameters!.Value)!.AsObject();
        if(plan.Payload["sceneBinding"] is JsonObject binding)parameters[kind=="Keyframe"?"sceneLock":"sceneContext"]=binding.DeepClone();
        parameters[Marker]=CharacterStoryStore.Object(new{schema="story-pipeline-v1",mode="ReviewPreview",kind,planId=plan.Id,planSha256=plan.Sha256,shotId=plan.EntityId,episodeId=CharacterStoryStore.Number(plan.Payload,"episodeId"),workflowSha256=workflowHash,inputSha256=firstHash,inputHashes,render=input});
        if(continuation is not null)parameters[Marker]!["continuation"]=continuation;
        parameters["audioStrategy"]=CharacterStoryStore.Text(plan.Payload,"audioStrategy");task.Parameters=JsonSerializer.SerializeToElement(parameters,Json);
        return task;
    }
    private static void RequireContinuousComposition(JsonObject previous,JsonObject current)
    {
        foreach(var name in new[]{"episodeId","shotFraming","scene","camera","props","audioStrategy"})
            if(!JsonNode.DeepEquals(previous[name],current[name]))throw new AssetValidationException("续接必须保持同一场景、镜头、道具及音频策略；切镜或换场景须重新制作关键帧");
        if(!JsonNode.DeepEquals(previous["sceneBinding"],current["sceneBinding"]))throw new AssetValidationException("续接场景版本不一致");
        var a=previous["actors"]!.AsArray();var b=current["actors"]!.AsArray();if(a.Count!=b.Count)throw new AssetValidationException("续接人物数量变化，须重新制作关键帧");
        for(var i=0;i<a.Count;i++)foreach(var key in new[]{"role","versionId","versionSha256","characterId","position","view","framing","reference","identity","outfitReference","referenceMode","legacyHeadshotReferenceId"})
            if(!JsonNode.DeepEquals(a[i]?[key],b[i]?[key]))throw new AssetValidationException("续接人物、造型、方向或站位发生变化");
    }
    public async Task ValidateTaskAsync(TaskInput input,CancellationToken ct=default)
    {
        if(input.Parameters is not {ValueKind:JsonValueKind.Object} p || !p.TryGetProperty(Marker,out var m))return;
        if(m.ValueKind!=JsonValueKind.Object)throw new AssetValidationException("剧情调用快照无效");
        var render=m.GetProperty("render").Deserialize<StoryRenderInput>(Json)??throw new AssetValidationException("剧情请求无效");
        var expected=await BuildAsync(m.GetProperty("kind").GetString()!,render,ct);
        await RequireSubmissionBudgetAsync(m.GetProperty("kind").GetString()!,render,ct);
        if(input.ProjectId!=expected.ProjectId || input.ShotId is not null || input.EpisodeId is not null || input.ProductionRunId is not null || input.WorkflowId!=expected.WorkflowId || input.TaskType!=expected.TaskType
            || input.InputImagePath!=expected.InputImagePath || input.DependencyTaskId!=expected.DependencyTaskId || input.ResourceClass!="GPU" || input.MaxRetries!=0 || input.LoraIds is {Count:>0}
            || input.Stage!=expected.Stage || !CharacterStoryStore.Equal(p,expected.Parameters!.Value))throw new AssetValidationException("剧情计划、人物、场景、输入图、工作流或送审模式被篡改");
    }
    public async Task<object> SubmitAsync(string kind,StoryRenderInput input,TaskSubmissionPreflightService preflight,GenerationQueue queue,CancellationToken ct)
    {
        var submissionPlan=await store.GetAsync(input.PlanId,"ShotCast",ct);
        await using var connection=await db.OpenAsync(ct);await using var tx=await connection.BeginTransactionAsync(System.Data.IsolationLevel.ReadCommitted,ct);
        // All plan versions for the same shot share a stable submission lock.
        await using(var shotGuard=new MySqlConnector.MySqlCommand("SELECT id FROM shots WHERE id=@id FOR UPDATE",connection,tx))
        {StudioDb.Add(shotGuard,"@id",submissionPlan.EntityId);if(await shotGuard.ExecuteScalarAsync(ct) is null)throw new ArgumentException("镜头不存在");}
        await using(var guard=new MySqlConnector.MySqlCommand("SELECT id FROM entity_versions WHERE id=@id AND entity_type='ShotCast' FOR UPDATE",connection,tx))
        {StudioDb.Add(guard,"@id",input.PlanId);if(await guard.ExecuteScalarAsync(ct) is null)throw new ArgumentException("镜头人物计划不存在");}
        var task=await BuildAsync(kind,input,ct);await RequireSubmissionBudgetAsync(kind,input,ct);
        var check=await preflight.CheckAsync(task,ct,businessSubmission:true);if(!check.Passed)throw new AssetValidationException("剧情预检未通过："+string.Join("；",check.Issues));
        var existing=await repository.TaskByIdempotencyKeyAsync(input.IdempotencyKey,ct);var id=await repository.CreateTaskAsync(task,ct);
        await tx.CommitAsync(ct);if(existing is null||existing.Text("status")=="Pending")queue.Enqueue(id);
        return new{id,created=existing is null,mode="ReviewPreview",contentReview="NeedReview",publication="Blocked"};
    }
    public async Task RequireSubmissionBudgetAsync(string kind,StoryRenderInput input,CancellationToken ct)
    {
        if(await repository.TaskByIdempotencyKeyAsync(input.IdempotencyKey,ct) is not null)return;
        var plan=await Plan(input.PlanId,ct);
        // Once a shot opts into start-only plans, switching to an older plan
        // cannot reset that shot's initial-plus-two-repairs limit.
        var shotOptedIn=await db.ScalarAsync("SELECT COUNT(*) FROM entity_versions WHERE entity_type='ShotCast' AND entity_id=@shot AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.keyframeStartOnly'))='true'",c=>StudioDb.Add(c,"@shot",plan.EntityId),ct);
        var perShot=plan.Payload["sceneBinding"] is not null||Convert.ToInt32(shotOptedIn)>0;
        var scope=perShot?"$.parameters.storyPipeline.shotId":"$.parameters.storyPipeline.planId";
        var count=await db.ScalarAsync("SELECT COUNT(*) FROM generation_tasks WHERE JSON_UNQUOTE(JSON_EXTRACT(input_json,@scope))=@entity AND JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.parameters.storyPipeline.kind'))=@kind",c=>{StudioDb.Add(c,"@scope",scope);StudioDb.Add(c,"@entity",(perShot?plan.EntityId:input.PlanId).ToString());StudioDb.Add(c,"@kind",kind);},ct);
        if(Convert.ToInt32(count)>=3)throw new AssetValidationException("本计划该阶段已达到初次＋两次定向修复上限；保留失败证据并交由人工决定");
        if(Convert.ToInt32(count)>0)
        {
            if(input.RepairOfTaskId is null||string.IsNullOrWhiteSpace(input.ChangeReason))throw new ArgumentException("重做只针对失败镜头，请提供原任务和具体改变原因");
            var original=(await db.QueryAsync("SELECT input_json,status FROM generation_tasks WHERE id=@id",c=>StudioDb.Add(c,"@id",input.RepairOfTaskId),ct)).FirstOrDefault()??throw new ArgumentException("原任务不存在");
            var old=JsonNode.Parse(original.Text("inputJson")??"{}")?["parameters"]?[Marker];
            if((perShot?CharacterStoryStore.Number(old,"shotId")!=plan.EntityId:CharacterStoryStore.Number(old,"planId")!=input.PlanId)||CharacterStoryStore.Text(old,"kind")!=kind)throw new ArgumentException("不能用其他镜头任务作为修复来源");
            var review=await store.LatestAsync("KeyframeReview",input.RepairOfTaskId.Value,ct);
            if(original.Text("status")!="Failed"&&CharacterStoryStore.Text(review?.Payload,"decision")!="Failed")throw new ArgumentException("先记录具体内容失败，再定向修复");
            if(CharacterStoryStore.Number(old?["render"],"seed")==input.Seed&&CharacterStoryStore.Text(old?["render"],"promptAdjustment").Trim()== (input.PromptAdjustment??"").Trim())throw new ArgumentException("修复须改变相关种子或定向提示词，并说明改变原因");
        }
    }
    public async Task<CharacterStoryRecord> ReviewTaskAsync(StoryReviewInput input,string actor,CancellationToken ct)
    {
        if(input.Decision is not("Passed" or "Failed" or "NeedReview")||input.Scope is not("PreviewInspection" or "HumanReview"))throw new ArgumentException("请明确区分试片检查和人工最终审核");
        if(input.Scope=="HumanReview"&&!input.HumanConfirmed)throw new ArgumentException("人工审核需操作员明确确认；助手检查应使用PreviewInspection并保留内容待审");
        var (task,result)=await TaskOutput(input.TaskId,ct);var marker=task["input"]?["parameters"]?[Marker]??throw new ArgumentException("不是剧情送审任务");
        var plan=await Plan(CharacterStoryStore.Number(marker,"planId"),ct);
        return await store.AppendAsync("KeyframeReview",input.TaskId,plan.ProjectId,CharacterStoryStore.Object(new{schema="story-inspection-v1",requestId=CharacterStoryStore.RequestKey(input.IdempotencyKey),taskId=input.TaskId,planId=plan.Id,sha256=CharacterStoryStore.Text(result,"sha256"),assetPath=CharacterStoryStore.Text(result,"path"),decision=input.Decision,scope=input.Scope,note=CharacterStoryStore.Required(input.Note,"具体检查说明"),reviewer=actor,identityScore=(double?)null,contentReview=input.Scope=="HumanReview"&&input.Decision=="Passed"?"HumanReviewed":"NeedReview",publication="Blocked"}),actor,ct);
    }
    public static string KeyframePrompt(JsonObject plan)
    {
        var actors=plan["actors"]!.AsArray();var framing=CharacterStoryStore.Text(plan,"shotFraming");
        var lines=new List<string>{"Create ONE coherent photorealistic STORY KEYFRAME, exactly "+actors.Count+" adult person(s). Replace the reference studio background with the specified story environment. Preserve the specific identities, ages, hairstyles and outfits. No collage, inset, extra person, text or logo."};
        for(var i=0;i<actors.Count;i++)
        { var a=actors[i]!;lines.Add(actors.Count==2?$"Image{1+i*2} defines person {i+1} IDENTITY; image{2+i*2} defines ONLY that person's WARDROBE. ":"Image1 defines the same person's identity. ");lines.Add($"Person {i+1}: preserve this reference person's facial identity, age and hairstyle. Position: picture {CharacterStoryStore.Text(a,"position")}. Starting action: {CharacterStoryStore.Text(a,"action")}. Keep each person's clothes on that same person. "+CharacterWorkshopService.Direction(CharacterStoryStore.Text(a,"view","front"))); }
        lines.Add("Framing: "+(framing=="closeUp"?"Tight face and shoulders, complete crown visible; only upper collar is shown.":framing=="fullBody"?"Complete standing figure, full crown, both hands, both complete shoes and visible floor with margin.":framing=="twoShot"?"Two-person medium composition, two distinct unobstructed faces, clear gap between bodies.":"Medium waist-up composition with clear face and natural body structure."));
        lines.Add("Scene: "+CharacterStoryStore.Text(plan,"scene"));
        if(plan["keyframeStartOnly"]?.GetValue<bool>()==true)
            lines.Add("This still shows only the initial state specified for each person above, before any later event or expression.");
        else lines.Add("Action starting state: "+CharacterStoryStore.Text(plan,"action"));
        lines.Add("Camera: "+CharacterStoryStore.Text(plan,"camera"));lines.Add("Props and relationships: "+CharacterStoryStore.Text(plan,"props"));
        if(plan["sceneBinding"] is not null)lines.Add("Image5 is the FIXED ROOM AND COMPOSITION reference, not an additional identity. Preserve its exact eye-level camera, bookshelf grid, book arrangements, wall outlet, warm gray wall and lighting. Person1 stays at picture left around x=0.33; person2 stays at picture right around x=0.68. Keep body size and position exactly as image5. Change only the requested small pose or gaze inside each person's own region. ONE WOMAN on LEFT in cream sweater/gray trousers and ONE MAN on RIGHT in navy shirt/beige trousers, exactly two DIFFERENT people. No swapping, extra limbs or replacement room. Background outside the two person regions is retained by an explicit compositor.");
        if(plan["sceneBinding"] is JsonObject sb&&CharacterSceneService.VersionFor(sb)==CharacterSceneService.MaskedWorkflowVersion)lines.Add("In Image5 the old HEADS have been deliberately blanked out to remove the old gaze direction. Retain its original body scale, clothing and relaxed arms, then replace the neutral head regions with the matching faces and hair from images1-4 in the REQUESTED directions. Do NOT reproduce neutral rectangles. Each requested nose/gaze direction overrides source portrait pose. This is a cropped standing medium two-shot, heads near y=50..300, waists near y=600, hands near y=730, bodies extending below the frame; do not shrink into full-body miniatures. Both people have exactly two arms and two hands, all four hands DOWN at their sides; no raised hand, no gesture, no extra hand near either hip.");
        return string.Join("\n",lines);
    }
    public static string Adjustment(string? value)=>string.IsNullOrWhiteSpace(value)?"":"\nTargeted correction while preserving bound identities/outfits: "+CharacterStoryStore.Required(value,"定向提示词",1000);
    public static string VideoPrompt(JsonObject plan)=>string.Join("\n",new[]{"Animate the CONFIRMED story keyframe. Preserve every person's face, age, hair, outfit, body structure and screen position. One continuous shot, no identity swap, no extra person.","Action: "+CharacterStoryStore.Text(plan,"action"),"Camera: "+CharacterStoryStore.Text(plan,"camera"),"Scene: "+CharacterStoryStore.Text(plan,"scene"),"Audio strategy: "+CharacterStoryStore.Text(plan,"audioStrategy")+(CharacterStoryStore.Text(plan,"audioStrategy")=="NativeH3"?". Natural matching native sound.":". No dialogue or vocal performance; delivery preview uses post-production/selected dubbing and will mute raw voices.")})+(plan["sceneBinding"] is null?"":"\nThe camera is rigidly locked. The room, bookshelf divisions, books, wall outlet and perspective remain stationary. Maintain the same screen positions and body scale. Only the explicitly requested small head/eye response moves; relaxed hands stay down. No speaking mouth motion or camera drift.");
}
