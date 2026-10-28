using System.Text.Json;

namespace VideoStudio.Server;

public sealed partial class StudioRepository
{
    public Task<List<Dictionary<string, object?>>> QualityRepairRunsAsync(long? shotId = null, CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM quality_repair_runs WHERE (@shot IS NULL OR shot_id=@shot) ORDER BY created_at DESC,id DESC", c => StudioDb.Add(c, "@shot", shotId), ct);

    public Task<List<Dictionary<string, object?>>> QualityExperimentsAsync(CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM quality_experiments ORDER BY updated_at DESC,id DESC", cancellationToken: ct);

    public Task<long> CreateQualityExperimentAsync(QualityExperimentInput input, CancellationToken ct = default)
        => _db.ExecuteInsertAsync(@"
            INSERT INTO quality_experiments(name,experiment_type,baseline_id,controlled_variable,status,description)
            VALUES(@name,@type,@baseline,@variable,@status,@description)
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id),experiment_type=VALUES(experiment_type),baseline_id=VALUES(baseline_id),controlled_variable=VALUES(controlled_variable),status=VALUES(status),description=VALUES(description)", c =>
        {
            StudioDb.Add(c, "@name", input.Name.Trim());
            StudioDb.Add(c, "@type", input.ExperimentType);
            StudioDb.Add(c, "@baseline", input.BaselineId);
            StudioDb.Add(c, "@variable", input.ControlledVariable);
            StudioDb.Add(c, "@status", input.Status);
            StudioDb.Add(c, "@description", input.Description);
        }, ct);

    public Task<List<Dictionary<string, object?>>> QualityExperimentRunsAsync(long experimentId, CancellationToken ct = default)
        => _db.QueryAsync("SELECT r.*,t.status AS task_status,t.duration_ms,t.vram_peak_mib,t.vram_free_mib,t.error_type FROM quality_experiment_runs r LEFT JOIN generation_tasks t ON t.id=r.task_id WHERE r.experiment_id=@experiment ORDER BY r.created_at,r.id", c => StudioDb.Add(c, "@experiment", experimentId), ct);

    public Task<long> AddQualityExperimentRunAsync(long experimentId, QualityExperimentRunInput input, CancellationToken ct = default)
        => _db.ExecuteInsertAsync(@"
            INSERT INTO quality_experiment_runs(experiment_id,test_case,task_id,parent_task_id,workflow_version,model_name,status,parameters_json,metrics_json,human_rating,notes)
            VALUES(@experiment,@case,@task,@parent,@workflow,@model,@status,@parameters,@metrics,@rating,@notes)", c =>
        {
            StudioDb.Add(c, "@experiment", experimentId);
            StudioDb.Add(c, "@case", input.TestCase.Trim());
            StudioDb.Add(c, "@task", input.TaskId);
            StudioDb.Add(c, "@parent", input.ParentTaskId);
            StudioDb.Add(c, "@workflow", input.WorkflowVersion);
            StudioDb.Add(c, "@model", input.ModelName);
            StudioDb.Add(c, "@status", input.Status);
            StudioDb.Add(c, "@parameters", StudioDb.JsonOrNull(input.Parameters));
            StudioDb.Add(c, "@metrics", StudioDb.JsonOrNull(input.Metrics));
            StudioDb.Add(c, "@rating", input.HumanRating is null ? null : Math.Clamp(input.HumanRating.Value, 0, 100));
            StudioDb.Add(c, "@notes", input.Notes);
        }, ct);

    public Task<List<Dictionary<string, object?>>> QualityGoldenSamplesAsync(CancellationToken ct = default)
        => _db.QueryAsync("SELECT * FROM quality_golden_samples WHERE is_active=1 ORDER BY sample_type,sample_key", cancellationToken: ct);

    public Task<long> UpsertQualityGoldenSampleAsync(QualityGoldenSampleInput input, CancellationToken ct = default)
        => _db.ExecuteInsertAsync(@"
            INSERT INTO quality_golden_samples(sample_key,sample_type,path,task_id,quality_score,metadata_json,is_active)
            VALUES(@key,@type,@path,@task,@score,@metadata,@active)
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id),sample_type=VALUES(sample_type),path=VALUES(path),task_id=VALUES(task_id),quality_score=VALUES(quality_score),metadata_json=VALUES(metadata_json),is_active=VALUES(is_active)", c =>
        {
            StudioDb.Add(c, "@key", input.SampleKey.Trim());
            StudioDb.Add(c, "@type", input.SampleType);
            StudioDb.Add(c, "@path", input.Path);
            StudioDb.Add(c, "@task", input.TaskId);
            StudioDb.Add(c, "@score", input.QualityScore);
            StudioDb.Add(c, "@metadata", StudioDb.JsonOrNull(input.Metadata));
            StudioDb.Add(c, "@active", input.IsActive);
        }, ct);

    public Task<long> AddQualityRepairRunAsync(long? shotId, long? sourceTaskId, long? retryTaskId, string issueCode, string strategy, JsonElement? changedParameters, string? resultStatus = null, JsonElement? metrics = null, CancellationToken ct = default)
        => _db.ExecuteInsertAsync(@"
            INSERT INTO quality_repair_runs(shot_id,source_task_id,retry_task_id,issue_code,strategy,changed_parameters_json,result_status,metrics_json)
            VALUES(@shot,@source,@retry,@issue,@strategy,@changed,@status,@metrics)", c =>
        {
            StudioDb.Add(c, "@shot", shotId);
            StudioDb.Add(c, "@source", sourceTaskId);
            StudioDb.Add(c, "@retry", retryTaskId);
            StudioDb.Add(c, "@issue", issueCode);
            StudioDb.Add(c, "@strategy", strategy);
            StudioDb.Add(c, "@changed", StudioDb.JsonOrNull(changedParameters));
            StudioDb.Add(c, "@status", resultStatus);
            StudioDb.Add(c, "@metrics", StudioDb.JsonOrNull(metrics));
        }, ct);

    public Task<int> UpdateQualityRepairRunAsync(long retryTaskId, string resultStatus, JsonElement? metrics = null, CancellationToken ct = default)
        => _db.ExecuteAsync("UPDATE quality_repair_runs SET result_status=@status,metrics_json=@metrics WHERE retry_task_id=@task", c => { StudioDb.Add(c, "@task", retryTaskId); StudioDb.Add(c, "@status", resultStatus); StudioDb.Add(c, "@metrics", StudioDb.JsonOrNull(metrics)); }, ct);
}
