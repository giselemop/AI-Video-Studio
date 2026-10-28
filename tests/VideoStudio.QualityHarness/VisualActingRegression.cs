using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

/// <summary>CPU-only protocol fixtures. The synthetic runner does not import LivePortrait or load models.</summary>
internal static class VisualActingRegression
{
    public static async Task Run()
    {
        var root = Path.Combine(@"C:\install\AI\Data\acceptance", "visual_acting_" + Guid.NewGuid().ToString("N"));
        var studio = Path.Combine(root, "Studio");
        var scriptFolder = Path.Combine(studio, "tools", "visual_pilot_acting");
        var runtime = Path.Combine(root, "LivePortraitPilot", "venv", "Scripts");
        var official = Path.Combine(root, "LivePortraitPilot", "official");
        foreach (var dir in new[] { root, studio, scriptFolder, runtime, official }) Directory.CreateDirectory(dir);
        // Isolated local CPython standard-library runner for cancellation/receipt tests.
        var python = @"C:\install\Python";
        foreach (var name in new[] { "python.exe", "python3.dll", "python313.dll", "vcruntime140.dll", "vcruntime140_1.dll" })
            File.Copy(Path.Combine(python, name), Path.Combine(runtime, name), false);
        await File.WriteAllTextAsync(Path.Combine(runtime, "python313._pth"), python + "\\Lib\n" + python + "\\DLLs\n.\n");
        var script = Path.Combine(scriptFolder, "run.py");
        await File.WriteAllTextAsync(script, """
import argparse,json,pathlib,subprocess,sys,time,hashlib
p=argparse.ArgumentParser();p.add_argument('--manifest');p.add_argument('--receipt',required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args()
script=pathlib.Path(__file__);mode=script.with_name('fixture-mode.txt').read_text().strip();receipt=pathlib.Path(a.receipt)
def sha(x):return hashlib.sha256(pathlib.Path(x).read_bytes()).hexdigest()
if mode=='cancel-child':
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)'])
 script.with_name('child.pid').write_text(str(child.pid));time.sleep(90)
if a.preflight:
 receipt.write_text(json.dumps({'status':'Failed' if mode=='bad-preflight-status' else 'Passed','modelLoaded':False,'gpuInferenceStarted':False,'licenseStatus':'ExperimentalNonCommercialInsightFaceWeights'}));sys.exit(0)
q=json.loads(pathlib.Path(a.manifest).read_text(encoding='utf-8-sig'));out=pathlib.Path(q['outputDirectory']);out.mkdir()
video=out/'synthetic-protocol-output.mp4'
duration=3 if mode=='wrong-duration' else q.get('durationSeconds',2)
subprocess.run([r'C:\install\FFmpeg\bin\ffmpeg.exe','-nostdin','-v','error','-i',q['drivingPath'],'-t',str(duration),'-an','-c:v','libx264','-crf','16',str(video)],check=True)
if mode=='outside-output':video=pathlib.Path(q['drivingPath'])
if mode=='source-drift':pathlib.Path(q['sourcePath']).write_bytes(pathlib.Path(q['sourcePath']).read_bytes()+b'fixture-drift')
if mode=='script-drift':script.write_text(script.read_text()+'\n# fixture-drift\n')
r={'status':'Passed','provider':'OfficialLivePortraitLocalPilot','sourcePath':q['sourcePath'],'sourceSha256':q['sourceSha256'],'drivingPath':q['drivingPath'],'drivingSha256':q['drivingSha256'],'outputPath':str(video),'outputSha256':sha(video),'width':320,'height':256,'fps':'24/1','frames':int(duration*24),'durationSeconds':duration,'gpuInferenceStarted':True,'modelLoaded':True,'driverIsNewHumanPerformance':False,'cloudCalls':0,'licenseStatus':'ExperimentalNonCommercialInsightFaceWeights','contentReview':'NeedReview','publicationStatus':'Blocked','syntheticProtocolFixture':True}
if mode=='wrong-output-hash':r['outputSha256']='0'*64
if mode=='wrong-input-receipt':r['sourceSha256']='0'*64
if mode=='wrong-repair-receipt':r['repairProfile']='blink-residual-v1'
receipt.write_text(json.dumps(r))
""");
        var settings = new StudioSettings { RootPath = studio, DataPath = root };
        var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
        var paths = new AssetPathPolicy(settings, ffmpeg, NullLogger<AssetPathPolicy>.Instance);
        var service = new VisualActingService(settings, paths, ffmpeg);
        async Task Ffmpeg(params string[] args)
        {
            var start = new ProcessStartInfo(settings.FfmpegPath) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardError = true, RedirectStandardOutput = true };
            foreach (var arg in args) start.ArgumentList.Add(arg);
            using var process = Process.Start(start)!;
            var error = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            if (process.ExitCode != 0) throw new Exception(await error);
        }
        var source = Path.Combine(root, "synthetic-source.png");
        var driving = Path.Combine(root, "synthetic-driving.mp4");
        await Ffmpeg("-v", "error", "-f", "lavfi", "-i", "color=red:s=320x256", "-frames:v", "1", source);
        await Ffmpeg("-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x256:r=24:d=3", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", driving);
        var sourceBytes = await File.ReadAllBytesAsync(source);
        var checks = new List<object>(); var failed = new List<string>();
        void Check(string name, bool passed) { checks.Add(new { name, status = passed ? "Passed" : "Failed" }); if (!passed) failed.Add(name); }
        async Task<JsonElement> Parameters(Action<JsonObject>? change = null)
        {
            var manifest = new JsonObject
            {
                ["sourcePath"] = source, ["sourceSha256"] = await ffmpeg.Sha256Async(source),
                ["drivingPath"] = driving, ["drivingSha256"] = await ffmpeg.Sha256Async(driving),
                ["durationSeconds"] = 2, ["drivingStartSeconds"] = 0, ["drivingMultiplier"] = .6,
                ["animationRegion"] = "exp", ["licenseAcknowledgement"] = "ExperimentalNonCommercialInsightFaceWeights"
            };
            change?.Invoke(manifest);
            var file = Path.Combine(root, "manifest-" + Guid.NewGuid().ToString("N") + ".json");
            await File.WriteAllTextAsync(file, manifest.ToJsonString());
            return JsonSerializer.SerializeToElement(new { manifest = file, manifestSha256 = await ffmpeg.Sha256Async(file), engineVersion = service.Identity });
        }
        async Task Reject(string name, JsonElement parameters)
        {
            try { await service.ValidateAsync(parameters, false, CancellationToken.None); Check(name, false); }
            catch (Exception ex) when (ex is InvalidOperationException or JsonException or IOException or ArgumentException) { Check(name, true); }
        }
        var valid = await Parameters();
        await service.ValidateAsync(valid, false, CancellationToken.None); Check("valid-real-input-probes-no-runtime", true);
        await File.WriteAllTextAsync(Path.Combine(scriptFolder, "fixture-mode.txt"), "valid");
        await service.ValidateAsync(valid, true, CancellationToken.None); Check("valid-runtime-preflight-receipt-no-model", true);
        foreach (var (key, value) in new[] { ("durationSeconds", 1.0), ("durationSeconds", 4.0), ("drivingStartSeconds", 59.0), ("drivingMultiplier", 1.1) })
            await Reject("reject-" + key + "-" + value, await Parameters(m => m[key] = value));
        await Reject("reject-region", await Parameters(m => m["animationRegion"] = "pose"));
        await Reject("reject-license", await Parameters(m => m["licenseAcknowledgement"] = "approved"));
        await Reject("reject-source-hash", await Parameters(m => m["sourceSha256"] = new string('0', 64)));
        await Reject("reject-driver-extension", await Parameters(m => m["drivingPath"] = source));
        await Reject("reject-outside-data", await Parameters(m => m["sourcePath"] = Path.Combine(Path.GetDirectoryName(root)!, "outside.png")));
        var invalidEngine = JsonNode.Parse(valid.GetRawText())!.AsObject(); invalidEngine["engineVersion"] = new string('0', 64);
        await Reject("reject-engine-drift-before-execution", JsonSerializer.SerializeToElement(invalidEngine));
        var driftManifest = JsonNode.Parse(valid.GetRawText())!.AsObject(); driftManifest["manifestSha256"] = new string('0', 64);
        await Reject("reject-manifest-hash", JsonSerializer.SerializeToElement(driftManifest));
        await Reject("reject-unselected-repair-manifest", await Parameters(m => m["repairProfile"] = "blink-residual-v1"));
        var unknownRepair = JsonNode.Parse(valid.GetRawText())!.AsObject(); unknownRepair["repairProfile"] = "unknown";
        await Reject("reject-unknown-repair-profile", JsonSerializer.SerializeToElement(unknownRepair));
        unknownRepair["repairProfile"] = 123;
        await Reject("reject-nonstring-repair-profile", JsonSerializer.SerializeToElement(unknownRepair));
        async Task AnimateCase(string mode, bool shouldReject)
        {
            await File.WriteAllBytesAsync(source, sourceBytes);
            await File.WriteAllTextAsync(Path.Combine(scriptFolder, "fixture-mode.txt"), mode);
            var parameters = await Parameters();
            var stage = Path.Combine(root, "stage-" + mode, "unpublished.mp4"); Directory.CreateDirectory(Path.GetDirectoryName(stage)!);
            try
            {
                await service.AnimateAsync(parameters, stage, CancellationToken.None);
                Check(mode, !shouldReject && File.Exists(stage));
            }
            catch (InvalidOperationException) { Check(mode, shouldReject && !File.Exists(stage)); }
        }
        await AnimateCase("valid", false);
        await AnimateCase("outside-output", true);
        await AnimateCase("wrong-output-hash", true);
        await AnimateCase("source-drift", true);
        await AnimateCase("wrong-input-receipt", true);
        await AnimateCase("wrong-duration", true);
        await AnimateCase("wrong-repair-receipt", true);
        await AnimateCase("script-drift", true);
        await File.WriteAllBytesAsync(source, sourceBytes);
        await File.WriteAllTextAsync(Path.Combine(scriptFolder, "fixture-mode.txt"), "cancel-child");
        var run = typeof(VisualActingService).GetMethod("RunAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var cancelReceipt = Path.Combine(root, "cancel.json");
        var running = (Task)run.Invoke(service, [null, cancelReceipt, cancellation.Token, null])!;
        var childFile = Path.Combine(scriptFolder, "child.pid");
        for (var i = 0; i < 100 && !File.Exists(childFile); i++) await Task.Delay(50);
        Check("child-process-started", File.Exists(childFile));
        cancellation.Cancel();
        try { await running; Check("cancellation-propagated", false); } catch (OperationCanceledException) { Check("cancellation-propagated", true); }
        bool Alive(int pid) { try { using var process = Process.GetProcessById(pid); return !process.HasExited; } catch (ArgumentException) { return false; } }
        var childPid = int.Parse(await File.ReadAllTextAsync(childFile));
        for (var i = 0; i < 40 && Alive(childPid); i++) await Task.Delay(50);
        Check("cancel-kills-descendant-no-receipt", !Alive(childPid) && !File.Exists(cancelReceipt));
        await File.WriteAllTextAsync(Path.Combine(scriptFolder, "fixture-mode.txt"), "bad-preflight-status");
        var runtimeReceipt = Path.Combine(root, "preflight-status.json");
        try { await service.ValidateAsync(await Parameters(), true, CancellationToken.None); Check("reject-preflight-failed-status", false); }
        catch (InvalidOperationException) { Check("reject-preflight-failed-status", true); }
        var report = new { status = failed.Count == 0 ? "Passed" : "Failed", cpuSyntheticProtocolFixture = true, gpuInference = false, databaseWrites = false, root, checks, failed };
        await File.WriteAllTextAsync(Path.Combine(root, "report.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine(JsonSerializer.Serialize(new { report = Path.Combine(root, "report.json"), status = report.status, checks = checks.Count, failed }));
        if (failed.Count > 0) throw new Exception("Visual acting regression failed: " + string.Join(", ", failed));
    }
}
