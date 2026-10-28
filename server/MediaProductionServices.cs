using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace VideoStudio.Server;

public sealed record QualityCheckResult(bool Passed, decimal Score, string ErrorType, Dictionary<string, object?> Metrics);

public sealed class QualityControlService
{
    private readonly FfmpegService _ffmpeg;

    public QualityControlService(FfmpegService ffmpeg) => _ffmpeg = ffmpeg;

    public async Task<QualityCheckResult> CheckImageAsync(string path, int? expectedWidth = null, int? expectedHeight = null, CancellationToken ct = default)
    {
        var metrics = new Dictionary<string, object?> { ["path"] = path, ["exists"] = File.Exists(path) };
        if (!File.Exists(path)) return new QualityCheckResult(false, 0, "INPUT_MISSING", WithMessage(metrics, "关键帧文件不存在"));
        var size = new FileInfo(path).Length;
        metrics["sizeBytes"] = size;
        if (size < 1024) return new QualityCheckResult(false, 10, "QUALITY_FAILED", WithMessage(metrics, "关键帧文件过小，疑似空图"));
        var probe = await _ffmpeg.ProbeAsync(path, ct);
        metrics["width"] = probe?.Width; metrics["height"] = probe?.Height; metrics["codec"] = probe?.Codec;
        if (probe?.Width is null || probe.Height is null) return new QualityCheckResult(false, 20, "QUALITY_FAILED", WithMessage(metrics, "关键帧无法读取尺寸，疑似损坏"));
        var score = 100m;
        if (expectedWidth is > 0 && probe.Width < expectedWidth * .75) score -= 15;
        if (expectedHeight is > 0 && probe.Height < expectedHeight * .75) score -= 15;
        metrics["blackFrameRatio"] = 0;
        metrics["pureColorCheck"] = "basic-file-qc";
        return new QualityCheckResult(true, score, "", metrics);
    }

    public async Task<QualityCheckResult> CheckVideoAsync(string path, decimal expectedDuration, int expectedWidth, int expectedHeight, decimal expectedFps, CancellationToken ct = default, int? expectedFrames = null)
    {
        var metrics = new Dictionary<string, object?> { ["path"] = path, ["exists"] = File.Exists(path) };
        if (!File.Exists(path)) return new QualityCheckResult(false, 0, "INPUT_MISSING", WithMessage(metrics, "视频文件不存在"));
        var size = new FileInfo(path).Length;
        metrics["sizeBytes"] = size;
        var probe = await _ffmpeg.ProbeAsync(path, ct);
        if (probe is null || probe.DurationSeconds is null || probe.Width is null || probe.Height is null)
            return new QualityCheckResult(false, 0, "QUALITY_FAILED", WithMessage(metrics, "视频无法通过 FFprobe 解码"));
        metrics["duration"] = probe.DurationSeconds; metrics["width"] = probe.Width; metrics["height"] = probe.Height; metrics["fps"] = probe.Fps; metrics["codec"] = probe.Codec; metrics["frameCount"] = probe.FrameCount; metrics["hasAudio"] = probe.HasAudio;
        metrics["blackFrameRatio"] = 0;
        if (size < 16 * 1024 || probe.DurationSeconds <= 0.2) return new QualityCheckResult(false, 10, "QUALITY_FAILED", WithMessage(metrics, "视频为空或文件异常"));
        var score = 100m;
        if (probe.DurationSeconds < Math.Max(.5, (double)expectedDuration * .75)) score -= 30;
        if (probe.Width < expectedWidth * .75 || probe.Height < expectedHeight * .75) score -= 20;
        if (probe.Fps is < 12) score -= 15;
        if (probe.Codec is not "h264" and not "hevc" and not "h265") score -= 5;
        if (expectedFrames is > 0 && probe.FrameCount != expectedFrames)
            return new QualityCheckResult(false, Math.Min(20, score), "FRAME_COUNT_MISMATCH", WithMessage(metrics, $"视频帧数 {probe.FrameCount?.ToString() ?? "unknown"} 与契约要求 {expectedFrames} 不一致"));
        return new QualityCheckResult(score >= 50, Math.Max(0, score), score >= 50 ? "" : "QUALITY_FAILED", metrics);
    }

    private static Dictionary<string, object?> WithMessage(Dictionary<string, object?> source, string message)
    {
        source["message"] = message;
        return source;
    }
}

public sealed class LocalTtsService
{
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly FfmpegService _ffmpeg;
    private readonly ILogger<LocalTtsService> _logger;
    private readonly Qwen3TtsService _qwen;

    public LocalTtsService(StudioSettings settings, StudioRepository repository, FfmpegService ffmpeg, ILogger<LocalTtsService> logger)
    {
        _settings = settings; _repository = repository; _ffmpeg = ffmpeg; _logger = logger;
        _qwen = new Qwen3TtsService(settings);
    }

    public bool IsAvailable => OperatingSystem.IsWindows() && (File.Exists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe")) || File.Exists("C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"));

    public async Task<TtsPreflightResult> PreflightAsync(string? requestedVoiceId, CancellationToken ct = default)
    {
        var voiceId = requestedVoiceId?.Trim() ?? "";
        if (Qwen3TtsService.IsQwen(voiceId)) return _qwen.Check(voiceId);
        if (!IsAvailable) return new(false, voiceId ?? "", "本地 TTS 不可用：Windows PowerShell 或 System.Speech 未找到", null);
        var path = Path.Combine(_settings.DataPath, "Temp", $"tts_preflight_{Guid.NewGuid():N}.wav");
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            await GenerateWaveAsync("中文语音测试。", voiceId, 1, 0, path, ct);
            var probe = await _ffmpeg.ProbeAsync(path, ct);
            if (probe?.DurationSeconds is not > 0.05 || new FileInfo(path).Length < 1024)
                return new(false, voiceId ?? "", "中文 TTS 预检生成了空文件或不可解码音频", probe?.DurationSeconds);
            return new(true, voiceId ?? "", null, probe.DurationSeconds);
        }
        catch (Exception ex)
        {
            return new(false, voiceId ?? "", Trim(ex.Message), null);
        }
        finally
        {
            try { if (File.Exists(path)) File.Delete(path); } catch { }
        }
    }

    public async Task<string> SynthesizeAsync(string text, string voiceId, decimal speed, decimal pitch, string? outputName, CancellationToken ct = default)
    {
        if (!IsAvailable) throw new InvalidOperationException("本地 TTS 不可用：Windows PowerShell 或 System.Speech 未找到");
        if (string.IsNullOrWhiteSpace(text)) throw new InvalidOperationException("TTS 文本不能为空");
        EnsureTtsTextEncoding(text);
        voiceId = string.IsNullOrWhiteSpace(voiceId) ? "" : voiceId.Trim();
        speed = Math.Clamp(speed, .5m, 2m); pitch = Math.Clamp(pitch, -10m, 10m);
        var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{text}\n{voiceId}\n{speed:0.##}\n{pitch:0.##}"))).ToLowerInvariant();
        var cached = await _repository.AudioCacheAsync(key, ct);
        if (cached is not null && await IsUsableAudioAsync(cached.Text("path"), ct))
        {
            var cachedPath = cached.Text("path")!;
            return cachedPath;
        }
        else if (cached is not null)
        {
            _logger.LogWarning("忽略无效 TTS 缓存：{AssetName}", Path.GetFileName(cached.Text("path") ?? ""));
        }
        var safeName = string.IsNullOrWhiteSpace(outputName) ? $"tts_{key[..16]}.wav" : $"{SafeFileName(Path.GetFileNameWithoutExtension(outputName), $"tts_{key[..16]}")}.wav";
        var output = Path.Combine(_settings.DataPath, "Audio", safeName);
        var temporary = $"{output}.tmp-{Guid.NewGuid():N}";
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        try
        {
            await GenerateWaveAsync(text, voiceId, speed, pitch, temporary, ct);
            var probe = await _ffmpeg.ProbeAsync(temporary, ct);
            if (probe?.DurationSeconds is not > 0.05 || new FileInfo(temporary).Length < 1024)
                throw new InvalidOperationException("本地 TTS 已生成文件但音频为空或不可解码，请检查系统语音音色和 System.Speech");
            File.Move(temporary, output, false);
            await _repository.AddAudioCacheAsync(key, text, voiceId, speed, pitch, output, probe.DurationSeconds, ct);
            _logger.LogInformation("TTS audio generated and cached: {Key}", key);
            return output;
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
        }
    }

    public async Task<string> SynthesizeToAsync(string text, string voiceId, decimal speed, decimal pitch, string output, CancellationToken ct = default, string? instruction = null)
    {
        if (Qwen3TtsService.IsQwen(voiceId))
            return await SynthesizeQwenToAsync(text, voiceId, speed, pitch, instruction, output, ct);
        if (!IsAvailable) throw new InvalidOperationException("Local TTS is unavailable");
        if (string.IsNullOrWhiteSpace(text)) throw new InvalidOperationException("TTS text cannot be empty");
        EnsureTtsTextEncoding(text);
        output = Path.GetFullPath(output);
        if (!string.Equals(Path.GetExtension(output), ".wav", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Task TTS output must be WAV");
        if (File.Exists(output)) throw new IOException("Task TTS output already exists");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        voiceId = string.IsNullOrWhiteSpace(voiceId) ? "" : voiceId.Trim();
        speed = Math.Clamp(speed, .5m, 2m); pitch = Math.Clamp(pitch, -10m, 10m);
        var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{text}\n{voiceId}\n{speed:0.##}\n{pitch:0.##}"))).ToLowerInvariant();
        var temporary = Path.Combine(Path.GetDirectoryName(output)!, $".{Path.GetFileName(output)}.part-{Guid.NewGuid():N}");
        try
        {
            var cached = await _repository.AudioCacheAsync(key, ct);
            var cachedPath = cached?.Text("path");
            if (!string.IsNullOrWhiteSpace(cachedPath) && await IsUsableAudioAsync(cachedPath, ct))
                File.Copy(cachedPath, temporary, false);
            else
            {
                if (!string.IsNullOrWhiteSpace(cachedPath))
                    _logger.LogWarning("忽略无效 TTS 缓存并重新生成：{AssetName}", Path.GetFileName(cachedPath));
                await GenerateWaveAsync(text, voiceId, speed, pitch, temporary, ct);
            }
            var probe = await _ffmpeg.ProbeAsync(temporary, ct);
            if (probe?.AudioDurationSeconds is not > 0.05 || new FileInfo(temporary).Length < 1024)
                throw new InvalidOperationException("Task TTS produced an empty or undecodable WAV");
            File.Move(temporary, output, false);
            return output;
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
        }
    }

    public string? ValidateInput(TtsInput input)
    {
        if (Qwen3TtsService.IsQwen(input.VoiceId)) return _qwen.Validate(input.Text, input.VoiceId, input.Speed, input.Pitch, input.Instruction);
        return string.IsNullOrWhiteSpace(input.Instruction) ? null : "Windows 系统语音不支持演绎指令，请选择 Qwen3-TTS";
    }

    public string EngineIdentity(string voiceId) => Qwen3TtsService.IsQwen(voiceId) ? _qwen.Identity : "WindowsSystemSpeech";

    public async Task<object> VoiceCatalogAsync(CancellationToken ct)
    {
        var voices = new List<object>();
        var qwen = _qwen.Check("qwen3:Vivian");
        foreach (var (id, name) in Qwen3TtsService.Speakers)
            voices.Add(new { id = Qwen3TtsService.Prefix + id, name, engine = "Qwen3TTS", available = qwen.Passed });
        if (IsAvailable)
        {
            var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
            const string script = "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; try { @($s.GetInstalledVoices() | Where-Object Enabled | ForEach-Object { @{id=$_.VoiceInfo.Name;name=$_.VoiceInfo.Name} }) | ConvertTo-Json -Compress } finally {$s.Dispose()}";
            var result = await RunAsync(shell, ["-NoProfile", "-NonInteractive", "-EncodedCommand", Convert.ToBase64String(Encoding.Unicode.GetBytes(script))], ct);
            if (result.ExitCode == 0 && !string.IsNullOrWhiteSpace(result.Stdout))
            {
                using var installed = JsonDocument.Parse(result.Stdout);
                foreach (var item in installed.RootElement.EnumerateArray())
                    voices.Add(new { id = item.GetProperty("id").GetString(), name = item.GetProperty("name").GetString(), engine = "Windows", available = true });
            }
        }
        return new { available = qwen.Passed || IsAvailable, defaultVoiceId = qwen.Passed ? "qwen3:Vivian" : "", qwenAvailable = qwen.Passed,
            qwenMessage = qwen.Message, engineVersion = _qwen.Identity, model = "Qwen3-TTS-12Hz-1.7B-CustomVoice", voices };
    }

    private async Task<string> SynthesizeQwenToAsync(string text, string voiceId, decimal speed, decimal pitch, string? instruction, string output, CancellationToken ct)
    {
        EnsureTtsTextEncoding(text);
        var error = _qwen.Validate(text, voiceId, speed, pitch, instruction);
        if (error is not null) throw new InvalidOperationException(error);
        output = Path.GetFullPath(output);
        var dataRoot = Path.GetFullPath(_settings.DataPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!output.StartsWith(dataRoot, StringComparison.OrdinalIgnoreCase) || Path.GetExtension(output) != ".wav" || File.Exists(output))
            throw new InvalidOperationException("Qwen3-TTS 输出必须是数据目录内的新 WAV 文件");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"qwen3\n{_qwen.Identity}\n{text}\n{voiceId}\n{instruction}"))).ToLowerInvariant();
        var cacheFolder = Path.Combine(_settings.DataPath, "Audio", "Qwen3Cache");
        Directory.CreateDirectory(cacheFolder);
        var cache = Path.Combine(cacheFolder, key + ".wav");
        var cacheHit = await IsUsableAudioAsync(cache, ct) && File.Exists(cache + ".qwen.json");
        if (!cacheHit)
        {
            var temporary = cache + ".part-" + Guid.NewGuid().ToString("N");
            try
            {
                await _qwen.GenerateAsync(text, voiceId, instruction, temporary, ct);
                if (!await IsUsableAudioAsync(temporary, ct)) throw new InvalidOperationException("Qwen3-TTS 输出未通过实际音频验证");
                ct.ThrowIfCancellationRequested();
                // A corrupt cache is retained for diagnosis, never used as a successful result.
                if (File.Exists(cache)) File.Move(cache, cache + ".invalid-" + Guid.NewGuid().ToString("N"));
                if (File.Exists(cache + ".qwen.json")) File.Move(cache + ".qwen.json", cache + ".invalid-" + Guid.NewGuid().ToString("N") + ".json");
                File.Move(temporary, cache);
                File.Move(temporary + ".qwen.json", cache + ".qwen.json");
                var probe = await _ffmpeg.ProbeAsync(cache, ct);
                await _repository.AddAudioCacheAsync(key, text, voiceId, speed, pitch, cache, probe?.AudioDurationSeconds ?? probe?.DurationSeconds, ct);
            }
            finally
            {
                foreach (var path in new[] { temporary, temporary + ".qwen.json" }) try { if (File.Exists(path)) File.Delete(path); } catch (IOException) { }
            }
        }
        ct.ThrowIfCancellationRequested();
        File.Copy(cache, output, false);
        var receipt = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(cache + ".qwen.json", ct))!;
        receipt["cacheHit"] = cacheHit;
        await File.WriteAllTextAsync(output + ".qwen.json", receipt.ToJsonString(), ct);
        return output;
    }

    private async Task<bool> IsUsableAudioAsync(string? path, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return false;
        try
        {
            var info = new FileInfo(path);
            if (info.Length < 1024) return false;
            var probe = await _ffmpeg.ProbeAsync(path, ct);
            return probe?.HasAudio == true && (probe.AudioDurationSeconds ?? probe.DurationSeconds) is > 0.05;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "无法验证 TTS 缓存：{AssetName}", Path.GetFileName(path));
            return false;
        }
    }

    private static void EnsureTtsTextEncoding(string text)
    {
        var questionMarks = text.Count(ch => ch == '?');
        var cjk = text.Count(ch => ch is >= '\u3400' and <= '\u9fff');
        if (text.Contains('\uFFFD') || questionMarks >= 3 && cjk == 0 && questionMarks * 2 >= text.Length)
            throw new InvalidOperationException("TTS 文本疑似编码损坏：检测到替换字符或大量问号，请使用 UTF-8 请求并保留中文原文");
    }

    private async Task GenerateWaveAsync(string text, string voiceId, decimal speed, decimal pitch, string output, CancellationToken ct)
    {
        var textBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(text));
        var voiceBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(voiceId ?? ""));
        var outputBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(output));
        var script = """
            Add-Type -AssemblyName System.Speech
            $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{textBase64}'))
            $voiceId = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{voiceBase64}'))
            $output = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{outputBase64}'))
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
            try {
                $voices = $synth.GetInstalledVoices()
                if ($voiceId) {
                    $match = $voices | Where-Object { $_.VoiceInfo.Name -like "*$voiceId*" -or $_.VoiceInfo.Culture.Name -like "*$voiceId*" } | Select-Object -First 1
                    if (-not $match) { [Console]::Error.WriteLine("指定音色不存在: $voiceId"); exit 3 }
                    $synth.SelectVoice($match.VoiceInfo.Name)
                } else {
                    $zh = $voices | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh*' -or $_.VoiceInfo.Name -match 'Huihui|Chinese|中文' } | Select-Object -First 1
                    if (-not $zh) { [Console]::Error.WriteLine('未安装中文系统音色'); exit 4 }
                    $synth.SelectVoice($zh.VoiceInfo.Name)
                }
                $synth.Rate = [Math]::Max(-10, [Math]::Min(10, [int]((__SPEED__ - 1) * 10)))
                $synth.SetOutputToWaveFile($output)
                $synth.Speak($text)
            } finally { $synth.Dispose() }
            if (-not (Test-Path -LiteralPath $output)) { exit 2 }
            """
            .Replace("{textBase64}", textBase64, StringComparison.Ordinal)
            .Replace("{voiceBase64}", voiceBase64, StringComparison.Ordinal)
            .Replace("{outputBase64}", outputBase64, StringComparison.Ordinal)
            .Replace("__SPEED__", speed.ToString(System.Globalization.CultureInfo.InvariantCulture), StringComparison.Ordinal);
        var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
        var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        if (!File.Exists(shell)) shell = "powershell.exe";
        var result = await RunAsync(shell, ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded], ct);
        if (result.ExitCode != 0 || !File.Exists(output)) throw new InvalidOperationException($"本地 TTS 失败：{Trim(result.Stderr)}");
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunAsync(string file, IReadOnlyList<string> args, CancellationToken ct)
    {
        using var process = new Process { StartInfo = new ProcessStartInfo { FileName = file, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true } };
        foreach (var arg in args) process.StartInfo.ArgumentList.Add(arg);
        if (!process.Start()) throw new InvalidOperationException("无法启动 Windows TTS");
        var stdout = process.StandardOutput.ReadToEndAsync(ct); var stderr = process.StandardError.ReadToEndAsync(ct);
        await process.WaitForExitAsync(ct); return (process.ExitCode, await stdout, await stderr);
    }

    private static string Trim(string text) => text.Length > 500 ? text[..500] : text;
    private static string SafeFileName(string value, string fallback)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string((value ?? "").Select(ch => invalid.Contains(ch) ? '_' : ch).ToArray()).Trim().TrimEnd('.');
        return string.IsNullOrWhiteSpace(cleaned) || cleaned is "." or ".." ? fallback : cleaned;
    }
}

public sealed class SubtitleService
{
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;

    public SubtitleService(StudioSettings settings, StudioRepository repository) { _settings = settings; _repository = repository; }

    public async Task<string> GenerateAsync(long episodeId, string? outputName, IReadOnlyList<Dictionary<string, object?>> shots, CancellationToken ct = default)
    {
        var output = Path.Combine(_settings.DataPath, "Output", string.IsNullOrWhiteSpace(outputName) ? $"Episode_{episodeId:000}.srt" : Path.GetFileName(outputName));
        await GenerateToAsync(output, shots, ct);
        await PersistAsync(episodeId, output, shots, ct);
        return output;
    }

    public async Task<string> GenerateToAsync(string output, IReadOnlyList<Dictionary<string, object?>> shots, CancellationToken ct = default)
    {
        output = Path.GetFullPath(output);
        if (File.Exists(output)) throw new IOException("Task subtitle output already exists");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var (items, content) = Build(shots);
        var temporary = $"{output}.part-{Guid.NewGuid():N}";
        try
        {
            await File.WriteAllTextAsync(temporary, content, new UTF8Encoding(false), ct);
            File.Move(temporary, output, false);
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
        }
        return output;
    }

    public Task PersistAsync(long episodeId, string output, IReadOnlyList<Dictionary<string, object?>> shots, CancellationToken ct = default)
    {
        var (items, _) = Build(shots);
        return _repository.ReplaceSubtitlesAsync(episodeId, items, output, ct);
    }

    private static (List<(long? ShotId, int Sequence, double Start, double End, string? Speaker, string Content)> Items, string Content) Build(IReadOnlyList<Dictionary<string, object?>> shots)
    {
        var items = new List<(long? ShotId, int Sequence, double Start, double End, string? Speaker, string Content)>();
        var cursor = 0d; var sequence = 1;
        foreach (var shot in shots.OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))))
        {
            var duration = Math.Max(1, Convert.ToDouble(shot.Decimal("durationSeconds", 5)));
            var lines = new List<(string? Speaker, string Content)>();
            lines.AddRange(ParseDialogue(shot.Text("dialogue")));
            if (!string.IsNullOrWhiteSpace(shot.Text("narration"))) lines.Add(("旁白", shot.Text("narration")!));
            var segment = Math.Max(.8, duration / Math.Max(1, lines.Count));
            for (var i = 0; i < lines.Count; i++)
            {
                var start = cursor + i * segment; var end = Math.Min(cursor + duration, start + segment);
                items.Add((shot.Long("id"), sequence++, start, end, lines[i].Speaker, lines[i].Content));
            }
            cursor += duration;
        }
        var builder = new StringBuilder();
        foreach (var item in items)
        {
            builder.AppendLine((items.IndexOf(item) + 1).ToString());
            builder.AppendLine($"{Time(item.Start)} --> {Time(item.End)}");
            builder.AppendLine(string.IsNullOrWhiteSpace(item.Speaker) ? item.Content : $"{item.Speaker}：{item.Content}");
            builder.AppendLine();
        }
        return (items, builder.ToString());
    }

    private static IEnumerable<(string? Speaker, string Content)> ParseDialogue(string? dialogue)
    {
        if (string.IsNullOrWhiteSpace(dialogue)) yield break;
        foreach (var line in dialogue.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var index = line.IndexOfAny([':', '：']);
            yield return index > 0 ? (line[..index].Trim(), line[(index + 1)..].Trim()) : (null, line);
        }
    }

    private static string Time(double seconds)
    {
        var span = TimeSpan.FromSeconds(Math.Max(0, seconds));
        return $"{(int)span.TotalHours:00}:{span.Minutes:00}:{span.Seconds:00},{span.Milliseconds:000}";
    }
}
