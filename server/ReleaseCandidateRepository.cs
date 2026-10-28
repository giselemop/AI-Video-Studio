using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MySqlConnector;

namespace VideoStudio.Server;

public sealed class ReleaseCandidateRepository
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };
    private readonly StudioDb _db;

    public ReleaseCandidateRepository(StudioDb db) => _db = db;

    public async Task<ReleaseCandidatePackage> CreateAsync(long projectId, long episodeId, ReleaseEligibilityResult eligibility, ReleaseCandidateInput input, string? idempotencyKey = null, CancellationToken ct = default)
    {
        var normalizedKey = Limit(idempotencyKey, 128);
        var requestFingerprint = Fingerprint(eligibility, input);
        if (ReleaseEligibilityService.IsSha256ForExport(eligibility.SourceManifestSha256))
            await ExpireReadyForDifferentSourceAsync(episodeId, eligibility.SourceManifestSha256, "同一 Episode 的来源快照已变化，旧候选自动失效", ct);
        if (normalizedKey is not null)
        {
            var existing = await FindByIdempotencyKeyAsync(episodeId, normalizedKey, ct);
            if (existing is not null) return EnsureSameRequest(existing, requestFingerprint, eligibility.SourceManifestSha256);
        }
        if (eligibility.CanCreateCandidate)
        {
            var existingReady = await FindReadyBySourceHashAsync(episodeId, eligibility.SourceManifestSha256, ct);
            if (existingReady is not null) return EnsureSameRequest(existingReady, requestFingerprint, eligibility.SourceManifestSha256);
        }

        MySqlException? lastConflict = null;
        for (var attempt = 1; attempt <= 4; attempt++)
        {
            var version = Convert.ToInt32(await _db.ScalarAsync("SELECT COALESCE(MAX(version),0)+1 FROM release_candidate_packages WHERE episode_id=@episode", c => StudioDb.Add(c, "@episode", episodeId), ct));
            try
            {
                var source = JsonSerializer.Serialize(eligibility.SourceManifest);
                var license = JsonSerializer.Serialize(eligibility.LicenseEvidence);
                var disclosure = JsonSerializer.Serialize(eligibility.AiDisclosure);
                var id = await _db.ExecuteInsertAsync(@"
                    INSERT INTO release_candidate_packages(project_id,episode_id,version,status,technical_status,content_status,release_eligibility,source_manifest_json,source_manifest_sha256,license_evidence_json,ai_disclosure_json,reviewer,note,idempotency_key)
                    VALUES(@project,@episode,@version,@status,@technical,@content,@eligibility,@source,@source_hash,@license,@disclosure,@reviewer,@note,@idempotency)",
                    c =>
                    {
                        StudioDb.Add(c, "@project", projectId); StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@version", version);
                        StudioDb.Add(c, "@status", eligibility.CanCreateCandidate ? "Ready" : "Blocked");
                        StudioDb.Add(c, "@technical", eligibility.TechnicalStatus); StudioDb.Add(c, "@content", eligibility.ContentStatus);
                        StudioDb.Add(c, "@eligibility", eligibility.ReleaseEligibility); StudioDb.Add(c, "@source", source); StudioDb.Add(c, "@source_hash", eligibility.SourceManifestSha256);
                        StudioDb.Add(c, "@license", license); StudioDb.Add(c, "@disclosure", disclosure);
                        StudioDb.Add(c, "@reviewer", Limit(input.Reviewer, 128)); StudioDb.Add(c, "@note", Limit(input.Note, 1000)); StudioDb.Add(c, "@idempotency", normalizedKey);
                    }, ct);
                return await GetAsync(id, episodeId, ct) ?? throw new InvalidOperationException("候选包已写入但无法重新读取");
            }
            catch (MySqlException ex) when (ex.Number == 1062)
            {
                lastConflict = ex;
                if (normalizedKey is not null)
                {
                    var existing = await FindByIdempotencyKeyAsync(episodeId, normalizedKey, ct);
                    if (existing is not null) return EnsureSameRequest(existing, requestFingerprint, eligibility.SourceManifestSha256);
                }
                if (eligibility.CanCreateCandidate)
                {
                    var existingReady = await FindReadyBySourceHashAsync(episodeId, eligibility.SourceManifestSha256, ct);
                    if (existingReady is not null) return EnsureSameRequest(existingReady, requestFingerprint, eligibility.SourceManifestSha256);
                }
                if (attempt < 4) await Task.Delay(TimeSpan.FromMilliseconds(25 * attempt), ct);
            }
        }
        if (lastConflict is not null) throw lastConflict;
        throw new InvalidOperationException("候选包版本分配冲突，重试后仍未成功");
    }

    public Task<int> ExpireReadyForDifferentSourceAsync(long episodeId, string currentSourceHash, string reason, CancellationToken ct = default)
        => _db.ExecuteAsync(@"
            UPDATE release_candidate_packages
            SET status='Expired',release_eligibility='Expired',expired_at=NOW(3),expired_reason=@reason
            WHERE episode_id=@episode AND status='Ready' AND source_manifest_sha256<>@source_hash",
            c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@source_hash", currentSourceHash); StudioDb.Add(c, "@reason", Limit(reason, 1000)); }, ct);

    public async Task<ReleaseCandidatePackage?> GetAsync(long candidateId, long? episodeId = null, CancellationToken ct = default)
    {
        var rows = await _db.QueryAsync(@"
            SELECT id,project_id,episode_id,version,status,technical_status,content_status,release_eligibility,source_manifest_json,source_manifest_sha256,license_evidence_json,ai_disclosure_json,reviewer,note,created_at,idempotency_key,export_task_id,expired_at,expired_reason
            FROM release_candidate_packages WHERE id=@id AND (@episode IS NULL OR episode_id=@episode) LIMIT 1", c => { StudioDb.Add(c, "@id", candidateId); StudioDb.Add(c, "@episode", episodeId); }, ct);
        return rows.Count == 0 ? null : Parse(rows[0]);
    }

    public Task<List<Dictionary<string, object?>>> ListAsync(long episodeId, CancellationToken ct = default)
        => _db.QueryAsync(@"
            SELECT id,project_id,episode_id,version,status,technical_status,content_status,release_eligibility,source_manifest_json,source_manifest_sha256,license_evidence_json,ai_disclosure_json,reviewer,note,created_at,idempotency_key,export_task_id,expired_at,expired_reason
            FROM release_candidate_packages WHERE episode_id=@episode ORDER BY version DESC", c => StudioDb.Add(c, "@episode", episodeId), ct);

    public Task<int> MarkExpiredAsync(long candidateId, string reason, CancellationToken ct = default)
        => _db.ExecuteAsync(@"
            UPDATE release_candidate_packages
            SET status='Expired',release_eligibility='Expired',expired_at=NOW(3),expired_reason=@reason
            WHERE id=@id AND status='Ready'", c => { StudioDb.Add(c, "@id", candidateId); StudioDb.Add(c, "@reason", Limit(reason, 1000)); }, ct);

    public async Task<bool> MarkExportTaskAsync(long candidateId, long taskId, CancellationToken ct = default)
    {
        var updated = await _db.ExecuteAsync("UPDATE release_candidate_packages SET export_task_id=@task WHERE id=@id AND status='Ready' AND (export_task_id IS NULL OR export_task_id=@task)", c => { StudioDb.Add(c, "@id", candidateId); StudioDb.Add(c, "@task", taskId); }, ct);
        if (updated > 0) return true;
        var current = await GetAsync(candidateId, null, ct);
        return current is not null && string.Equals(current.Status, "Ready", StringComparison.OrdinalIgnoreCase) && current.ExportTaskId == taskId;
    }

    private async Task<ReleaseCandidatePackage?> FindByIdempotencyKeyAsync(long episodeId, string key, CancellationToken ct)
    {
        var rows = await _db.QueryAsync(@"
            SELECT id,project_id,episode_id,version,status,technical_status,content_status,release_eligibility,source_manifest_json,source_manifest_sha256,license_evidence_json,ai_disclosure_json,reviewer,note,created_at,idempotency_key,export_task_id,expired_at,expired_reason
            FROM release_candidate_packages WHERE episode_id=@episode AND idempotency_key=@key LIMIT 1", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@key", key); }, ct);
        return rows.Count == 0 ? null : Parse(rows[0]);
    }

    private async Task<ReleaseCandidatePackage?> FindReadyBySourceHashAsync(long episodeId, string sourceHash, CancellationToken ct)
    {
        var rows = await _db.QueryAsync(@"
            SELECT id,project_id,episode_id,version,status,technical_status,content_status,release_eligibility,source_manifest_json,source_manifest_sha256,license_evidence_json,ai_disclosure_json,reviewer,note,created_at,idempotency_key,export_task_id,expired_at,expired_reason
            FROM release_candidate_packages
            WHERE episode_id=@episode AND status='Ready' AND release_eligibility='Ready' AND source_manifest_sha256=@source_hash
            ORDER BY version DESC LIMIT 1", c => { StudioDb.Add(c, "@episode", episodeId); StudioDb.Add(c, "@source_hash", sourceHash); }, ct);
        return rows.Count == 0 ? null : Parse(rows[0]);
    }

    private static ReleaseCandidatePackage EnsureSameRequest(ReleaseCandidatePackage existing, string requestFingerprint, string sourceHash)
    {
        var storedFingerprint = Fingerprint(existing);
        if (!string.Equals(existing.SourceManifestSha256, sourceHash, StringComparison.OrdinalIgnoreCase) || !string.Equals(storedFingerprint, requestFingerprint, StringComparison.OrdinalIgnoreCase))
            throw new IdempotencyConflictException("相同幂等键对应了不同的发布候选来源或证据");
        return existing;
    }

    private static ReleaseCandidatePackage Parse(IReadOnlyDictionary<string, object?> row)
    {
        var sourceJson = row.Text("sourceManifestJson") ?? "{}";
        var source = JsonSerializer.Deserialize<ReleaseSourceManifest>(sourceJson, JsonOptions) ?? new ReleaseSourceManifest();
        var sourceHash = row.Text("sourceManifestSha256");
        sourceHash = string.IsNullOrWhiteSpace(sourceHash) ? ReleaseEligibilityService.ComputeSourceManifestSha256(source) : sourceHash;
        var license = JsonSerializer.Deserialize<ReleaseLicenseEvidence>(row.Text("licenseEvidenceJson") ?? "{}", JsonOptions) ?? new ReleaseLicenseEvidence();
        var disclosure = JsonSerializer.Deserialize<ReleaseAiDisclosure>(row.Text("aiDisclosureJson") ?? "{}", JsonOptions) ?? new ReleaseAiDisclosure();
        return new ReleaseCandidatePackage(
            row.Long("id"), row.Long("projectId"), row.Long("episodeId"), row.Int("version"), row.Text("status") ?? "",
            row.Text("technicalStatus") ?? "", row.Text("contentStatus") ?? "", row.Text("releaseEligibility") ?? "",
            source, sourceHash, license, disclosure, row.Text("reviewer"), row.Text("note"), ToDateTime(row["createdAt"]),
            row.Text("idempotencyKey"), row.LongOrNull("exportTaskId"), ToDateTime(row["expiredAt"]), row.Text("expiredReason"));
    }

    private static string Fingerprint(ReleaseEligibilityResult eligibility, ReleaseCandidateInput input)
        => Fingerprint(JsonSerializer.Serialize(new { eligibility.SourceManifestSha256, eligibility.LicenseEvidence, eligibility.AiDisclosure, input.Reviewer, input.Note }));

    private static string Fingerprint(ReleaseCandidatePackage candidate)
        => Fingerprint(JsonSerializer.Serialize(new { candidate.SourceManifestSha256, candidate.LicenseEvidence, candidate.AiDisclosure, candidate.Reviewer, candidate.Note }));

    private static string Fingerprint(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static DateTime? ToDateTime(object? value)
        => value is DateTime dateTime ? dateTime : DateTime.TryParse(Convert.ToString(value), out var parsed) ? parsed : null;

    private static string? Limit(string? value, int max)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim().Length <= max ? value.Trim() : value.Trim()[..max];
}
