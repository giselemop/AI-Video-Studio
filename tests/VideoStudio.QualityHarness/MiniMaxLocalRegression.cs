using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using VideoStudio.Server;

internal static class MiniMaxLocalRegression
{
    public static async Task Run()
    {
        var root = Path.Combine("C:/install/AI/Data/acceptance", "minimax_local_contract_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "config"));
        var settings = new StudioSettings { RootPath = root, ModelsPath = Path.Combine(root, "models"), WorkflowsPath = Path.Combine(root, "workflows") };
        var assets = Enumerable.Range(1, 4).Select(index =>
        {
            var data = Encoding.UTF8.GetBytes($"test-only-model-{index}");
            var relative = $"diffusion_models/test-{index}.gguf";
            var path = Path.Combine(settings.ModelsPath, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllBytes(path, data);
            return new MiniMaxLocalAsset($"role-{index}", "test/fixture", "fixed", $"test-{index}.gguf", relative, data.Length, Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant());
        }).ToArray();
        var manifest = new MiniMaxLocalManifest(1, "test-fixture", "test-only", "https://example.invalid", assets);
        await File.WriteAllTextAsync(Path.Combine(root, "config/minimax-local-assets.json"), JsonSerializer.Serialize(manifest));
        var local = new MiniMaxLocalService(settings);
        var checks = 0;
        void Check(bool condition) { if (!condition) throw new Exception("MiniMax local regression failed"); checks++; }
        Check(local.AssetStatus().All(asset => asset.Present && !asset.Verified));
        await local.EnsureVerifiedAsync();
        Check(local.AssetStatus().All(asset => asset.Verified));
        var task = MiniMaxLocalService.BuildTask(new(42, "A gentle gesture; quiet ambience.", "Projects/42/frame.png", 123), 7, "request", "fixed-key");
        Check(task.ProjectId == 42 && task.ShotId is null && task.EpisodeId is null && task.ProductionRunId is null);
        Check(task.ResourceClass == "GPU" && task.MaxRetries == 0 && task.WorkflowId == 7);
        Check(task.Parameters!.Value.GetProperty("frames").GetInt32() == 124 && task.Parameters.Value.GetProperty("fps").GetInt32() == 24);
        Check(task.Parameters.Value.GetProperty("extractNativeAudio").GetBoolean());
        MiniMaxLocalService.ValidateManagedParameters(task.Parameters.Value);
        var quality = MiniMaxLocalService.BuildTask(new(42, "Reference anchored shot; natural ambience.", "Projects/42/frame.png", 123, "quality768"), 8, "request768", "fixed-key768");
        Check(quality.Parameters!.Value.GetProperty("width").GetInt32() == 1376 && quality.Parameters.Value.GetProperty("height").GetInt32() == 768);
        Check(quality.Parameters.Value.GetProperty("steps").GetInt32() == 20 && quality.MaxRetries == 0);
        MiniMaxLocalService.ValidateManagedParameters(quality.Parameters.Value, "minimax_h3_local_768_i2v_api.json");
        Check(MiniMaxLocalService.IsManagedWorkflow("minimax_h3_local_768_i2v_api.json"));
        var native = MiniMaxLocalService.BuildTask(new(42, "Visible slow camera movement; crisp foliage.", "Projects/42/frame.png", 123, "native1080"), 9, "request1080", "fixed-key1080");
        Check(native.Parameters!.Value.GetProperty("width").GetInt32() == 1920 && native.Parameters.Value.GetProperty("height").GetInt32() == 1088);
        Check(native.MaxRetries == 0 && native.Parameters.Value.GetProperty("frames").GetInt32() == 124 && native.Parameters.Value.GetProperty("steps").GetInt32() == 20);
        MiniMaxLocalService.ValidateManagedParameters(native.Parameters.Value, MiniMaxLocalService.Native1080WorkflowFileName);
        Check(MiniMaxLocalService.IsManagedWorkflow(MiniMaxLocalService.Native1080WorkflowFileName));
        var text = MiniMaxLocalService.BuildTask(new(42, "A fresh fictional campus story opening.", "", 123, "native1080", true), 10, "request-text", "fixed-key-text");
        Check(text.TaskType == "TextToVideo" && string.IsNullOrEmpty(text.InputImagePath));
        Check(text.Parameters!.Value.GetProperty("textToVideo").GetBoolean() && text.Parameters.Value.GetProperty("width").GetInt32() == 1920);
        MiniMaxLocalService.ValidateManagedParameters(text.Parameters.Value, MiniMaxLocalService.Native1080TextWorkflowFileName);
        Check(MiniMaxLocalService.IsManagedWorkflow(MiniMaxLocalService.Native1080TextWorkflowFileName));
        Check(MiniMaxLocalService.IsTextToVideoWorkflow(MiniMaxLocalService.Native1080TextWorkflowFileName.ToUpperInvariant()));
        Check(MiniMaxLocalService.Profiles.Length == 4 && MiniMaxLocalService.ManagedProfiles.Count() == 7);
        var quality30 = MiniMaxLocalService.BuildTask(new(42, "Pick up one red notebook and hold it still.", "Projects/42/frame.png", 123, "native1080", false, 30), 11, "req-30", "key-30");
        Check(quality30.Parameters!.Value.GetProperty("steps").GetInt32() == 30 && quality30.Parameters.Value.GetProperty("seed").GetInt64() == 123);
        Check(MiniMaxLocalService.ResolveWorkflowFileName(MiniMaxLocalService.ResolveProfile("native1080"), false, 30) == MiniMaxLocalService.Native1080Quality30WorkflowFileName);
        MiniMaxLocalService.ValidateManagedParameters(quality30.Parameters.Value, MiniMaxLocalService.Native1080Quality30WorkflowFileName);
        Check(MiniMaxLocalService.IsManagedWorkflow(MiniMaxLocalService.Native1080Quality30WorkflowFileName) && MiniMaxLocalService.IsNative1080Workflow(MiniMaxLocalService.Native1080Quality30WorkflowFileName));
        foreach (var pair in new[] { (quality30.Parameters.Value, MiniMaxLocalService.Native1080WorkflowFileName), (native.Parameters.Value, MiniMaxLocalService.Native1080Quality30WorkflowFileName) })
        {
            try { MiniMaxLocalService.ValidateManagedParameters(pair.Item1, pair.Item2); throw new Exception("Sampling steps accepted the wrong pinned graph"); }
            catch (InvalidOperationException) { checks++; }
        }
        foreach (var invalid in new[] { new MiniMaxLocalInput(42, "valid", "frame.png", 123, "quality768", false, 30),
            new MiniMaxLocalInput(42, "valid", "", 123, "native1080", true, 30), new MiniMaxLocalInput(42, "valid", "frame.png", 123, "native1080", false, 29) })
        {
            try { MiniMaxLocalService.BuildTask(invalid, 11, "req", "key"); throw new Exception("Unapproved step variant accepted"); }
            catch (InvalidOperationException) { checks++; }
        }
        try { MiniMaxLocalService.BuildTask(new(42, "valid", "frame.png", 123, "native1080", true), 10, "req", "key"); throw new Exception("T2V silently ignored a reference"); }
        catch (InvalidOperationException) { checks++; }
        try { MiniMaxLocalService.ValidateManagedParameters(text.Parameters.Value, MiniMaxLocalService.Native1080WorkflowFileName); throw new Exception("T2V accepted an I2V graph"); }
        catch (InvalidOperationException) { checks++; }
        try { MiniMaxLocalService.BuildTask(new(42, "valid", "", 123, "baseline480", true), 10, "req", "key"); throw new Exception("Unregistered text route accepted"); }
        catch (InvalidOperationException) { checks++; }
        try { MiniMaxLocalService.ValidateManagedParameters(native.Parameters.Value, "minimax_h3_local_768_i2v_api.json"); throw new Exception("Native canvas with another workflow accepted"); }
        catch (InvalidOperationException) { checks++; }
        try { MiniMaxLocalService.ValidateManagedParameters(quality.Parameters.Value, MiniMaxLocalService.WorkflowFileName); throw new Exception("Cross-profile workflow accepted"); }
        catch (InvalidOperationException) { checks++; }
        try { MiniMaxLocalService.ResolveProfile("automatic"); throw new Exception("Unknown profile accepted"); }
        catch (InvalidOperationException) { checks++; }
        foreach (var pair in new[] { ("frames", 121), ("steps", 4), ("width", 1920) })
        {
            var changed = System.Text.Json.Nodes.JsonNode.Parse(task.Parameters.Value.GetRawText())!.AsObject();
            changed[pair.Item1] = pair.Item2;
            try { MiniMaxLocalService.ValidateManagedParameters(JsonSerializer.SerializeToElement(changed)); throw new Exception("Implicit route change accepted"); }
            catch (InvalidOperationException) { checks++; }
        }
        foreach (var input in new[] { new MiniMaxLocalInput(0, "valid", "frame.png"), new MiniMaxLocalInput(1, " ", "frame.png"), new MiniMaxLocalInput(1, "valid", ""), new MiniMaxLocalInput(1, "valid", "frame.png", -1) })
        {
            try { MiniMaxLocalService.BuildTask(input, 7, "req", "key"); throw new Exception("Invalid experiment accepted"); }
            catch (InvalidOperationException) { checks++; }
        }
        var model = Path.Combine(settings.ModelsPath, assets[0].Target);
        await File.WriteAllBytesAsync(model, Enumerable.Repeat((byte)'x', (int)assets[0].Size).ToArray());
        File.SetLastWriteTimeUtc(model, DateTime.UtcNow.AddSeconds(2));
        try { await local.EnsureVerifiedAsync(); throw new Exception("Drifted model accepted"); }
        catch (InvalidOperationException) { checks++; }
        Check(!local.AssetStatus()[0].Verified);
        File.Delete(model);
        await File.WriteAllBytesAsync(model + ".part", new byte[assets[0].Size]);
        await File.WriteAllTextAsync(model + ".download.json", JsonSerializer.Serialize(new { sha256 = assets[0].Sha256, chunk_size = 4, completed = new[] { 0 } }));
        Check(local.AssetStatus()[0].DownloadedBytes == 4 && !local.AssetStatus()[0].Present);
        var escaped = manifest with { Assets = [assets[0] with { Target = "../outside.gguf" }, assets[1], assets[2], assets[3]] };
        await File.WriteAllTextAsync(Path.Combine(root, "config/minimax-local-assets.json"), JsonSerializer.Serialize(escaped));
        try { local.AssetStatus(); throw new Exception("Escaped asset accepted"); }
        catch (InvalidOperationException) { checks++; }
        Console.WriteLine($"MiniMax local contract: {checks} Passed; fixtures={root}; no GPU, remote API or database calls");
    }
}
