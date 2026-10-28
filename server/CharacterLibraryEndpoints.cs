namespace VideoStudio.Server;

public static class CharacterLibraryEndpoints
{
    public static void Map(WebApplication app)
    {
        var group = app.MapGroup("/api/character-library");
        group.MapGet("/history", async (CharacterLibraryService library, CancellationToken ct) => Results.Ok(await library.HistoryAsync(ct)));
        group.MapGet("", async (CharacterLibraryService library, CancellationToken ct) =>
        {
            var versions = await library.ListAsync(ct);
            return Results.Ok(new
            {
                versions, views = CharacterLibraryService.Views, framings = CharacterLibraryService.Framings,
                coverage = versions.Select(v => new { versionId = v.Id, coverage = CharacterLibraryService.Coverage(v.Payload.References) }),
                basicSlots = CharacterLibraryService.BasicSlots, viewConvention = CharacterLibraryService.ViewConvention,
                mode = "Experimental", contentReview = "NeedReview", automaticPublication = false
            });
        });
        group.MapPost("/{characterId:long}/versions", async (long characterId, LibraryVersionInput input, CharacterLibraryService library,
            LocalAuthService auth, HttpContext context, CancellationToken ct) =>
        {
            try { return Results.Ok(await library.CaptureAsync(characterId, input, auth.CurrentPrincipal(context)?.Username ?? "local-operator", ct)); }
            catch (Exception ex) when (ex is ArgumentException or AssetValidationException) { return Results.UnprocessableEntity(new { error = ex.Message }); }
        });
        group.MapPost("/resolve", async (LibraryGenerateInput input, CharacterLibraryService library, CancellationToken ct) =>
        {
            try
            {
                var resolved = await library.ResolveAsync(input, ct);
                return Results.Ok(new { version = resolved.Version, binding = resolved.Binding, resolvedPrompt = resolved.ResolvedPrompt,
                    task = resolved.Task, contentReview = "NeedReview", publication = "Blocked" });
            }
            catch (Exception ex) when (ex is ArgumentException or AssetValidationException or InvalidOperationException)
            { return Results.UnprocessableEntity(new { error = ex.Message }); }
        });
        group.MapPost("/generate", async (LibraryGenerateInput input, CharacterLibraryService library, StudioRepository repository,
            TaskSubmissionPreflightService preflight, GenerationQueue queue, CancellationToken ct) =>
        {
            try
            {
                if (string.IsNullOrWhiteSpace(input.IdempotencyKey) || input.IdempotencyKey.Length is < 8 or > 128 || input.IdempotencyKey.Any(char.IsControl))
                    return Results.UnprocessableEntity(new { error = "请提供8–128字符的请求标识；网络重试必须复用原标识" });
                var resolved = await library.ResolveAsync(input, ct);
                var check = await preflight.CheckAsync(resolved.Task, ct);
                if (!check.Passed) return Results.UnprocessableEntity(new { error = "人物库视频预检未通过", preflight = check });
                var existing = await repository.TaskByIdempotencyKeyAsync(input.IdempotencyKey, ct);
                var id = await repository.CreateTaskAsync(resolved.Task, ct);
                queue.Enqueue(id);
                return Results.Ok(new { id, created = existing is null, binding = resolved.Binding, contentReview = "NeedReview", publication = "Blocked" });
            }
            catch (IdempotencyConflictException ex) { return Results.Conflict(new { error = ex.Message }); }
            catch (Exception ex) when (ex is ArgumentException or AssetValidationException or InvalidOperationException)
            { return Results.UnprocessableEntity(new { error = ex.Message }); }
        });
    }
}
