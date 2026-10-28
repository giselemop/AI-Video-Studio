namespace VideoStudio.Server;

public sealed partial class GenerationQueue
{
    private async Task ExecuteMusicSynthesisAsync(IReadOnlyDictionary<string,object?> row,CancellationToken ct)
    {
        using var document=row.Json("inputJson");var root=document.RootElement;
        var parameters=root.TryGetProperty("parameters",out var p)?p:root;
        if(!OriginalMusicService.Valid(parameters)||row.Text("resourceClass")!="CPU"||row.LongOrNull("projectId") is not >0||row.LongOrNull("episodeId") is not null||row.LongOrNull("shotId") is not null)
            throw new InvalidOperationException("原创配乐任务参数或资源类别无效");
        var taskId=row.Long("id");var staged=_artifacts.CreateStagedPath(RequireWorkspace(taskId),"window_warm_piano.wav",$"task_{taskId}.wav");
        await OriginalMusicService.RenderAsync(staged,ct);
        var probe=await _ffmpeg.ProbeAsync(staged,ct);
        if(probe?.HasAudio!=true||probe.AudioDurationSeconds is not >15.4)throw new InvalidOperationException("原创配乐输出不可解码或时长不足");
        await PublishArtifactAsync(row,ArtifactPurpose.Audio,staged,"window_warm_piano.wav",ct);
    }
}
