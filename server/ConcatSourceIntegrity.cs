using System.Text.Json;

namespace VideoStudio.Server;

/// <summary>Optional frozen inputs for a review concat; existing concat modes are unchanged.</summary>
public static class ConcatSourceIntegrity
{
    public static async Task ValidateAsync(JsonElement parameters,AssetPathPolicy paths,FfmpegService ffmpeg,CancellationToken ct)
    {
        if(!parameters.TryGetProperty("sourceChecks",out var checks))return;
        if(checks.ValueKind!=JsonValueKind.Array||checks.GetArrayLength() is <1 or >64)throw new AssetValidationException("合成来源哈希清单无效");
        var declared=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
        foreach(var item in checks.EnumerateArray())
        {
            if(item.ValueKind!=JsonValueKind.Object||!item.TryGetProperty("path",out var pathValue)||pathValue.ValueKind!=JsonValueKind.String||!item.TryGetProperty("sha256",out var hashValue)||hashValue.ValueKind!=JsonValueKind.String)throw new AssetValidationException("合成来源路径或哈希缺失");
            var hash=hashValue.GetString()??"";
            if(hash.Length!=64||!hash.All(Uri.IsHexDigit)||!paths.TryResolveExisting(pathValue.GetString(),out var full,out _)||!declared.TryAdd(full,hash))throw new AssetValidationException("合成来源不存在、重复或哈希无效");
        }
        var referenced=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void Add(string? path)
        {if(!paths.TryResolveExisting(path,out var full,out _))throw new AssetValidationException("合成来源文件不存在");referenced.Add(full);}
        if(!parameters.TryGetProperty("files",out var files)||files.ValueKind!=JsonValueKind.Array)throw new AssetValidationException("合成视频清单缺失");
        foreach(var file in files.EnumerateArray()){if(file.ValueKind!=JsonValueKind.String)throw new AssetValidationException("合成视频路径无效");Add(file.GetString());}
        if(parameters.TryGetProperty("audioTracks",out var tracks))
        {if(tracks.ValueKind!=JsonValueKind.Array)throw new AssetValidationException("合成音轨清单无效");foreach(var track in tracks.EnumerateArray()){if(track.ValueKind!=JsonValueKind.Object||!track.TryGetProperty("path",out var path)||path.ValueKind!=JsonValueKind.String)throw new AssetValidationException("合成音轨路径缺失");Add(path.GetString());}}
        if(parameters.TryGetProperty("subtitlePath",out var caption)&&caption.ValueKind==JsonValueKind.String&&!string.IsNullOrWhiteSpace(caption.GetString()))Add(caption.GetString());
        if(!referenced.SetEquals(declared.Keys))throw new AssetValidationException("合成来源与冻结哈希清单不一致");
        foreach(var (full,hash) in declared)if(!string.Equals(await ffmpeg.Sha256Async(full,ct),hash,StringComparison.OrdinalIgnoreCase))throw new AssetValidationException("合成来源文件SHA256已变化");
    }
}
