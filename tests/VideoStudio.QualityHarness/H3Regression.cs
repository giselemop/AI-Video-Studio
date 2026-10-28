using System.Text.Json;
using System.Text.Json.Nodes;
using VideoStudio.Server;

internal static class H3Regression
{
    public static void Run()
    {
        JsonObject Workflow() => JsonNode.Parse("""
        {"1":{"class_type":"MiniMaxH3ImageToVideo","inputs":{"prompt":"old","width":864,"height":480,"length":124}},
         "2":{"class_type":"LoadImage","inputs":{"image":"old.png"}},
         "3":{"class_type":"KSampler","inputs":{"seed":1,"steps":20}}}
        """)!.AsObject();
        JsonElement Params(string json) => JsonSerializer.Deserialize<JsonElement>(json);
        var passed = 0;
        void Check(bool condition) { if (!condition) throw new Exception("H3 regression failed"); passed++; }
        void Reject(string json)
        {
            try { H3WorkflowPolicy.Validate(Workflow(), Params(json)); }
            catch (InvalidOperationException) { passed++; return; }
            throw new Exception("Unsafe H3 parameters accepted");
        }
        var workflow = Workflow();
        H3WorkflowPolicy.Validate(workflow, Params("""{"width":1376,"height":768,"frames":124,"fps":24}"""));
        Check(true);
        Check(H3WorkflowPolicy.IsH3(workflow));
        var refs = ComfyUiClient.PatchWorkflow(workflow, "I2V", "new prompt", null, null, ["reference.png"], null,
            Params("""{"width":1152,"height":640,"frames":124,"fps":24,"seed":42}"""), "h3_test");
        Check(workflow["1"]!["inputs"]!["prompt"]!.GetValue<string>() == "new prompt");
        Check(workflow["1"]!["inputs"]!["width"]!.GetValue<int>() == 1152);
        Check(workflow["1"]!["inputs"]!["length"]!.GetValue<int>() == 124);
        Check(refs == 1 && workflow["2"]!["inputs"]!["image"]!.GetValue<string>() == "reference.png");
        Check(workflow["3"]!["inputs"]!["seed"]!.GetValue<long>() == 42);
        Reject("""{"width":1280,"height":720}""");
        Reject("""{"width":1920,"height":1088}""");
        Reject("""{"profile":"quality768","width":1920,"height":1088}""");
        Reject("""{"profile":"native1080","width":1376,"height":768}""");
        var nativeParameters = Params("""{"profile":"native1080","width":1920,"height":1088,"frames":124,"fps":24}""");
        workflow = Workflow();
        workflow["5"] = JsonNode.Parse("""{"class_type":"SaveVideo","inputs":{"codec":"h264","codec.encoding":"re-encode","codec.encoding.crf":16.0}}""");
        H3WorkflowPolicy.Validate(workflow, nativeParameters);
        var invalidCodec = (JsonObject)workflow.DeepClone();
        invalidCodec["5"]!["inputs"]!["codec"] = JsonNode.Parse("""{"codec":"h264"}""");
        try { H3WorkflowPolicy.Validate(invalidCodec, nativeParameters); throw new Exception("Nested dynamic codec accepted"); }
        catch (InvalidOperationException) { passed++; }
        workflow["4"] = JsonNode.Parse("""{"class_type":"ImageCrop","inputs":{"image":["1",0],"width":1920,"height":1080,"x":0,"y":4}}""");
        ComfyUiClient.PatchWorkflow(workflow, "I2V", "native", null, "frame.png", null, null, nativeParameters, "native1080_test");
        Check(workflow["1"]!["inputs"]!["height"]!.GetValue<int>() == 1088);
        Check(workflow["4"]!["inputs"]!["height"]!.GetValue<int>() == 1080 && workflow["4"]!["inputs"]!["y"]!.GetValue<int>() == 4);
        var legacyCrop = JsonNode.Parse("""{"1":{"class_type":"ImageCrop","inputs":{"width":512,"height":320,"x":0,"y":0}}}""")!.AsObject();
        ComfyUiClient.PatchWorkflow(legacyCrop, "Image", null, null, null, null, null,
            Params("""{"profile":123,"width":640,"height":384}"""), "legacy_crop");
        Check(legacyCrop["1"]!["inputs"]!["width"]!.GetValue<int>() == 640 && legacyCrop["1"]!["inputs"]!["height"]!.GetValue<int>() == 384);
        var deadline = typeof(GenerationQueue).GetMethod("TaskDeadline", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", "dialogue_sync_full_shot_3_i2v_v1_api.json"])! == TimeSpan.FromMinutes(60));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", "dialogue_sync_full_shot_1_i2v_v1_api.json"])! == TimeSpan.FromMinutes(30));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", "unknown151_api.json"])! == TimeSpan.FromMinutes(30));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "CPU", "dialogue_sync_full_shot_3_i2v_v1_api.json"])! == TimeSpan.FromMinutes(10));
        Check((TimeSpan)deadline.Invoke(null, ["TextToVideo", "GPU", "dialogue_sync_full_shot_3_i2v_v1_api.json"])! == TimeSpan.FromMinutes(30));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", MiniMaxLocalService.Native1080WorkflowFileName])! == TimeSpan.FromMinutes(360));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", MiniMaxLocalService.Native1080Quality30WorkflowFileName])! == TimeSpan.FromMinutes(480));
        Check((TimeSpan)deadline.Invoke(null, ["TextToVideo", "GPU", MiniMaxLocalService.Native1080TextWorkflowFileName])! == TimeSpan.FromMinutes(360));
        Check((TimeSpan)deadline.Invoke(null, ["TextToVideo", "GPU", MiniMaxLocalService.Quality768TextWorkflowFileName])! == TimeSpan.FromMinutes(90));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", "minimax_h3_local_768_i2v_api.json"])! == TimeSpan.FromMinutes(90));
        Check((TimeSpan)deadline.Invoke(null, ["ImageToVideo", "GPU", MiniMaxLocalService.WorkflowFileName])! == TimeSpan.FromMinutes(30));
        Check((TimeSpan)deadline.Invoke(null, ["Enhance", "CPU", MiniMaxLocalService.Native1080WorkflowFileName])! == TimeSpan.FromMinutes(10));
        Reject("""{"frames":121}""");
        Reject("""{"fps":30}""");
        var legacy = JsonNode.Parse("""{"1":{"class_type":"LTXVImgToVideo","inputs":{"length":73}}}""")!.AsObject();
        H3WorkflowPolicy.Validate(legacy, Params("{}"));
        Check(!H3WorkflowPolicy.IsH3(legacy));
        workflow = Workflow();
        workflow["1"]!["class_type"] = "MiniMaxH3ReferenceToVideo";
        try { H3WorkflowPolicy.Validate(workflow, Params("{}")); throw new Exception("R2V accepted"); }
        catch (InvalidOperationException) { passed++; }
        workflow = Workflow();
        workflow["4"] = JsonNode.Parse("""{"class_type":"EmptyMiniMaxH3LatentAV","inputs":{"width":1152,"height":640,"length":124}}""");
        try { H3WorkflowPolicy.Validate(workflow, Params("{}")); throw new Exception("Mismatched latent accepted"); }
        catch (InvalidOperationException) { passed++; }
        workflow = Workflow();
        try
        {
            ComfyUiClient.PatchWorkflow(workflow, "I2V", "prompt", null, "primary.png", ["extra.png"], null, Params("{}"), "test");
            throw new Exception("Ambiguous reference roles accepted");
        }
        catch (InvalidOperationException) { passed++; }
        Console.WriteLine($"H3 regression: {passed} Passed; no GPU/API/database writes");
    }
}
