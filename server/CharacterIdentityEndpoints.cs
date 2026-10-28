using System.Text.Json;

namespace VideoStudio.Server;

public sealed class MotionRouteInput
{
    public string? Action { get; set; }
    public string? Description { get; set; }
    public string? Dialogue { get; set; }
    public string? Narration { get; set; }
    public string? CameraMotion { get; set; }
    public string? MotionPreset { get; set; }
    public int ReferenceCount { get; set; }
    public bool ReferenceRequired { get; set; }
}

public sealed class ReferenceSelectInput
{
    public ReferenceSelectorRequest Request { get; set; } = new();
    public List<GoldenReference> References { get; set; } = [];
}

public sealed class CharacterReferenceReviewInput
{
    public string Decision { get; set; } = "NeedReview";
    public string? Reviewer { get; set; }
    public string? Note { get; set; }
}

public static class CharacterIdentityEndpoints
{
    public static void Map(WebApplication app)
    {
        app.MapPost("/api/quality/character/evaluate", async (CharacterQaBatchInput input, CharacterQualityService quality, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.MasterPath) || input.Candidates.Count == 0)
                return Results.BadRequest(new { error = "MasterPath 和至少一个候选图不能为空" });
            var results = await quality.EvaluateBatchAsync(input, ct);
            var pack = CharacterQualityService.BuildGoldenPack("api-input", input.MasterPath, input.IdentityThreshold, results);
            return Results.Ok(new
            {
                embeddingModel = pack.EmbeddingModel,
                scoreRange = pack.ScoreRange,
                identityThreshold = pack.IdentityThreshold,
                results,
                goldenPack = pack
            });
        });

        app.MapPost("/api/quality/character/golden-pack", async (CharacterQaBatchInput input, CharacterQualityService quality, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.MasterPath)) return Results.BadRequest(new { error = "MasterPath 不能为空" });
            var results = await quality.EvaluateBatchAsync(input, ct);
            var pack = CharacterQualityService.BuildGoldenPack("api-input", input.MasterPath, input.IdentityThreshold, results);
            return Results.Ok(pack);
        });

        app.MapPost("/api/quality/reference/select", (ReferenceSelectInput input) =>
            Results.Ok(ReferenceSelectorV2.Select(input.Request, input.References)));

        app.MapGet("/api/characters/{id:long}/references", async (long id, StudioRepository repository, AssetPathPolicy paths, CancellationToken ct) =>
        {
            if ((await repository.QueryCharacterAsync(id, ct)).FirstOrDefault() is null) return Results.NotFound(new { error = "角色不存在" });
            var references = await repository.CharacterReferencesAsync(id, ct);
            return Results.Ok(references.Select(reference =>
            {
                var available = paths.TryResolveExisting(reference.Text("path"), out _, out var assetPath);
                var reviewStatus = "NeedReview";
                var assetVersion = 0;
                string? assetSha256 = null;
                string? reviewer = null;
                var stage = ReferenceMetadata.DefaultStage;
                var role = reference.Text("kind") ?? ReferenceMetadata.DefaultRole;
                string? changeReason = null;
                try
                {
                    var metadata = ReferenceMetadata.Read(reference.Text("metadataJson"), role);
                    reviewStatus = metadata.ReviewStatus; assetVersion = metadata.AssetVersion; assetSha256 = metadata.Sha256; reviewer = metadata.Reviewer;
                    stage = metadata.Stage; role = metadata.Role; changeReason = metadata.ChangeReason;
                }
                catch { }
                return new
                {
                    id = reference.Long("id"),
                    characterId = id,
                    kind = reference.Text("kind"),
                    isAnchor = reference.Bool("isAnchor"),
                    width = reference.Int("width"),
                    height = reference.Int("height"),
                    reviewStatus,
                    assetVersion,
                    assetSha256,
                    reviewer,
                    stage,
                    role,
                    changeReason,
                    available,
                    assetPath = available ? assetPath : null,
                    mediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(assetPath)}" : null,
                    createdAt = reference["createdAt"]
                };
            }));
        });

        app.MapPost("/api/characters/{id:long}/references/{referenceId:long}/review", async (long id, long referenceId, CharacterReferenceReviewInput input, HttpContext context, LocalAuthService auth, StudioRepository repository, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var decision = input.Decision is "Approved" or "Rejected" or "NeedReview" ? input.Decision : null;
            if (decision is null) return Results.BadRequest(new { error = "角色参考图审核决定必须是 Approved、Rejected 或 NeedReview" });
            var principal = auth.CurrentPrincipal(context);
            if (principal is null) return Results.Unauthorized();
            var reference = (await repository.CharacterReferencesAsync(id, ct)).FirstOrDefault(row => row.Long("id") == referenceId);
            if (reference is null) return Results.NotFound(new { error = "角色参考图不存在" });
            if (!paths.TryResolveExisting(reference.Text("path"), out _, out _))
                return Results.UnprocessableEntity(new { error = "角色参考图不存在或不在受控媒体目录，不能写入批准记录" });
            try
            {
                var updated = await repository.ReviewCharacterReferenceAsync(id, referenceId, decision, principal.Username, input.Note, ct);
                return updated == 0 ? Results.NotFound(new { error = "角色参考图不存在" }) : Results.Ok(new { updated, status = decision, reviewer = principal.Username, manualReviewRequired = decision != "Approved" });
            }
            catch (MySqlConnector.MySqlException ex) when (ex.Number == 1146)
            {
                return Results.Json(new{error="素材审核日志表缺失；请管理员执行迁移011_character_reference_review_audit.sql（补齐009已定义表）。审核已回滚，未更新素材状态",code="REFERENCE_REVIEW_MIGRATION_REQUIRED"},statusCode:503);
            }
        });

        app.MapPost("/api/motion/analyze", (JsonElement input) =>
        {
            var action = ReadString(input, "action") ?? ReadString(input, "description") ?? ReadString(input, "prompt") ?? "";
            return Results.Ok(MotionComplexityAnalyzer.Analyze(action));
        });

        app.MapPost("/api/motion/route", (MotionRouteInput input, ModelRouter router) =>
        {
            var shot = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
            {
                ["action"] = input.Action,
                ["description"] = input.Description,
                ["dialogue"] = input.Dialogue,
                ["narration"] = input.Narration,
                ["cameraMotion"] = input.CameraMotion,
                ["motionPreset"] = input.MotionPreset,
                ["referenceRequired"] = input.ReferenceRequired
            };
            return Results.Ok(router.Resolve(shot, Math.Max(0, input.ReferenceCount)));
        });

        app.MapGet("/api/quality/character/capabilities", () => Results.Ok(new
        {
            embeddingModel = "UNAVAILABLE",
            landmarkModel = "UNAVAILABLE",
            faceDetector = "UNAVAILABLE",
            proxyDetector = "cpu-raster-symmetry-proxy",
            scoreRange = "0..1",
            identityThreshold = .85,
            keyViewThreshold = .90,
            humanReviewRequired = true,
            loraStatus = "BLOCKED_DATASET_QUALITY until Golden Pack passes"
        }));
    }

    private static string? ReadString(JsonElement input, string name)
        => input.ValueKind == JsonValueKind.Object && input.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
}
