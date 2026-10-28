using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace VideoStudio.Server;

public sealed class ReleaseCandidateInput
{
    public bool LicenseEvidenceConfirmed { get; set; }
    public string? LicenseReference { get; set; }
    public string? LicenseScope { get; set; }
    public string? LicenseModels { get; set; }
    public string? AssetVersionBinding { get; set; }
    public string? LicenseTerritory { get; set; }
    public string? LicensePlatforms { get; set; }
    public bool AiDisclosureRecorded { get; set; }
    public string? AiDisclosure { get; set; }
    public string? AiDisclosurePath { get; set; }
    public string? Reviewer { get; set; }
    public string? Note { get; set; }
}

public sealed class ReleaseFileSnapshot
{
    public string Role { get; set; } = "";
    public string? SourceId { get; set; }
    public string? RelativePath { get; set; }
    public string? Sha256 { get; set; }
    public long? AssetId { get; set; }
    public long? ManifestId { get; set; }
    public long? SizeBytes { get; set; }
    public int? Version { get; set; }
    public object? Probe { get; set; }
}

public sealed class ReleaseSlotBindingSnapshot
{
    public string Role { get; set; } = "";
    public string? RelativePath { get; set; }
    public string? Sha256 { get; set; }
    public long? AssetId { get; set; }
    public long? ManifestId { get; set; }
    public int? AssetVersion { get; set; }
}

public sealed class ReleaseCharacterSnapshot
{
    public long CharacterId { get; set; }
    public long ReferenceId { get; set; }
    public string RelativePath { get; set; } = "";
    public int AssetVersion { get; set; }
    public string AssetSha256 { get; set; } = "";
    public string ReviewStatus { get; set; } = "";
    public string Reviewer { get; set; } = "";
}

public sealed class ReleaseShotSnapshot
{
    public long ShotId { get; set; }
    public int ShotNumber { get; set; }
    public string? Title { get; set; }
    public string? QaStatus { get; set; }
    public int QaVersion { get; set; }
    public int PromptVersion { get; set; }
    public long? WorkflowId { get; set; }
    public string? WorkflowContractId { get; set; }
    public string? WorkflowContractVersion { get; set; }
    public string? WorkflowSha256 { get; set; }
    public string? RuntimeDependencyFingerprint { get; set; }
    public string? LicenseStatus { get; set; }
    public List<string> ModelFiles { get; set; } = [];
    public Dictionary<string, string> ModelPaths { get; set; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> ModelFingerprints { get; set; } = new(StringComparer.OrdinalIgnoreCase);
    public string? VideoQcSha256 { get; set; }
    public ReleaseFileSnapshot? Video { get; set; }
    public List<ReleaseSlotBindingSnapshot> SlotBindings { get; set; } = [];
    public List<ReleaseCharacterSnapshot> CharacterReferences { get; set; } = [];
}

public sealed class ReleaseSourceManifest
{
    public long EpisodeId { get; set; }
    public long? ProjectId { get; set; }
    public string? EpisodeStatus { get; set; }
    public string? EpisodeQaStatus { get; set; }
    public int EpisodeQaVersion { get; set; }
    public bool QaLocked { get; set; }
    public ReleaseFileSnapshot? EpisodeOutput { get; set; }
    public ReleaseFileSnapshot? Subtitle { get; set; }
    public ReleaseFileSnapshot? Cover { get; set; }
    public List<ReleaseFileSnapshot> Audio { get; set; } = [];
    public List<ReleaseFileSnapshot> SoundEffects { get; set; } = [];
    public List<ReleaseFileSnapshot> Bgm { get; set; } = [];
    public List<ReleaseShotSnapshot> Shots { get; set; } = [];
}

public sealed class ReleaseLicenseEvidence
{
    public bool Confirmed { get; set; }
    public string? Reference { get; set; }
    public string? Scope { get; set; }
    public string? Models { get; set; }
    public string? AssetVersions { get; set; }
    public string? Territory { get; set; }
    public string? Platforms { get; set; }
    public bool Complete { get; set; }
}

public sealed class ReleaseAiDisclosure
{
    public bool Recorded { get; set; }
    public string? Text { get; set; }
    public ReleaseFileSnapshot? File { get; set; }
    public bool Complete { get; set; }
}

public sealed record ReleaseEligibilityResult(
    string TechnicalStatus,
    string ContentStatus,
    string ReleaseEligibility,
    bool CanCreateCandidate,
    IReadOnlyList<string> BlockingReasons,
    EpisodeQualityGateSummary QualityGate,
    ReleaseSourceManifest SourceManifest,
    ReleaseLicenseEvidence LicenseEvidence,
    ReleaseAiDisclosure AiDisclosure,
    string SourceManifestSha256);

public sealed record ReleaseCandidateValidationResult(
    bool Valid,
    bool ShouldExpire,
    string Reason,
    string CurrentSourceManifestSha256,
    ReleaseEligibilityResult CurrentEligibility);

public sealed class ReleaseEligibilityService
{
    private static readonly JsonSerializerOptions SnapshotJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false
    };

    private readonly CharacterReferenceGateService _characterReferences;
    private readonly WorkflowContractService _contracts;

    public ReleaseEligibilityService(CharacterReferenceGateService characterReferences, WorkflowContractService contracts)
    {
        _characterReferences = characterReferences;
        _contracts = contracts;
    }

    public async Task<ReleaseEligibilityResult> EvaluateAsync(
        IReadOnlyDictionary<string, object?> episode,
        IReadOnlyList<Dictionary<string, object?>> shots,
        StudioRepository repository,
        FfmpegService ffmpeg,
        AssetPathPolicy paths,
        ReleaseCandidateInput? evidence,
        CancellationToken ct = default)
    {
        var gate = await EpisodeQualityGateEvaluator.EvaluateAsync(episode, shots, repository, ffmpeg, paths, ct);
        var technicalReasons = new List<string>();
        var contentReasons = new List<string>();
        technicalReasons.AddRange(gate.Sources.Where(source => !source.FormalReady).Select(source => $"Shot {source.ShotNumber}: {source.BlockedReason}"));

        var manifest = await BuildManifestAsync(episode, shots, gate, repository, ffmpeg, paths, technicalReasons, ct);
        foreach (var shot in shots)
        {
            var traceIssues = await ValidateShotTraceAsync(shot, ffmpeg, paths, ct);
            technicalReasons.AddRange(traceIssues.Select(issue => $"Shot {shot.Int("shotNumber")}: {issue}"));
        }

        if (!gate.AllShotsPassed) contentReasons.Add($"镜头 QA 尚未全部 Passed（{gate.PassedShotCount}/{gate.ShotCount}）");
        if (!gate.EpisodeApproved || !gate.QaLocked) contentReasons.Add("Episode 尚未 Approved 并锁定");
        if (gate.OpenBlockingIssueCount > 0) contentReasons.Add($"仍有 {gate.OpenBlockingIssueCount} 个 Critical/Error 问题未关闭");

        var license = new ReleaseLicenseEvidence
        {
            Confirmed = evidence?.LicenseEvidenceConfirmed == true,
            Reference = Clean(evidence?.LicenseReference),
            Scope = Clean(evidence?.LicenseScope),
            Models = Clean(evidence?.LicenseModels),
            AssetVersions = Clean(evidence?.AssetVersionBinding),
            Territory = Clean(evidence?.LicenseTerritory),
            Platforms = Clean(evidence?.LicensePlatforms)
        };
        license.Complete = license.Confirmed
            && new[] { license.Reference, license.Scope, license.Models, license.AssetVersions, license.Territory, license.Platforms }.All(value => !string.IsNullOrWhiteSpace(value));
        if (!license.Confirmed) technicalReasons.Add("缺少许可证据确认");
        if (license.Confirmed && string.IsNullOrWhiteSpace(license.Reference)) technicalReasons.Add("许可证据说明不能为空");
        if (string.IsNullOrWhiteSpace(license.Scope)) technicalReasons.Add("许可证适用范围不能为空");
        if (string.IsNullOrWhiteSpace(license.Models)) technicalReasons.Add("许可证据必须列出具体模型及版本");
        if (string.IsNullOrWhiteSpace(license.AssetVersions)) technicalReasons.Add("许可证据必须绑定素材版本/哈希范围");
        if (string.IsNullOrWhiteSpace(license.Territory)) technicalReasons.Add("许可证适用地域不能为空，不能默认全球适用");
        if (string.IsNullOrWhiteSpace(license.Platforms)) technicalReasons.Add("许可证适用发布平台不能为空");
        var sourceHash = ComputeSourceManifestSha256(manifest);
        var assetBindingComplete = !string.IsNullOrWhiteSpace(license.AssetVersions) && license.AssetVersions.Contains(sourceHash, StringComparison.OrdinalIgnoreCase);
        if (!assetBindingComplete)
            technicalReasons.Add("许可证据的素材版本绑定必须包含本次 sourceManifestSha256");
        var modelBindingComplete = true;
        foreach (var model in manifest.Shots.SelectMany(GetModelNames).Distinct(StringComparer.OrdinalIgnoreCase))
            if (string.IsNullOrWhiteSpace(license.Models) || !license.Models.Contains(model, StringComparison.OrdinalIgnoreCase))
            {
                modelBindingComplete = false;
                technicalReasons.Add($"许可证据未绑定实际模型 {model}");
            }
        foreach (var fingerprint in manifest.Shots.SelectMany(shot => shot.ModelFingerprints).DistinctBy(pair => $"{pair.Key}:{pair.Value}", StringComparer.OrdinalIgnoreCase))
            if (string.IsNullOrWhiteSpace(license.Models) || !license.Models.Contains(fingerprint.Key, StringComparison.OrdinalIgnoreCase) || !license.Models.Contains(fingerprint.Value, StringComparison.OrdinalIgnoreCase))
            {
                modelBindingComplete = false;
                technicalReasons.Add($"许可证据未绑定模型权重哈希 {fingerprint.Key}");
            }
        foreach (var shot in manifest.Shots.Where(shot => IsPendingLicense(shot.LicenseStatus)))
            technicalReasons.Add($"Shot {shot.ShotNumber}: 工作流许可仍待核实，不能靠勾选覆盖（{shot.LicenseStatus}）");
        license.Complete = license.Complete && assetBindingComplete && modelBindingComplete && !manifest.Shots.Any(shot => IsPendingLicense(shot.LicenseStatus));

        var disclosureFile = await CaptureFileAsync("aiDisclosure", evidence?.AiDisclosurePath, null, paths, ffmpeg, ct);
        var disclosure = new ReleaseAiDisclosure
        {
            Recorded = evidence?.AiDisclosureRecorded == true,
            Text = Clean(evidence?.AiDisclosure),
            File = disclosureFile
        };
        disclosure.Complete = disclosure.Recorded && !string.IsNullOrWhiteSpace(disclosure.Text) && disclosure.File is not null && disclosure.File.SizeBytes is > 0 && IsSha256(disclosure.File.Sha256);
        if (!disclosure.Recorded) technicalReasons.Add("缺少 AI 内容披露记录");
        if (string.IsNullOrWhiteSpace(disclosure.Text)) technicalReasons.Add("AI 披露内容不能为空");
        if (disclosure.File is null) technicalReasons.Add("AI 披露必须绑定实际交付文件");
        else if (disclosure.File.SizeBytes is not > 0) technicalReasons.Add("AI 披露交付文件不能为空");

        var blocking = technicalReasons.Concat(contentReasons).Distinct(StringComparer.Ordinal).ToList();
        return new ReleaseEligibilityResult(
            technicalReasons.Count == 0 ? "Passed" : "Failed",
            contentReasons.Count == 0 ? "Passed" : "NeedReview",
            blocking.Count == 0 ? "Ready" : "Blocked",
            blocking.Count == 0,
            blocking,
            gate,
            manifest,
            license,
            disclosure,
            sourceHash);
    }

    public async Task<ReleaseCandidateValidationResult> ValidateCandidateForExportAsync(
        ReleaseCandidatePackage candidate,
        long episodeId,
        StudioRepository repository,
        FfmpegService ffmpeg,
        AssetPathPolicy paths,
        CancellationToken ct = default)
    {
        if (candidate.EpisodeId != episodeId) return Invalid(false, "候选包不属于当前 Episode", "", null);
        if (!ReleaseCandidatePolicy.SourceSnapshotMatches(candidate.SourceManifest, candidate.SourceManifestSha256))
            return Invalid(true, "候选包内容与来源快照摘要不一致，候选包已过期", candidate.SourceManifestSha256, null);
        if (!string.Equals(candidate.Status, "Ready", StringComparison.OrdinalIgnoreCase)
            || !string.Equals(candidate.ReleaseEligibility, "Ready", StringComparison.OrdinalIgnoreCase))
            return Invalid(false, "候选包不是可导出的 Ready 状态", candidate.SourceManifestSha256, null);
        var episode = (await repository.EpisodeAsync(episodeId, ct)).FirstOrDefault();
        if (episode is null) return Invalid(false, "Episode 不存在", candidate.SourceManifestSha256, null);
        var current = await EvaluateAsync(episode, await repository.ShotsAsync(episodeId, ct), repository, ffmpeg, paths, ToInput(candidate), ct);
        var currentHash = ComputeSourceManifestSha256(current.SourceManifest);
        if (!string.Equals(candidate.SourceManifestSha256, currentHash, StringComparison.OrdinalIgnoreCase))
            return new(false, true, "候选包来源在创建后发生变化，候选包已过期", currentHash, current);
        if (!current.CanCreateCandidate)
            return new(false, true, "候选包的当前许可证、AI 披露、技术追溯或内容门禁已失效", currentHash, current);
        return new(true, false, "候选包来源、版本、哈希和发布门禁均仍一致", currentHash, current);
    }

    public static string ComputeSourceManifestSha256(ReleaseSourceManifest manifest)
    {
        var json = JsonSerializer.Serialize(manifest, SnapshotJsonOptions);
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(json))).ToLowerInvariant();
    }

    public static bool IsSha256ForExport(string? value) => IsSha256(value);

    private async Task<ReleaseSourceManifest> BuildManifestAsync(
        IReadOnlyDictionary<string, object?> episode,
        IReadOnlyList<Dictionary<string, object?>> shots,
        EpisodeQualityGateSummary gate,
        StudioRepository repository,
        FfmpegService ffmpeg,
        AssetPathPolicy paths,
        List<string> issues,
        CancellationToken ct)
    {
        var manifest = new ReleaseSourceManifest
        {
            EpisodeId = episode.Long("id"),
            ProjectId = episode.LongOrNull("projectId"),
            EpisodeStatus = episode.Text("status"),
            EpisodeQaStatus = episode.Text("qaStatus"),
            EpisodeQaVersion = episode.Int("qaVersion"),
            QaLocked = episode.Bool("qaLocked"),
            EpisodeOutput = await CaptureTrackedFileAsync("episodeOutput", episode.Text("outputPath"), "video", repository, paths, ffmpeg, issues, ct)
        };
        if (manifest.EpisodeOutput is null) issues.Add("Episode 正式输出不存在或无法计算当前哈希");
        manifest.Subtitle = await CaptureTrackedFileAsync("subtitle", episode.Text("subtitlePath"), "subtitle", repository, paths, ffmpeg, issues, ct);
        if (manifest.Subtitle is null) issues.Add("候选包缺少字幕交付文件，无法锁定字幕来源");
        manifest.Cover = await CaptureTrackedFileAsync("cover", episode.Text("coverPath"), "cover", repository, paths, ffmpeg, issues, ct);
        if (manifest.Cover is null) issues.Add("候选包缺少封面交付文件，无法锁定封面来源");

        var audioIndex = 0;
        foreach (var audio in await repository.EpisodeAudioResultsAsync(episode.Long("id"), ct))
        {
            var snapshot = await CaptureTrackedFileAsync("audio", audio.Text("path"), "audio", repository, paths, ffmpeg, issues, ct, $"{audioIndex++}:shot-{audio.LongOrNull("shotId")}");
            if (snapshot is null) issues.Add("候选包包含缺失的音频来源"); else manifest.Audio.Add(snapshot);
        }
        var effectIndex = 0;
        foreach (var effect in await repository.EpisodeSoundEffectsAsync(episode.Long("id"), ct))
        {
            var snapshot = await CaptureTrackedFileAsync("soundEffect", effect.Text("path"), "audio", repository, paths, ffmpeg, issues, ct, $"{effectIndex++}:shot-{effect.LongOrNull("shotId")}");
            if (snapshot is null) issues.Add("候选包包含缺失的音效来源"); else manifest.SoundEffects.Add(snapshot);
        }
        var bgmIndex = 0;
        foreach (var bgm in await repository.EpisodeBgmAsync(episode.Long("id"), ct))
        {
            var snapshot = await CaptureTrackedFileAsync("bgm", bgm.Text("path"), "audio", repository, paths, ffmpeg, issues, ct, $"{bgmIndex++}:{bgm.LongOrNull("id")}");
            if (snapshot is null) issues.Add("候选包包含缺失的 BGM 来源"); else manifest.Bgm.Add(snapshot);
        }

        foreach (var shot in shots.OrderBy(row => row.Int("sortOrder", row.Int("shotNumber"))))
        {
            var source = gate.Sources.FirstOrDefault(item => item.ShotId == shot.Long("id"));
            var snapshot = new ReleaseShotSnapshot
            {
                ShotId = shot.Long("id"),
                ShotNumber = shot.Int("shotNumber"),
                Title = shot.Text("title"),
                QaStatus = shot.Text("qaStatus"),
                QaVersion = shot.Int("qaVersion"),
                PromptVersion = shot.Int("promptVersion", 1),
                WorkflowId = shot.LongOrNull("workflowId"),
                Video = await CaptureTrackedFileAsync("shotVideo", source?.FinalVideoPath, "video", repository, paths, ffmpeg, issues, ct, $"shot-{shot.Long("id")}"),
                VideoQcSha256 = HashText(shot.Text("videoQcJson"))
            };
            if (snapshot.Video is null) issues.Add($"Shot {snapshot.ShotNumber}: 正式视频来源不存在或无法计算哈希");
            var trace = ParseJsonObject(shot.Text("videoQcJson"));
            if (trace is not null && TryGetObject(trace.Value, "workflowContract", out var contract))
            {
                snapshot.WorkflowContractId = GetString(contract, "contractId");
                snapshot.WorkflowContractVersion = GetString(contract, "contractVersion");
                snapshot.WorkflowSha256 = GetString(contract, "sha256") ?? GetString(contract, "workflowSha256");
                snapshot.RuntimeDependencyFingerprint = GetString(contract, "runtimeDependencyFingerprint");
                snapshot.LicenseStatus = GetString(contract, "licenseStatus");
            }
            if (trace is not null && TryGetObject(trace.Value, "modelFingerprints", out var modelFingerprints))
            {
                foreach (var model in modelFingerprints.EnumerateObject())
                {
                    snapshot.ModelFiles.Add(model.Name);
                    if (model.Value.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(model.Value.GetString()))
                        snapshot.ModelFingerprints[model.Name] = model.Value.GetString()!;
                }
            }
            if (trace is not null && TryGetObject(trace.Value, "modelPaths", out var modelPaths))
            {
                foreach (var model in modelPaths.EnumerateObject())
                    if (model.Value.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(model.Value.GetString()))
                        snapshot.ModelPaths[model.Name] = model.Value.GetString()!;
            }
            if (trace is not null && TryGetObject(trace.Value, "slotBindings", out var slots))
            {
                foreach (var slot in slots.EnumerateObject())
                {
                    var binding = new ReleaseSlotBindingSnapshot { Role = slot.Name };
                    if (slot.Value.ValueKind == JsonValueKind.Object)
                    {
                        binding.RelativePath = GetString(slot.Value, "relativePath") ?? GetString(slot.Value, "path");
                        binding.Sha256 = GetString(slot.Value, "sha256");
                        binding.AssetId = GetLong(slot.Value, "assetId");
                        binding.ManifestId = GetLong(slot.Value, "manifestId");
                        binding.AssetVersion = GetInt(slot.Value, "assetVersion");
                    }
                    snapshot.SlotBindings.Add(binding);
                }
            }
            var characterGate = await _characterReferences.CheckShotAsync(snapshot.ShotId, ct);
            if (!characterGate.Passed) issues.AddRange(characterGate.Issues.Select(issue => $"Shot {snapshot.ShotNumber}: {issue}"));
            snapshot.CharacterReferences.AddRange(characterGate.References.Select(reference => new ReleaseCharacterSnapshot
            {
                CharacterId = reference.CharacterId,
                ReferenceId = reference.ReferenceId,
                RelativePath = reference.RelativePath,
                AssetVersion = reference.AssetVersion,
                AssetSha256 = reference.AssetSha256,
                ReviewStatus = reference.ReviewStatus,
                Reviewer = reference.Reviewer
            }));
            manifest.Shots.Add(snapshot);
        }
        return manifest;
    }

    private async Task<List<string>> ValidateShotTraceAsync(IReadOnlyDictionary<string, object?> shot, FfmpegService ffmpeg, AssetPathPolicy paths, CancellationToken ct)
    {
        var issues = new List<string>();
        var qc = ParseJsonObject(shot.Text("videoQcJson"));
        if (qc is null) return ["video_qc_json 缺失或不是对象"];
        JsonElement contract = default;
        var hasContract = TryGetObject(qc.Value, "workflowContract", out contract) && contract.EnumerateObject().Any();
        if (!hasContract) issues.Add("workflowContract 缺失或为空");
        else
        {
            issues.AddRange(_contracts.ValidateRuntimeTrace(contract));
            if (!string.Equals(GetString(contract, "validationStatus"), "Passed", StringComparison.OrdinalIgnoreCase)) issues.Add("workflowContract.validationStatus 不是 Passed");
            if (string.IsNullOrWhiteSpace(GetString(contract, "licenseStatus"))) issues.Add("workflowContract.licenseStatus 缺失");
        }
        if (!TryGetObject(qc.Value, "slotBindings", out var slots) || !slots.EnumerateObject().Any()) issues.Add("slotBindings 缺失或为空，无法证明输入资产绑定");
        else
        {
            var expectedContract = hasContract ? _contracts.Find(null, GetString(contract, "contractId")) : null;
            if (expectedContract is not null)
            {
                foreach (var requiredSlot in expectedContract.Slots.Where(slot => slot.Required))
                    if (!slots.TryGetProperty(requiredSlot.Role, out _)) issues.Add($"slotBindings 缺少必需槽位 {requiredSlot.Role}");
            }
            foreach (var slot in slots.EnumerateObject())
            {
                if (slot.Value.ValueKind != JsonValueKind.Object || !IsSha256(GetString(slot.Value, "sha256")))
                {
                    issues.Add($"slotBindings.{slot.Name} 缺少当前资产哈希");
                    continue;
                }
                if (GetLong(slot.Value, "assetId") is not > 0 || GetLong(slot.Value, "manifestId") is not > 0 || GetInt(slot.Value, "assetVersion") is not > 0)
                    issues.Add($"slotBindings.{slot.Name} 缺少稳定 assetId/manifestId/version");
                var relativePath = GetString(slot.Value, "relativePath") ?? GetString(slot.Value, "path");
                if (!paths.TryResolveExisting(relativePath, out var slotPath, out _))
                {
                    issues.Add($"slotBindings.{slot.Name} 来源不存在或不在受控目录");
                    continue;
                }
                var currentSlotHash = await ffmpeg.Sha256Async(slotPath, ct);
                if (!string.Equals(currentSlotHash, GetString(slot.Value, "sha256"), StringComparison.OrdinalIgnoreCase))
                    issues.Add($"slotBindings.{slot.Name} 文件哈希已变化");
            }
        }
        if (!TryGetObject(qc.Value, "outputProbe", out var output) || !output.EnumerateObject().Any()) issues.Add("outputProbe 缺失或为空");
        else
        {
            if (!string.Equals(GetString(output, "status"), "Passed", StringComparison.OrdinalIgnoreCase)) issues.Add("outputProbe.status 不是 Passed");
            foreach (var field in new[] { "width", "height", "durationSeconds", "fps", "frameCount" })
                if (!TryGetNumber(output, field)) issues.Add($"outputProbe.{field} 缺失");
            var outputHash = GetString(output, "fileSha256");
            if (!IsSha256(outputHash)) issues.Add("outputProbe.fileSha256 缺失或无效");
            var currentPath = shot.Text("finalVideoPath") ?? shot.Text("videoPath") ?? shot.Text("resultPath");
            if (!paths.TryResolveExisting(currentPath, out var fullPath, out _)) issues.Add("当前正式视频不存在或不在受控目录");
            else
            {
                var currentHash = await ffmpeg.Sha256Async(fullPath, ct);
                if (!string.Equals(currentHash, outputHash, StringComparison.OrdinalIgnoreCase)) issues.Add("outputProbe.fileSha256 与当前正式视频不一致");
            }
        }
        return issues;
    }

    private static async Task<ReleaseFileSnapshot?> CaptureFileAsync(string role, string? storedPath, string? kind, AssetPathPolicy paths, FfmpegService ffmpeg, CancellationToken ct, string? sourceId = null)
    {
        if (!paths.TryResolveExisting(storedPath, out var fullPath, out var relativePath)) return null;
        var hash = await ffmpeg.Sha256Async(fullPath, ct);
        if (!IsSha256(hash)) return null;
        object? probe = null;
        if (kind is "video" or "cover" or "audio") probe = await ffmpeg.ProbeAsync(fullPath, ct);
        var info = new FileInfo(fullPath);
        return new ReleaseFileSnapshot { Role = role, SourceId = sourceId, RelativePath = relativePath, Sha256 = hash, SizeBytes = info.Length, Probe = probe };
    }

    private static async Task<ReleaseFileSnapshot?> CaptureTrackedFileAsync(string role, string? storedPath, string? kind, StudioRepository repository, AssetPathPolicy paths, FfmpegService ffmpeg, List<string> issues, CancellationToken ct, string? sourceId = null)
    {
        var snapshot = await CaptureFileAsync(role, storedPath, kind, paths, ffmpeg, ct, sourceId);
        if (snapshot is null || string.IsNullOrWhiteSpace(snapshot.RelativePath) || string.IsNullOrWhiteSpace(snapshot.Sha256)) return snapshot;
        var tracked = (await repository.TrackedAssetAsync(null, snapshot.RelativePath, snapshot.Sha256, ct)).FirstOrDefault();
        if (tracked is null)
        {
            issues.Add($"{role} 未绑定 Ready asset/manifest，无法锁定稳定资产 ID、版本和哈希");
            return snapshot;
        }
        snapshot.AssetId = tracked.LongOrNull("id");
        snapshot.ManifestId = tracked.LongOrNull("manifestId");
        snapshot.Version = Math.Max(1, tracked.Int("version", 1));
        return snapshot;
    }

    private static ReleaseCandidateInput ToInput(ReleaseCandidatePackage candidate)
        => new()
        {
            LicenseEvidenceConfirmed = candidate.LicenseEvidence.Confirmed,
            LicenseReference = candidate.LicenseEvidence.Reference,
            LicenseScope = candidate.LicenseEvidence.Scope,
            LicenseModels = candidate.LicenseEvidence.Models,
            AssetVersionBinding = candidate.LicenseEvidence.AssetVersions,
            LicenseTerritory = candidate.LicenseEvidence.Territory,
            LicensePlatforms = candidate.LicenseEvidence.Platforms,
            AiDisclosureRecorded = candidate.AiDisclosure.Recorded,
            AiDisclosure = candidate.AiDisclosure.Text,
            AiDisclosurePath = candidate.AiDisclosure.File?.RelativePath,
            Reviewer = candidate.Reviewer,
            Note = candidate.Note
        };

    private static ReleaseCandidateValidationResult Invalid(bool expire, string reason, string currentHash, ReleaseEligibilityResult? current)
        => new(false, expire, reason, currentHash, current ?? new ReleaseEligibilityResult("Failed", "NeedReview", "Blocked", false, [reason], new EpisodeQualityGateSummary(0, 0, 0, 0, 0, false, false, false, false, false, [reason], []), new ReleaseSourceManifest(), new ReleaseLicenseEvidence(), new ReleaseAiDisclosure(), currentHash));

    private static JsonElement? ParseJsonObject(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return null;
        try
        {
            using var document = JsonDocument.Parse(json);
            return document.RootElement.ValueKind == JsonValueKind.Object ? document.RootElement.Clone() : null;
        }
        catch (JsonException) { return null; }
    }

    private static bool TryGetObject(JsonElement root, string name, out JsonElement value)
    {
        if (TryGet(root, name, out value) && value.ValueKind == JsonValueKind.Object) return true;
        value = default;
        return false;
    }

    private static bool TryGet(JsonElement root, string name, out JsonElement value)
    {
        if (root.ValueKind == JsonValueKind.Object)
            foreach (var property in root.EnumerateObject())
                if (string.Equals(property.Name, name, StringComparison.OrdinalIgnoreCase)) { value = property.Value; return true; }
        value = default;
        return false;
    }

    private static string? GetString(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static int? GetInt(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.TryGetInt32(out var result) ? result : null;

    private static long? GetLong(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.TryGetInt64(out var result) ? result : null;

    private static bool TryGetNumber(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.ValueKind is JsonValueKind.Number && value.TryGetDouble(out _);

    private static IEnumerable<string> GetModelNames(ReleaseShotSnapshot shot)
        => shot.ModelFiles;

    private static string? Clean(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? HashText(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static bool IsSha256(string? value)
        => !string.IsNullOrWhiteSpace(value) && value.Length == 64 && value.All(Uri.IsHexDigit);

    private static bool IsPendingLicense(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return true;
        var normalized = value.Trim();
        if (normalized.Contains("PENDING", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("UNKNOWN", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("UNREVIEWED", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("BLOCKED", StringComparison.OrdinalIgnoreCase)) return true;
        return !(normalized.Equals("APPROVED", StringComparison.OrdinalIgnoreCase)
            || normalized.EndsWith("_APPROVED", StringComparison.OrdinalIgnoreCase)
            || normalized.EndsWith("-APPROVED", StringComparison.OrdinalIgnoreCase)
            || normalized.Equals("LICENSED", StringComparison.OrdinalIgnoreCase)
            || normalized.Equals("CLEARED", StringComparison.OrdinalIgnoreCase));
    }
}

public static class ReleaseCandidatePolicy
{
    public static bool SourceSnapshotMatches(ReleaseSourceManifest manifest, string? sourceManifestSha256)
        => ReleaseEligibilityService.IsSha256ForExport(sourceManifestSha256)
           && string.Equals(ReleaseEligibilityService.ComputeSourceManifestSha256(manifest), sourceManifestSha256, StringComparison.OrdinalIgnoreCase);

    public static bool VersionAndSnapshotMatch(ReleaseCandidatePackage candidate, int expectedVersion, string? expectedSourceManifestSha256)
        => candidate.Version == expectedVersion
           && string.Equals(candidate.SourceManifestSha256, expectedSourceManifestSha256, StringComparison.OrdinalIgnoreCase)
           && SourceSnapshotMatches(candidate.SourceManifest, candidate.SourceManifestSha256);
}

public sealed record ReleaseCandidatePackage(
    long Id,
    long ProjectId,
    long EpisodeId,
    int Version,
    string Status,
    string TechnicalStatus,
    string ContentStatus,
    string ReleaseEligibility,
    ReleaseSourceManifest SourceManifest,
    string SourceManifestSha256,
    ReleaseLicenseEvidence LicenseEvidence,
    ReleaseAiDisclosure AiDisclosure,
    string? Reviewer,
    string? Note,
    DateTime? CreatedAt,
    string? IdempotencyKey = null,
    long? ExportTaskId = null,
    DateTime? ExpiredAt = null,
    string? ExpiredReason = null);
