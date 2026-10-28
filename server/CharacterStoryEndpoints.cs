namespace VideoStudio.Server;

public static class CharacterStoryEndpoints
{
    static string Actor(LocalAuthService auth,HttpContext context)=>auth.CurrentPrincipal(context)?.Username??throw new UnauthorizedAccessException("需要本机操作员或登录身份");
    static async Task<IResult> Execute(Func<Task<object>> action)
    {
        try{return Results.Ok(await action());}
        catch(IdempotencyConflictException ex){return Results.Conflict(new{error=ex.Message});}
        catch(MySqlConnector.MySqlException ex) when(ex.Number is 3819 or 1142){return Results.Json(new{error="数据库迁移010未完成或账号权限不足；未提交生成任务。请管理员执行010_character_story_records.sql",code="STORY_MIGRATION_REQUIRED"},statusCode:503);}
        catch(Exception ex)when(ex is ArgumentException or InvalidOperationException or System.Text.Json.JsonException or KeyNotFoundException){return Results.UnprocessableEntity(new{error=ex.Message});}
    }
    public static void Map(WebApplication app)
    {
        var g=app.MapGroup("/api/character-story");
        g.MapGet("/capabilities",()=>Results.Ok(CharacterStoryService.Capabilities));
        g.MapGet("/readiness",(CharacterStoryService s,CancellationToken ct)=>Execute(()=>s.ReadinessAsync(ct)));
        g.MapGet("/scenes",(long? projectId,CharacterSceneService s,CancellationToken ct)=>Execute(()=>s.ListAsync(projectId,ct)));
        g.MapPost("/scenes/{id:long}/capture",(long id,SceneCaptureInput input,CharacterSceneService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.CaptureAsync(id,input,Actor(auth,ctx),ct)));
        g.MapPost("/preview",(StoryPreviewInput input,CharacterStoryService s,StudioRepository repository,TaskSubmissionPreflightService preflight,GenerationQueue queue,CancellationToken ct)=>Execute(async()=>{var task=await s.BuildPreviewAsync(input,ct);var check=await preflight.CheckAsync(task,ct,businessSubmission:true);if(!check.Passed)throw new AssetValidationException(string.Join("；",check.Issues));var existing=await repository.TaskByIdempotencyKeyAsync(input.IdempotencyKey,ct);var id=await repository.CreateTaskAsync(task,ct);if(existing is null)queue.Enqueue(id);return new{id,created=existing is null,contentReview="NeedReview",publication="Blocked"};}));
        g.MapGet("/library-reviews",(CharacterStoryService s,CancellationToken ct)=>Execute(async()=>await s.LibraryReviewStatesAsync(ct)));
        g.MapPost("/versions/{id:long}/review",(long id,StoryReviewInput input,CharacterStoryService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.ReviewVersionAsync(id,input,Actor(auth,ctx),ct)));
        g.MapGet("/projects/{id:long}/cast",(long id,long? episodeId,CharacterStoryService s,CancellationToken ct)=>Execute(async()=>await s.CastStateAsync(id,episodeId,ct)));
        g.MapPost("/projects/{id:long}/cast",(long id,StoryCastInput input,CharacterStoryService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.SaveProjectCastAsync(id,input,Actor(auth,ctx),ct)));
        g.MapPost("/episodes/{id:long}/cast",(long id,StoryCastInput input,CharacterStoryService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.SnapshotEpisodeAsync(id,input.IdempotencyKey,Actor(auth,ctx),ct)));
        g.MapGet("/shots/{id:long}",(long id,CharacterStoryService s,CancellationToken ct)=>Execute(async()=>await s.ShotStateAsync(id,ct)));
        g.MapPost("/shots/{id:long}",(long id,StoryShotInput input,CharacterStoryService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.SaveShotAsync(id,input,Actor(auth,ctx),ct)));
        g.MapPost("/resolve/{kind}",(string kind,StoryRenderInput input,CharacterStoryService s,CancellationToken ct)=>Execute(async()=>new{task=await s.BuildAsync(kind,input,ct),mode="ReviewPreview",contentReview="NeedReview",publication="Blocked"}));
        g.MapPost("/generate/{kind}",(string kind,StoryRenderInput input,CharacterStoryService s,TaskSubmissionPreflightService preflight,GenerationQueue queue,CancellationToken ct)=>Execute(()=>s.SubmitAsync(kind,input,preflight,queue,ct)));
        g.MapPost("/inspect",(StoryReviewInput input,CharacterStoryService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.ReviewTaskAsync(input,Actor(auth,ctx),ct)));
        var w=app.MapGroup("/api/character-workshop");
        w.MapGet("/prompt-policy",()=>Results.Ok(CharacterReferencePrompts.Policy()));
        w.MapGet("",(CharacterWorkshopService s,CancellationToken ct)=>Execute(()=>s.SummariesAsync(ct)));
        w.MapGet("/{id:long}",(long id,CharacterWorkshopService s,CancellationToken ct)=>Execute(()=>s.StateAsync(id,ct)));
        w.MapPost("/{id:long}/anchors",(long id,WorkshopAnchorInput input,CharacterWorkshopService s,LocalAuthService auth,HttpContext ctx,CancellationToken ct)=>Execute(async()=>await s.AnchorsAsync(id,input,Actor(auth,ctx),ct)));
        w.MapPost("/{id:long}/collect",(long id,WorkshopCollectInput input,CharacterWorkshopService s,CancellationToken ct)=>Execute(()=>s.CollectAsync(id,input,ct)));
        w.MapPost("/resolve",(WorkshopGenerateInput input,CharacterWorkshopService s,CancellationToken ct)=>Execute(async()=>new{task=await s.BuildAsync(input,ct),contentReview="NeedReview"}));
        w.MapPost("/generate",(WorkshopGenerateInput input,CharacterWorkshopService s,TaskSubmissionPreflightService preflight,GenerationQueue queue,CancellationToken ct)=>Execute(()=>s.SubmitAsync(input,preflight,queue,ct)));
    }
}
