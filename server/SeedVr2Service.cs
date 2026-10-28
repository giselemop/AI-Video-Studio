using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

public sealed class SeedVr2Service
{
    private readonly StudioSettings _settings;
    private string ConfigPath => Path.Combine(_settings.RootPath, "config", "seedvr2.json");
    private string ScriptPath => Path.Combine(_settings.RootPath, "tools", "video_detail", "restore.py");
    public SeedVr2Service(StudioSettings settings) => _settings = settings;
    public string Identity => File.Exists(ConfigPath) && File.Exists(ScriptPath)
        ? Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(File.ReadAllText(ConfigPath) + "\n" + File.ReadAllText(ScriptPath)))) : "unconfigured";
    private JsonObject Configuration() => JsonNode.Parse(File.ReadAllText(ConfigPath))!.AsObject();
    public (bool Ready, string Message) Check()
    {
        try
        {
            var c = Configuration();
            if (!File.Exists(c["python"]!.GetValue<string>()) || !File.Exists(ScriptPath)
                || !File.Exists(Path.Combine(c["engineDirectory"]!.GetValue<string>(), "inference_cli.py")))
                return (false, "SeedVR2独立环境尚未部署");
            var model = Path.GetFullPath(c["modelDirectory"]!.GetValue<string>());
            var root = Path.GetFullPath(_settings.ModelsPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!model.StartsWith(root, StringComparison.OrdinalIgnoreCase)) return (false, "SeedVR2模型路径超出受控目录");
            var receipt = JsonNode.Parse(File.ReadAllText(Path.Combine(model, "deployment.json")))!;
            if (receipt["revision"]?.GetValue<string>() != c["revision"]?.GetValue<string>()
                || receipt["engineRevision"]?.GetValue<string>() != c["engineRevision"]?.GetValue<string>()) return (false, "SeedVR2部署版本不一致");
            foreach (var f in c["files"]!.AsArray())
            {
                var p = Path.GetFullPath(Path.Combine(model, f!["file"]!.GetValue<string>()));
                if (!p.StartsWith(model + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                    || !File.Exists(p) || new FileInfo(p).Length != f["size"]!.GetValue<long>()) return (false, "SeedVR2模型文件缺失或大小不一致");
            }
            return (true, "SeedVR2 3B FP8就绪；仅用于受GPU互斥保护的独立预览修复");
        }
        catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException or ArgumentException) { return (false, "SeedVR2部署配置不可用"); }
    }

    public static (int Width, int Height, string Profile) ResolveOutput(JsonElement parameters, int sourceWidth, int sourceHeight)
    {
        var profile = "source";
        if (parameters.TryGetProperty("outputProfile", out var selected))
        {
            if (selected.ValueKind != JsonValueKind.String) throw new InvalidOperationException("SeedVR2输出规格必须为source或qhd1440");
            profile = selected.GetString()!;
        }
        if (profile == "source")
        {
            if (parameters.TryGetProperty("targetWidth", out _) || parameters.TryGetProperty("targetHeight", out _))
                throw new InvalidOperationException("保留源尺寸时不接受目标尺寸；2K超分需显式选择qhd1440");
            return (sourceWidth, sourceHeight, profile);
        }
        if (profile != "qhd1440"
            || !parameters.TryGetProperty("targetWidth", out var width) || !width.TryGetInt32(out var w) || w != 2560
            || !parameters.TryGetProperty("targetHeight", out var height) || !height.TryGetInt32(out var h) || h != 1440
            || sourceWidth * 9 != sourceHeight * 16)
            throw new InvalidOperationException("qhd1440仅接受16:9源视频并明确输出2560×1440");
        return (2560, 1440, profile);
    }

    public async Task RestoreAsync(string source, string sourceSha256, string output, double strength, int[] cuts,
        int outputWidth, int outputHeight, string outputProfile, CancellationToken ct)
    {
        var ready = Check();
        if (!ready.Ready) throw new InvalidOperationException(ready.Message);
        var c = Configuration();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(c["timeoutSeconds"]!.GetValue<int>()));
        using var process = new Process { StartInfo = new ProcessStartInfo
        {
            FileName = c["python"]!.GetValue<string>(), WorkingDirectory = _settings.RootPath,
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        } };
        foreach (var arg in new[] { "-u", ScriptPath, "--config", ConfigPath }) process.StartInfo.ArgumentList.Add(arg);
        process.StartInfo.Environment["PYTHONUTF8"] = "1";
        process.StartInfo.Environment["HF_HUB_OFFLINE"] = "1";
        process.StartInfo.Environment["TRANSFORMERS_OFFLINE"] = "1";
        process.StartInfo.Environment["HF_HOME"] = Path.Combine(_settings.DataPath, "Cache", "SeedVR2");
        process.StartInfo.Environment["PATH"] = Path.GetDirectoryName(_settings.FfmpegPath) + Path.PathSeparator + Environment.GetEnvironmentVariable("PATH");
        if (!process.Start()) throw new InvalidOperationException("无法启动SeedVR2本地修复");
        using var cancellation = timeout.Token.Register(() => { try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { } });
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        await process.StandardInput.WriteAsync(JsonSerializer.Serialize(new { source, sourceSha256, output, strength, cutFrames = cuts,
            outputWidth, outputHeight, outputProfile,
            dataRoot = _settings.DataPath, ffmpeg = _settings.FfmpegPath, ffprobe = _settings.FfprobePath }));
        process.StandardInput.Close();
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } catch (InvalidOperationException) { }
            if (!ct.IsCancellationRequested) throw new TimeoutException("SeedVR2超过配置时限，推理进程已终止");
            throw;
        }
        var log = await stdout + "\n" + await stderr;
        await File.WriteAllTextAsync(output + ".seedvr.log", log, CancellationToken.None);
        if (process.ExitCode != 0 || !File.Exists(output) || !File.Exists(output + ".seedvr.json"))
            throw new InvalidOperationException("SeedVR2修复失败：" + log[^Math.Min(2000, log.Length)..]);
    }
}
