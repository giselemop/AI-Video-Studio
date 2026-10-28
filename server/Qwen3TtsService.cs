using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

/// <summary>Offline Qwen inference; the generation queue owns the shared GPU lease.</summary>
public sealed class Qwen3TtsService
{
    public const string Prefix = "qwen3:";
    private readonly StudioSettings _settings;
    private string ConfigPath => Path.Combine(_settings.RootPath, "config", "qwen3-tts.json");
    private string ScriptPath => Path.Combine(_settings.RootPath, "tools", "qwen3_tts", "generate.py");
    public static readonly (string Id, string Name)[] Speakers =
    [
        ("Vivian", "Vivian · 中文女声"), ("Serena", "Serena · 中文女声"),
        ("Uncle_Fu", "Uncle Fu · 中文男声"), ("Dylan", "Dylan · 北京话男声"),
        ("Eric", "Eric · 四川话男声"), ("Ryan", "Ryan · 英语男声"),
        ("Aiden", "Aiden · 英语男声"), ("Ono_Anna", "Ono Anna · 日语女声"), ("Sohee", "Sohee · 韩语女声")
    ];

    public Qwen3TtsService(StudioSettings settings) => _settings = settings;
    public static bool IsQwen(string? voiceId) => voiceId?.StartsWith(Prefix, StringComparison.OrdinalIgnoreCase) == true;
    public static string ResourceClass(string? voiceId) => IsQwen(voiceId) ? "GPU" : "CPU";
    private JsonObject Configuration() => JsonNode.Parse(File.ReadAllText(ConfigPath))?.AsObject()
        ?? throw new InvalidOperationException("Qwen3-TTS 配置无效");
    public string Identity => File.Exists(ConfigPath) && File.Exists(ScriptPath)
        ? Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(File.ReadAllText(ConfigPath) + "\n" + File.ReadAllText(ScriptPath)))) : "unconfigured";

    public TtsPreflightResult Check(string voiceId)
    {
        try
        {
            if (!IsQwen(voiceId)) return new(false, voiceId, "Qwen3-TTS 音色标识无效", null);
            var speaker = voiceId[Prefix.Length..];
            if (!Speakers.Any(v => v.Id.Equals(speaker, StringComparison.OrdinalIgnoreCase)))
                return new(false, voiceId, "Qwen3-TTS 音色不存在", null);
            var config = Configuration();
            if (!File.Exists(config["python"]!.GetValue<string>()) || !File.Exists(ScriptPath))
                return new(false, voiceId, "Qwen3-TTS 本地运行环境尚未部署", null);
            var modelDirectory = Path.GetFullPath(config["modelDirectory"]!.GetValue<string>());
            var modelsRoot = Path.GetFullPath(_settings.ModelsPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!modelDirectory.StartsWith(modelsRoot, StringComparison.OrdinalIgnoreCase))
                return new(false, voiceId, "Qwen3-TTS 模型必须位于模型目录", null);
            var receiptPath = Path.Combine(modelDirectory, "deployment.json");
            if (!File.Exists(receiptPath)) return new(false, voiceId, "Qwen3-TTS 模型下载或哈希验证尚未完成", null);
            var receipt = JsonNode.Parse(File.ReadAllText(receiptPath))!;
            if (receipt["revision"]?.GetValue<string>() != config["revision"]?.GetValue<string>())
                return new(false, voiceId, "Qwen3-TTS 模型版本与部署记录不一致", null);
            foreach (var file in receipt["files"]!.AsArray())
            {
                var path = Path.GetFullPath(Path.Combine(modelDirectory, file!["file"]!.GetValue<string>()));
                if (!path.StartsWith(modelDirectory + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                    || !File.Exists(path) || new FileInfo(path).Length != file["size"]!.GetValue<long>())
                    return new(false, voiceId, "Qwen3-TTS 模型文件缺失或大小发生变化", null);
            }
            return new(true, voiceId, "本地模型文件就绪；推理按 GPU 任务执行", null);
        }
        catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException or ArgumentException)
        {
            return new(false, voiceId, "Qwen3-TTS 本地部署配置不可用", null);
        }
    }

    public string? Validate(string text, string voiceId, decimal speed, decimal pitch, string? instruction)
    {
        var check = Check(voiceId);
        if (!check.Passed) return check.Message;
        var config = Configuration();
        if (string.IsNullOrWhiteSpace(text) || text.Length > config["maxTextCharacters"]!.GetValue<int>()) return "Qwen3-TTS 每段文本需为 1–500 字符，请分段生成";
        if ((instruction?.Length ?? 0) > config["maxInstructionCharacters"]!.GetValue<int>()) return "演绎指令最多 300 字符";
        if (speed != 1 || pitch != 0) return "Qwen3-TTS 请通过演绎指令调整语速和声线；数值语速需为 1、音高为 0";
        return null;
    }

    public async Task GenerateAsync(string text, string voiceId, string? instruction, string output, CancellationToken ct)
    {
        var error = Validate(text, voiceId, 1, 0, instruction);
        if (error is not null) throw new InvalidOperationException(error);
        var config = Configuration();
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(TimeSpan.FromSeconds(config["timeoutSeconds"]!.GetValue<int>()));
        using var process = new Process { StartInfo = new ProcessStartInfo
        {
            FileName = config["python"]!.GetValue<string>(), UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = _settings.RootPath
        } };
        foreach (var argument in new[] { "-u", ScriptPath, "--config", ConfigPath }) process.StartInfo.ArgumentList.Add(argument);
        process.StartInfo.Environment["PYTHONUTF8"] = "1";
        process.StartInfo.Environment["HF_HOME"] = Path.Combine(_settings.DataPath, "Cache", "Qwen3TTS");
        process.StartInfo.Environment["HF_HUB_OFFLINE"] = "1";
        process.StartInfo.Environment["TRANSFORMERS_OFFLINE"] = "1";
        if (!process.Start()) throw new InvalidOperationException("无法启动 Qwen3-TTS 本地引擎");
        using var cancellation = deadline.Token.Register(() => { try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { } });
        var stdout = process.StandardOutput.ReadToEndAsync(deadline.Token);
        var stderr = process.StandardError.ReadToEndAsync(deadline.Token);
        await process.StandardInput.WriteAsync(JsonSerializer.Serialize(new { text, speaker = voiceId[Prefix.Length..], instruction = instruction ?? "", output }));
        process.StandardInput.Close();
        try { await process.WaitForExitAsync(deadline.Token); }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } catch (InvalidOperationException) { }
            if (!ct.IsCancellationRequested) throw new TimeoutException("Qwen3-TTS 本地配音超过配置时限，推理进程已终止");
            throw;
        }
        _ = await stdout;
        var diagnostic = await stderr;
        if (process.ExitCode != 0 || !File.Exists(output) || !File.Exists(output + ".qwen.json"))
            throw new InvalidOperationException("Qwen3-TTS 本地合成失败：" + diagnostic[^Math.Min(1800, diagnostic.Length)..]);
    }
}
