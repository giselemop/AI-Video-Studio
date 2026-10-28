using System.Globalization;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed partial class FfmpegService
{
    public static bool IsRemuxGeometryCompatible(int? videoWidth, int? videoHeight, int? audioWidth, int? audioHeight, bool allowResolutionDifference)
    {
        if (videoWidth is not > 0 || videoHeight is not > 0 || audioWidth is not > 0 || audioHeight is not > 0) return false;
        if (videoWidth == audioWidth && videoHeight == audioHeight) return true;
        // Even output widths may round a scaled 16:9 image by less than one
        // pixel (1366x768). Explicit opt-in remains required; crop changes fail.
        return allowResolutionDifference && Math.Abs((long)videoWidth.Value * audioHeight.Value - (long)audioWidth.Value * videoHeight.Value)
            <= Math.Max(videoHeight.Value, audioHeight.Value);
    }
    public async Task<string> RemuxAudioAsync(string video, string audioSource, string output, CancellationToken ct = default, bool allowResolutionDifference = false)
    {
        var v = await ProbeAsync(video, ct); var a = await ProbeAsync(audioSource, ct);
        var compatibleGeometry = IsRemuxGeometryCompatible(v?.Width, v?.Height, a?.Width, a?.Height, allowResolutionDifference);
        if (v?.DurationSeconds is not > 0 || a?.HasAudio != true || v.FrameCount != a.FrameCount || v.Fps != a.Fps
            || !compatibleGeometry || Math.Abs(v.DurationSeconds.Value - (a.DurationSeconds ?? 0)) > .001
            || !await HasZeroVideoClockAsync(video, ct) || !await HasZeroVideoClockAsync(audioSource, ct))
            throw new InvalidOperationException("无损换轨要求同时长、同帧率帧数、零起点；跨分辨率必须显式启用且宽高比相同");
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath,
            ["-hide_banner", "-loglevel", "error", "-i", video, "-i", audioSource, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", output], output, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException("无损换轨失败: " + result.Stderr);
        return output;
    }

    /// <summary>Normalize, concatenate, trim and mix in one video encode; no padded video frames.</summary>
    public async Task<string> ExportSinglePassAsync(IReadOnlyList<string> files, string output,
        int width, int height, int fps, double duration, double startSeconds = 0,
        IReadOnlyList<FfmpegAudioTrack>? tracks = null, double originalVolume = 1, CancellationToken ct = default, string? subtitlePath = null)
    {
        if (files.Count is < 1 or > 20 || files.Any(p => !File.Exists(p))) throw new InvalidOperationException("保细节导出要求1–20个有效源视频");
        if (width is < 256 or > 3840 || height is < 256 or > 3840 || width % 2 != 0 || height % 2 != 0
            || fps is < 24 or > 60 || !double.IsFinite(duration) || duration is <= 0 or > 3600
            || !double.IsFinite(startSeconds) || startSeconds is < 0 or > 3600
            || Math.Abs(duration * fps - Math.Round(duration * fps)) > .001
            || Math.Abs(startSeconds * fps - Math.Round(startSeconds * fps)) > .001
            || !double.IsFinite(originalVolume) || originalVolume is < 0 or > 2)
            throw new InvalidOperationException("保细节导出的尺寸、帧率、时长或音量无效");
        tracks ??= [];
        if (subtitlePath is not null && (!File.Exists(subtitlePath) || !string.Equals(Path.GetExtension(subtitlePath), ".srt", StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException("一次编码字幕必须是已存在的SRT文件");
        if (tracks.Any(t => !File.Exists(t.Path) || !double.IsFinite(t.Tempo) || t.Tempo is < .5 or > 2
            || !double.IsFinite(t.Volume) || t.Volume is < .05 or > 2 || !double.IsFinite(t.StartSeconds) || t.StartSeconds is < 0 or > 3600))
            throw new InvalidOperationException("保细节导出的旁白参数无效");
        var probes = new List<FfmpegProbe>();
        foreach (var file in files)
        {
            var probe = await ProbeAsync(file, ct);
            if (probe?.DurationSeconds is not > 0 || probe.Width is not > 0 || probe.Height is not > 0)
                throw new InvalidOperationException("源视频缺少可验证的画面和时长");
            probes.Add(probe);
        }
        var total = probes.Sum(p => p.DurationSeconds!.Value);
        if (total + .001 < duration + startSeconds) throw new InvalidOperationException("CONCAT_DELIVERY_SOURCE_SHORT: 源视频不足，不使用静帧补足");
        static string N(double value) => value.ToString("0.#########", CultureInfo.InvariantCulture);
        var args = new List<string> { "-hide_banner", "-loglevel", "error" };
        foreach (var path in files.Concat(tracks.Select(t => t.Path))) args.AddRange(["-i", path]);
        var filters = new List<string>();
        var concat = new List<string>();
        for (var i = 0; i < files.Count; i++)
        {
            var seconds = N(probes[i].DurationSeconds!.Value);
            filters.Add($"[{i}:v]setpts=PTS-STARTPTS,fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,settb=AVTB[v{i}]");
            filters.Add(probes[i].HasAudio
                ? $"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=N/SR/TB,apad=whole_dur={seconds},atrim=duration={seconds}[a{i}]"
                : $"anullsrc=r=48000:cl=stereo,atrim=duration={seconds},asetpts=N/SR/TB[a{i}]");
            concat.Add($"[v{i}][a{i}]");
        }
        filters.Add(string.Join("", concat) + $"concat=n={files.Count}:v=1:a=1[basev][basea]");
        var videoFilter = $"[basev]trim=start={N(startSeconds)}:duration={N(duration)},setpts=PTS-STARTPTS";
        if (subtitlePath is not null)
        {
            var escaped = subtitlePath.Replace("\\", "/").Replace(":", "\\:").Replace("'", "\\'").Replace("[", "\\[").Replace("]", "\\]").Replace(",", "\\,").Replace(";", "\\;");
            videoFilter += $",subtitles='{escaped}'";
        }
        filters.Add(videoFilter + "[vout]");
        filters.Add($"[basea]volume={N(originalVolume)}[original]");
        var mix = new List<string> { "[original]" };
        for (var i = 0; i < tracks.Count; i++)
        {
            var t = tracks[i];
            filters.Add($"[{files.Count + i}:a]atempo={N(t.Tempo)},asetpts=PTS-STARTPTS,adelay={(int)Math.Round(t.StartSeconds * 1000)}:all=1,volume={N(t.Volume)}[n{i}]");
            mix.Add($"[n{i}]");
        }
        filters.Add(string.Join("", mix) + $"amix=inputs={mix.Count}:normalize=0:duration=longest:dropout_transition=0,apad=whole_dur={N(total)},asetpts=N/SR/TB,atrim=start={N(startSeconds)}:duration={N(duration)},asetpts=N/SR/TB[aout]");
        args.AddRange(["-filter_complex", string.Join(';', filters), "-map", "[vout]", "-map", "[aout]", "-t", N(duration),
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output]);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var result = await RunToAtomicOutputAsync(_settings.FfmpegPath, args, output, ct);
        if (result.ExitCode != 0) throw new InvalidOperationException("保细节导出失败: " + result.Stderr);
        return output;
    }

    private async Task<bool> HasZeroVideoClockAsync(string video, CancellationToken ct)
    {
        var result = await RunAsync(_settings.FfprobePath, ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=start_time,duration", "-of", "json", video], ct);
        if (result.ExitCode != 0) return false;
        try
        {
            using var doc = JsonDocument.Parse(result.Stdout);
            var stream = doc.RootElement.GetProperty("streams")[0];
            return double.TryParse(stream.GetProperty("start_time").GetString(), CultureInfo.InvariantCulture, out var start)
                && Math.Abs(start) < .000001 && double.TryParse(stream.GetProperty("duration").GetString(), CultureInfo.InvariantCulture, out var duration) && duration > 0;
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or IndexOutOfRangeException) { return false; }
    }
}
