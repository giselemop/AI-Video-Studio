using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;

namespace VideoStudio.Server;

public static class CharacterSceneSelfTest
{
    public static async Task<int> RunAsync()
    {
        var checks=new List<object>();
        void Check(bool ok,string name){checks.Add(new{name,status=ok?"Passed":"Failed"});if(!ok)throw new InvalidOperationException(name);}
        void Reject(Action action,string name){var rejected=false;try{action();}catch(ArgumentException){rejected=true;}Check(rejected,name);}
        List<SceneActorRegion> Regions()=>[new(){Side="left",X=300,Y=50,Width=420,Height=814,Feather=32},new(){Side="right",X=820,Y=8,Width=430,Height=856,Feather=32}];
        CharacterSceneService.ValidateRegions(Regions());Check(true,"valid left/right regions preserve substantial background");
        var r=Regions();r[0].X=-1;Reject(()=>CharacterSceneService.ValidateRegions(r),"negative coordinate rejected");
        r=Regions();r[1].Width=900;Reject(()=>CharacterSceneService.ValidateRegions(r),"out-of-canvas region rejected");
        r=Regions();r[0].Side="right";Reject(()=>CharacterSceneService.ValidateRegions(r),"duplicate region side rejected");
        r=Regions();r[1].X=700;r[1].Width=400;Reject(()=>CharacterSceneService.ValidateRegions(r),"overlapping actor regions rejected");
        r=Regions();r[0].Feather=90;Reject(()=>CharacterSceneService.ValidateRegions(r),"unbounded feather rejected");
        r=Regions();r[0].X=0;r[0].Y=0;r[0].Width=768;r[0].Height=864;r[1].X=768;r[1].Y=0;r[1].Width=768;r[1].Height=864;Reject(()=>CharacterSceneService.ValidateRegions(r),"whole-image replacement cannot masquerade as background lock");
        Reject(()=>CharacterSceneService.ValidateRegions(Regions(),864,480),"reference canvas cannot silently change");
        var binding=CharacterStoryStore.Object(new{payload=new{camera=CharacterSceneService.Camera,sceneDescription="Frozen reading room",actorVersions=new[]{new{characterId=19,versionId=4,position="left"},new{characterId=20,versionId=5,position="right"}},regions=Regions()}});
        var plan=CharacterStoryStore.Object(new{camera=CharacterSceneService.Camera,scene="Frozen reading room",shotFraming="twoShot",actors=new[]{new{characterId=19,versionId=4,position="left"},new{characterId=20,versionId=5,position="right"}}});
        CharacterSceneService.RequireFixedComposition(binding,plan);Check(true,"same actors versions camera and positions accepted");
        var changed=plan.DeepClone().AsObject();changed["actors"]![0]!["versionId"]=3L;Reject(()=>CharacterSceneService.RequireFixedComposition(binding,changed),"wrong actor version rejected");
        changed=plan.DeepClone().AsObject();changed["camera"]="Pan right";Reject(()=>CharacterSceneService.RequireFixedComposition(binding,changed),"camera motion rejected for fixed-background mode");
        changed=plan.DeepClone().AsObject();changed["scene"]="Different room";Reject(()=>CharacterSceneService.RequireFixedComposition(binding,changed),"unfrozen scene change rejected");
        changed=plan.DeepClone().AsObject();changed["shotFraming"]="closeUp";Reject(()=>CharacterSceneService.RequireFixedComposition(binding,changed),"new camera framing requires a new composition");
        var root=StudioPaths.FindRoot();var cfg=new ConfigurationBuilder().AddJsonFile(Path.Combine(root,"config/appsettings.json")).Build();var settings=StudioPaths.Load(cfg,root);var contracts=new WorkflowContractService(settings,NullLogger<WorkflowContractService>.Instance);
        var file=Path.Combine(settings.WorkflowsPath,CharacterSceneService.WorkflowFile);var slots=new Dictionary<string,string?>{{"firstFrame","identity-a.png"},{"wardrobeReference","outfit-a.png"},{"secondIdentity","identity-b.png"},{"secondWardrobe","outfit-b.png"},{"sceneReference","scene.png"}};
        var parameters=JsonSerializer.SerializeToElement(new{workflowVersion=CharacterSceneService.WorkflowVersion,width=1536,height=864,steps=4,cfg=1,seed=2026102731,positive="scene-contract-test",sceneLock=binding},CharacterStoryStore.Json);
        var execution=contracts.Prepare(file,"Keyframe",parameters,slots,false);Check(execution.Slots.Count==5,"five independent actual contract slots admitted");
        var graph=ComfyUiClient.LoadWorkflow(file);ComfyUiClient.PatchWorkflow(graph,"Keyframe",null,null,"identity-a.png",null,null,parameters,"scene-self-test",execution);
        Check(graph["61"]!["inputs"]!["width"]!.GetValue<int>()==420&&graph["64"]!["inputs"]!["height"]!.GetValue<int>()==856,"actor geometry survives generic canvas parameter patching");
        Check(graph["63"]!["inputs"]!["x"]!.GetValue<int>()==300&&graph["66"]!["inputs"]!["y"]!.GetValue<int>()==8,"region positions retained");
        Check(graph["67"]!["inputs"]!["destination"]![0]!.GetValue<string>()=="50"&&graph["18"]!["inputs"]!["images"]![0]!.GetValue<string>()=="67","saved output explicitly composites frozen scene");
        Check(graph["50"]!["inputs"]!["image"]!.GetValue<string>()=="scene.png"&&graph["40"]!["inputs"]!["image"]!.GetValue<string>()=="outfit-b.png","scene slot cannot replace second identity or wardrobe");
        var guarded=false;try{CharacterSceneService.ApplyGeometry(graph,parameters,new WorkflowExecutionPlan{WorkflowFileName="other.json"});}catch(WorkflowContractException){guarded=true;}Check(guarded,"scene geometry cannot override unrelated workflows");
        var maskedBinding=binding.DeepClone().AsObject();maskedBinding["payload"]!["workflowVersion"]=CharacterSceneService.MaskedWorkflowVersion;
        var maskedParameters=JsonSerializer.SerializeToElement(new{workflowVersion=CharacterSceneService.MaskedWorkflowVersion,width=1536,height=864,steps=4,cfg=1,seed=2026102831,positive="head-pose-exclusion-test",sceneLock=maskedBinding},CharacterStoryStore.Json);
        var maskedFile=Path.Combine(settings.WorkflowsPath,CharacterSceneService.MaskedWorkflowFile);var maskedPlan=contracts.Prepare(maskedFile,"Keyframe",maskedParameters,slots,false);var maskedGraph=ComfyUiClient.LoadWorkflow(maskedFile);ComfyUiClient.PatchWorkflow(maskedGraph,"Keyframe",null,null,"identity-a.png",null,null,maskedParameters,"masked-scene-self-test",maskedPlan);
        Check(maskedGraph["51"]!["inputs"]!["image"]![0]!.GetValue<string>()=="69","old head poses excluded only from scene conditioning");
        Check(maskedGraph["71"]!["inputs"]!["width"]!.GetValue<int>()==294&&maskedGraph["73"]!["inputs"]!["height"]!.GetValue<int>()==340,"head exclusion geometry follows validated actor regions");
        Check(maskedGraph["67"]!["inputs"]!["destination"]![0]!.GetValue<string>()=="50","final image uses original scene rather than neutral head masks");
        Check(CharacterSceneService.WorkflowFor(maskedBinding)==CharacterSceneService.MaskedWorkflowFile&&CharacterSceneService.WorkflowFor(binding)==CharacterSceneService.WorkflowFile,"scene route revisions explicit and old version remains readable");
        var db=new StudioDb(settings,NullLogger<StudioDb>.Instance);var repository=new StudioRepository(db,NullLogger<StudioRepository>.Instance);var ffmpeg=new FfmpegService(settings,NullLogger<FfmpegService>.Instance);var paths=new AssetPathPolicy(settings,ffmpeg,NullLogger<AssetPathPolicy>.Instance);var store=new CharacterStoryStore(db);var library=new CharacterLibraryService(db,repository,paths,ffmpeg);var scenes=new CharacterSceneService(db,repository,store,paths,ffmpeg);var service=new CharacterStoryService(db,repository,store,library,paths,ffmpeg,scenes);
        var ready=await service.ReadinessAsync(CancellationToken.None);Check(JsonSerializer.SerializeToElement(ready).GetProperty("ready").GetBoolean(),"existing Scene ledger requires no new migration");
        var folder=Path.Combine(settings.DataPath,"CharacterScene20261027");Directory.CreateDirectory(folder);await File.WriteAllTextAsync(Path.Combine(folder,"backend-checks.json"),JsonSerializer.Serialize(new{status="Passed",checks,gpuTasksCreated=0,humanApprovals=0},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"CHARACTER_SCENE_SELF_TEST_PASSED {checks.Count}");return 0;
    }
}
