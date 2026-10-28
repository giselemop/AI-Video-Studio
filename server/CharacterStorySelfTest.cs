using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;

namespace VideoStudio.Server;

/// <summary>Real local read checks plus policy tests; never submits GPU work or writes approval records.</summary>
public static class CharacterStorySelfTest
{
    public static async Task<int> ReferencesAsync()
    {
        var root=StudioPaths.FindRoot();var cfg=new ConfigurationBuilder().AddJsonFile(Path.Combine(root,"config/appsettings.json")).Build();var settings=StudioPaths.Load(cfg,root);
        var folder=Path.Combine(settings.DataPath,"CharacterStory20261027");var fixture=JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(folder,"api-fixtures.json")))!;var cid=fixture["characterId"]!.GetValue<long>();
        var db=new StudioDb(settings,NullLogger<StudioDb>.Instance);var repository=new StudioRepository(db,NullLogger<StudioRepository>.Instance);var ffmpeg=new FfmpegService(settings,NullLogger<FfmpegService>.Instance);var paths=new AssetPathPolicy(settings,ffmpeg,NullLogger<AssetPathPolicy>.Instance);var library=new CharacterLibraryService(db,repository,paths,ffmpeg);var service=new CharacterStoryService(db,repository,new CharacterStoryStore(db),library,paths,ffmpeg);
        var owner=(await repository.QueryCharacterAsync(cid)).Single();if(owner.Text("name")!="接口验证人物草稿（未生成）")throw new InvalidOperationException("Fixture owner is not the labelled test character");
        var original=CharacterLibraryService.SelectReference(await library.GetAsync(4),"front","closeUp");paths.TryResolveExisting(original.AssetPath,out var source,out _);
        var fixtureFolder=Path.Combine(folder,"test-fixtures");Directory.CreateDirectory(fixtureFolder);var copy=Path.Combine(fixtureFolder,"existing-reference-copy.png");var missing=Path.Combine(fixtureFolder,"existing-reference-copy.missing-test");
        if(File.Exists(missing))throw new InvalidOperationException("Interrupted missing-file test retained its checkpoint; inspect before resuming");
        if(!File.Exists(copy))File.Copy(source,copy,false);
        if(await ffmpeg.Sha256Async(copy)!=original.Sha256)throw new InvalidOperationException("Existing fixture differs; do not overwrite unknown work");
        var row=(await repository.CharacterReferencesAsync(cid)).FirstOrDefault(r=>r.Text("kind")=="regression-file-policy");
        var rid=row?.Long("id")??await repository.AddCharacterReferenceAsync(cid,copy,new ReferenceInput{Kind="regression-file-policy",Stage="regression-test",Role="identity",ChangeReason="受控接口测试副本，复制既有参考，未生成新人物，禁止作为人物库素材或人工通过证据"});
        paths.TryResolveExisting(copy,out _,out var relative);var reference=new LibraryReference(rid,"front",relative,original.Sha256,1,"NeedReview","closeUp");var checks=new List<object>();
        async Task Reject(Func<Task> action,string name){var rejected=false;try{await action();}catch(AssetValidationException){rejected=true;}checks.Add(new{name,status=rejected?"Passed":"Failed"});if(!rejected)throw new InvalidOperationException(name);}
        var auditReady=Convert.ToInt32(await db.ScalarAsync("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='character_reference_reviews'"))==1;var rejectionWritten=false;
        try
        {
            await service.CheckReferenceAsync(cid,reference);checks.Add(new{name="controlled real-file fixture accepted before mutation",status="Passed"});
            await Reject(async()=>{await service.CheckReferenceAsync(19,reference);},"reference owned by another character rejected");
            await Reject(async()=>{await service.CheckReferenceAsync(cid,reference with{AssetVersion=2});},"wrong reference version rejected");
            await File.AppendAllTextAsync(copy,"\nSHA-drift-regression-test\n");
            await Reject(async()=>{await service.CheckReferenceAsync(cid,reference);},"actual changed file bytes rejected even with unchanged metadata");
            File.Copy(source,copy,true);
            File.Move(copy,missing,false);
            await Reject(async()=>{await service.CheckReferenceAsync(cid,reference);},"actual missing file rejected without fallback");
            File.Move(missing,copy,false);
            if(auditReady)
            {
                await repository.ReviewCharacterReferenceAsync(cid,rid,"Rejected","automated-regression-test","仅验证拒绝门禁的测试副本；不是对真实人物素材的人工审核");rejectionWritten=true;
                await Reject(async()=>{await service.CheckReferenceAsync(cid,reference);},"explicit rejected fixture cannot enter story input");
            }
            else checks.Add(new{name="rejected material gate requires missing review audit table",status="Blocked"});
        }
        finally
        {
            if(File.Exists(missing)&&!File.Exists(copy))File.Move(missing,copy,false);
            if(await ffmpeg.Sha256Async(copy)!=original.Sha256)File.Copy(source,copy,true);
            if(rejectionWritten)await repository.ReviewCharacterReferenceAsync(cid,rid,"NeedReview","automated-regression-test","恢复受控测试副本为待审，不写Approved，不用于生成或库版本");
        }
        await service.CheckReferenceAsync(cid,reference);checks.Add(new{name="fixture restored with no original media or approval change",status="Passed"});
        if(await ffmpeg.Sha256Async(source)!=original.Sha256)throw new InvalidOperationException("Protected original changed");
        await File.WriteAllTextAsync(Path.Combine(folder,"reference-policy-checks.json"),JsonSerializer.Serialize(new{status=auditReady?"Passed":"Blocked",checks,fixtureCharacterId=cid,fixtureReferenceId=rid,fixturePath=relative,sourceReferenceId=original.ReferenceId,sourceSha256=original.Sha256,gpuTasksCreated=0,humanApprovalsWritten=0,fixtureNotGenerated=true,originalFileUnchanged=true,reviewAuditReady=auditReady},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"CHARACTER_STORY_REFERENCE_TEST {(auditReady?"Passed":"Blocked")} {checks.Count}; controlled copy only, originals unchanged, no GPU or approval");return auditReady?0:2;
    }
    public static async Task<int> ContractsAsync()
    {
        var root=StudioPaths.FindRoot();var cfg=new ConfigurationBuilder().AddJsonFile(Path.Combine(root,"config/appsettings.json")).Build();var settings=StudioPaths.Load(cfg,root);
        var db=new StudioDb(settings,NullLogger<StudioDb>.Instance);var repository=new StudioRepository(db,NullLogger<StudioRepository>.Instance);var ffmpeg=new FfmpegService(settings,NullLogger<FfmpegService>.Instance);var paths=new AssetPathPolicy(settings,ffmpeg,NullLogger<AssetPathPolicy>.Instance);var library=new CharacterLibraryService(db,repository,paths,ffmpeg);
        var a=await library.GetAsync(4);var b=await library.GetAsync(5);string Ref(LibraryVersion v,string framing){paths.TryResolveExisting(CharacterLibraryService.SelectReference(v,"front",framing).AssetPath,out var full,out _);return full;}
        var files=new[]{("realvisxl_reference_api.json","realvisxl-reference-1536-v1",0),("character_pack_klein4b_single_api.json","character-pack-klein4b-single-1536-v1",1),("character_pack_klein4b_dual_api.json","character-pack-klein4b-dual-1536-v1",2),(CharacterStoryService.FourWorkflow,"character-story-klein4b-four-1536-v1",4)};
        var service=new WorkflowContractService(settings,NullLogger<WorkflowContractService>.Instance);var checks=new List<object>();using var client=new HttpClient{BaseAddress=new Uri(settings.ComfyUrl),Timeout=TimeSpan.FromSeconds(30)};var available=JsonNode.Parse(await client.GetStringAsync("/object_info"))!.AsObject();
        foreach(var (file,version,count) in files)
        {
            var slots=new Dictionary<string,string?>();if(count>0)slots["firstFrame"]=Ref(a,"closeUp");if(count>1)slots["wardrobeReference"]=Ref(a,"fullBody");if(count>2){slots["secondIdentity"]=Ref(b,"closeUp");slots["secondWardrobe"]=Ref(b,"fullBody");}
            var p=JsonSerializer.SerializeToElement(new{workflowVersion=version,positive="Contract check only, no generation",negative="",seed=2026102701,width=1536,height=864,steps=count==0?35:4,cfg=count==0?5.5:1,inputSlots=slots});
            var filePath=Path.Combine(settings.WorkflowsPath,file);var execution=service.Prepare(filePath,"Keyframe",p,slots,requireProductionRoute:false);
            var graph=JsonNode.Parse(await File.ReadAllTextAsync(filePath))!.AsObject();foreach(var node in graph)if(!available.ContainsKey(node.Value!["class_type"]!.GetValue<string>()))throw new InvalidOperationException("Missing real Comfy node: "+node.Value!["class_type"]);
            if(execution.Slots.Count!=count)throw new InvalidOperationException("Independent slot count differs");
            checks.Add(new{file,status="Passed",inputCount=count,models="actual pinned file fingerprints checked",comfyNodes="actual object_info checked",gpuSubmitted=0});Console.WriteLine("CONTRACT_PASSED "+file);
        }
        await File.WriteAllTextAsync(Path.Combine(settings.DataPath,"CharacterStory20261027","workflow-contract-checks.json"),JsonSerializer.Serialize(new{status="Passed",checks,empiricalMultiActorIdentity="Unverified",h3Ref2VA=false},new JsonSerializerOptions{WriteIndented=true}));return 0;
    }
    public static async Task<int> RunAsync()
    {
        var checks=new List<object>();
        void Check(bool passed,string name){checks.Add(new{name,status=passed?"Passed":"Failed"});if(!passed)throw new InvalidOperationException(name);}
        void Reject(Action action,string name){var rejected=false;try{action();}catch(ArgumentException){rejected=true;}Check(rejected,name);}
        bool Equal(string a,string b){using var aa=JsonDocument.Parse(a);using var bb=JsonDocument.Parse(b);return CharacterStoryStore.Equal(aa.RootElement,bb.RootElement);}
        Check(Equal("{\"duration\":5.166666666666667,\"id\":9007199254740993}","{\"id\":9007199254740993,\"duration\":5.16666666666667}"),"MySQL normalization keeps contract duration and exact integer ids");
        Check(!Equal("{\"seed\":9007199254740993}","{\"seed\":9007199254740992}"),"integer seed drift rejected without floating-point rounding");
        Check(!Equal("{\"path\":\"A.png\"}","{\"path\":\"B.png\"}"),"different actual first frame rejected");
        Check(!Equal("{\"slots\":[\"identityA\",\"outfitA\",\"identityB\",\"outfitB\"]}","{\"slots\":[\"identityA\",\"identityB\",\"outfitA\",\"outfitB\"]}"),"identity and wardrobe slot order cannot interchange");
        using(var persisted=JsonDocument.Parse("{\"ProjectId\":49,\"TaskType\":\"Keyframe\",\"parameters\":{}}"))
        {
            var task=CharacterStoryStore.RestoreTask(persisted.RootElement,new Dictionary<string,object?>{["projectId"]=49L,["taskType"]="Keyframe",["resourceClass"]="GPU",["maxRetries"]=0,["stage"]="Story-Keyframe-Preview",["idempotencyKey"]="preserved-network-key"});
            Check(task.MaxRetries==0&&task.Stage=="Story-Keyframe-Preview","worker restores scheduling columns absent from input_json");
            Check(task.IdempotencyKey=="preserved-network-key"&&task.ProjectId==49,"restart reuses actual persisted idempotency and parent columns");
        }
        Reject(()=>CharacterStoryStore.RequestKey("short"),"idempotency key required");
        Reject(()=>CharacterWorkshopService.Direction("unknown"),"unknown camera direction rejected");
        Check(CharacterWorkshopService.Direction("back").Contains("cannot verify front identity"),"back view does not assert front identity");
        Check(CharacterWorkshopService.Direction("threeQuarterLeft").Contains("not a profile")&&CharacterWorkshopService.Direction("threeQuarterRight").Contains("not a profile"),"quarter views differ from strict profiles");
        var plan=CharacterStoryStore.Object(new{shotFraming="closeUp",scene="Quiet reading room",action="Gentle nod",camera="Locked",props="None",audioStrategy="PostDubbing",actors=new[]{new{fixedPrompt="face; complete trousers and shoes",position="center",action="look toward camera"}}});
        var close=CharacterStoryService.KeyframePrompt(plan);Check(!close.Contains("trousers and shoes"),"close-up does not inherit complete outfit text");
        plan["shotFraming"]="twoShot";plan["actors"]!.AsArray().Add(CharacterStoryStore.Object(new{position="right",action="look left"}));
        var dual=CharacterStoryService.KeyframePrompt(plan);Check(dual.Contains("Image1 defines person 1 IDENTITY")&&dual.Contains("Image3 defines person 2 IDENTITY")&&dual.Contains("image4 defines ONLY that person's WARDROBE"),"two-person keyframe names four separate identity/wardrobe inputs");
        Check(CharacterStoryService.VideoPrompt(plan).Contains("No dialogue")&&CharacterStoryService.VideoPrompt(plan).Contains("mute raw voices"),"post-dubbing audio policy explicit");
        var root=StudioPaths.FindRoot();var cfg=new ConfigurationBuilder().AddJsonFile(Path.Combine(root,"config/appsettings.json")).Build();var settings=StudioPaths.Load(cfg,root);
        var db=new StudioDb(settings,NullLogger<StudioDb>.Instance);var repository=new StudioRepository(db,NullLogger<StudioRepository>.Instance);var ffmpeg=new FfmpegService(settings,NullLogger<FfmpegService>.Instance);var paths=new AssetPathPolicy(settings,ffmpeg,NullLogger<AssetPathPolicy>.Instance);var library=new CharacterLibraryService(db,repository,paths,ffmpeg);var store=new CharacterStoryStore(db);var service=new CharacterStoryService(db,repository,store,library,paths,ffmpeg);
        var versions=await library.ListAsync();Check(versions.Any(v=>v.Payload.Schema==CharacterLibraryService.Schema),"existing legacy payloads remain readable");
        foreach(var version in versions.Where(v=>v.Id is 4 or 5))
        {
            Check(CharacterLibraryService.Coverage(version.Payload.References).Complete,$"version {version.Id} has nine distinct slots");
            foreach(var reference in version.Payload.References){await service.CheckReferenceAsync(version.Payload.CharacterId,reference);Check(true,$"version {version.Id} reference {reference.ReferenceId} actual file hash");}
            var reference0=version.Payload.References[0];var rejected=false;try{await service.CheckReferenceAsync(version.Payload.CharacterId,reference0 with{AssetVersion=reference0.AssetVersion+1});}catch(AssetValidationException){rejected=true;}Check(rejected,$"version {version.Id} reference version drift rejected");
        }
        var graph=JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(settings.WorkflowsPath,CharacterStoryService.FourWorkflow)))!;
        Check(graph["11"]!["inputs"]!["positive"]![0]!.GetValue<string>()=="43"&&graph["11"]!["inputs"]!["negative"]![0]!.GetValue<string>()=="44","four reference graph reaches CFG after all four inputs");
        Check(new[]{"4","20","30","40"}.All(id=>graph[id]?["class_type"]?.GetValue<string>()=="LoadImage"),"four reference slots have actual independent LoadImage nodes");
        var readiness=await service.ReadinessAsync(default);var folder=Path.Combine(settings.DataPath,"CharacterStory20261027");Directory.CreateDirectory(folder);
        await File.WriteAllTextAsync(Path.Combine(folder,"backend-self-test.json"),JsonSerializer.Serialize(new{status="Passed",checks,readiness,gpuSubmitted=0,humanApprovalsWritten=0},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"CHARACTER_STORY_SELF_TEST_PASSED {checks.Count}; schema readiness recorded separately; no GPU submitted");return 0;
    }
}
