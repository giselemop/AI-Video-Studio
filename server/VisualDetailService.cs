using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed class VisualDetailService(StudioSettings settings, AssetPathPolicy paths)
{
    private string Script => Path.Combine(settings.RootPath, "tools", "visual_targeted", "detail.py");
    public string Identity => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Script))).ToLowerInvariant();
    public async Task RunAsync(JsonElement p, string? output, CancellationToken ct)
    {
        string Required(string key) => p.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : throw new InvalidOperationException("缺少细节回补参数");
        var manifest = paths.RequireExisting(Required("manifest"), "细节清单必须位于受控Data目录");
        if (Required("engineVersion") != Identity || Path.GetExtension(manifest) != ".json"
            || Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(manifest, ct))).ToLowerInvariant() != Required("manifestSha256"))
            throw new InvalidOperationException("细节回补脚本或清单发生漂移");
        var boundIdentity = Identity;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct); timeout.CancelAfter(TimeSpan.FromMinutes(output is null ? 3 : 15));
        using var process = new Process { StartInfo = new ProcessStartInfo {
            FileName = Path.Combine(Directory.GetParent(settings.RootPath)!.FullName, "ComfyUI", "venv", "Scripts", "python.exe"),
            WorkingDirectory = settings.RootPath, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        }};
        foreach (var arg in new[] { "-u", Script }) process.StartInfo.ArgumentList.Add(arg);
        process.StartInfo.Environment["CUDA_VISIBLE_DEVICES"] = "";
        process.StartInfo.Environment["PYTHONUTF8"] = "1";
        process.StartInfo.Environment["HF_HUB_OFFLINE"] = "1";
        if (!process.Start()) throw new InvalidOperationException("本地细节回补进程未启动");
        using var cancellation = timeout.Token.Register(() => { try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { } });
        var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
        await process.StandardInput.WriteAsync(JsonSerializer.Serialize(new { manifest, manifestSha256 = Required("manifestSha256"),
            dataRoot = settings.DataPath, output, ffmpeg = settings.FfmpegPath, ffprobe = settings.FfprobePath, validateOnly = output is null }));
        process.StandardInput.Close();
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException)
        {
            if (!process.HasExited) process.Kill(true);
            await process.WaitForExitAsync(CancellationToken.None);
            if (ct.IsCancellationRequested) throw;
            throw new TimeoutException("细节回补超时，进程树已停止");
        }
        var log = await stdout + "\n" + await stderr;
        if (output is not null) await File.WriteAllTextAsync(output + ".detail.log", log, CancellationToken.None);
        if (process.ExitCode != 0 || Identity != boundIdentity) throw new InvalidOperationException("细节回补校验/合成失败或版本发生漂移：" + log[^Math.Min(1000, log.Length)..]);
    }
}
