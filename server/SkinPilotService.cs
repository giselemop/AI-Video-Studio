using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed class SkinPilotService(StudioSettings settings)
{
    private string Script => Path.Combine(settings.RootPath, "tools", "skin_pilot", "compose.py");
    private string Python => Path.Combine(Directory.GetParent(settings.RootPath)!.FullName, "ComfyUI", "venv", "Scripts", "python.exe");
    public string Identity => File.Exists(Script) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Script))) : "unconfigured";

    public Task ValidateAsync(JsonElement parameters, CancellationToken ct) => RunAsync(parameters, null, ct);
    public Task ComposeAsync(JsonElement parameters, string output, CancellationToken ct) => RunAsync(parameters, output, ct);

    private async Task RunAsync(JsonElement parameters, string? output, CancellationToken ct)
    {
        if (!File.Exists(Python) || !File.Exists(Script)) throw new InvalidOperationException("本地肤质合成环境缺失");
        if (!parameters.TryGetProperty("manifest", out var path) || path.ValueKind != JsonValueKind.String
            || !parameters.TryGetProperty("manifestSha256", out var hash) || hash.ValueKind != JsonValueKind.String
            || hash.GetString()?.Length != 64) throw new InvalidOperationException("肤质小样需要绑定清单及SHA256");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromMinutes(output is null ? 3 : 30));
        using var process = new Process { StartInfo = new ProcessStartInfo {
            FileName = Python, WorkingDirectory = settings.RootPath, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        }};
        foreach (var arg in new[] { "-u", Script }) process.StartInfo.ArgumentList.Add(arg);
        process.StartInfo.Environment["PYTHONUTF8"] = "1";
        process.StartInfo.Environment["HF_HUB_OFFLINE"] = "1";
        process.StartInfo.Environment["TRANSFORMERS_OFFLINE"] = "1";
        process.StartInfo.Environment["CUDA_VISIBLE_DEVICES"] = "";
        if (!process.Start()) throw new InvalidOperationException("本地肤质合成无法启动");
        using var cancellation = timeout.Token.Register(() => { try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { } });
        var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
        await process.StandardInput.WriteAsync(JsonSerializer.Serialize(new { manifest = path.GetString(), manifestSha256 = hash.GetString(),
            output, dataRoot = settings.DataPath, ffmpeg = settings.FfmpegPath, ffprobe = settings.FfprobePath, validateOnly = output is null }));
        process.StandardInput.Close();
        await process.WaitForExitAsync(timeout.Token);
        var log = await stdout + "\n" + await stderr;
        if (output is not null) await File.WriteAllTextAsync(output + ".skin.log", log, CancellationToken.None);
        if (process.ExitCode != 0) throw new InvalidOperationException("局部肤质清单或合成失败：" + log[^Math.Min(1800, log.Length)..]);
        if (output is not null && (!File.Exists(output) || !File.Exists(output + ".skin.json")))
            throw new InvalidOperationException("局部肤质合成缺少实际视频或回执");
    }
}
