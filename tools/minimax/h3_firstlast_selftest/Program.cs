using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

var folder = Path.GetFullPath(args.Length > 0 ? args[0] : "C:/install/AI/Data/VisualValidation20261024/h3-integration");
Directory.CreateDirectory(folder);
H3Regression.Run();
await MiniMaxLocalRegression.Run();
var settings = new StudioSettings();
var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
var paths = new AssetPathPolicy(settings, ffmpeg, NullLogger<AssetPathPolicy>.Instance);
var service = new MiniMaxLocalService(settings);
var fixtures = Path.Combine(folder, "fixtures");
Directory.CreateDirectory(fixtures);
async Task<string> Image(string name, string size, string color)
{
    var path = Path.Combine(fixtures, name);
    if (!File.Exists(path))
    {
        var start = new ProcessStartInfo(settings.FfmpegPath) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardError = true, RedirectStandardOutput = true };
        foreach (var arg in new[] { "-hide_banner", "-v", "error", "-f", "lavfi", "-i", $"color=c={color}:s={size}:r=1", "-frames:v", "1", path }) start.ArgumentList.Add(arg);
        using var process = Process.Start(start)!;
        var error = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        if (process.ExitCode != 0) throw new Exception(await error);
    }
    if (!paths.TryResolveExisting(path, out _, out var relative)) throw new Exception("Fixture path outside data"); return relative;
}
var first = await Image("synthetic-first.png", "864x480", "red");
var last = await Image("synthetic-last.png", "864x480", "blue");
var wrongSize = await Image("synthetic-wrong-size.png", "832x480", "green");
var firstHash = await ffmpeg.Sha256Async(paths.RequireExisting(first, "missing fixture"));
var lastHash = await ffmpeg.Sha256Async(paths.RequireExisting(last, "missing fixture"));
var input = new MiniMaxLocalInput(1, "One gentle gesture, same fictional subject.", first, 2026102401,
    MiniMaxLocalService.FirstLastProfile, LastFramePath: last, FirstFrameSha256: firstHash, LastFrameSha256: lastHash);
var task = MiniMaxLocalService.BuildTask(input, 1, "selftest", "h3-firstlast-selftest");
var parameters = task.Parameters!.Value;
var checks = new List<object>();
void Pass(string name, bool passed = true) { if (!passed) throw new Exception("Failed: " + name); checks.Add(new { name, status = "Passed" }); }
void Reject(string name, Action action)
{
    try { action(); } catch (InvalidOperationException) { Pass(name); return; }
    throw new Exception("Unsafe input accepted: " + name);
}
async Task RejectAsync(string name, JsonObject changed)
{
    try { await service.ValidateFrameAssetsAsync(first, JsonSerializer.SerializeToElement(changed), paths, ffmpeg); }
    catch (InvalidOperationException) { Pass(name); return; }
    throw new Exception("Unsafe media accepted: " + name);
}
JsonObject Params() => JsonNode.Parse(parameters.GetRawText())!.AsObject();
JsonObject Graph() => JsonNode.Parse(File.ReadAllText(Path.Combine(settings.WorkflowsPath, MiniMaxLocalService.FirstLastWorkflowFileName)))!.AsObject();
MiniMaxLocalService.ValidateManagedParameters(parameters, MiniMaxLocalService.FirstLastWorkflowFileName);
var bindings = await service.ValidateFrameAssetsAsync(first, parameters, paths, ffmpeg);
Pass("two-real-static-inputs-with-sha256", bindings.Count == 2 && bindings.All(b => b.Width == 864 && b.Height == 480));
Pass("baseline-profile-unchanged", MiniMaxLocalService.ResolveProfile("baseline480").WorkflowFileName == MiniMaxLocalService.WorkflowFileName);
Pass("new-profile-no-auto-retry", task.MaxRetries == 0 && task.ShotId is null && task.EpisodeId is null);
Reject("missing-last-frame", () => MiniMaxLocalService.BuildTask(input with { LastFramePath = null }, 1, "test", "test"));
Reject("missing-first-sha", () => MiniMaxLocalService.BuildTask(input with { FirstFrameSha256 = null }, 1, "test", "test"));
Reject("last-frame-on-baseline", () => MiniMaxLocalService.BuildTask(input with { Profile = "baseline480" }, 1, "test", "test"));
Reject("cross-profile-workflow", () => MiniMaxLocalService.ValidateManagedParameters(parameters, MiniMaxLocalService.WorkflowFileName));
Reject("firstlast-parameters-on-unmanaged-graph", () => MiniMaxLocalService.ValidateFrameWorkflowSelection(parameters, "unmanaged-h3.json"));
MiniMaxLocalService.ValidateFrameWorkflowSelection(parameters, MiniMaxLocalService.FirstLastWorkflowFileName); Pass("firstlast-managed-selection");
var changed = Params(); changed["lastFrameSha256"] = new string('0', 64); await RejectAsync("tail-hash-drift", changed);
changed = Params(); changed["firstFrameSha256"] = new string('0', 64); await RejectAsync("first-hash-drift", changed);
changed = Params(); changed["lastFramePath"] = "../outside.png"; changed["inputSlots"]!["lastFrame"] = "../outside.png"; await RejectAsync("outside-data-path", changed);
changed = Params(); changed["lastFramePath"] = wrongSize; changed["inputSlots"]!["lastFrame"] = wrongSize;
changed["lastFrameSha256"] = await ffmpeg.Sha256Async(paths.RequireExisting(wrongSize, "missing fixture")); await RejectAsync("wrong-tail-canvas-no-silent-crop", changed);
changed = Params(); changed["inputSlots"]!["firstFrame"] = last; await RejectAsync("first-slot-root-mismatch", changed);
changed = Params(); changed["inputSlots"]!["extra"] = first; await RejectAsync("ambiguous-extra-slot", changed);
changed = Params(); changed["lastFramePath"] = "VisualValidation20261024/missing.png"; changed["inputSlots"]!["lastFrame"] = "VisualValidation20261024/missing.png"; await RejectAsync("missing-tail-file", changed);
var graph = Graph(); H3WorkflowPolicy.Validate(graph, parameters); Pass("native-node-first-last-link-contract");
graph["6"]!["inputs"]!["last_frame"] = new JsonArray("5", 0);
Reject("tail-node-link-drift", () => H3WorkflowPolicy.Validate(graph, parameters));
graph = Graph(); graph["16"]!["class_type"] = "LoadImageMask";
Reject("tail-node-class-drift", () => H3WorkflowPolicy.Validate(graph, parameters));
graph = Graph(); changed = Params(); changed["profile"] = "baseline480";
Reject("tail-graph-on-first-only-profile", () => H3WorkflowPolicy.Validate(graph, JsonSerializer.SerializeToElement(changed)));
graph = Graph(); ComfyUiClient.PatchWorkflow(graph, "ImageToVideo", "fixed", null, "copied-first.png", null, null, parameters, "selftest");
H3WorkflowPolicy.BindCopiedFrames(graph, parameters, "copied-first.png", "copied-last.png");
Pass("explicit-copied-node-bindings", graph["5"]!["inputs"]!["image"]!.GetValue<string>() == "copied-first.png" && graph["16"]!["inputs"]!["image"]!.GetValue<string>() == "copied-last.png");
Reject("missing-copied-tail", () => H3WorkflowPolicy.BindCopiedFrames(graph, parameters, "copied-first.png", null));
changed = Params(); changed["fps"] = 60;
Reject("unregistered-fps", () => MiniMaxLocalService.ValidateManagedParameters(JsonSerializer.SerializeToElement(changed), MiniMaxLocalService.FirstLastWorkflowFileName));
await service.EnsureWorkflowPinnedAsync(Path.Combine(settings.WorkflowsPath, MiniMaxLocalService.FirstLastWorkflowFileName));
Pass("deployed-template-pinned-to-source");
var contractDocument = JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(settings.RootPath, "config", "workflow-contracts.json")))!;
var contract = contractDocument["contracts"]!.AsArray().Single(node => node!["id"]!.GetValue<string>() == "minimax-h3-firstlast480-v1")!;
var workflowHash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(Path.Combine(settings.WorkflowsPath, MiniMaxLocalService.FirstLastWorkflowFileName)))).ToLowerInvariant();
Pass("catalog-hash-matches-deployed-bytes", contract["notes"]!.GetValue<string>().Split('|')[0].Trim() == "sha256=" + workflowHash);
var report = new { status = "Passed", syntheticFixturesOnly = true, gpuSubmissions = 0, databaseWrites = 0, remoteCalls = 0, checks };
await File.WriteAllTextAsync(Path.Combine(folder, "selftest.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(JsonSerializer.Serialize(new { status = "Passed", checks = checks.Count, gpuSubmissions = 0, report = Path.Combine(folder, "selftest.json") }));
