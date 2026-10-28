using System.Globalization;

namespace VideoStudio.Server;

public sealed partial class StudioRepository
{
    public Task<List<Dictionary<string, object?>>> QaPresetsAsync(CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT * FROM qa_presets WHERE active=1 ORDER BY FIELD(name,'Draft','Standard','HighQuality'),name", cancellationToken: ct);

    public async Task<Dictionary<string, object?>?> QaPresetAsync(string name, CancellationToken ct = default)
        => (await _db.QueryAsync("SELECT * FROM qa_presets WHERE name=@name AND active=1 LIMIT 1", c => StudioDb.Add(c, "@name", name), ct)).FirstOrDefault();

    public Task<long> CreateQaRunAsync(long? episodeId, long? shotId, int version, string preset, string runType, string mode, CancellationToken ct = default)
        => _db.ExecuteInsertAsync(@"
            INSERT INTO qa_runs(episode_id,shot_id,qa_version,preset_name,run_type,mode,status,started_at)
            VALUES(@episode,@shot,@version,@preset,@type,@mode,'Running',NOW(3))", c =>
        {
            StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@shot", shotId); StudioDb.Add(c, "@version", version);
            StudioDb.Add(c, "@preset", preset); StudioDb.Add(c, "@type", runType); StudioDb.Add(c, "@mode", mode);
        }, ct);

    public Task<int> CompleteQaRunAsync(long runId, string status, decimal? score, int issueCount, string resultJson, CancellationToken ct = default)
        => _db.ExecuteAsync(@"UPDATE qa_runs SET status=@status,score=@score,issue_count=@issues,result_json=@result,finished_at=NOW(3) WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", runId); StudioDb.Add(c, "@status", status); StudioDb.Add(c, "@score", score);
            StudioDb.Add(c, "@issues", issueCount); StudioDb.Add(c, "@result", resultJson);
        }, ct);

    public Task<long> AddQaIssueAsync(long? runId, long? episodeId, long? shotId, QaIssueDraft issue, CancellationToken ct = default)
        => _db.ExecuteInsertAsync(@"
            INSERT INTO qa_issues(qa_run_id,episode_id,shot_id,issue_type,severity,description,frame_time,frame_path,status)
            VALUES(@run,@episode,@shot,@type,@severity,@description,@time,@path,'Open')", c =>
        {
            StudioDb.Add(c, "@run", runId); StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@shot", shotId);
            StudioDb.Add(c, "@type", issue.IssueType); StudioDb.Add(c, "@severity", issue.Severity); StudioDb.Add(c, "@description", issue.Description);
            StudioDb.Add(c, "@time", issue.FrameTime); StudioDb.Add(c, "@path", issue.FramePath);
        }, ct);

    public Task<List<Dictionary<string, object?>>> QaRunsAsync(long? episodeId = null, long? shotId = null, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT * FROM qa_runs WHERE (@episode IS NULL OR episode_id=@episode) AND (@shot IS NULL OR shot_id=@shot)
        ORDER BY created_at DESC", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@shot", shotId); }, ct);

    public Task<List<Dictionary<string, object?>>> QaIssuesAsync(long? episodeId = null, long? shotId = null, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT * FROM qa_issues WHERE (@episode IS NULL OR episode_id=@episode) AND (@shot IS NULL OR shot_id=@shot)
        ORDER BY FIELD(severity,'Critical','Error','Warning','Info'),created_at DESC", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@shot", shotId); }, ct);

    public Task<List<Dictionary<string, object?>>> QaEpisodesAsync(long? projectId = null, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT e.*,p.name AS project_name,
               (SELECT COUNT(*) FROM shots s WHERE s.episode_id=e.id) AS shot_count,
               (SELECT COUNT(*) FROM shots s WHERE s.episode_id=e.id AND s.qa_status='Passed') AS passed_shot_count,
               (SELECT COUNT(*) FROM shots s WHERE s.episode_id=e.id AND s.qa_status='Rejected') AS rejected_shot_count,
               (SELECT COUNT(*) FROM qa_issues q WHERE q.episode_id=e.id AND q.status='Open' AND q.severity IN ('Critical','Error')) AS blocking_issue_count
        FROM episodes e JOIN projects p ON p.id=e.project_id
        WHERE (@project IS NULL OR e.project_id=@project) ORDER BY e.episode_number,e.id", c => StudioDb.Add(c, "@project", projectId), ct);

    public Task<List<Dictionary<string, object?>>> QaShotAsync(long shotId, CancellationToken ct = default) => _db.QueryAsync(@"
        SELECT s.*,sc.name AS scene_name,
               (SELECT a.path FROM assets a WHERE a.shot_id=s.id ORDER BY a.created_at DESC LIMIT 1) AS result_path
        FROM shots s LEFT JOIN scenes sc ON sc.id=s.scene_id WHERE s.id=@id", c => StudioDb.Add(c, "@id", shotId), ct);

    public Task<int> UpdateShotQaAsync(long shotId, ShotQaEvaluation evaluation, int version, int? retryCount = null, CancellationToken ct = default)
    {
        var component = evaluation.ComponentScores;
        return _db.ExecuteAsync(@"UPDATE shots SET qa_status=@status,qa_score=@score,qa_result=@result,qa_version=@version,
            character_consistency_score=@character,motion_quality_score=@motion,temporal_stability_score=@temporal,
            semantic_match_score=@semantic,visual_quality_score=@visual,composition_score=@composition,
            scene_consistency_score=@scene,audio_score=@audio,qa_retry_count=COALESCE(@retry,qa_retry_count)
            WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@status", evaluation.Status); StudioDb.Add(c, "@score", evaluation.Score);
            StudioDb.Add(c, "@result", evaluation.ResultJson); StudioDb.Add(c, "@version", version); StudioDb.Add(c, "@retry", retryCount);
            StudioDb.Add(c, "@character", component.GetValueOrDefault("Character", 0)); StudioDb.Add(c, "@motion", component.GetValueOrDefault("Motion", 0));
            StudioDb.Add(c, "@temporal", component.GetValueOrDefault("Temporal", 0)); StudioDb.Add(c, "@semantic", component.GetValueOrDefault("Semantic", 0));
            StudioDb.Add(c, "@visual", component.GetValueOrDefault("Visual", 0)); StudioDb.Add(c, "@composition", component.GetValueOrDefault("Composition", 0));
            StudioDb.Add(c, "@scene", component.GetValueOrDefault("Scene", 0)); StudioDb.Add(c, "@audio", component.GetValueOrDefault("AudioSubtitles", 0));
        }, ct);
    }

    public Task<int> UpdateEpisodeQaAsync(long episodeId, EpisodeQaEvaluation evaluation, int version, string preset, CancellationToken ct = default)
        => _db.ExecuteAsync(@"UPDATE episodes SET qa_status=@status,overall_score=@score,qa_result=@result,qa_version=@version,qa_preset=@preset WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", episodeId); StudioDb.Add(c, "@status", evaluation.Status); StudioDb.Add(c, "@score", evaluation.Score);
            StudioDb.Add(c, "@result", evaluation.ResultJson); StudioDb.Add(c, "@version", version); StudioDb.Add(c, "@preset", preset);
        }, ct);

    public Task<int> ReviewShotQaAsync(long shotId, string decision, string? reviewer, string? note, CancellationToken ct = default)
        => _db.ExecuteAsync(@"UPDATE shots SET qa_status=@status,qa_reviewer=@reviewer,qa_review_time=NOW(3),
            qa_result=JSON_SET(COALESCE(qa_result,JSON_OBJECT()),'$.manualDecision',@decision,'$.reviewNote',COALESCE(@note,'')) WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@status", decision); StudioDb.Add(c, "@decision", decision);
            StudioDb.Add(c, "@reviewer", reviewer); StudioDb.Add(c, "@note", note);
        }, ct);

    public Task<int> ReviewEpisodeQaAsync(long episodeId, string decision, string? reviewer, string? note, CancellationToken ct = default)
        => _db.ExecuteAsync(@"UPDATE episodes SET qa_status=@status,qa_reviewer=@reviewer,qa_review_time=NOW(3),
            qa_locked=IF(@status='Approved',1,0),status=CASE WHEN @status='Approved' THEN 'Approved' WHEN @status='Rejected' THEN 'Completed' ELSE status END,
            qa_approved_at=IF(@status='Approved',NOW(3),NULL),
            qa_result=JSON_SET(COALESCE(qa_result,JSON_OBJECT()),'$.manualDecision',@status,'$.reviewNote',COALESCE(@note,'')) WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", episodeId); StudioDb.Add(c, "@status", decision); StudioDb.Add(c, "@reviewer", reviewer); StudioDb.Add(c, "@note", note);
        }, ct);

    public Task<int> UnlockEpisodeQaAsync(long episodeId, CancellationToken ct = default)
        => _db.ExecuteAsync("UPDATE episodes SET qa_locked=0,qa_status='NeedReview',status='Completed',qa_approved_at=NULL WHERE id=@id", c => StudioDb.Add(c, "@id", episodeId), ct);

    public Task<int> SetShotQaStatusAsync(long shotId, string status, CancellationToken ct = default)
        => _db.ExecuteAsync("UPDATE shots SET qa_status=@status WHERE id=@id", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@status", status); }, ct);

    public Task<int> SetEpisodeQaStatusAsync(long episodeId, string status, CancellationToken ct = default)
        => _db.ExecuteAsync("UPDATE episodes SET qa_status=@status WHERE id=@id", c => { StudioDb.Add(c, "@id", episodeId); StudioDb.Add(c, "@status", status); }, ct);

    public Task<int> ResolveQaIssueAsync(long issueId, string status, string? note, CancellationToken ct = default)
        => _db.ExecuteAsync("UPDATE qa_issues SET status=@status,resolution_note=@note,resolved_at=IF(@status IN ('Resolved','Ignored'),NOW(3),NULL) WHERE id=@id", c =>
        { StudioDb.Add(c, "@id", issueId); StudioDb.Add(c, "@status", status); StudioDb.Add(c, "@note", note); }, ct);

    public async Task<bool> IncrementQaRetryAsync(long shotId, int maxRetries, CancellationToken ct = default)
    {
        var changed = await _db.ExecuteAsync(@"UPDATE shots s JOIN episodes e ON e.id=s.episode_id
            SET s.qa_retry_count=s.qa_retry_count+1,s.qa_status='NotChecked'
            WHERE s.id=@id AND e.qa_locked=0 AND s.qa_retry_count<@max", c => { StudioDb.Add(c, "@id", shotId); StudioDb.Add(c, "@max", Math.Max(0, maxRetries)); }, ct);
        return changed > 0;
    }

    public Task<int> UpdateEpisodeReleaseAsync(long episodeId, string? masterPath, string? coverPath, string? reportPath, string? reportJsonPath, CancellationToken ct = default)
        => _db.ExecuteAsync(@"UPDATE episodes SET master_path=@master,cover_path=COALESCE(@cover,cover_path),qa_report_path=@report,qa_report_json_path=@reportJson WHERE id=@id", c =>
        {
            StudioDb.Add(c, "@id", episodeId); StudioDb.Add(c, "@master", masterPath); StudioDb.Add(c, "@cover", coverPath);
            StudioDb.Add(c, "@report", reportPath); StudioDb.Add(c, "@reportJson", reportJsonPath);
        }, ct);

    public async Task<bool> EpisodeHasOpenBlockingIssueAsync(long episodeId, CancellationToken ct = default)
        => Convert.ToInt32(await _db.ScalarAsync("SELECT COUNT(*) FROM qa_issues WHERE episode_id=@episode AND status='Open' AND severity IN ('Critical','Error')", c => StudioDb.Add(c, "@episode", episodeId), ct), CultureInfo.InvariantCulture) > 0;

    public async Task<int> OpenBlockingIssueCountAsync(long episodeId, CancellationToken ct = default)
        => Convert.ToInt32(await _db.ScalarAsync("SELECT COUNT(*) FROM qa_issues WHERE episode_id=@episode AND status='Open' AND severity IN ('Critical','Error')", c => StudioDb.Add(c, "@episode", episodeId), ct), CultureInfo.InvariantCulture);

    public async Task<bool> AllEpisodeShotsPassedAsync(long episodeId, CancellationToken ct = default)
        => Convert.ToInt32(await _db.ScalarAsync(@"SELECT CASE WHEN COUNT(*)>0 AND SUM(CASE WHEN qa_status='Passed' THEN 0 ELSE 1 END)=0 THEN 1 ELSE 0 END
            FROM shots WHERE episode_id=@episode", c => StudioDb.Add(c, "@episode", episodeId), ct), CultureInfo.InvariantCulture) == 1;
}
