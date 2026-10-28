using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

public sealed record VisualActingOutput(string Receipt, int Width, int Height, decimal Fps, int Frames, decimal Duration, string? SupportMask = null);

/// <summary>Fixed, offline LivePortrait preview runner. Never executes a client-provided command.</summary>
public sealed class VisualActingService(StudioSettings settings, AssetPathPolicy paths, FfmpegService ffmpeg)
{
    private string Script => Path.Combine(settings.RootPath, "tools", "visual_pilot_acting", "run.py");
    private string Python => Path.Combine(Directory.GetParent(settings.RootPath)!.FullName, "LivePortraitPilot", "venv", "Scripts", "python.exe");
    public string Identity => File.Exists(Script) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Script))).ToLowerInvariant() : "unconfigured";
    private string ScriptFor(JsonElement p)
    {
        if (p.TryGetProperty("repairProfile", out var selected) && selected.ValueKind != JsonValueKind.String)
            throw new InvalidOperationException("修复分支必须为已登记字符串");
        var profile = Value(p, "repairProfile");
        if (profile is null) return Script;
        if (profile == "dialogue-blink-v1") return Path.Combine(settings.RootPath, "tools", "dialogue_visual", "acting.py");
        if (profile == "dialogue-stable-v1") return Path.Combine(settings.RootPath, "tools", "dialogue_stable", "acting.py");
        if (profile == "dialogue-stable-v2") return Path.Combine(settings.RootPath, "tools", "dialogue_stable", "deterministic.py");
        if (profile == "dialogue-hybrid-full-v1") return Path.Combine(settings.RootPath, "tools", "dialogue_sync_full", "hybrid.py");
        if (profile == "dialogue-hybrid-v1") return Path.Combine(settings.RootPath, "tools", "dialogue_sync", "hybrid.py");
        if (profile != "blink-residual-v1") throw new InvalidOperationException("未知的表演修复分支");
        return Path.Combine(settings.RootPath, "tools", "visual_targeted", "blink.py");
    }
    public string IdentityFor(JsonElement p) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(ScriptFor(p)))).ToLowerInvariant();

    public async Task<JsonObject> ValidateAsync(JsonElement parameters, bool inspectRuntime, CancellationToken ct)
    {
        var selectedScript = ScriptFor(parameters);
        if (!File.Exists(Python) || !File.Exists(selectedScript)) throw new InvalidOperationException("本地参考表演环境尚未就绪");
        var manifest = paths.RequireExisting(Value(parameters, "manifest"), "表演清单必须位于受控Data目录");
        if (Path.GetExtension(manifest) != ".json" || await ffmpeg.Sha256Async(manifest, ct) != Value(parameters, "manifestSha256"))
            throw new InvalidOperationException("表演清单哈希不符");
        if (!string.Equals(Value(parameters, "engineVersion"), IdentityFor(parameters), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("参考表演脚本版本已改变");
        var request = JsonNode.Parse(await File.ReadAllTextAsync(manifest, ct))?.AsObject()
            ?? throw new InvalidOperationException("参考表演清单无效");
        if (request["repairProfile"]?.GetValue<string>() != Value(parameters, "repairProfile"))
            throw new InvalidOperationException("修复清单与已选分支不一致");
        if (Value(parameters, "repairProfile") is "blink-residual-v1" or "dialogue-blink-v1" or "dialogue-hybrid-v1" or "dialogue-hybrid-full-v1")
        {
            var gain = request["eyeResidualGain"]?.GetValue<double>() ?? 1;
            if (gain is not (1 or 1.5)) throw new InvalidOperationException("眼部残差强度未登记");
        }
        var stable = Value(parameters, "repairProfile") is "dialogue-stable-v1" or "dialogue-stable-v2";
        var fullHybrid = Value(parameters, "repairProfile") == "dialogue-hybrid-full-v1";
        var hybrid = fullHybrid || Value(parameters, "repairProfile") == "dialogue-hybrid-v1";
        var hybridFrames = fullHybrid ? 151 : 57;
        var dialogue = stable || Value(parameters, "repairProfile") is "dialogue-blink-v1" or "dialogue-hybrid-v1" or "dialogue-hybrid-full-v1";
        if (dialogue && request["faceDirection"]?.GetValue<string>() is not ("large-small" or "left-right" or "right-left"))
            throw new InvalidOperationException("对话镜头必须明确绑定人物方向");
        foreach (var role in new[] { "source", "driving" })
        {
            var file = paths.RequireExisting(request[role + "Path"]?.GetValue<string>(), "表演输入必须位于受控Data目录");
            var extension = Path.GetExtension(file).ToLowerInvariant();
            if (role == "source" && extension is not (".png" or ".jpg" or ".jpeg" or ".webp") || role == "driving" && extension != ".mp4")
                throw new InvalidOperationException("表演源必须为图片，驱动必须为MP4，不接受脚本或模板输入");
            if (!string.Equals(await ffmpeg.Sha256Async(file, ct), request[role + "Sha256"]?.GetValue<string>(), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("表演输入哈希不符");
            request[role + "Path"] = file;
        }
        var duration = request["durationSeconds"]?.GetValue<double>() ?? 2;
        var start = request["drivingStartSeconds"]?.GetValue<double>() ?? 0;
        var multiplier = request["drivingMultiplier"]?.GetValue<double>() ?? .6;
        var region = request["animationRegion"]?.GetValue<string>() ?? "exp";
        if (!double.IsFinite(duration) || duration < (dialogue ? 1 : 2) || duration > (dialogue ? 7 : 3) || !double.IsFinite(start) || start is < 0 or > 60
            || !double.IsFinite(multiplier) || multiplier is < .1 or > 1 || region is not ("exp" or "all"))
            throw new InvalidOperationException("参考表演仅开放2至3秒、exp/all区域的独立实验");
        if (request["licenseAcknowledgement"]?.GetValue<string>() != "ExperimentalNonCommercialInsightFaceWeights")
            throw new InvalidOperationException("本轮表演使用非商用研究检测权重，必须明确绑定实验许可");
        var probe = await ffmpeg.ProbeAsync(request["drivingPath"]!.GetValue<string>(), ct)
            ?? throw new InvalidOperationException("驱动视频无法探测");
        if (stable)
        {
            var role = request["stableRole"]?.GetValue<string>();
            var (count, direction) = role switch {
                "female-close" => (57, "large-small"), "male-close" => (46, "large-small"),
                "female-wide" => (151, "left-right"), "male-wide" => (151, "right-left"),
                _ => throw new InvalidOperationException("稳定表演角色未登记")
            };
            var pose = paths.RequireExisting(request["posePath"]?.GetValue<string>(), "稳定姿态必须位于Data目录");
            var poseProbe = await ffmpeg.ProbeAsync(pose, ct);
            if (Path.GetExtension(pose) != ".mp4" || await ffmpeg.Sha256Async(pose, ct) != request["poseSha256"]?.GetValue<string>()
                || duration != count / 25d || start != 0 || multiplier != 1 || region != "all"
                || request["faceDirection"]?.GetValue<string>() != direction || (request["eyeResidualGain"]?.GetValue<double>() ?? 1) != 1
                || probe.Fps != 25 || probe.FrameCount != count || poseProbe?.Fps != 25 || poseProbe.FrameCount != count)
                throw new InvalidOperationException("稳定表演仅开放固定角色、帧数、25FPS和已绑定姿态");
            request["posePath"] = pose;
        }
        if (hybrid)
        {
            var pose = paths.RequireExisting(request["posePath"]?.GetValue<string>(), "独立姿态驱动必须位于受控Data目录");
            if (Path.GetExtension(pose) != ".mp4" || await ffmpeg.Sha256Async(pose, ct) != request["poseSha256"]?.GetValue<string>())
                throw new InvalidOperationException("独立姿态驱动类型或SHA不符");
            var poseProbe = await ffmpeg.ProbeAsync(pose, ct);
            if (duration != hybridFrames / 25d || multiplier != 1 || region != "all" || request["faceDirection"]?.GetValue<string>() is not ("left-right" or "right-left")
                || probe.Fps != 25 || probe.FrameCount != hybridFrames || poseProbe?.Fps != 25 || poseProbe.FrameCount != hybridFrames || poseProbe.DurationSeconds is not { } poseDuration
                || Math.Abs(poseDuration - hybridFrames / 25d) > .001)
                throw new InvalidOperationException("双人嘴部与姿态解耦须满足已登记分支的固定帧数、25FPS与系数1");
            request["posePath"] = pose;
        }
        if (probe.DurationSeconds is not { } length || length + .02 < start + duration) throw new InvalidOperationException("驱动片段长度不足，禁止循环填充");
        if (probe.Fps is not { } fps || fps is not (24 or 25) || Math.Abs(duration * fps - Math.Round(duration * fps)) > .001)
            throw new InvalidOperationException("参考表演仅接收24或25FPS且帧数可精确对齐的短片");
        var source = await ffmpeg.ProbeAsync(request["sourcePath"]!.GetValue<string>(), ct)
            ?? throw new InvalidOperationException("人物图片无法探测");
        if (source.Width is not { } width || source.Height is not { } height || width < 256 || height < 256
            || width > 1280 || height > 1280 || width % 2 != 0 || height % 2 != 0)
            throw new InvalidOperationException("参考表演原图边长仅开放256至1280的偶数画幅");
        if ((hybrid || stable) && (width != 1024 || height != 576)) throw new InvalidOperationException("嘴部与姿态分离仅开放1024×576参考图");
        request["expectedWidth"] = width; request["expectedHeight"] = height;
        request["expectedFps"] = fps; request["expectedFrames"] = (int)Math.Round(duration * fps);
        if (inspectRuntime)
        {
            var directory = Path.Combine(settings.DataPath, stable ? "DialogueStable20261025" : fullHybrid ? "DialogueSyncFull20261025" : hybrid ? "DialogueSync20261025" : dialogue ? "DialogueVisual20261025" : Value(parameters, "repairProfile") is null ? "VisualValidation20261024" : "VisualTargeted20261024", "service-preflight");
            Directory.CreateDirectory(directory);
            var receipt = Path.Combine(directory, Guid.NewGuid().ToString("N") + ".json");
            await RunAsync(null, receipt, ct, selectedScript);
            var preflight = JsonNode.Parse(await File.ReadAllTextAsync(receipt, ct))?.AsObject();
            if (preflight?["status"]?.GetValue<string>() != "Passed" || preflight["modelLoaded"]?.GetValue<bool>() != false
                || preflight["gpuInferenceStarted"]?.GetValue<bool>() != false
                || preflight["licenseStatus"]?.GetValue<string>() != "ExperimentalNonCommercialInsightFaceWeights")
                throw new InvalidOperationException("表演环境预检回执未明确通过无GPU、无模型加载检查");
            if (preflight["repairProfile"]?.GetValue<string>() != Value(parameters, "repairProfile"))
                throw new InvalidOperationException("表演预检分支不一致");
        }
        return request;
    }

    public async Task<VisualActingOutput> AnimateAsync(JsonElement parameters, string stagingPath, CancellationToken ct)
    {
        var request = await ValidateAsync(parameters, false, ct);
        var directory = Path.GetDirectoryName(stagingPath)!;
        request["outputDirectory"] = Path.Combine(directory, "liveportrait-output");
        var manifest = stagingPath + ".manifest.json";
        var receipt = stagingPath + ".acting.json";
        await File.WriteAllTextAsync(manifest, request.ToJsonString(), new UTF8Encoding(false), ct);
        await RunAsync(manifest, receipt, ct, ScriptFor(parameters));
        var response = JsonNode.Parse(await File.ReadAllTextAsync(receipt, ct))!.AsObject();
        if (response["repairProfile"]?.GetValue<string>() != Value(parameters, "repairProfile"))
            throw new InvalidOperationException("表演输出修复分支不一致");
        if ((Value(parameters, "repairProfile") is "blink-residual-v1" or "dialogue-blink-v1" or "dialogue-hybrid-v1" or "dialogue-hybrid-full-v1")
            && response["eyeResidualGain"]?.GetValue<double>() != (request["eyeResidualGain"]?.GetValue<double>() ?? 1))
            throw new InvalidOperationException("眼部残差回执强度与清单不一致");
        string? supportMask = null;
        if (Value(parameters, "repairProfile") is "dialogue-blink-v1" or "dialogue-hybrid-v1" or "dialogue-hybrid-full-v1" or "dialogue-stable-v1" or "dialogue-stable-v2")
        {
            if (response["faceDirection"]?.GetValue<string>() != request["faceDirection"]?.GetValue<string>()) throw new InvalidOperationException("对话人物方向回执不符");
            var mask = paths.RequireExisting(response["faceSupportMaskPath"]?.GetValue<string>(), "对话人物支持区域缺失");
            var supportRoot = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!mask.StartsWith(supportRoot, StringComparison.OrdinalIgnoreCase) || await ffmpeg.Sha256Async(mask, ct) != response["faceSupportMaskSha256"]?.GetValue<string>())
                throw new InvalidOperationException("对话人物支持区域来源或SHA不符");
            var maskProbe = await ffmpeg.ProbeAsync(mask, ct);
            if (Path.GetExtension(mask) != ".png" || maskProbe?.Width != request["expectedWidth"]!.GetValue<int>() || maskProbe?.Height != request["expectedHeight"]!.GetValue<int>())
                throw new InvalidOperationException("对话人物支持区域画幅不符");
            supportMask = mask;
        }
        if (Value(parameters, "repairProfile") is "dialogue-hybrid-v1" or "dialogue-hybrid-full-v1")
        {
            if (response["poseSha256"]?.GetValue<string>() != request["poseSha256"]?.GetValue<string>() || response["sourceLipNormalized"]?.GetValue<bool>() != true
                || response["hybridMotionFrames"] is not JsonArray motion || motion.Count != request["expectedFrames"]!.GetValue<int>()
                || motion.Any(frame => frame?["poseFieldsMaxChange"]?.GetValue<double>() != 0 || frame?["nonLipExpressionMaxChange"]?.GetValue<double>() != 0)
                || await ffmpeg.Sha256Async(request["posePath"]!.GetValue<string>(), ct) != request["poseSha256"]?.GetValue<string>())
                throw new InvalidOperationException("嘴部与姿态分离回执或姿态源发生漂移");
        }
        if (Value(parameters, "repairProfile") is "dialogue-stable-v1" or "dialogue-stable-v2")
        {
            if (response["stableRole"]?.GetValue<string>() != request["stableRole"]?.GetValue<string>()
                || response["poseSha256"]?.GetValue<string>() != request["poseSha256"]?.GetValue<string>()
                || response["sourceLipNormalized"]?.GetValue<bool>() != true || response["eyeResidualGain"]?.GetValue<double>() != 1
                || response["controlledMotionFrames"] is not JsonArray controls || controls.Count != request["expectedFrames"]!.GetValue<int>()
                || controls.Any(f => f?["poseFieldsMaxChange"]?.GetValue<double>() != 0 || f?["eyeExpressionDeltaMax"]?.GetValue<double>() != 0)
                || await ffmpeg.Sha256Async(request["posePath"]!.GetValue<string>(), ct) != request["poseSha256"]?.GetValue<string>())
                throw new InvalidOperationException("稳定表演控制轨迹或绑定姿态不符");
            if (Value(parameters, "repairProfile") == "dialogue-stable-v2" && (response["deterministicAlgorithms"]?.GetValue<bool>() != true
                || response["cudnnBenchmark"]?.GetValue<bool>() != false || response["tf32"]?.GetValue<bool>() != false))
                throw new InvalidOperationException("稳定V2未明确确认确定性推理参数");
        }
        var output = paths.RequireExisting(response["outputPath"]?.GetValue<string>(), "表演输出必须位于受控Data目录");
        var requiredRoot = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!Path.GetFullPath(output).StartsWith(requiredRoot, StringComparison.OrdinalIgnoreCase)
            || Path.GetExtension(output) != ".mp4" || await ffmpeg.Sha256Async(output, ct) != response["outputSha256"]?.GetValue<string>())
            throw new InvalidOperationException("表演输出来源或哈希无效");
        var width = request["expectedWidth"]!.GetValue<int>(); var height = request["expectedHeight"]!.GetValue<int>();
        var fps = request["expectedFps"]!.GetValue<double>(); var frames = request["expectedFrames"]!.GetValue<int>();
        var duration = request["durationSeconds"]?.GetValue<double>() ?? 2;
        var actual = await ffmpeg.ProbeAsync(output, ct) ?? throw new InvalidOperationException("表演输出无法独立探测");
        if (actual.Width != width || actual.Height != height || actual.FrameCount != frames || actual.Fps is not { } actualFps
            || Math.Abs(actualFps - fps) > .001 || actual.DurationSeconds is not { } actualDuration || Math.Abs(actualDuration - duration) > 1 / fps)
            throw new InvalidOperationException("表演实际视频与已冻结的原图画幅、驱动帧率或请求时长不符");
        if (response["status"]?.GetValue<string>() != "Passed" || response["provider"]?.GetValue<string>() != "OfficialLivePortraitLocalPilot"
            || response["gpuInferenceStarted"]?.GetValue<bool>() != true || response["driverIsNewHumanPerformance"]?.GetValue<bool>() != false
            || response["sourceSha256"]?.GetValue<string>() != request["sourceSha256"]?.GetValue<string>()
            || response["drivingSha256"]?.GetValue<string>() != request["drivingSha256"]?.GetValue<string>()
            || response["width"]?.GetValue<int>() != width || response["height"]?.GetValue<int>() != height || response["frames"]?.GetValue<int>() != frames)
            throw new InvalidOperationException("表演回执与实际请求、输入或输出规格不一致");
        var source = paths.RequireExisting(request["sourcePath"]!.GetValue<string>(), "表演原图缺失");
        var driving = paths.RequireExisting(request["drivingPath"]!.GetValue<string>(), "表演驱动缺失");
        if (await ffmpeg.Sha256Async(source, ct) != request["sourceSha256"]?.GetValue<string>()
            || await ffmpeg.Sha256Async(driving, ct) != request["drivingSha256"]?.GetValue<string>())
            throw new InvalidOperationException("表演执行期间输入发生漂移");
        if (!string.Equals(Value(parameters, "engineVersion"), IdentityFor(parameters), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("参考表演执行期间脚本版本发生漂移");
        ct.ThrowIfCancellationRequested();
        File.Copy(output, stagingPath, false);
        return new(receipt, width, height, (decimal)fps, frames, (decimal)duration, supportMask);
    }

    private async Task RunAsync(string? manifest, string receipt, CancellationToken ct, string? script = null)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromMinutes(manifest is null ? 5 : 30));
        using var process = new Process { StartInfo = new ProcessStartInfo {
            FileName = Python, WorkingDirectory = Path.Combine(Directory.GetParent(settings.RootPath)!.FullName, "LivePortraitPilot", "official"),
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        }};
        foreach (var arg in new[] { "-u", script ?? Script, "--receipt", receipt }) process.StartInfo.ArgumentList.Add(arg);
        if (manifest is null) process.StartInfo.ArgumentList.Add("--preflight");
        else { process.StartInfo.ArgumentList.Add("--manifest"); process.StartInfo.ArgumentList.Add(manifest); }
        foreach (var variable in new[] { "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY", "PYTHONUTF8" })
            process.StartInfo.Environment[variable] = "1";
        if (manifest is null) process.StartInfo.Environment["CUDA_VISIBLE_DEVICES"] = "";
        if (!process.Start()) throw new InvalidOperationException("本地表演进程无法启动");
        using var cancellation = timeout.Token.Register(() => { try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { } });
        var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { }
            // The GPU lease is held by our caller until the actual model process has exited.
            await process.WaitForExitAsync(CancellationToken.None);
            await File.WriteAllTextAsync(receipt + ".log", await stdout + "\n" + await stderr, CancellationToken.None);
            if (ct.IsCancellationRequested) throw;
            throw new TimeoutException("本地参考表演超过时限，模型进程树已停止");
        }
        var log = await stdout + "\n" + await stderr;
        await File.WriteAllTextAsync(receipt + ".log", log, CancellationToken.None);
        if (process.ExitCode != 0 || !File.Exists(receipt))
            throw new InvalidOperationException("本地表演预检或推理失败：" + log[^Math.Min(1800, log.Length)..]);
    }

    private static string? Value(JsonElement p, string name) => p.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
}
