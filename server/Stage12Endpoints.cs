namespace VideoStudio.Server;

public static class Stage12Endpoints
{
    public static void MapStage12Endpoints(this WebApplication app)
    {
        var group = app.MapGroup("/api/production");

        group.MapGet("/schema", async (ProductionCoreRepository repository, CancellationToken ct) =>
            Results.Ok(new { migration = Stage12SchemaMigrator.Version, ready = await repository.IsSchemaReadyAsync(ct) }));

        group.MapGet("/projects/{projectId:long}/profiles", async (long projectId, ProductionCoreRepository repository, CancellationToken ct) =>
            Results.Ok(await repository.ProfilesAsync(projectId, ct)));

        group.MapPost("/profiles", async (ProductionProfileInput input, ProductionCoreRepository repository, CancellationToken ct) =>
        {
            try
            {
                var id = await repository.CreateProfileAsync(input, ct);
                return Results.Created($"/api/production/profiles/{id}", new { id, immutable = true });
            }
            catch (Exception ex) when (ex is ArgumentException or InvalidOperationException) { return Results.BadRequest(new { error = ex.Message }); }
        });

        group.MapPost("/projects/{projectId:long}/profiles/{profileId:long}/activate", async (long projectId, long profileId, HttpContext context, ProductionCoreRepository repository, LocalAuthService auth, CancellationToken ct) =>
        {
            try
            {
                var actor = auth.CurrentPrincipal(context)?.Username ?? "administrator";
                await repository.BindProfileAsync(projectId, profileId, actor, ct);
                return Results.Ok(new { projectId, profileId, active = true });
            }
            catch (InvalidOperationException ex) { return Results.BadRequest(new { error = ex.Message }); }
        });

        group.MapGet("/projects/{projectId:long}/entity-versions", async (long projectId, string? entityType, long? entityId, ProductionCoreRepository repository, CancellationToken ct) =>
            Results.Ok(await repository.EntityVersionsAsync(projectId, entityType, entityId, ct)));

        group.MapPost("/entity-versions/capture", async (EntityVersionCaptureInput input, ProductionCoreRepository repository, CancellationToken ct) =>
        {
            try
            {
                var id = await repository.CaptureEntityVersionAsync(input, ct);
                return Results.Created($"/api/production/entity-versions/{id}", new { id, immutable = true });
            }
            catch (Exception ex) when (ex is ArgumentException or InvalidOperationException) { return Results.BadRequest(new { error = ex.Message }); }
        });

        group.MapGet("/shots/{shotId:long}/plans", async (long shotId, ProductionCoreRepository repository, CancellationToken ct) =>
            Results.Ok(await repository.ShotPlansAsync(shotId, ct)));

        group.MapPost("/shot-plans", async (ShotPlanInput input, ProductionCoreRepository repository, CancellationToken ct) =>
        {
            try
            {
                var id = await repository.CreateShotPlanAsync(input, ct);
                return Results.Created($"/api/production/shot-plans/{id}", new { id, immutable = true });
            }
            catch (Exception ex) when (ex is ArgumentException or InvalidOperationException) { return Results.BadRequest(new { error = ex.Message }); }
        });

        group.MapPost("/tasks", async (FormalTaskInput input, FormalTaskSubmissionService service, GenerationQueue queue, CancellationToken ct) =>
        {
            try
            {
                var result = await service.SubmitAsync(input, ct);
                if (result.Created) queue.Enqueue(result.TaskId);
                return Results.Json(new { id = result.TaskId, result.Created, result.IdempotencyKey, result.Fingerprint }, statusCode: result.Created ? StatusCodes.Status201Created : StatusCodes.Status200OK);
            }
            catch (IdempotencyConflictException ex) { return Results.Conflict(new { error = ex.Message }); }
            catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or AssetValidationException) { return Results.BadRequest(new { error = ex.Message }); }
        });

        group.MapGet("/tasks/{taskId:long}/attempts", async (long taskId, StudioDb db, CancellationToken ct) =>
            Results.Ok(await db.QueryAsync("SELECT id,task_id,attempt_no,worker_id,status,state_version,temp_relative_path,lease_expires_at,heartbeat_at,started_at,finished_at,failure_code,error_message,output_manifest_id FROM task_attempts WHERE task_id=@task ORDER BY attempt_no", command => StudioDb.Add(command, "@task", taskId), ct)));

        group.MapGet("/tasks/{taskId:long}/manifests", async (long taskId, StudioDb db, CancellationToken ct) =>
            Results.Ok(await db.QueryAsync("SELECT id,project_id,episode_id,shot_id,task_id,attempt_id,source_kind,production_profile_id,shot_plan_id,purpose,version,relative_path,file_name,extension,mime_type,size_bytes,sha256,status,finalized_at,created_at FROM asset_manifests WHERE task_id=@task ORDER BY purpose,version", command => StudioDb.Add(command, "@task", taskId), ct)));

        group.MapGet("/projects/{projectId:long}/assets/{assetId:long}", async (long projectId, long assetId, string? purpose, AssetReferenceResolver resolver, CancellationToken ct) =>
        {
            try
            {
                var purposes = string.IsNullOrWhiteSpace(purpose) ? Enum.GetValues<ArtifactPurpose>()
                    : Enum.TryParse<ArtifactPurpose>(purpose, true, out var parsed) ? [parsed] : [];
                if (purposes.Length == 0) return Results.BadRequest(new { error = "Unknown asset purpose" });
                var asset = await resolver.ResolveAsync(assetId, projectId, purposes, ct);
                return Results.Ok(new { asset.AssetId, asset.ProjectId, asset.EpisodeId, asset.ShotId, asset.Purpose, asset.RelativePath, asset.Extension, asset.Status, asset.ManifestId, mediaUrl = $"/api/production/projects/{projectId}/assets/{assetId}/media" });
            }
            catch (AssetValidationException ex) { return Results.BadRequest(new { error = ex.Message }); }
        });

        group.MapGet("/projects/{projectId:long}/assets/{assetId:long}/media", async (long projectId, long assetId, AssetReferenceResolver resolver, CancellationToken ct) =>
        {
            try
            {
                var asset = await resolver.ResolveAsync(assetId, projectId, Enum.GetValues<ArtifactPurpose>(), ct);
                return Results.File(asset.FullPath, ContentType(asset.Extension), enableRangeProcessing: true);
            }
            catch (AssetValidationException) { return Results.NotFound(); }
        });
    }

    private static string ContentType(string extension) => extension.ToLowerInvariant() switch
    {
        ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp", ".mp4" => "video/mp4",
        ".wav" => "audio/wav", ".mp3" => "audio/mpeg", ".ogg" => "audio/ogg", ".flac" => "audio/flac", ".srt" => "application/x-subrip",
        ".vtt" => "text/vtt", ".json" => "application/json", ".md" => "text/markdown", _ => "application/octet-stream"
    };
}
