using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed record FfmpegAudioTrack(string Path, double Volume, double StartSeconds = 0, double Tempo = 1, double FadeOutStartSeconds = 0, double FadeOutDurationSeconds = 0);

public sealed partial class FfmpegService
{
    private readonly StudioSettings _settings;
    private readonly ILogger<FfmpegService> _logger;

    public FfmpegService(StudioSettings settings, ILogger<FfmpegService> logger)
    {
        _settings = settings;
        _logger = logger;
    }

    public bool IsAvailable => File.Exists(_settings.FfmpegPath) && File.Exists(_settings.FfprobePath);

    public async Task<string?> Sha256Async(string? path, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return null;
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, ct)).ToLowerInvariant();
    }

    public async Task<FfmpegProbe?> ProbeAsync(string path, CancellationToken ct = default)
    {
        var detailed = await ProbeDetailedAsync(path, ct);
        return detailed is null ? null : new FfmpegProbe(detailed.Width, detailed.Height, detailed.DurationSeconds, detailed.Fps, detailed.Codec, detailed.HasAudio, detailed.AudioDurationSeconds, detailed.SizeBytes, detailed.FrameCount);
    }

    public async Task<FfmpegDetailedProbe?> ProbeDetailedAsync(string path, CancellationToken ct = default)
    {
        if (!File.Exists(_settings.FfprobePath) || !File.Exists(path)) return null;
        var result = await RunAsync(_settings.FfprobePath, ["-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", path], ct);
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
                size,
                GetLong(video, "nb_read_frames") ?? GetLong(video, "nb_frames"));
        }
        catch (Exception ex) { _logger.LogWarning(ex, "Unable to parse detailed ffprobe output for asset {AssetName}", Path.GetFileName(path)); return null; }
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
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-ss", Math.Max(0, seconds).ToString("0.###", CultureInfo.InvariantCulture), "-i", input, "-frames:v", "1", "-vf", "scale=640:-2:flags=lanczos", "-an", output], output, ct);
        if (result.ExitCode != 0 || !File.Exists(output)) throw new InvalidOperationException($"FFmpeg 抽帧失败: {result.Stderr}");
        return output;
    }

    /// <summary>Compare against a deterministic, full-resolution decode of the actual final frame.</summary>
    public async Task<bool> MatchesDecodedLastFrameAsync(string video, string image, long frameCount, CancellationToken ct = default)
    {
        if(frameCount<1||!File.Exists(video)||!File.Exists(image))return false;
        var folder=Path.Combine(_settings.DataPath,"Temp","StoryContinuationChecks");Directory.CreateDirectory(folder);
        var output=Path.Combine(folder,$"tail-{Guid.NewGuid():N}.png");
        try
        {
            var result=await RunToAtomicOutputAsync(_settings.FfmpegPath,["-y","-hide_banner","-loglevel","error","-i",video,"-vf",$"select=eq(n\\,{frameCount-1})","-frames:v","1","-pix_fmt","rgb24",output],output,ct);
            if(result.ExitCode!=0||!File.Exists(output))throw new InvalidOperationException("无法从前一镜头精确解码尾帧："+result.Stderr);
            return string.Equals(await Sha256Async(output,ct),await Sha256Async(image,ct),StringComparison.OrdinalIgnoreCase);
        }
        finally {try{if(File.Exists(output))File.Delete(output);}catch(IOException){}}
    }

    public async Task<string> ConvertToMp4Async(string input, string output, CancellationToken ct = default, double? targetFps = null, bool preserveAudio = false)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var args = new List<string> { "-y", "-hide_banner", "-loglevel", "error", "-i", input };
        if (targetFps is > 0) args.AddRange(["-r", targetFps.Value.ToString("0.###", CultureInfo.InvariantCulture)]);
        args.AddRange(["-map", "0:v:0"]);
        if (preserveAudio) args.AddRange(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"]);
        else args.Add("-an");
        args.AddRange(["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output]);
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, args, output, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 转码失败: {result.Stderr}");
        return output;
    }

    public async Task<string> ExtractAudioAsync(string input, string output, CancellationToken ct = default)
    {
        if (!File.Exists(input) || (await ProbeAsync(input, ct))?.HasAudio != true)
            throw new InvalidOperationException("原生视频没有可提取的声音");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath,
            ["-hide_banner", "-loglevel", "error", "-i", input, "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", "-ar", "32000", output], output, ct);
        if (result.ExitCode != 0 || (await ProbeAsync(output, ct))?.HasAudio != true)
            throw new InvalidOperationException("原生音轨提取未生成可解码的 WAV");
        return output;
    }

    public async Task<string> EnhanceAsync(string input, string output, int fps = 30, CancellationToken ct = default, bool deflicker = false, bool interpolate = false, int width = 1920, int height = 1080)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var safeFps = Math.Clamp(fps, 24, 60);
        var safeWidth = Math.Max(2, Math.Clamp(width, 256, 7680) / 2 * 2);
        var safeHeight = Math.Max(2, Math.Clamp(height, 256, 7680) / 2 * 2);
        var filters = new List<string>();
        if (deflicker) filters.Add("deflicker=mode=median:size=5");
        if (interpolate) filters.Add($"minterpolate=fps={safeFps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1");
        filters.Add($"scale={safeWidth}:{safeHeight}:force_original_aspect_ratio=decrease:flags=lanczos");
        filters.Add($"pad={safeWidth}:{safeHeight}:(ow-iw)/2:(oh-ih)/2:color=black");
        filters.Add("setsar=1");
        var filter = string.Join(',', filters);
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-i", input, "-vf", filter, "-r", safeFps.ToString(CultureInfo.InvariantCulture), "-map", "0:v:0", "-map", "0:a?", "-c:a", "aac", "-b:a", "192k", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output], output, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 增强失败: {result.Stderr}");
        return output;
    }

    public async Task<string> ConcatAsync(IEnumerable<string> inputs, string output, int fps = 30, CancellationToken ct = default, bool preserveAudio = true, bool requireAllInputs = false)
    {
        var requested = inputs.ToList();
        if(requireAllInputs&&requested.Any(p=>!File.Exists(p)))throw new FileNotFoundException("已选剧情视频有文件缺失，禁止跳过镜头合成");
        var paths = requested.Where(File.Exists).ToList();
        if (paths.Any(path => path.Contains('\r') || path.Contains('\n'))) throw new InvalidOperationException("FFmpeg concat input path contains a line break");
        if (paths.Count == 0) throw new InvalidOperationException("没有可拼接的视频文件");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var listPath = Path.Combine(_settings.DataPath, "Temp", $"concat_{Guid.NewGuid().ToString("N")}.txt");
        Directory.CreateDirectory(Path.GetDirectoryName(listPath)!);
        await File.WriteAllLinesAsync(listPath, paths.Select(p => $"file '{p.Replace("'", "'\\''")}'"), new System.Text.UTF8Encoding(false), ct);
        try
        {
            var arguments=new List<string>{"-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",listPath,"-vf",$"fps={Math.Clamp(fps,24,60)}","-map","0:v:0"};
            if(preserveAudio)arguments.AddRange(["-map","0:a?","-c:a","aac","-b:a","192k"]);else arguments.Add("-an");
            arguments.AddRange(["-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",output]);
            var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, arguments, output, ct);
            if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 拼接失败: {result.Stderr}");
            return output;
        }
        finally { try { File.Delete(listPath); } catch { } }
    }

    public async Task<string> NormalizeVideoAsync(string input, string output, int width, int height, int fps = 30, CancellationToken ct = default, double? targetDurationSeconds = null)
    {
        if (!File.Exists(input)) throw new FileNotFoundException("待归一化视频不存在", input);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var safeWidth = Math.Max(2, Math.Clamp(width, 256, 7680) / 2 * 2);
        var safeHeight = Math.Max(2, Math.Clamp(height, 256, 7680) / 2 * 2);
        var safeFps = Math.Clamp(fps, 24, 60);
        var filter = $"fps={safeFps},scale={safeWidth}:{safeHeight}:force_original_aspect_ratio=decrease:flags=lanczos,pad={safeWidth}:{safeHeight}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1";
        if (targetDurationSeconds is > 0)
        {
            var duration = targetDurationSeconds.Value.ToString("0.###", CultureInfo.InvariantCulture);
            filter += $",tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setpts=PTS-STARTPTS";
        }
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-i", input, "-vf", filter, "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", output], output, ct);
        if (result.ExitCode != 0 || !File.Exists(output)) throw new InvalidOperationException($"FFmpeg 视频规格归一化失败: {result.Stderr}");
        return output;
    }

    public Task<string> MixAudioAsync(string video, IEnumerable<(string Path, double Volume)> tracks, string output, CancellationToken ct = default)
        => MixAudioAsync(video, tracks.Select(x => new FfmpegAudioTrack(x.Path, x.Volume)), output, ct);

    public async Task<string> MixAudioAsync(string video, IEnumerable<FfmpegAudioTrack> tracks, string output, CancellationToken ct = default, double originalVolume = 1d)
    {
        if (!double.IsFinite(originalVolume) || originalVolume is < 0 or > 2) throw new InvalidOperationException("原音音量必须为0–2的有限数值");
        var audioTracks = tracks.Where(x => File.Exists(x.Path)).ToList();
        if (audioTracks.Any(x => !double.IsFinite(x.Tempo) || x.Tempo is < .5 or > 2))
            throw new InvalidOperationException("音频变速必须为0.5–2的有限数值");
        if(audioTracks.Any(x=>!double.IsFinite(x.FadeOutStartSeconds)||!double.IsFinite(x.FadeOutDurationSeconds)||x.FadeOutStartSeconds is <0 or >3600||x.FadeOutDurationSeconds is <0 or >60))
            throw new InvalidOperationException("音频淡出起点和时长无效");
        var hasOriginalAudio = (await ProbeAsync(video, ct))?.HasAudio == true;
        if (audioTracks.Count == 0 && !hasOriginalAudio) return video;
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var args = new List<string> { "-y", "-hide_banner", "-loglevel", "error", "-i", video };
        foreach (var track in audioTracks) { args.Add("-i"); args.Add(track.Path); }
        var filters = new List<string>();
        var mixInputs = new List<string>();
        if (hasOriginalAudio)
        {
            filters.Add($"[0:a]volume={originalVolume.ToString("0.###", CultureInfo.InvariantCulture)}[original]");
            mixInputs.Add("[original]");
        }
        for (var i = 0; i < audioTracks.Count; i++)
        {
            var delay = Math.Max(0, (int)Math.Round(audioTracks[i].StartSeconds * 1000));
            var label = $"track{i}";
            var tempo = audioTracks[i].Tempo == 1 ? "" : $"atempo={audioTracks[i].Tempo.ToString("0.######", CultureInfo.InvariantCulture)},asetpts=PTS-STARTPTS,";
            var fade=audioTracks[i].FadeOutDurationSeconds>0?$"afade=t=out:st={audioTracks[i].FadeOutStartSeconds.ToString("0.###",CultureInfo.InvariantCulture)}:d={audioTracks[i].FadeOutDurationSeconds.ToString("0.###",CultureInfo.InvariantCulture)},":"";
            filters.Add($"[{i + 1}:a]{tempo}{fade}adelay={delay}:all=1,volume={Math.Clamp(audioTracks[i].Volume, 0.05, 2).ToString("0.###",CultureInfo.InvariantCulture)}[{label}]");
            mixInputs.Add($"[{label}]");
        }
        var videoDuration = (await ProbeAsync(video, ct))?.DurationSeconds;
        var copyVideo = await HasZeroVideoClockAsync(video, ct);
        filters.Add(string.Join("", mixInputs) + $"amix=inputs={mixInputs.Count}:duration=longest:dropout_transition=3:normalize=0[mixed]");
        if (videoDuration is > 0)
        {
            var duration = videoDuration.Value.ToString("0.###", CultureInfo.InvariantCulture);
            filters.Add($"[mixed]apad=whole_dur={duration},asetpts=N/SR/TB[aout]");
            args.AddRange(["-filter_complex", string.Join(';', filters), "-map", "0:v:0", "-map", "[aout]"]);
            if (copyVideo) args.AddRange(["-c:v", "copy"]);
            else args.AddRange(["-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264", "-preset", "medium", "-crf", "18"]);
            args.AddRange(["-t", duration, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output]);
        }
        else
        {
            filters.Add("[mixed]anull[aout]");
            args.AddRange(["-filter_complex", string.Join(';', filters), "-map", "0:v:0", "-map", "[aout]", "-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", output]);
        }
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, args, output, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 混音失败: {result.Stderr}");
        return output;
    }

    public async Task<string> BurnSubtitlesAsync(string video, string subtitlePath, string output, CancellationToken ct = default)
    {
        if (!File.Exists(subtitlePath)) throw new FileNotFoundException("字幕文件不存在", subtitlePath);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var escaped = subtitlePath.Replace("\\", "/").Replace(":", "\\:").Replace("'", "\\'").Replace("[", "\\[").Replace("]", "\\]").Replace(",", "\\,").Replace(";", "\\;");
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, ["-y", "-hide_banner", "-loglevel", "error", "-i", video, "-vf", $"subtitles='{escaped}'", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy", "-movflags", "+faststart", output], output, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException($"FFmpeg 字幕烧录失败: {result.Stderr}");
        return output;
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunToAtomicOutputAsync(string fileName, IReadOnlyList<string> args, string output, CancellationToken ct)
    {
        if (args.Count == 0 || !string.Equals(args[^1], output, StringComparison.Ordinal))
            throw new InvalidOperationException("FFmpeg output argument must be the final argument");
        var directory = Path.GetDirectoryName(output);
        if (string.IsNullOrWhiteSpace(directory)) throw new InvalidOperationException("FFmpeg output directory is required");
        var temporary = Path.Combine(directory, $".{Path.GetFileNameWithoutExtension(output)}.part-{Guid.NewGuid():N}{Path.GetExtension(output)}");
        var rewritten = args.ToArray();
        rewritten[^1] = temporary;
        try
        {
            var result = await RunAsync(fileName, rewritten, ct);
            if (result.ExitCode == 0 && File.Exists(temporary)) File.Move(temporary, output, false);
            else if (result.ExitCode == 0) result = (1, result.Stdout, result.Stderr + Environment.NewLine + "FFmpeg did not produce the expected output");
            return result;
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
        }
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunAsync(string fileName, IReadOnlyList<string> args, CancellationToken ct)
    {
        if (!File.Exists(fileName)) throw new FileNotFoundException("FFmpeg 未找到", fileName);
        using var process = new Process { StartInfo = new ProcessStartInfo { FileName = fileName, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true } };
        foreach (var arg in args) process.StartInfo.ArgumentList.Add(arg);
        if (!process.Start()) throw new InvalidOperationException($"无法启动 {fileName}");
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        try
        {
            await process.WaitForExitAsync(ct);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            try { await process.WaitForExitAsync(CancellationToken.None); } catch { }
            throw;
        }
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
