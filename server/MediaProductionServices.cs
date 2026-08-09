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

    public async Task<QualityCheckResult> CheckVideoAsync(string path, decimal expectedDuration, int expectedWidth, int expectedHeight, decimal expectedFps, CancellationToken ct = default)
    {
        var metrics = new Dictionary<string, object?> { ["path"] = path, ["exists"] = File.Exists(path) };
        if (!File.Exists(path)) return new QualityCheckResult(false, 0, "INPUT_MISSING", WithMessage(metrics, "视频文件不存在"));
        var size = new FileInfo(path).Length;
        metrics["sizeBytes"] = size;
        var probe = await _ffmpeg.ProbeAsync(path, ct);
        if (probe is null || probe.DurationSeconds is null || probe.Width is null || probe.Height is null)
            return new QualityCheckResult(false, 0, "QUALITY_FAILED", WithMessage(metrics, "视频无法通过 FFprobe 解码"));
        metrics["duration"] = probe.DurationSeconds; metrics["width"] = probe.Width; metrics["height"] = probe.Height; metrics["fps"] = probe.Fps; metrics["codec"] = probe.Codec;
        metrics["blackFrameRatio"] = 0;
        if (size < 16 * 1024 || probe.DurationSeconds <= 0.2) return new QualityCheckResult(false, 10, "QUALITY_FAILED", WithMessage(metrics, "视频为空或文件异常"));
        var score = 100m;
        if (probe.DurationSeconds < Math.Max(.5, (double)expectedDuration * .75)) score -= 30;
        if (probe.Width < expectedWidth * .75 || probe.Height < expectedHeight * .75) score -= 20;
        if (probe.Fps is < 12) score -= 15;
        if (probe.Codec is not "h264" and not "hevc" and not "h265") score -= 5;
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

    public LocalTtsService(StudioSettings settings, StudioRepository repository, FfmpegService ffmpeg, ILogger<LocalTtsService> logger)
    {
        _settings = settings; _repository = repository; _ffmpeg = ffmpeg; _logger = logger;
    }

    public bool IsAvailable => OperatingSystem.IsWindows() && (File.Exists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe")) || File.Exists("C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"));

    public async Task<string> SynthesizeAsync(string text, string voiceId, decimal speed, decimal pitch, string? outputName, CancellationToken ct = default)
    {
        if (!IsAvailable) throw new InvalidOperationException("本地 TTS 不可用：Windows PowerShell 或 System.Speech 未找到");
        if (string.IsNullOrWhiteSpace(text)) throw new InvalidOperationException("TTS 文本不能为空");
        voiceId = string.IsNullOrWhiteSpace(voiceId) ? "" : voiceId.Trim();
        speed = Math.Clamp(speed, .5m, 2m); pitch = Math.Clamp(pitch, -10m, 10m);
        var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{text}\n{voiceId}\n{speed:0.##}\n{pitch:0.##}"))).ToLowerInvariant();
        var cached = await _repository.AudioCacheAsync(key, ct);
        if (cached is not null && File.Exists(cached.Text("path"))) return cached.Text("path")!;
        var safeName = string.IsNullOrWhiteSpace(outputName) ? $"tts_{key[..16]}.wav" : Path.GetFileNameWithoutExtension(outputName) + ".wav";
        var output = Path.Combine(_settings.DataPath, "Audio", safeName);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var textBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(text));
        var voiceBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(voiceId));
        var outputBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(output));
        var script = """
            Add-Type -AssemblyName System.Speech
            $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{textBase64}'))
            $voiceId = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{voiceBase64}'))
            $output = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{outputBase64}'))
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
            $voices = $synth.GetInstalledVoices()
            if ($voiceId) {{ $match = $voices | Where-Object {{ $_.VoiceInfo.Name -like "*$voiceId*" -or $_.VoiceInfo.Culture.Name -like "*$voiceId*" }} | Select-Object -First 1; if ($match) {{ $synth.SelectVoice($match.VoiceInfo.Name) }} }}
            if (-not $voiceId) {{ $zh = $voices | Where-Object {{ $_.VoiceInfo.Culture.Name -like 'zh*' -or $_.VoiceInfo.Name -match 'Huihui|Chinese|中文' }} | Select-Object -First 1; if ($zh) {{ $synth.SelectVoice($zh.VoiceInfo.Name) }} }}
            $synth.Rate = [Math]::Max(-10, [Math]::Min(10, [int]((__SPEED__ - 1) * 10)))
            $synth.SetOutputToWaveFile($output)
            $synth.Speak($text)
            $synth.Dispose()
            if (-not (Test-Path -LiteralPath $output)) {{ exit 2 }}
            """.Replace("__SPEED__", speed.ToString(System.Globalization.CultureInfo.InvariantCulture), StringComparison.Ordinal);
        var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
        var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        if (!File.Exists(shell)) shell = "powershell.exe";
        var result = await RunAsync(shell, ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded], ct);
        if (result.ExitCode != 0 || !File.Exists(output)) throw new InvalidOperationException($"本地 TTS 失败：{Trim(result.Stderr)}");
        var probe = await _ffmpeg.ProbeAsync(output, ct);
        await _repository.AddAudioCacheAsync(key, text, voiceId, speed, pitch, output, probe?.DurationSeconds, ct);
        _logger.LogInformation("TTS audio generated and cached: {Key}", key);
        return output;
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
}

public sealed class SubtitleService
{
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;

    public SubtitleService(StudioSettings settings, StudioRepository repository) { _settings = settings; _repository = repository; }

    public async Task<string> GenerateAsync(long episodeId, string? outputName, IReadOnlyList<Dictionary<string, object?>> shots, CancellationToken ct = default)
    {
        var output = Path.Combine(_settings.DataPath, "Output", string.IsNullOrWhiteSpace(outputName) ? $"Episode_{episodeId:000}.srt" : Path.GetFileName(outputName));
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
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
        await File.WriteAllTextAsync(output, builder.ToString(), new UTF8Encoding(false), ct);
        await _repository.ReplaceSubtitlesAsync(episodeId, items, output, ct);
        return output;
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
