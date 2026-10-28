using System.Diagnostics;
using System.Net;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

internal static class Qwen3TtsRegression
{
    public static async Task Run()
    {
        var root = Path.Combine(@"C:\install\AI\Data\acceptance", "qwen3_contract_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "config"));
        Directory.CreateDirectory(Path.Combine(root, "Models", "voice"));
        Directory.CreateDirectory(Path.Combine(root, "tools", "qwen3_tts"));
        var model = Path.Combine(root, "Models", "voice");
        var script = Path.Combine(root, "tools", "qwen3_tts", "generate.py");
        var config = new { python = @"C:\install\Python\python.exe", modelDirectory = model, revision = "fixture-v1",
            timeoutSeconds = 30, maxTextCharacters = 500, maxInstructionCharacters = 300 };
        await File.WriteAllTextAsync(Path.Combine(root, "config", "qwen3-tts.json"), JsonSerializer.Serialize(config));
        await File.WriteAllTextAsync(script, "import time; time.sleep(30)");
        var settings = new StudioSettings { RootPath = root, ModelsPath = Path.Combine(root, "Models") };
        var engine = new Qwen3TtsService(settings);
        var checks = 0;
        void Check(bool condition, string name) { if (!condition) throw new Exception("Qwen regression failed: " + name); checks++; }
        Check(!engine.Check("qwen3:Vivian").Passed, "missing deployment must fail closed");
        await File.WriteAllTextAsync(Path.Combine(model, "weight.bin"), "fixture");
        await File.WriteAllTextAsync(Path.Combine(model, "deployment.json"), JsonSerializer.Serialize(new {
            revision = "fixture-v1", files = new[] { new { file = "weight.bin", size = 7 } }
        }));
        Check(engine.Check("qwen3:Vivian").Passed, "verified deployment metadata");
        Check(!engine.Check("qwen3:unknown").Passed && !engine.Check("Huihui").Passed, "no silent voice fallback");
        Check(engine.Validate(new string('中', 501), "qwen3:Vivian", 1, 0, "") is not null, "bounded text");
        Check(engine.Validate("中文", "qwen3:Vivian", 1, 0, new string('中', 301)) is not null, "bounded instruction");
        Check(engine.Validate("中文", "qwen3:Vivian", 1.1m, 0, "") is not null, "unsupported speed is explicit");
        Check(engine.Validate("中文", "qwen3:Vivian", 1, 1, "") is not null, "unsupported pitch is explicit");
        await File.AppendAllTextAsync(Path.Combine(model, "weight.bin"), "changed");
        Check(!engine.Check("qwen3:Vivian").Passed, "model file size drift");
        await File.WriteAllTextAsync(Path.Combine(model, "weight.bin"), "fixture");

        var before = engine.Identity;
        await File.AppendAllTextAsync(script, "\n# new integration version");
        Check(before != engine.Identity, "pending task detects engine code changes");
        var childPidFile = Path.Combine(root, "child.pid");
        await File.WriteAllTextAsync(script, "import subprocess,sys,time,pathlib\n" +
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n" +
            "pathlib.Path(" + JsonSerializer.Serialize(childPidFile.Replace('\\', '/')) + ").write_text(str(p.pid))\n" +
            "sys.stdin.read()\ntime.sleep(30)\n");
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var generation = engine.GenerateAsync("中文", "qwen3:Vivian", "", Path.Combine(root, "unpublished.wav"), cancellation.Token);
        for (var i = 0; i < 100 && !File.Exists(childPidFile); i++) await Task.Delay(50);
        Check(File.Exists(childPidFile), "child process started for cancellation fixture");
        var childPid = int.Parse(await File.ReadAllTextAsync(childPidFile));
        cancellation.Cancel();
        try { await generation; throw new Exception("Cancellation did not abort generation"); }
        catch (OperationCanceledException) { checks++; }
        await Task.Delay(200);
        var childAlive = false;
        try { using var child = Process.GetProcessById(childPid); childAlive = !child.HasExited; } catch (ArgumentException) { }
        Check(!childAlive && !File.Exists(Path.Combine(root, "unpublished.wav")), "cancellation kills process tree without audio publication");

        var timeoutConfig = System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(config))!;
        timeoutConfig["timeoutSeconds"] = 1;
        await File.WriteAllTextAsync(Path.Combine(root, "config", "qwen3-tts.json"), timeoutConfig.ToJsonString());
        try { await engine.GenerateAsync("中文", "qwen3:Vivian", "", Path.Combine(root, "timed-out.wav"), CancellationToken.None); throw new Exception("Timeout was not reported"); }
        catch (TimeoutException) { checks++; }
        var timedOutChildPid = int.Parse(await File.ReadAllTextAsync(childPidFile));
        var timedOutChildAlive = false;
        try { using var child = Process.GetProcessById(timedOutChildPid); timedOutChildAlive = !child.HasExited; } catch (ArgumentException) { }
        Check(!timedOutChildAlive && !File.Exists(Path.Combine(root, "timed-out.wav")), "timeout kills process tree and is not reported as user cancellation");

        using var http = new HttpClient(new BusyComfyHandler()) { BaseAddress = new Uri("http://127.0.0.1:8188") };
        var comfy = new ComfyUiClient(http, settings, NullLogger<ComfyUiClient>.Instance);
        try { await comfy.EnsureIdleForExternalGpuAsync(); throw new Exception("Busy Comfy was accepted"); }
        catch (InvalidOperationException ex) when (ex.Message.Contains("ComfyUI 仍有")) { checks++; }
        Console.WriteLine($"Qwen3 TTS contract: {checks} Passed; fixtures={root}; no GPU, cloud or database calls");
    }

    private sealed class BusyComfyHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"queue_running\":[[1,\"busy\"]],\"queue_pending\":[]}") });
    }
}
