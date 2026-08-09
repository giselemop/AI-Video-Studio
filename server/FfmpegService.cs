using System.Diagnostics;
using System.Globalization;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed record FfmpegAudioTrack(string Path, double Volume, double StartSeconds = 0);

public sealed class FfmpegService
{
    private readonly StudioSettings _settings;
    private readonly ILogger<FfmpegService> _logger;

    public FfmpegService(StudioSettings settings, ILogger<FfmpegService> logger)
    {
        _settings = settings;
        _logger = logger;
    }

    public bool IsAvailable => File.Exists(_settings.FfmpegPath) && File.Exists(_settings.FfprobePath);

    public async Task<FfmpegProbe?> ProbeAsync(string path, CancellationToken ct = default)
    {
        var detailed = await ProbeDetailedAsync(path, ct);
        return detailed is null ? null : new FfmpegProbe(detailed.Width, detailed.Height, detailed.DurationSeconds, detailed.Fps, detailed.Codec, detailed.HasAudio);
    }

    public async Task<FfmpegDetailedProbe?> ProbeDetailedAsync(string path, CancellationToken ct = default)
    {
        if (!File.Exists(_settings.FfprobePath) || !File.Exists(path)) return null;
        var result = await RunAsync(_settings.FfprobePath, ["-v", "error", "-show_streams", "-show_format", "-of", "json", path], ct);
        if (result.ExitCode != 0) return null;
        try
        {
            using var doc = JsonDocument.Parse(result.Stdout);
            var streams = doc.RootElement.TryGetProperty("streams", out var streamElement) && streamElement.ValueKind == JsonValueKind.Array
                ? streamElement.EnumerateArray().ToArray() : [];
            var video = streams.FirstOrDefault(x => x.TryGetProperty("codec_type", out var type) && type.GetString() == "video");
            var audio = streams.FirstOrDefault(x => x.TryGetProperty("codec_type", out var type) && type.GetString() == "audio");
            var subtitle = streams.FirstOrDefault(x => x.TryGetProperty("codec_type", out var type) && type.GetString() == "subtitle");
            var width = GetInt(video, "width");
            var height = GetInt(video, "height");
            var codec = GetString(video, "codec_name");
            var fps = ParseRate(GetString(video, "r_frame_rate"));
            var formatDuration = GetDouble(doc.RootElement.TryGetProperty("format", out var format) ? format : default, "duration");
            var duration = GetDouble(video, "duration") ?? formatDuration;
            var audioDuration = GetDouble(audio, "duration") ?? (audio.ValueKind == JsonValueKind.Undefined ? null : formatDuration);
            var size = GetLong(doc.RootElement.TryGetProperty("format", out format) ? format : default, "size") ?? (File.Exists(path) ? new FileInfo(path).Length : null);
            return new FfmpegDetailedProbe(
                width, height, duration, fps, codec,
                audio.ValueKind != JsonValueKind.Undefined,
                audioDuration,
                GetString(audio, "codec_name"),
                subtitle.ValueKind != JsonValueKind.Undefined,
                GetString(subtitle, "codec_name"),
                size);
        }
        catch (Exception ex) { _logger.LogWarning(ex, "Unable to parse detailed ffprobe output for {Path}", path); return null; }
    }

    public async Task<FfmpegDecodeResult> CheckDecodeAsync(string path, CancellationToken ct = default)
    {
        if (!File.Exists(path)) return new FfmpegDecodeResult(false, 1, "媒体文件不存在");
        var result = await RunAsync(_settings.FfmpegPath, ["-hide_banner", "-v", "error", "-i", path, "-map", "0:v:0", "-f", "null", "-"], ct);
        var errors = result.Stderr.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return new FfmpegDecodeResult(result.ExitCode == 0 && errors.Length == 0, errors.Length, errors.Length == 0 ? null : string.Join(" | ", errors.Take(5)));
    }

    public async Task<string> ExtractFrameAsync(string input, double seconds, string output, CancellationToken ct = default)
    {
        if (!File.Exists(input)) throw new FileNotFoundException("视频不存在", input);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var result = await RunAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-ss", Math.Max(0, seconds).ToString("0.###", CultureInfo.InvariantCulture), "-i", input, "-frames:v", "1", "-vf", "scale=640:-2:flags=lanczos", "-an", output], ct);
        if (result.ExitCode != 0 || !File.Exists(output)) throw new InvalidOperationException($"FFmpeg 抽帧失败: {result.Stderr}");
        return output;
    }

    public async Task<string> ConvertToMp4Async(string input, string output, CancellationToken ct = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var result = await RunAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-i", input, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output], ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 转码失败: {result.Stderr}");
        return output;
    }

    public async Task<string> EnhanceAsync(string input, string output, int fps = 30, CancellationToken ct = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var filter = $"deflicker=mode=median:size=5,minterpolate=fps={Math.Clamp(fps, 24, 60)}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080";
        var result = await RunAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-i", input, "-vf", filter, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output], ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 增强失败: {result.Stderr}");
        return output;
    }

    public async Task<string> ConcatAsync(IEnumerable<string> inputs, string output, int fps = 30, CancellationToken ct = default)
    {
        var paths = inputs.Where(File.Exists).ToList();
        if (paths.Count == 0) throw new InvalidOperationException("没有可拼接的视频文件");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var listPath = Path.Combine(_settings.DataPath, "Temp", $"concat_{Guid.NewGuid().ToString("N")}.txt");
        Directory.CreateDirectory(Path.GetDirectoryName(listPath)!);
        await File.WriteAllLinesAsync(listPath, paths.Select(p => $"file '{p.Replace("'", "'\\''")}'"), new System.Text.UTF8Encoding(false), ct);
        try
        {
            var result = await RunAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-vf", $"fps={Math.Clamp(fps, 24, 60)}", "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output], ct);
            if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 拼接失败: {result.Stderr}");
            return output;
        }
        finally { try { File.Delete(listPath); } catch { } }
    }

    public Task<string> MixAudioAsync(string video, IEnumerable<(string Path, double Volume)> tracks, string output, CancellationToken ct = default)
        => MixAudioAsync(video, tracks.Select(x => new FfmpegAudioTrack(x.Path, x.Volume)), output, ct);

    public async Task<string> MixAudioAsync(string video, IEnumerable<FfmpegAudioTrack> tracks, string output, CancellationToken ct = default)
    {
        var audioTracks = tracks.Where(x => File.Exists(x.Path)).ToList();
        var hasOriginalAudio = (await ProbeAsync(video, ct))?.HasAudio == true;
        if (audioTracks.Count == 0 && !hasOriginalAudio) return video;
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var args = new List<string> { "-y", "-hide_banner", "-loglevel", "error", "-i", video };
        foreach (var track in audioTracks) { args.Add("-i"); args.Add(track.Path); }
        var filters = new List<string>();
        var mixInputs = new List<string>();
        if (hasOriginalAudio)
        {
            filters.Add("[0:a]volume=1[original]");
            mixInputs.Add("[original]");
        }
        for (var i = 0; i < audioTracks.Count; i++)
        {
            var delay = Math.Max(0, (int)Math.Round(audioTracks[i].StartSeconds * 1000));
            var label = $"track{i}";
            filters.Add($"[{i + 1}:a]adelay={delay}:all=1,volume={Math.Clamp(audioTracks[i].Volume, 0.05, 2):0.###}[{label}]");
            mixInputs.Add($"[{label}]");
        }
        filters.Add(string.Join("", mixInputs) + $"amix=inputs={mixInputs.Count}:duration=longest:dropout_transition=3:normalize=0[aout]");
        args.AddRange(["-filter_complex", string.Join(';', filters), "-map", "0:v:0", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", output]);
        var result = await RunAsync(_settings.FfmpegPath, args, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 混音失败: {result.Stderr}");
        return output;
    }

    public async Task<string> BurnSubtitlesAsync(string video, string subtitlePath, string output, CancellationToken ct = default)
    {
        if (!File.Exists(subtitlePath)) throw new FileNotFoundException("字幕文件不存在", subtitlePath);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var escaped = subtitlePath.Replace("\\", "/").Replace(":", "\\:").Replace("'", "\\'");
        var result = await RunAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-i", video, "-vf", $"subtitles='{escaped}'", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy", "-movflags", "+faststart", output], ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 字幕烧录失败: {result.Stderr}");
        return output;
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunAsync(string fileName, IReadOnlyList<string> args, CancellationToken ct)
    {
        if (!File.Exists(fileName)) throw new FileNotFoundException("FFmpeg 未找到", fileName);
        using var process = new Process { StartInfo = new ProcessStartInfo { FileName = fileName, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true } };
        foreach (var arg in args) process.StartInfo.ArgumentList.Add(arg);
        if (!process.Start()) throw new InvalidOperationException($"无法启动 {fileName}");
        var stdout = process.StandardOutput.ReadToEndAsync(ct);
        var stderr = process.StandardError.ReadToEndAsync(ct);
        await process.WaitForExitAsync(ct);
        return (process.ExitCode, await stdout, await stderr);
    }

    private static int? GetInt(JsonElement element, string name)
    {
        if (element.ValueKind == JsonValueKind.Undefined || !element.TryGetProperty(name, out var value)) return null;
        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number)) return number;
        return int.TryParse(value.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed) ? parsed : null;
    }

    private static long? GetLong(JsonElement element, string name)
    {
        if (element.ValueKind == JsonValueKind.Undefined || !element.TryGetProperty(name, out var value)) return null;
        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number)) return number;
        return long.TryParse(value.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed) ? parsed : null;
    }
    private static string? GetString(JsonElement element, string name) => element.ValueKind != JsonValueKind.Undefined && element.TryGetProperty(name, out var value) ? value.ToString() : null;
    private static double? GetDouble(JsonElement element, string name)
    {
        if (element.ValueKind == JsonValueKind.Undefined || !element.TryGetProperty(name, out var value)) return null;
        if (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var result)) return result;
        return double.TryParse(value.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out result) ? result : null;
    }

    private static double? ParseRate(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var parts = value.Split('/');
        if (parts.Length == 2 && double.TryParse(parts[0], NumberStyles.Any, CultureInfo.InvariantCulture, out var n) && double.TryParse(parts[1], NumberStyles.Any, CultureInfo.InvariantCulture, out var d) && d != 0) return n / d;
        return double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out var result) ? result : null;
    }
}
