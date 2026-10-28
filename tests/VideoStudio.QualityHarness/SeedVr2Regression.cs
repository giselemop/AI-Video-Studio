using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using VideoStudio.Server;

internal static class SeedVr2Regression
{
    public static async Task Run()
    {
        var root = Path.Combine(@"C:\install\AI\Data\acceptance", "seedvr2_contract_" + Guid.NewGuid().ToString("N"));
        foreach (var dir in new[] { "config", "Models/seed", "engine", "tools/video_detail" }) Directory.CreateDirectory(Path.Combine(root, dir));
        var model = Path.Combine(root, "Models", "seed");
        var script = Path.Combine(root, "tools", "video_detail", "restore.py");
        var configPath = Path.Combine(root, "config", "seedvr2.json");
        var config = new { python = @"C:\install\Python\python.exe", modelDirectory = model,
            engineDirectory = Path.Combine(root, "engine"), revision = "fixture-v1", engineRevision = "fixture-engine-v1", timeoutSeconds = 30,
            files = new[] { new { file = "weight.bin", size = 7 } } };
        await File.WriteAllTextAsync(configPath, JsonSerializer.Serialize(config));
        await File.WriteAllTextAsync(Path.Combine(root, "engine", "inference_cli.py"), "# synthetic test engine");
        await File.WriteAllTextAsync(script, "import sys;sys.stdin.read()");
        var engine = new SeedVr2Service(new StudioSettings { RootPath = root, DataPath = root, ModelsPath = Path.Combine(root, "Models") });
        var checks = 0;
        void Check(bool passed, string name) { if (!passed) throw new Exception("SeedVR2 regression failed: " + name); checks++; }
        Check(!engine.Check().Ready, "missing deployment fails closed");
        await File.WriteAllTextAsync(Path.Combine(model, "weight.bin"), "fixture");
        await File.WriteAllTextAsync(Path.Combine(model, "deployment.json"), JsonSerializer.Serialize(new { revision = "fixture-v1", engineRevision = "fixture-engine-v1" }));
        Check(engine.Check().Ready, "deployed fixture metadata accepted");
        await File.AppendAllTextAsync(Path.Combine(model, "weight.bin"), "drift");
        Check(!engine.Check().Ready, "weight size drift rejected");
        await File.WriteAllTextAsync(Path.Combine(model, "weight.bin"), "fixture");
        var identity = engine.Identity;
        await File.AppendAllTextAsync(script, "\n# changed worker version");
        Check(engine.Identity != identity, "pending job identity detects worker drift");
        var childPidFile = Path.Combine(root, "child.pid");
        await File.WriteAllTextAsync(script, "import subprocess,sys,time,pathlib\n" +
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n" +
            "pathlib.Path(" + JsonSerializer.Serialize(childPidFile.Replace('\\', '/')) + ").write_text(str(p.pid))\n" +
            "sys.stdin.read()\ntime.sleep(30)\n");
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var output = Path.Combine(root, "unpublished.mp4");
        var restoration = engine.RestoreAsync("synthetic-input", "synthetic-hash", output, .65, [], 320, 192, "source", cancellation.Token);
        for (var i = 0; i < 100 && !File.Exists(childPidFile); i++) await Task.Delay(50);
        Check(File.Exists(childPidFile), "process tree starts for cancellation fixture");
        var childPid = int.Parse(await File.ReadAllTextAsync(childPidFile));
        cancellation.Cancel();
        try { await restoration; throw new Exception("Cancellation was ignored"); } catch (OperationCanceledException) { checks++; }
        bool Alive(int pid) { try { using var child = Process.GetProcessById(pid); return !child.HasExited; } catch (ArgumentException) { return false; } }
        Check(!Alive(childPid) && !File.Exists(output), "cancellation kills children and publishes no media");
        var timeoutConfig = JsonNode.Parse(JsonSerializer.Serialize(config))!;
        timeoutConfig["timeoutSeconds"] = 1;
        await File.WriteAllTextAsync(configPath, timeoutConfig.ToJsonString());
        try { await engine.RestoreAsync("synthetic-input", "synthetic-hash", output, .65, [], 320, 192, "source", CancellationToken.None); throw new Exception("Timeout was ignored"); }
        catch (TimeoutException) { checks++; }
        Check(!Alive(int.Parse(await File.ReadAllTextAsync(childPidFile))) && !File.Exists(output), "timeout kills children without false cancellation or publication");
        await File.WriteAllTextAsync(script, "import sys;sys.stdin.read()");
        try { await engine.RestoreAsync("synthetic-input", "synthetic-hash", output, .65, [], 320, 192, "source", CancellationToken.None); throw new Exception("Missing media accepted"); }
        catch (InvalidOperationException ex) when (ex.Message.Contains("SeedVR2修复失败")) { checks++; }
        var deadline = (TimeSpan)typeof(GenerationQueue).GetMethod("TaskDeadline", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, ["VideoRestore", "GPU", null])!;
        Check(deadline == TimeSpan.FromMinutes(95), "queue deadline covers the bounded inference process");
        await File.WriteAllTextAsync(Path.Combine(root, "report.json"), JsonSerializer.Serialize(new { status = "Passed", checks, gpuInference = false, databaseWrites = false }));
        Console.WriteLine($"SeedVR2 contract: {checks} Passed; fixtures={root}; no GPU or database calls");
    }
}
