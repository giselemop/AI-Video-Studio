using System.Text.Json.Nodes;

namespace VideoStudio.Server;

/// <summary>Shared by the workbench and offline batch tools; content review remains separate.</summary>
public static class CharacterReferencePrompts
{
    public static JsonObject Policy() => JsonNode.Parse(File.ReadAllText(Path.Combine(StudioPaths.FindRoot(), "config", "character-reference-prompts.json")))!.AsObject();
    public static string Direction(string view) => Policy()["directions"]?[view]?.GetValue<string>() ?? throw new ArgumentException("方向无效");
    public static string Compose(string view, string framing, int referenceCount, string identity, string outfit, string body)
    {
        var policy = Policy();
        if (!CharacterLibraryService.BasicSlots.Any(s => s.View == view && s.Framing == framing) || referenceCount is < 0 or > 2)
            throw new ArgumentException("参考图方向、景别或参考数量无效");
        var parts = new List<string> { policy["subject"]!.GetValue<string>(), policy["directions"]![view]!.GetValue<string>(), policy["references"]![referenceCount]!.GetValue<string>(),
            "Identity traits: " + identity, policy["face"]!.GetValue<string>(), policy["head"]!.GetValue<string>(),
            policy[framing]!.GetValue<string>() };
        if (framing == "fullBody") { parts.Add("Body proportions: " + body); parts.Add("Complete wardrobe: " + outfit); }
        else parts.Add("Visible collar and upper garment only: " + System.Text.RegularExpressions.Regex.Split(outfit,"[,，、;；]")[0]);
        parts.Add(policy["finish"]!.GetValue<string>());
        return string.Join(" ", parts);
    }
    public static int SelfTest()
    {
        var matrix=new List<object>();
        foreach(var slot in CharacterLibraryService.BasicSlots)
        foreach(var count in new[]{0,1,2})
        {
            var prompt=Compose(slot.View,slot.Framing,count,"oval face, adult age 30","green cotton top, black trousers, white shoes","natural adult proportions");
            if(!prompt.Contains("ONE anatomically normal head")||!prompt.Contains("ONE face")||!prompt.Contains("ONE neck"))throw new InvalidOperationException("Single head/face/neck missing");
            if(slot.Framing=="closeUp"&&(prompt.Contains("black trousers")||prompt.Contains("white shoes")||prompt.Contains("Exactly two legs")))throw new InvalidOperationException("Close-up leaks lower-body instructions");
            if(slot.Framing=="fullBody"&&(!prompt.Contains("Exactly two arms")||!prompt.Contains("Exactly two legs")||!prompt.Contains("five anatomically plausible fingers")||!prompt.Contains("occlusion are allowed")))throw new InvalidOperationException("Full-body anatomy/occlusion missing");
            if(slot.View is "left" or "right" && (prompt.Contains("both eyes remain naturally visible")||!prompt.Contains("far eye and far side of the face are occluded")))throw new InvalidOperationException("Profile conflicts with frontal eyes");
            if(slot.View=="back"&&!prompt.Contains("no eyes, nose, mouth or cheek visible"))throw new InvalidOperationException("Rear face constraint missing");
            matrix.Add(new{view=slot.View,framing=slot.Framing,count,prompt});
        }
        foreach(var bad in new[]{("invalid","fullBody",1),("back","closeUp",1),("front","closeUp",3)})
        {
            var rejected=false;try{Compose(bad.Item1,bad.Item2,bad.Item3,"","","");}catch(ArgumentException){rejected=true;}
            if(!rejected)throw new InvalidOperationException("Invalid direction, crop or reference count accepted");
        }
        var folder=Path.Combine(StudioPaths.FindRoot(),"..","Data","CharacterReferenceRepair20261027");Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,"prompt-matrix-dotnet.json"),System.Text.Json.JsonSerializer.Serialize(matrix));
        Console.WriteLine("CHARACTER_PROMPT_POLICY_PASSED 27 view/framing/reference combinations + 3 rejection cases");return 0;
    }
}
