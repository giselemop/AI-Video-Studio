using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;

namespace VideoStudio.Server;

/// <summary>Read-only tests for explicitly selected approved legacy portraits.</summary>
public static class CharacterStoryLegacyHeadshotSelfTest
{
    public static async Task<int> RunAsync()
    {
        var checks=new List<object>();
        void Check(bool ok,string name){checks.Add(new{name,status=ok?"Passed":"Failed"});if(!ok)throw new InvalidOperationException(name);}
        void Reject(Action action,string name){var rejected=false;try{action();}catch(ArgumentException){rejected=true;}Check(rejected,name);}
        var root=StudioPaths.FindRoot();var cfg=new ConfigurationBuilder().AddJsonFile(Path.Combine(root,"config/appsettings.json")).Build();var settings=StudioPaths.Load(cfg,root);
        var db=new StudioDb(settings,NullLogger<StudioDb>.Instance);var repo=new StudioRepository(db,NullLogger<StudioRepository>.Instance);var ffmpeg=new FfmpegService(settings,NullLogger<FfmpegService>.Instance);var paths=new AssetPathPolicy(settings,ffmpeg,NullLogger<AssetPathPolicy>.Instance);var library=new CharacterLibraryService(db,repo,paths,ffmpeg);var service=new CharacterStoryService(db,repo,new CharacterStoryStore(db),library,paths,ffmpeg);
        var version=await library.GetAsync(3);var actor=new StoryActorInput{Role="林安",View="front",Framing="closeUp",Position="center",LegacyHeadshotReferenceId=36};var shot=new StoryShotInput{ShotFraming="closeUp",Actors=[actor]};
        var chosen=CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor);Check(chosen.ReferenceId==36&&chosen.View=="front"&&chosen.Framing is null,"explicit legacy front image selected without inventing full-body metadata");
        var row=await service.CheckReferenceAsync(version.Payload.CharacterId,chosen);Check(ReferenceMetadata.Read(row.Text("metadataJson")).ReviewStatus=="Approved","current selected reference is actually Approved");
        Check(!CharacterLibraryService.Coverage(version.Payload.References).Complete,"legacy portrait remains visibly incomplete as a nine-image pack");
        actor.LegacyHeadshotReferenceId=null;Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"missing explicit reference rejected");
        actor.LegacyHeadshotReferenceId=37;Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"another view cannot replace the specified front image");
        actor.LegacyHeadshotReferenceId=999999;Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"unknown reference rejected");
        actor.LegacyHeadshotReferenceId=36;actor.View="threeQuarterRight";Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"other view rejected");actor.View="front";
        shot.ShotFraming="fullBody";Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"full body cannot use the legacy portrait");shot.ShotFraming="closeUp";
        shot.Actors.Add(new StoryActorInput{Role="other"});Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"two-person composition rejected");shot.Actors.RemoveAt(1);
        shot.SceneVersionId=29;Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(version,shot,actor),"fixed multi-actor scene rejected");shot.SceneVersionId=null;
        var modern=await library.GetAsync(4);Reject(()=>CharacterStoryService.SelectExplicitLegacyHeadshot(modern,shot,actor),"modern version and its rejected images cannot use legacy exception");
        var promptPlan=JsonNode.Parse("""
            {"actors":[{"position":"center","action":"calm neutral start","view":"front"}],"shotFraming":"closeUp","scene":"window","action":"later she turns and smiles","camera":"locked","props":"none"}
            """)!.AsObject();
        Check(CharacterStoryService.KeyframePrompt(promptPlan).Contains("later she turns and smiles"),"historical plans keep original keyframe prompt");
        promptPlan["keyframeStartOnly"]=true;
        var stillPrompt=CharacterStoryService.KeyframePrompt(promptPlan);
        Check(stillPrompt.Contains("calm neutral start")&&!stillPrompt.Contains("later she turns and smiles"),"opt-in keyframe excludes later animation and retains actor start");
        Check(CharacterStoryService.VideoPrompt(promptPlan).Contains("later she turns and smiles"),"video prompt retains complete later action");
        var path=Path.Combine(settings.DataPath,"CharacterPlotPreview20261027","legacy-self-test.json");Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        await File.WriteAllTextAsync(path,JsonSerializer.Serialize(new{status="Passed",checks,gpuSubmitted=0,humanApprovals=0},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"CHARACTER_STORY_LEGACY_HEADSHOT_SELF_TEST_PASSED {checks.Count}");return 0;
    }
}
