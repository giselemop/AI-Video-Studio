using System.Diagnostics;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

internal static class DeliveryRegression
{
    public static async Task Run(string ffmpegPath)
    {
        var folder = Path.Combine("C:/install/AI/Data/acceptance", "delivery720_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss_fff"));
        Directory.CreateDirectory(folder);
        var settings = new StudioSettings
        {
            FfmpegPath = ffmpegPath,
            FfprobePath = Path.Combine(Path.GetDirectoryName(ffmpegPath)!, "ffprobe.exe")
        };
        var service = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
        var evidence = new List<object>();
        foreach (var audio in new[] { true, false })
        {
            var source = Path.Combine(folder, audio ? "synthetic_audio_source.mp4" : "synthetic_silent_source.mp4");
            var output = Path.Combine(folder, audio ? "synthetic_audio_720p.mp4" : "synthetic_silent_720p.mp4");
            var start = new ProcessStartInfo(ffmpegPath) { UseShellExecute = false, CreateNoWindow = true };
            foreach (var arg in new[] { "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=864x480:rate=24" }) start.ArgumentList.Add(arg);
            if (audio) foreach (var arg in new[] { "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-c:a", "aac" }) start.ArgumentList.Add(arg);
            foreach (var arg in new[] { "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-n", source }) start.ArgumentList.Add(arg);
            using var process = Process.Start(start)!;
            await process.WaitForExitAsync();
            if (process.ExitCode != 0) throw new Exception("Fixture generation failed");
            var timer = Stopwatch.StartNew();
            await service.EnhanceAsync(source, output, 24, default, false, false, 1280, 720);
            var probe = await service.ProbeDetailedAsync(output);
            if (probe is null || probe.Width != 1280 || probe.Height != 720 || probe.HasAudio != audio ||
                probe.Codec != "h264" || probe.Fps != 24 || Math.Abs((probe.DurationSeconds ?? 0) - 2) > .1 ||
                (audio && (probe.AudioCodec != "aac" || Math.Abs((probe.AudioDurationSeconds ?? 0) - 2) > .1)))
                throw new Exception("720p/audio preservation failed");
            if (audio)
            {
                var extracted = Path.Combine(folder, "native_audio.wav");
                await service.ExtractAudioAsync(output, extracted);
                var audioProbe = await service.ProbeDetailedAsync(extracted);
                if (audioProbe?.HasAudio != true || audioProbe.Width is > 0 || Math.Abs((audioProbe.AudioDurationSeconds ?? 0) - 2) > .1)
                    throw new Exception("Native audio extraction failed");
            }
            else
            {
                try { await service.ExtractAudioAsync(output, Path.Combine(folder, "silent_must_not_exist.wav")); throw new Exception("Silent input accepted"); }
                catch (InvalidOperationException) { }
            }
            evidence.Add(new { source, output, elapsedSeconds = timer.Elapsed.TotalSeconds, probe, technicalStatus = "Passed", contentStatus = "NotApplicableSyntheticFixture" });
        }
        // An actual 24 FPS multi-shot delivery: preserve frames, delay narration,
        // mute native audio, and burn UTF-8 Chinese captions. These are synthetic
        // technical fixtures, never evidence of generated story content quality.
        var joined = Path.Combine(folder, "synthetic_story_joined.mp4");
        await service.ConcatAsync(new[] { Path.Combine(folder, "synthetic_audio_source.mp4"), Path.Combine(folder, "synthetic_audio_source.mp4") }, joined, 24);
        var normalized = Path.Combine(folder, "synthetic_story_normalized.mp4");
        await service.NormalizeVideoAsync(joined, normalized, 864, 480, 24, targetDurationSeconds: 4);
        var normalizedProbe = await service.ProbeDetailedAsync(normalized);
        if (normalizedProbe?.FrameCount != 96 || normalizedProbe.Fps != 24)
            throw new Exception("24 FPS concat normalization dropped a frame");
        var narration = Path.Combine(folder, "synthetic_narration.wav");
        var voiceStart = new ProcessStartInfo(ffmpegPath) { UseShellExecute = false, CreateNoWindow = true };
        foreach (var arg in new[] { "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "0.5", "-n", narration }) voiceStart.ArgumentList.Add(arg);
        using (var voice = Process.Start(voiceStart)!) { await voice.WaitForExitAsync(); if (voice.ExitCode != 0) throw new Exception("Narration fixture failed"); }
        var offsetMixed = Path.Combine(folder, "synthetic_story_offset_mixed.mp4");
        await service.MixAudioAsync(joined, new[] { new FfmpegAudioTrack(narration, 1, 1) }, offsetMixed, originalVolume: 0);
        var offsetProbe = await service.ProbeDetailedAsync(offsetMixed);
        if (offsetProbe?.FrameCount != 96 || offsetProbe.Fps != 24)
            throw new Exception("Mixing a concat output with a nonzero starting timestamp dropped a frame");
        var mixed = Path.Combine(folder, "synthetic_story_narrated.mp4");
        await service.MixAudioAsync(normalized, new[] { new FfmpegAudioTrack(narration, 1, 1) }, mixed, originalVolume: 0);
        var captions = Path.Combine(folder, "synthetic_story.srt");
        await File.WriteAllTextAsync(captions, "1\n00:00:01,000 --> 00:00:01,500\n校园剧情技术测试\n", new System.Text.UTF8Encoding(false));
        var captioned = Path.Combine(folder, "synthetic_story_captioned.mp4");
        await service.BurnSubtitlesAsync(mixed, captions, captioned);
        var storyProbe = await service.ProbeDetailedAsync(captioned);
        if (storyProbe?.Fps != 24 || storyProbe.FrameCount != 96 || storyProbe.HasAudio != true || Math.Abs((storyProbe.DurationSeconds ?? 0) - 4) > .05)
            throw new Exception("24 FPS story frame/duration/audio delivery failed");
        var pcmPath = Path.Combine(folder, "synthetic_story_pcm.wav");
        await service.ExtractAudioAsync(captioned, pcmPath);
        // Decode to raw samples through FFmpeg so WAV chunk ordering is irrelevant.
        var rawPath = Path.Combine(folder, "synthetic_story_pcm.raw");
        var decodeStart = new ProcessStartInfo(ffmpegPath) { UseShellExecute = false, CreateNoWindow = true };
        foreach (var arg in new[] { "-hide_banner", "-loglevel", "error", "-i", pcmPath, "-ac", "1", "-ar", "48000", "-f", "s16le", "-n", rawPath }) decodeStart.ArgumentList.Add(arg);
        using (var decode = Process.Start(decodeStart)!) { await decode.WaitForExitAsync(); if (decode.ExitCode != 0) throw new Exception("Story audio decode failed"); }
        var samples = await File.ReadAllBytesAsync(rawPath);
        double Rms(double from, double to)
        {
            var begin = (int)(from * 48000); var end = Math.Min((int)(to * 48000), samples.Length / 2);
            double sum = 0;
            for (var n = begin; n < end; n++) { var sample = BitConverter.ToInt16(samples, n * 2) / 32768d; sum += sample * sample; }
            return Math.Sqrt(sum / (end - begin));
        }
        var beforeNarration = Rms(.2, .8); var duringNarration = Rms(1.1, 1.4); var afterNarration = Rms(2, 3);
        if (beforeNarration > .001 || duringNarration < .02 || afterNarration > .001)
            throw new Exception("Native audio muting or narration offset failed");
        var soloMuted = Path.Combine(folder, "synthetic_story_original_muted.mp4");
        await service.MixAudioAsync(joined, Array.Empty<FfmpegAudioTrack>(), soloMuted, originalVolume: 0);
        var soloProbe = await service.ProbeDetailedAsync(soloMuted);
        if (soloProbe?.FrameCount != 96 || soloProbe.HasAudio != true) throw new Exception("Native-only audio gain failed");
        var silent = Path.Combine(folder, "synthetic_silent_source.mp4");
        var unusedMix = Path.Combine(folder, "silent_unneeded_mix.mp4");
        if (await service.MixAudioAsync(silent, Array.Empty<FfmpegAudioTrack>(), unusedMix, originalVolume: 0) != silent || File.Exists(unusedMix))
            throw new Exception("Already silent input must return its existing video path");
        foreach (var invalid in new[] { double.NaN, -1d, 3d })
        {
            try { await service.MixAudioAsync(joined, Array.Empty<FfmpegAudioTrack>(), Path.Combine(folder, "invalid.mp4"), originalVolume: invalid); throw new Exception("Invalid native audio gain accepted"); }
            catch (InvalidOperationException) { }
        }
        var tempoMixed = Path.Combine(folder, "synthetic_tempo_2x.mp4");
        await service.MixAudioAsync(joined, new[] { new FfmpegAudioTrack(narration, 1, 1, 2) }, tempoMixed, originalVolume: 0);
        var tempoProbe = await service.ProbeDetailedAsync(tempoMixed);
        if (tempoProbe?.FrameCount != 96 || tempoProbe.Fps != 24) throw new Exception("Audio tempo changed video frames");
        var tempoRaw = Path.Combine(folder, "synthetic_tempo_2x.raw");
        var tempoDecode = new ProcessStartInfo(ffmpegPath) { UseShellExecute = false, CreateNoWindow = true };
        foreach (var arg in new[] { "-v", "error", "-i", tempoMixed, "-ac", "1", "-ar", "48000", "-f", "s16le", "-n", tempoRaw }) tempoDecode.ArgumentList.Add(arg);
        using (var decode = Process.Start(tempoDecode)!) { await decode.WaitForExitAsync(); if (decode.ExitCode != 0) throw new Exception("Tempo fixture decode failed"); }
        var tempoSamples = await File.ReadAllBytesAsync(tempoRaw);
        double TempoRms(double from, double to)
        {
            double sum = 0; var begin = (int)(from * 48000); var end = (int)(to * 48000);
            for (var n = begin; n < end; n++) { var value = BitConverter.ToInt16(tempoSamples, n * 2) / 32768d; sum += value * value; }
            return Math.Sqrt(sum / (end - begin));
        }
        var crossings = 0;
        for (var n = (int)(1.06 * 48000); n < (int)(1.18 * 48000); n++)
            if (BitConverter.ToInt16(tempoSamples, n * 2) <= 0 && BitConverter.ToInt16(tempoSamples, (n + 1) * 2) > 0) crossings++;
        var frequency = crossings / .12;
        if (TempoRms(.2, .8) > .001 || TempoRms(1.06, 1.18) < .02 || TempoRms(1.35, 1.7) > .001 || frequency is < 820 or > 940)
            throw new Exception("Tempo failed duration, start offset, silence or preserved 880 Hz pitch check");
        foreach (var invalidTempo in new[] { double.NaN, 0d, 2.1 })
        {
            try { await service.MixAudioAsync(joined, new[] { new FfmpegAudioTrack(narration, 1, 0, invalidTempo) }, Path.Combine(folder, "invalid_tempo.mp4")); throw new Exception("Invalid tempo accepted"); }
            catch (InvalidOperationException) { }
        }
        evidence.Add(new { tempoMixed, tempoProbe, tempo = 2, expectedFrequency = 880, measuredFrequency = frequency, before = TempoRms(.2, .8), during = TempoRms(1.06, 1.18), after = TempoRms(1.35, 1.7), technicalStatus = "Passed" });
        evidence.Add(new { captioned, storyProbe, offsetMixed, offsetProbe, normalizedProbe, soloMuted, soloProbe, beforeNarration, duringNarration, afterNarration, technicalStatus = "Passed", contentStatus = "NotApplicableSyntheticFixture" });
        async Task<string> Command(params string[] command)
        {
            var info = new ProcessStartInfo(ffmpegPath) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var arg in command) info.ArgumentList.Add(arg);
            using var child = Process.Start(info)!;
            var stdout = child.StandardOutput.ReadToEndAsync(); var stderr = child.StandardError.ReadToEndAsync();
            await child.WaitForExitAsync();
            if (child.ExitCode != 0) throw new Exception(await stderr);
            return await stdout;
        }
        async Task<string[]> FrameHashes(string file) => (await Command("-v", "error", "-i", file, "-map", "0:v", "-f", "framemd5", "-"))
            .Split('\n').Where(line => line.Length > 0 && !line.StartsWith('#')).Select(line => line.Split(',')[^1].Trim()).ToArray();
        var preserved = (await FrameHashes(normalized)).SequenceEqual(await FrameHashes(mixed));
        if (!preserved) throw new Exception("Zero-PTS audio mixing reencoded or changed video frames");
        var onePass = Path.Combine(folder, "synthetic_single_pass.mp4");
        await service.ExportSinglePassAsync(new[] { Path.Combine(folder, "synthetic_audio_source.mp4"), silent }, onePass,
            864, 480, 24, 3, .5, new[] { new FfmpegAudioTrack(narration, 1, 1, 2) }, 0);
        var oneProbe = await service.ProbeDetailedAsync(onePass);
        if (oneProbe?.FrameCount != 72 || oneProbe.Fps != 24 || oneProbe.Width != 864 || oneProbe.Height != 480 || Math.Abs(oneProbe.DurationSeconds!.Value - 3) > .001)
            throw new Exception("One-pass concat/trim changed frame count or duration");
        var oneRaw = Path.Combine(folder, "single_pass.raw");
        await Command("-v", "error", "-i", onePass, "-ac", "1", "-ar", "48000", "-f", "s16le", "-n", oneRaw);
        var oneSamples = await File.ReadAllBytesAsync(oneRaw);
        double OneRms(double begin, double end)
        {
            double sum = 0; var first = (int)(begin * 48000); var last = (int)(end * 48000);
            for (var n = first; n < last; n++) { var value = BitConverter.ToInt16(oneSamples, n * 2) / 32768d; sum += value * value; }
            return Math.Sqrt(sum / (last - first));
        }
        var oneCrossings = 0;
        for (var n = (int)(.56 * 48000); n < (int)(.68 * 48000); n++)
            if (BitConverter.ToInt16(oneSamples, n * 2) <= 0 && BitConverter.ToInt16(oneSamples, (n + 1) * 2) > 0) oneCrossings++;
        var oneFrequency = oneCrossings / .12;
        if (OneRms(.1, .4) > .001 || OneRms(.56, .68) < .02 || OneRms(1, 2.8) > .001 || oneFrequency is < 820 or > 940)
            throw new Exception("One-pass concat failed native mute, narration tempo, trim offset or pitch check");
        var fractional = Path.Combine(folder, "single_pass_49frames.mp4");
        await service.ExportSinglePassAsync(new[] { Path.Combine(folder, "synthetic_audio_source.mp4"), silent }, fractional,
            864, 480, 24, 49d / 24, 1, originalVolume: 0);
        if ((await service.ProbeDetailedAsync(fractional))?.FrameCount != 49) throw new Exception("Fractional frame-aligned trim changed frame count");
        foreach (var bad in new[] { (Duration: 5d, Start: 0d), (Duration: 1d, Start: .01), (Duration: double.NaN, Start: 0d) })
        {
            try { await service.ExportSinglePassAsync(new[] { silent }, Path.Combine(folder, "invalid_single_pass.mp4"), 864, 480, 24, bad.Duration, bad.Start); throw new Exception("Invalid or short source delivery accepted"); }
            catch (InvalidOperationException) { }
        }
        await Command("-v", "error", "-i", onePass, "-f", "null", "-");
        evidence.Add(new { onePass, oneProbe, fractional, unchangedMixedVideo = preserved, oneFrequency, before = OneRms(.1, .4), during = OneRms(.56, .68), after = OneRms(1, 2.8), technicalStatus = "Passed" });
        var videoOnly = Path.Combine(folder, "single_pass_video_only.mp4");
        await Command("-v", "error", "-i", onePass, "-map", "0:v:0", "-c:v", "copy", "-an", "-n", videoOnly);
        var remuxed = Path.Combine(folder, "single_pass_audio_remuxed.mp4");
        await service.RemuxAudioAsync(videoOnly, onePass, remuxed);
        var sourceAudioHash = await Command("-v", "error", "-i", onePass, "-map", "0:a:0", "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-");
        var copiedAudioHash = await Command("-v", "error", "-i", remuxed, "-map", "0:a:0", "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-");
        if (sourceAudioHash != copiedAudioHash || !(await FrameHashes(videoOnly)).SequenceEqual(await FrameHashes(remuxed)))
            throw new Exception("Separate audio remux changed video frames or encoded audio packets");
        foreach (var invalidAudioSource in new[] { videoOnly, silent })
        {
            try { await service.RemuxAudioAsync(videoOnly, invalidAudioSource, Path.Combine(folder, "invalid_remux.mp4")); throw new Exception("Missing audio or mismatched duration accepted"); }
            catch (InvalidOperationException) { }
        }
        evidence.Add(new { remuxed, sourceAudioHash, copiedAudioHash, unchangedVideo = true, technicalStatus = "Passed" });
        await File.WriteAllTextAsync(Path.Combine(folder, "report.json"), JsonSerializer.Serialize(evidence, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"720p delivery regression Passed: {folder}");
    }
}
