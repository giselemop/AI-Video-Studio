using System.Data;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Formal production tasks accept immutable version ids and Asset ids only.
/// Raw filesystem paths remain a legacy UI compatibility surface and cannot
/// enter this service.
/// </summary>
public sealed class FormalTaskSubmissionService
{
    private static readonly HashSet<string> AllowedTaskTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "Image", "Keyframe", "ImageToVideo", "Video", "Enhance", "VideoEnhancement",
        "Audio", "TTS", "Subtitles", "EpisodeRender", "Concat", "VideoConcat",
        "ShotQA", "EpisodeQA", "QAExport"
    };

    private readonly StudioSettings _settings;
    private readonly AssetReferenceResolver _assets;
    private readonly StudioDb _db;
    private readonly WorkflowContractService _contracts;

    public FormalTaskSubmissionService(StudioSettings settings, AssetReferenceResolver assets, StudioDb db, WorkflowContractService contracts)
    {
        _settings = settings; _assets = assets; _db = db; _contracts = contracts;
    }

    public async Task<FormalTaskSubmission> SubmitAsync(FormalTaskInput input, CancellationToken ct = default)
    {
        var projectId = input.ProjectId ?? throw new ArgumentException("ProjectId is required", nameof(input));
        if (projectId <= 0 || input.ProductionProfileId <= 0) throw new ArgumentException("ProjectId and ProductionProfileId are required", nameof(input));
        var taskType = input.TaskType?.Trim() ?? "";
        if (!AllowedTaskTypes.Contains(taskType)) throw new ArgumentException("Unsupported formal task type", nameof(input));
        if (!string.IsNullOrWhiteSpace(input.InputImagePath)) throw new AssetValidationException("Formal tasks reject raw InputImagePath; submit InputAssetId instead");
        var idempotencyKey = NormalizeIdempotencyKey(input.IdempotencyKey);
        var parameters = input.Parameters is { ValueKind: JsonValueKind.Object } suppliedParameters
            ? suppliedParameters
            : JsonSerializer.SerializeToElement(new { });
        var slotAssetIds = ReadSlotAssetIds(parameters);
        var allAssets = input.InputAssetIds.Concat(input.InputAssetId is { } primary ? [primary] : []).Concat(slotAssetIds).Where(id => id > 0).Distinct().ToArray();
        var allowedPurposes = AllowedInputPurposes(taskType);
        foreach (var assetId in allAssets) await _assets.ResolveAsync(assetId, projectId, allowedPurposes, ct);
        if (IsComfyTask(taskType))
        {
            var workflowPath = await ResolveWorkflowPathAsync(input.WorkflowId, ct);
            var requestedVersion = ReadString(parameters, "workflowVersion");
            if (workflowPath is null && string.IsNullOrWhiteSpace(requestedVersion))
                throw new WorkflowContractException("WORKFLOW_REQUIRED", "正式 ComfyUI 任务必须声明 WorkflowId 或 workflowVersion");
            var contract = _contracts.Find(workflowPath, requestedVersion);
            if (contract is null)
                throw new WorkflowContractException("WORKFLOW_UNCONTRACTED", "正式任务的工作流没有匹配到已审查契约");
            _contracts.Prepare(workflowPath ?? contract.FileName, taskType, parameters, requireProductionRoute: true);
        }

        var payload = CanonicalJson.Serialize(new
        {
            projectId,
            input.EpisodeId,
            input.ShotId,
            taskType,
            input.ProductionProfileId,
            input.ShotPlanId,
            input.InputAssetId,
            inputAssetIds = allAssets,
            input.WorkflowId,
            loraIds = input.LoraIds?.Distinct().Order().ToArray(),
            outputName = input.OutputName is null ? null : Path.GetFileName(input.OutputName),
            parameters,
            resourceClass = NormalizeResource(input.ResourceClass),
            input.Stage,
            input.DependencyTaskId,
            input.ProductionRunId
        });
        var fingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(payload))).ToLowerInvariant();

        await using var connection = new MySqlConnection(_settings.DatabaseConnectionString);
        await connection.OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            await ValidateOwnershipAsync(connection, transaction, input, projectId, ct);
            var existing = await ExistingAsync(connection, transaction, idempotencyKey, ct);
            if (existing is not null)
            {
                if (!string.Equals(existing.Value.Fingerprint, fingerprint, StringComparison.OrdinalIgnoreCase))
                    throw new IdempotencyConflictException("The idempotency key already belongs to a different formal task payload");
                await transaction.CommitAsync(ct);
                return new FormalTaskSubmission(existing.Value.Id, false, idempotencyKey, fingerprint);
            }

            long taskId;
            await using (var command = new MySqlCommand(@"INSERT INTO generation_tasks(project_id,episode_id,shot_id,production_run_id,task_type,status,priority,max_retries,workflow_id,input_json,
                resource_class,stage,dependency_task_id,request_id,idempotency_key,input_fingerprint,production_profile_id,shot_plan_id,input_asset_id,queued_at)
                VALUES(@project,@episode,@shot,@run,@type,'Pending',@priority,@retries,@workflow,@input,@resource,@stage,@dependency,@request,@key,@fingerprint,@profile,@plan,@asset,NOW(3))", connection, transaction))
            {
                Add(command, "@project", projectId); Add(command, "@episode", input.EpisodeId); Add(command, "@shot", input.ShotId); Add(command, "@run", input.ProductionRunId);
                Add(command, "@type", taskType); Add(command, "@priority", input.Priority); Add(command, "@retries", Math.Clamp(input.MaxRetries, 0, 5)); Add(command, "@workflow", input.WorkflowId);
                Add(command, "@input", payload); Add(command, "@resource", NormalizeResource(input.ResourceClass)); Add(command, "@stage", Limit(input.Stage, 64)); Add(command, "@dependency", input.DependencyTaskId);
                Add(command, "@request", Limit(input.RequestId, 128)); Add(command, "@key", idempotencyKey); Add(command, "@fingerprint", fingerprint); Add(command, "@profile", input.ProductionProfileId);
                Add(command, "@plan", input.ShotPlanId); Add(command, "@asset", input.InputAssetId);
                try
                {
                    await command.ExecuteNonQueryAsync(ct);
                    taskId = command.LastInsertedId;
                }
                catch (MySqlException ex) when (ex.Number == 1062)
                {
                    var raced = await ExistingAsync(connection, transaction, idempotencyKey, ct);
                    if (raced is null || !string.Equals(raced.Value.Fingerprint, fingerprint, StringComparison.OrdinalIgnoreCase))
                        throw new IdempotencyConflictException("Concurrent submission reused the idempotency key with a different payload");
                    await transaction.CommitAsync(ct);
                    return new FormalTaskSubmission(raced.Value.Id, false, idempotencyKey, fingerprint);
                }
            }
            if (input.DependencyTaskId is { } dependency)
            {
                await using var dependencyCommand = new MySqlCommand("INSERT IGNORE INTO task_dependencies(task_id,depends_on_task_id) VALUES(@task,@dependency)", connection, transaction);
                Add(dependencyCommand, "@task", taskId); Add(dependencyCommand, "@dependency", dependency); await dependencyCommand.ExecuteNonQueryAsync(ct);
            }
            await transaction.CommitAsync(ct);
            return new FormalTaskSubmission(taskId, true, idempotencyKey, fingerprint);
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    private async Task<string?> ResolveWorkflowPathAsync(long? workflowId, CancellationToken ct)
    {
        if (workflowId is null) return null;
        var row = (await _db.QueryAsync("SELECT path FROM workflows WHERE id=@id LIMIT 1", c => StudioDb.Add(c, "@id", workflowId), ct)).FirstOrDefault();
        if (row is null || string.IsNullOrWhiteSpace(row.Text("path")))
            throw new WorkflowContractException("WORKFLOW_RECORD_MISSING", $"WorkflowId {workflowId} 未登记或没有文件路径");
        return row.Text("path");
    }

    private static bool IsComfyTask(string taskType)
        => taskType.Equals("Image", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Keyframe", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase)
            || taskType.Equals("Video", StringComparison.OrdinalIgnoreCase);

    private static IEnumerable<long> ReadSlotAssetIds(JsonElement parameters)
    {
        if (parameters.ValueKind != JsonValueKind.Object || !parameters.TryGetProperty("inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object) yield break;
        foreach (var property in slots.EnumerateObject())
        {
            if (property.Value.ValueKind == JsonValueKind.Number && property.Value.TryGetInt64(out var direct))
            {
                yield return direct;
                continue;
            }
            if (property.Value.ValueKind == JsonValueKind.Object && property.Value.TryGetProperty("assetId", out var asset) && asset.TryGetInt64(out var id))
                yield return id;
        }
    }

    private static string? ReadString(JsonElement root, string name)
        => root.ValueKind == JsonValueKind.Object && root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static async Task ValidateOwnershipAsync(MySqlConnection connection, MySqlTransaction transaction, FormalTaskInput input, long projectId, CancellationToken ct)
    {
        await RequireScalarAsync(connection, transaction, "SELECT COUNT(*) FROM production_profiles WHERE id=@id AND project_id=@project", input.ProductionProfileId, projectId, "ProductionProfile does not belong to the project", ct);
        if (input.EpisodeId is { } episodeId)
            await RequireScalarAsync(connection, transaction, "SELECT COUNT(*) FROM episodes WHERE id=@id AND project_id=@project", episodeId, projectId, "Episode does not belong to the project", ct);
        if (input.ShotId is { } shotId)
        {
            await RequireScalarAsync(connection, transaction, "SELECT COUNT(*) FROM shots WHERE id=@id AND project_id=@project", shotId, projectId, "Shot does not belong to the project", ct);
            if (input.ShotPlanId is null) throw new InvalidOperationException("Shot tasks require an immutable ShotPlanId");
        }
        if (input.ShotPlanId is { } planId)
        {
            await using var plan = new MySqlCommand(@"SELECT COUNT(*) FROM shot_plans WHERE id=@id AND project_id=@project AND production_profile_id=@profile
                AND (@episode IS NULL OR episode_id=@episode) AND (@shot IS NULL OR shot_id=@shot)", connection, transaction);
            Add(plan, "@id", planId); Add(plan, "@project", projectId); Add(plan, "@profile", input.ProductionProfileId); Add(plan, "@episode", input.EpisodeId); Add(plan, "@shot", input.ShotId);
            if (Convert.ToInt32(await plan.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture) != 1)
                throw new InvalidOperationException("ShotPlan ownership/profile/shot binding does not match the task");
        }
    }

    private static async Task RequireScalarAsync(MySqlConnection connection, MySqlTransaction transaction, string sql, long id, long projectId, string error, CancellationToken ct)
    {
        await using var command = new MySqlCommand(sql, connection, transaction);
        Add(command, "@id", id); Add(command, "@project", projectId);
        if (Convert.ToInt32(await command.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture) != 1) throw new InvalidOperationException(error);
    }

    private static async Task<(long Id, string Fingerprint)?> ExistingAsync(MySqlConnection connection, MySqlTransaction transaction, string key, CancellationToken ct)
    {
        await using var command = new MySqlCommand("SELECT id,input_fingerprint FROM generation_tasks WHERE idempotency_key=@key LIMIT 1", connection, transaction);
        Add(command, "@key", key);
        await using var reader = await command.ExecuteReaderAsync(ct);
        return await reader.ReadAsync(ct) ? (reader.GetInt64(0), reader.IsDBNull(1) ? "" : reader.GetString(1)) : null;
    }

    private static ArtifactPurpose[] AllowedInputPurposes(string taskType)
        => taskType.ToLowerInvariant() switch
        {
            "image" or "keyframe" or "imagetovideo" => [ArtifactPurpose.Image, ArtifactPurpose.Cover],
            "enhance" or "videoenhancement" or "shotqa" => [ArtifactPurpose.Video],
            "episoderender" or "concat" or "videoconcat" or "episodeqa" or "qaexport" => [ArtifactPurpose.Video, ArtifactPurpose.Episode, ArtifactPurpose.EpisodePreview],
            "audio" or "tts" or "subtitles" => [],
            _ => []
        };

    private static string NormalizeIdempotencyKey(string? value)
    {
        var key = value?.Trim() ?? "";
        if (key.Length is < 8 or > 128 || key.Any(character => char.IsControl(character)))
            throw new ArgumentException("Formal IdempotencyKey must contain 8-128 printable characters", nameof(value));
        return key;
    }

    private static string NormalizeResource(string? value)
        => string.Equals(value, "CPU", StringComparison.OrdinalIgnoreCase) ? "CPU" : "GPU";

    private static string? Limit(string? value, int max) => string.IsNullOrWhiteSpace(value) ? null : value.Trim().Length <= max ? value.Trim() : value.Trim()[..max];
    private static void Add(MySqlCommand command, string name, object? value) => command.Parameters.AddWithValue(name, value ?? DBNull.Value);
}
