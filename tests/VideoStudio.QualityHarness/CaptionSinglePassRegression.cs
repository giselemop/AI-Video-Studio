using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

internal static class CaptionSinglePassRegression
{
    public static async Task Run()
    {
        var folder = Path.Combine(@"C:\install\AI\Data\acceptance", "caption_singlepass_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var settings = new StudioSettings();
        var service = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
        async Task<byte[]> Execute(params string[] args)
        {
            var info = new ProcessStartInfo(settings.FfmpegPath) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var arg in args) info.ArgumentList.Add(arg);
            using var p = Process.Start(info)!; using var data = new MemoryStream();
            var copy = p.StandardOutput.BaseStream.CopyToAsync(data); var error = p.StandardError.ReadToEndAsync();
            await p.WaitForExitAsync(); await copy;
            if (p.ExitCode != 0) throw new Exception(await error);
            return data.ToArray();
        }
        var a = Path.Combine(folder, "red.mp4"); var b = Path.Combine(folder, "blue.mp4");
        foreach (var (color, file) in new[] { ("red", a), ("blue", b) })
            await Execute("-v", "error", "-n", "-f", "lavfi", "-i", $"color=c={color}:s=640x360:r=24:d=1", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", file);
        var captions = Path.Combine(folder, "对白 caption.srt");
        await File.WriteAllTextAsync(captions, "1\n00:00:00,200 --> 00:00:00,800\n女：你好。\n\n2\n00:00:01,200 --> 00:00:01,800\n男：你好。\n", new UTF8Encoding(false));
        var plain = Path.Combine(folder, "plain.mp4"); var captioned = Path.Combine(folder, "captioned.mp4");
        await service.ExportSinglePassAsync([a, b], plain, 640, 360, 24, 2, originalVolume: 0);
        await service.ExportSinglePassAsync([a, b], captioned, 640, 360, 24, 2, originalVolume: 0, subtitlePath: captions);
        var checks = new List<object>(); var failed = new List<string>();
        void Check(string name, bool yes) { checks.Add(new { name, status = yes ? "Passed" : "Failed" }); if (!yes) failed.Add(name); }
        Check("remux-same-size-default", FfmpegService.IsRemuxGeometryCompatible(2560,1440,2560,1440,false));
        Check("remux-768-requires-opt-in", !FfmpegService.IsRemuxGeometryCompatible(1366,768,2560,1440,false));
        Check("remux-768-even-width-rounding", FfmpegService.IsRemuxGeometryCompatible(1366,768,2560,1440,true));
        Check("remux-720-exact-ratio", FfmpegService.IsRemuxGeometryCompatible(1280,720,2560,1440,true));
        Check("remux-reject-crop", !FfmpegService.IsRemuxGeometryCompatible(1366,768,1920,1200,true));
        Check("remux-reject-invalid-size", !FfmpegService.IsRemuxGeometryCompatible(0,768,2560,1440,true));
        foreach (var (label,file) in new[] { ("legacy-without-caption",plain), ("single-pass-caption",captioned) })
        {
            var probe = await service.ProbeDetailedAsync(file);
            Check(label+"-geometry-clock", probe?.Width == 640 && probe.Height == 360 && probe.Fps == 24 && probe.FrameCount == 48 && Math.Abs((probe.DurationSeconds ?? 0)-2)<.001);
            await Execute("-nostdin", "-v", "error", "-i", file, "-f", "null", "-");
            Check(label+"-complete-decode", true);
        }
        async Task<byte[]> Frame(int index) => await Execute("-v", "error", "-i", captioned, "-vf", $"select=eq(n\\,{index})", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1");
        int Whites(byte[] pixels)
        {
            var count=0;
            for(var y=250;y<360;y++) for(var x=0;x<640;x++) { var i=(y*640+x)*3; if(pixels[i]>180 && pixels[i+1]>180 && pixels[i+2]>180) count++; }
            return count;
        }
        var f0=await Frame(0); var f12=await Frame(12); var f23=await Frame(23); var f24=await Frame(24); var f36=await Frame(36);
        Check("caption-off-before-first-line", Whites(f0)<10);
        Check("utf8-first-caption-visible", Whites(f12)>50);
        Check("second-caption-visible", Whites(f36)>50);
        var centre=(180*640+320)*3;
        Check("cut-frame23-red", f23[centre]>200 && f23[centre+2]<40);
        Check("cut-frame24-blue", f24[centre+2]>200 && f24[centre]<40);
        foreach(var (label,path) in new[] { ("missing-srt",Path.Combine(folder,"missing.srt")), ("non-srt",a) })
        {
            var output=Path.Combine(folder,label+".mp4");
            try { await service.ExportSinglePassAsync([a,b],output,640,360,24,2,subtitlePath:path);Check(label,false); }
            catch(InvalidOperationException) { Check(label,!File.Exists(output)); }
        }
        // The real dialogue uses fractional shot lengths53/24,43/24,144/24.
        // This catches frame rounding at the actual two cut positions.
        var fractional = new List<string>();
        foreach(var (color,count) in new[] { ("red",53), ("blue",43), ("lime",144) })
        {
            var file=Path.Combine(folder,$"fractional-{color}.mp4");
            await Execute("-v","error","-n","-f","lavfi","-i",$"color=c={color}:s=640x360:r=24","-frames:v",count.ToString(),"-an","-c:v","libx264","-pix_fmt","yuv420p",file);
            fractional.Add(file);
        }
        var exact=Path.Combine(folder,"fractional-captioned-10s.mp4");
        await service.ExportSinglePassAsync(fractional,exact,640,360,24,10,originalVolume:0,subtitlePath:captions);
        var exactProbe=await service.ProbeDetailedAsync(exact);
        Check("real-three-shot-240-frames-10s",exactProbe?.FrameCount==240 && exactProbe.Fps==24 && Math.Abs((exactProbe.DurationSeconds??0)-10)<.001);
        await Execute("-nostdin","-v","error","-i",exact,"-f","null","-");Check("real-three-shot-complete-decode",true);
        foreach(var (index,channel) in new[] { (52,0),(53,2),(95,2),(96,1) })
        {
            var pixels=await Execute("-v","error","-i",exact,"-vf",$"select=eq(n\\,{index})","-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1");
            Check("real-cut-frame-"+index,pixels[centre+channel]>200 && pixels[centre+(channel+1)%3]<40 && pixels[centre+(channel+2)%3]<40);
        }
        var report=Path.Combine(folder,"report.json");
        await File.WriteAllTextAsync(report,JsonSerializer.Serialize(new { status=failed.Count==0?"Passed":"Failed",syntheticTechnicalFixture=true,gpuInference=false,databaseWrites=false,checks,failed },new JsonSerializerOptions { WriteIndented=true }));
        Console.WriteLine(JsonSerializer.Serialize(new { report,status=failed.Count==0?"Passed":"Failed",checks=checks.Count,failed }));
        if(failed.Count>0)throw new Exception("Caption single-pass regression failed");
    }
}
