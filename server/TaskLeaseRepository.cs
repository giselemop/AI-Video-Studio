using System.Data;
using System.Globalization;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// The only worker-facing task transition gateway for the stage 1/2 schema.
/// Every running-state mutation is fenced by task id, attempt id and a random
/// lease token. Cancellation is serialized on the same task row lock.
/// </summary>
public sealed class TaskLeaseRepository
{
    private readonly StudioSettings _settings;

    public TaskLeaseRepository(StudioSettings settings) => _settings = settings;

    public async Task<TaskLease?> ClaimAsync(long taskId, string workerId, TimeSpan lease, TimeSpan? deadline = null, CancellationToken ct = default)
    {
        if (taskId <= 0) throw new ArgumentOutOfRangeException(nameof(taskId));
        if (string.IsNullOrWhiteSpace(workerId)) throw new ArgumentException("Worker id is required", nameof(workerId));
        var leaseSeconds = Math.Max(1, (int)Math.Ceiling(lease.TotalSeconds));
        var deadlineSeconds = deadline is { } value ? Math.Max(1, (int)Math.Ceiling(value.TotalSeconds)) : (int?)null;
        var token = Guid.NewGuid().ToString();

        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            var row = await ReadTaskForUpdateAsync(connection, transaction, taskId, ct);
            if (row is null || !string.Equals(row.Status, "Pending", StringComparison.OrdinalIgnoreCase) || row.Paused) return null;
            TaskStateMachine.Require(TaskStateMachine.Parse(row.Status), TaskLifecycleState.Running);

            var attemptNo = row.Attempts + 1;
            var stateVersion = row.StateVersion + 1;
            var tempRelativePath = $"Temp/Tasks/task-{taskId}/attempt-{attemptNo}-{token[..8]}";
            long attemptId;
            await using (var insert = new MySqlCommand(@"INSERT INTO task_attempts(task_id,attempt_no,lease_token,worker_id,status,state_version,temp_relative_path,lease_expires_at,heartbeat_at)
                VALUES(@task,@attempt,@token,@worker,'Running',@version,@temp,DATE_ADD(NOW(3), INTERVAL @lease SECOND),NOW(3))", connection, transaction))
            {
                Add(insert, "@task", taskId); Add(insert, "@attempt", attemptNo); Add(insert, "@token", token); Add(insert, "@worker", NormalizeWorker(workerId));
                Add(insert, "@version", stateVersion); Add(insert, "@temp", tempRelativePath); Add(insert, "@lease", leaseSeconds);
                await insert.ExecuteNonQueryAsync(ct);
                attemptId = insert.LastInsertedId;
            }

            await using (var update = new MySqlCommand(@"UPDATE generation_tasks SET status='Running',attempts=@attempt,state_version=@version,
                active_attempt_id=@attempt_id,lease_token=@token,lease_owner=@worker,
                lease_expires_at=DATE_ADD(NOW(3), INTERVAL @lease SECOND),heartbeat_at=NOW(3),
                deadline_at=IF(@deadline IS NULL,NULL,DATE_ADD(NOW(3), INTERVAL @deadline SECOND)),timed_out_at=NULL,
                started_at=NOW(3),finished_at=NULL,progress=0,error_message=NULL,cancel_requested_at=NULL,output_manifest_id=NULL
                WHERE id=@task AND status='Pending' AND paused=0 AND state_version=@old_version", connection, transaction))
            {
                Add(update, "@attempt", attemptNo); Add(update, "@version", stateVersion); Add(update, "@attempt_id", attemptId);
                Add(update, "@token", token); Add(update, "@worker", NormalizeWorker(workerId)); Add(update, "@lease", leaseSeconds);
                Add(update, "@deadline", deadlineSeconds); Add(update, "@task", taskId); Add(update, "@old_version", row.StateVersion);
                if (await update.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Task changed while it was being claimed");
            }
            await AddEventAsync(connection, transaction, taskId, attemptId, token, "Pending", "Running", "queue", workerId, "task claimed", stateVersion, null, ct);
            await transaction.CommitAsync(ct);
            return new TaskLease(taskId, attemptId, attemptNo, stateVersion, NormalizeWorker(workerId), token, tempRelativePath);
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    public Task<int> HeartbeatAsync(TaskLease lease, TimeSpan duration, CancellationToken ct = default)
        => ExecuteFencedPairAsync(lease,
            "UPDATE generation_tasks SET lease_expires_at=DATE_ADD(NOW(3), INTERVAL @seconds SECOND),heartbeat_at=NOW(3) WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker",
            "UPDATE task_attempts SET lease_expires_at=DATE_ADD(NOW(3), INTERVAL @seconds SECOND),heartbeat_at=NOW(3) WHERE id=@attempt AND task_id=@task AND status='Running' AND lease_token=@token AND worker_id=@worker",
            command => Add(command, "@seconds", Math.Max(1, (int)Math.Ceiling(duration.TotalSeconds))), ct);

    public Task<int> UpdateProgressAsync(TaskLease lease, decimal progress, CancellationToken ct = default)
        => ExecuteFencedTaskAsync(lease, "UPDATE generation_tasks SET progress=@progress WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker",
            command => Add(command, "@progress", Math.Clamp(progress, 0, 0.99m)), ct);

    public Task<int> UpdatePromptAsync(TaskLease lease, string promptId, CancellationToken ct = default)
        => ExecuteFencedTaskAsync(lease, "UPDATE generation_tasks SET comfy_prompt_id=@prompt WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker",
            command => Add(command, "@prompt", promptId), ct);

    public Task<int> UpdateGpuAsync(TaskLease lease, GpuSnapshot? gpu, long peak, CancellationToken ct = default)
        => ExecuteFencedTaskAsync(lease, "UPDATE generation_tasks SET gpu_name=@name,vram_free_mib=@free,vram_peak_mib=@peak,gpu_utilization=@util WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker", command =>
        {
            Add(command, "@name", gpu?.Name); Add(command, "@free", gpu?.FreeMiB); Add(command, "@peak", peak); Add(command, "@util", gpu?.UtilizationPercent);
        }, ct);

    public Task<int> SetErrorAsync(TaskLease lease, string code, string message, CancellationToken ct = default)
        => ExecuteFencedTaskAsync(lease, "UPDATE generation_tasks SET failure_code=@code,error_type=@code,error_message=@message WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker", command =>
        {
            Add(command, "@code", NormalizeCode(code)); Add(command, "@message", Limit(message, 3000));
        }, ct);

    public Task<int> UpdateInputAsync(TaskLease lease, string inputJson, CancellationToken ct = default)
        => ExecuteFencedTaskAsync(lease, "UPDATE generation_tasks SET input_json=@input WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker",
            command => Add(command, "@input", inputJson), ct);

    public Task<int> CompleteAsync(TaskLease lease, string terminalStatus, string? error = null, long? manifestId = null, CancellationToken ct = default)
    {
        var target = TaskStateMachine.Parse(terminalStatus);
        if (target is not (TaskLifecycleState.Succeeded or TaskLifecycleState.Failed or TaskLifecycleState.Cancelled))
            throw new ArgumentOutOfRangeException(nameof(terminalStatus), "Only terminal states are allowed");
        TaskStateMachine.Require(TaskLifecycleState.Running, target);
        return TransitionRunningAsync(lease, target.ToString(), error, null, manifestId, ct);
    }

    public Task<int> TimeoutAsync(TaskLease lease, string message, CancellationToken ct = default)
        => TransitionRunningAsync(lease, "Failed", message, "TASK_TIMEOUT", null, ct, timedOut: true);

    public Task<int> RequeueAsync(TaskLease lease, string failureCode, string message, CancellationToken ct = default)
    {
        TaskStateMachine.Require(TaskLifecycleState.Running, TaskLifecycleState.Pending);
        return TransitionRunningAsync(lease, "Pending", message, failureCode, null, ct);
    }

    public async Task<int> CancelAsync(long taskId, string reason, string actor = "user", CancellationToken ct = default)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            var row = await ReadTaskForUpdateAsync(connection, transaction, taskId, ct);
            if (row is null || row.Status is not ("Pending" or "Running")) return 0;
            TaskStateMachine.Require(TaskStateMachine.Parse(row.Status), TaskLifecycleState.Cancelled);
            var nextVersion = row.StateVersion + 1;
            await using var update = new MySqlCommand(@"UPDATE generation_tasks SET status='Cancelled',cancel_requested_at=NOW(3),state_version=@version,
                error_message=@reason,finished_at=NOW(3),duration_ms=IF(started_at IS NULL,NULL,TIMESTAMPDIFF(MICROSECOND,started_at,NOW(3))/1000),
                lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,lease_token=NULL,active_attempt_id=NULL WHERE id=@task AND state_version=@old_version", connection, transaction);
            Add(update, "@version", nextVersion); Add(update, "@reason", Limit(reason, 3000)); Add(update, "@task", taskId); Add(update, "@old_version", row.StateVersion);
            if (await update.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Task changed while cancellation was being applied");
            if (row.ActiveAttemptId is { } attemptId)
            {
                await using var abandon = new MySqlCommand("UPDATE task_attempts SET status='Cancelled',finished_at=NOW(3),error_message=@reason WHERE id=@attempt AND status='Running'", connection, transaction);
                Add(abandon, "@reason", Limit(reason, 3000)); Add(abandon, "@attempt", attemptId); await abandon.ExecuteNonQueryAsync(ct);
                await FinalizeArtifactsAsync(connection, transaction, attemptId, false, null, ct);
            }
            await AddEventAsync(connection, transaction, taskId, row.ActiveAttemptId, row.LeaseToken, row.Status, "Cancelled", actor, row.WorkerId, reason, nextVersion, null, ct);
            await transaction.CommitAsync(ct);
            return 1;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    public async Task<int> FailPendingAsync(long taskId, string errorCode, string message, CancellationToken ct = default)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            var row = await ReadTaskForUpdateAsync(connection, transaction, taskId, ct);
            if (row is null || row.Status != "Pending") return 0;
            TaskStateMachine.Require(TaskLifecycleState.Pending, TaskLifecycleState.Failed);
            var nextVersion = row.StateVersion + 1;
            await using var update = new MySqlCommand(@"UPDATE generation_tasks SET status='Failed',failure_code=@code,error_type=@code,error_message=@message,
                state_version=@version,finished_at=NOW(3) WHERE id=@task AND status='Pending' AND state_version=@old_version", connection, transaction);
            Add(update, "@code", NormalizeCode(errorCode)); Add(update, "@message", Limit(message, 3000)); Add(update, "@version", nextVersion); Add(update, "@task", taskId); Add(update, "@old_version", row.StateVersion);
            if (await update.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Pending task changed before failure transition");
            await AddEventAsync(connection, transaction, taskId, null, null, "Pending", "Failed", "queue", null, message, nextVersion, null, ct);
            await transaction.CommitAsync(ct);
            return 1;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    public async Task<int> RetryAsync(long taskId, string actor = "user", CancellationToken ct = default)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            var row = await ReadTaskForUpdateAsync(connection, transaction, taskId, ct);
            if (row is null || row.Status is not ("Failed" or "Cancelled")) return 0;
            // max_retries is the number of retry cycles after the first
            // attempt. Once attempts is greater than that budget, a manual
            // retry must not reopen the task indefinitely.
            if (row.Attempts > row.MaxRetries) return 0;
            TaskStateMachine.Require(TaskStateMachine.Parse(row.Status), TaskLifecycleState.Pending);
            var nextVersion = row.StateVersion + 1;
            await using var update = new MySqlCommand(@"UPDATE generation_tasks SET status='Pending',error_message=NULL,failure_code=NULL,error_type='UNKNOWN',
                cancel_requested_at=NULL,progress=0,queued_at=NOW(3),finished_at=NULL,lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                lease_token=NULL,active_attempt_id=NULL,output_manifest_id=NULL,state_version=@version
                WHERE id=@task AND status IN ('Failed','Cancelled') AND state_version=@old_version", connection, transaction);
            Add(update, "@task", taskId); Add(update, "@old_version", row.StateVersion); Add(update, "@version", nextVersion);
            if (await update.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Task changed before retry transition");
            await AddEventAsync(connection, transaction, taskId, null, null, row.Status, "Pending", actor, null, "task retry requested", nextVersion, null, ct);
            await transaction.CommitAsync(ct);
            return 1;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    public async Task<int> RecoverExpiredAsync(CancellationToken ct = default, bool characterStoryOnly = false)
    {
        var recovered = 0;
        while (true)
        {
            await using var connection = await OpenAsync(ct);
            await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
            try
            {
                TaskRow? row;
                await using (var select = new MySqlCommand(@"SELECT id,status,attempts,max_retries,state_version,paused,active_attempt_id,lease_token,lease_owner
                    FROM generation_tasks WHERE status='Running' AND lease_expires_at<NOW(3)
                    AND (@story_only=0 OR JSON_CONTAINS_PATH(input_json,'one','$.parameters.storyPipeline','$.parameters.characterWorkbench','$.parameters.storyPreview'))
                    ORDER BY lease_expires_at,id LIMIT 1 FOR UPDATE SKIP LOCKED", connection, transaction))
                {
                    Add(select,"@story_only",characterStoryOnly?1:0);
                    await using var reader = await select.ExecuteReaderAsync(ct);
                    row = await reader.ReadAsync(ct) ? ReadTaskRow(reader) : null;
                }
                if (row is null)
                {
                    await transaction.CommitAsync(ct);
                    return recovered;
                }
                TaskStateMachine.Require(TaskLifecycleState.Running, TaskLifecycleState.Pending);
                var nextVersion = row.StateVersion + 1;
                await using var update = new MySqlCommand(@"UPDATE generation_tasks SET status='Pending',failure_code='LEASE_EXPIRED',error_type='LEASE_EXPIRED',
                    error_message='task lease expired',state_version=@version,queued_at=NOW(3),lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,lease_token=NULL,active_attempt_id=NULL
                    WHERE id=@task AND status='Running' AND state_version=@old_version", connection, transaction);
                Add(update, "@version", nextVersion); Add(update, "@task", row.Id); Add(update, "@old_version", row.StateVersion);
                if (await update.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Expired task changed during recovery");
                if (row.ActiveAttemptId is { } attemptId)
                {
                    await using var abandon = new MySqlCommand("UPDATE task_attempts SET status='Abandoned',finished_at=NOW(3),failure_code='LEASE_EXPIRED',error_message='task lease expired' WHERE id=@attempt AND status='Running'", connection, transaction);
                    Add(abandon, "@attempt", attemptId); await abandon.ExecuteNonQueryAsync(ct);
                    await FinalizeArtifactsAsync(connection, transaction, attemptId, false, null, ct);
                }
                await AddEventAsync(connection, transaction, row.Id, row.ActiveAttemptId, row.LeaseToken, "Running", "Pending", "recovery", row.WorkerId, "task lease expired", nextVersion, null, ct);
                await transaction.CommitAsync(ct);
                recovered++;
            }
            catch
            {
                await transaction.RollbackAsync(CancellationToken.None);
                throw;
            }
        }
    }

    private async Task<int> TransitionRunningAsync(TaskLease lease, string target, string? message, string? failureCode, long? manifestId, CancellationToken ct, bool timedOut = false)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            var row = await ReadTaskForUpdateAsync(connection, transaction, lease.TaskId, ct);
            if (!Matches(row, lease)) return 0;
            TaskStateMachine.Require(TaskLifecycleState.Running, TaskStateMachine.Parse(target));
            var nextVersion = row!.StateVersion + 1;
            var isPending = target == "Pending";
            var attemptStatus = target switch { "Pending" => "Failed", _ => target };
            await FinalizeArtifactsAsync(connection, transaction, lease.AttemptId, target == "Succeeded", manifestId, ct);
            await using (var update = new MySqlCommand(@"UPDATE generation_tasks SET status=@target,failure_code=@code,error_type=COALESCE(@code,error_type),error_message=@message,
                progress=IF(@target='Succeeded',1,progress),state_version=@version,queued_at=IF(@target='Pending',NOW(3),queued_at),
                finished_at=IF(@target='Pending',NULL,NOW(3)),duration_ms=IF(@target='Pending',NULL,TIMESTAMPDIFF(MICROSECOND,started_at,NOW(3))/1000),
                timed_out_at=IF(@timed_out=1,NOW(3),timed_out_at),output_manifest_id=COALESCE(@manifest,output_manifest_id),
                lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,lease_token=NULL,active_attempt_id=NULL
                WHERE id=@task AND status='Running' AND active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker AND state_version=@old_version", connection, transaction))
            {
                Add(update, "@target", target); Add(update, "@code", failureCode is null ? null : NormalizeCode(failureCode)); Add(update, "@message", message is null ? null : Limit(message, 3000));
                Add(update, "@version", nextVersion); Add(update, "@timed_out", timedOut); Add(update, "@manifest", manifestId); BindLease(update, lease); Add(update, "@old_version", row.StateVersion);
                if (await update.ExecuteNonQueryAsync(ct) != 1) return 0;
            }
            await using (var attempt = new MySqlCommand(@"UPDATE task_attempts SET status=@status,finished_at=NOW(3),failure_code=@code,error_message=@message,output_manifest_id=COALESCE(@manifest,output_manifest_id)
                WHERE id=@attempt AND task_id=@task AND status='Running' AND lease_token=@token AND worker_id=@worker", connection, transaction))
            {
                Add(attempt, "@status", attemptStatus); Add(attempt, "@code", failureCode is null ? null : NormalizeCode(failureCode)); Add(attempt, "@message", message is null ? null : Limit(message, 3000)); Add(attempt, "@manifest", manifestId); BindLease(attempt, lease);
                if (await attempt.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Attempt changed before task transition completed");
            }
            await AddEventAsync(connection, transaction, lease.TaskId, lease.AttemptId, lease.LeaseToken, "Running", target, "queue", lease.WorkerId, message, nextVersion, manifestId, ct);
            await transaction.CommitAsync(ct);
            return 1;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    private async Task<int> ExecuteFencedTaskAsync(TaskLease lease, string sql, Action<MySqlCommand>? bind, CancellationToken ct)
    {
        await using var connection = await OpenAsync(ct);
        await using var command = new MySqlCommand(sql, connection);
        BindLease(command, lease); bind?.Invoke(command);
        return await command.ExecuteNonQueryAsync(ct);
    }

    private async Task<int> ExecuteFencedPairAsync(TaskLease lease, string taskSql, string attemptSql, Action<MySqlCommand>? bind, CancellationToken ct)
    {
        await using var connection = await OpenAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        try
        {
            await using var task = new MySqlCommand(taskSql, connection, transaction); BindLease(task, lease); bind?.Invoke(task);
            var changed = await task.ExecuteNonQueryAsync(ct);
            if (changed != 1) { await transaction.RollbackAsync(ct); return 0; }
            await using var attempt = new MySqlCommand(attemptSql, connection, transaction); BindLease(attempt, lease); bind?.Invoke(attempt);
            if (await attempt.ExecuteNonQueryAsync(ct) != 1) throw new DBConcurrencyException("Attempt heartbeat fencing failed");
            await transaction.CommitAsync(ct);
            return 1;
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    private async Task<MySqlConnection> OpenAsync(CancellationToken ct)
    {
        var connection = new MySqlConnection(_settings.DatabaseConnectionString);
        await connection.OpenAsync(ct);
        return connection;
    }

    private static async Task<TaskRow?> ReadTaskForUpdateAsync(MySqlConnection connection, MySqlTransaction transaction, long taskId, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT id,status,attempts,max_retries,state_version,paused,active_attempt_id,lease_token,lease_owner
            FROM generation_tasks WHERE id=@task FOR UPDATE", connection, transaction);
        Add(command, "@task", taskId);
        await using var reader = await command.ExecuteReaderAsync(ct);
        return await reader.ReadAsync(ct) ? ReadTaskRow(reader) : null;
    }

    private static TaskRow ReadTaskRow(MySqlDataReader reader) => new(
        reader.GetInt64("id"), Convert.ToString(reader.GetValue(reader.GetOrdinal("status")), CultureInfo.InvariantCulture) ?? "", reader.GetInt32("attempts"), reader.GetInt32("max_retries"), reader.GetInt32("state_version"), reader.GetBoolean("paused"),
        reader.IsDBNull("active_attempt_id") ? null : reader.GetInt64("active_attempt_id"),
        reader.IsDBNull("lease_token") ? null : Convert.ToString(reader.GetValue(reader.GetOrdinal("lease_token")), CultureInfo.InvariantCulture),
        reader.IsDBNull("lease_owner") ? null : Convert.ToString(reader.GetValue(reader.GetOrdinal("lease_owner")), CultureInfo.InvariantCulture));

    private static bool Matches(TaskRow? row, TaskLease lease)
        => row is not null && row.Status == "Running" && row.ActiveAttemptId == lease.AttemptId
            && string.Equals(row.LeaseToken, lease.LeaseToken, StringComparison.Ordinal)
            && string.Equals(row.WorkerId, lease.WorkerId, StringComparison.Ordinal);

    private static async Task AddEventAsync(MySqlConnection connection, MySqlTransaction transaction, long taskId, long? attemptId, string? leaseToken,
        string? from, string to, string actor, string? worker, string? reason, int stateVersion, long? manifestId, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"INSERT INTO task_events(task_id,attempt_id,lease_token,from_status,to_status,actor,worker,reason,state_version,output_manifest_id)
            VALUES(@task,@attempt,@token,@from,@to,@actor,@worker,@reason,@version,@manifest)", connection, transaction);
        Add(command, "@task", taskId); Add(command, "@attempt", attemptId); Add(command, "@token", leaseToken); Add(command, "@from", from); Add(command, "@to", to);
        Add(command, "@actor", Limit(actor, 64)); Add(command, "@worker", worker is null ? null : NormalizeWorker(worker)); Add(command, "@reason", reason is null ? null : Limit(reason, 3000)); Add(command, "@version", stateVersion); Add(command, "@manifest", manifestId);
        await command.ExecuteNonQueryAsync(ct);
    }

    private static async Task FinalizeArtifactsAsync(MySqlConnection connection, MySqlTransaction transaction, long attemptId, bool succeeded, long? primaryManifestId, CancellationToken ct)
    {
        if (succeeded)
        {
            await using (var countCommand = new MySqlCommand("SELECT COUNT(*) FROM asset_manifests WHERE attempt_id=@attempt AND status='Staged'", connection, transaction))
            {
                Add(countCommand, "@attempt", attemptId);
                var staged = Convert.ToInt32(await countCommand.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture);
                if (staged > 0 && primaryManifestId is null) throw new InvalidOperationException("A primary manifest is required when an attempt produced artifacts");
            }
            if (primaryManifestId is { } manifestId)
            {
                await using var primary = new MySqlCommand("SELECT COUNT(*) FROM asset_manifests WHERE id=@manifest AND attempt_id=@attempt AND status='Staged'", connection, transaction);
                Add(primary, "@manifest", manifestId); Add(primary, "@attempt", attemptId);
                if (Convert.ToInt32(await primary.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture) != 1)
                    throw new InvalidOperationException("Primary manifest is missing, stale, or belongs to another attempt");
            }
            await ExecuteArtifactUpdateAsync(connection, transaction, "UPDATE asset_manifests SET status='Ready',finalized_at=NOW(3) WHERE attempt_id=@attempt AND status='Staged'", attemptId, ct);
            await ExecuteArtifactUpdateAsync(connection, transaction, "UPDATE assets SET status='Ready' WHERE source_attempt_id=@attempt AND status='Staged'", attemptId, ct);
            await ExecuteArtifactUpdateAsync(connection, transaction, "UPDATE artifact_publish_intents SET status='Ready',finalized_at=NOW(3) WHERE attempt_id=@attempt AND status='Staging' AND manifest_id IS NOT NULL", attemptId, ct);
            return;
        }

        await ExecuteArtifactUpdateAsync(connection, transaction, "UPDATE asset_manifests SET status='Quarantined',finalized_at=NOW(3) WHERE attempt_id=@attempt AND status='Staged'", attemptId, ct);
        await ExecuteArtifactUpdateAsync(connection, transaction, "UPDATE assets SET status='Quarantined' WHERE source_attempt_id=@attempt AND status='Staged'", attemptId, ct);
        await ExecuteArtifactUpdateAsync(connection, transaction, "UPDATE artifact_publish_intents SET status=IF(manifest_id IS NULL,'NeedsReconcile','Rejected'),finalized_at=NOW(3),error_message=COALESCE(error_message,'attempt did not succeed') WHERE attempt_id=@attempt AND status='Staging'", attemptId, ct);
    }

    private static async Task ExecuteArtifactUpdateAsync(MySqlConnection connection, MySqlTransaction transaction, string sql, long attemptId, CancellationToken ct)
    {
        await using var command = new MySqlCommand(sql, connection, transaction);
        Add(command, "@attempt", attemptId);
        await command.ExecuteNonQueryAsync(ct);
    }

    private static void BindLease(MySqlCommand command, TaskLease lease)
    {
        Add(command, "@task", lease.TaskId); Add(command, "@attempt", lease.AttemptId); Add(command, "@token", lease.LeaseToken); Add(command, "@worker", lease.WorkerId);
    }

    private static void Add(MySqlCommand command, string name, object? value) => command.Parameters.AddWithValue(name, value ?? DBNull.Value);
    private static string NormalizeWorker(string value) => Limit(value.Trim(), 128);
    private static string NormalizeCode(string value) => new string(value.Trim().ToUpperInvariant().Where(character => char.IsLetterOrDigit(character) || character == '_').Take(64).ToArray()) is { Length: > 0 } code ? code : "UNKNOWN";
    private static string Limit(string value, int length) => value.Length <= length ? value : value[..length];

    private sealed record TaskRow(long Id, string Status, int Attempts, int MaxRetries, int StateVersion, bool Paused, long? ActiveAttemptId, string? LeaseToken, string? WorkerId);
}
