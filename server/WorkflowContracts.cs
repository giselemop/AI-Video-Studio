using System.Security;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Collections.Concurrent;

namespace VideoStudio.Server;

public sealed class WorkflowContractDocument
{
    public int SchemaVersion { get; set; } = 1;
    public List<WorkflowContractDefinition> Contracts { get; set; } = [];
}

public sealed class WorkflowContractDefinition
{
    public string Id { get; set; } = "";
    public string Version { get; set; } = "";
    public string FileName { get; set; } = "";
    public string WorkflowType { get; set; } = "Image";
    public bool ProductionEligible { get; set; }
    public bool Experimental { get; set; }
    public string LicenseStatus { get; set; } = "LOCAL_ONLY_PENDING_REVIEW";
    public List<string> TaskTypes { get; set; } = [];
    public List<string> ModelFiles { get; set; } = [];
    public Dictionary<string, string> ModelSha256 { get; set; } = new(StringComparer.OrdinalIgnoreCase);
    public List<WorkflowNodeDefinition> Nodes { get; set; } = [];
    public List<WorkflowSlotDefinition> Slots { get; set; } = [];
    public WorkflowMediaDefinition Media { get; set; } = new();
    public string Notes { get; set; } = "";
}

public sealed class WorkflowNodeDefinition
{
    public string Role { get; set; } = "";
    public string NodeId { get; set; } = "";
    public string ClassType { get; set; } = "";
    public string? InputName { get; set; }
    public bool Required { get; set; } = true;
}

public sealed class WorkflowSlotDefinition
{
    public string Role { get; set; } = "";
    public string NodeId { get; set; } = "";
    public string ClassType { get; set; } = "LoadImage";
    public string InputName { get; set; } = "image";
    public bool Required { get; set; } = true;
}

public sealed class WorkflowMediaDefinition
{
    public int DefaultWidth { get; set; }
    public int DefaultHeight { get; set; }
    public List<WorkflowDimensionDefinition> AllowedDimensions { get; set; } = [];
    public List<int> OutputFrames { get; set; } = [];
    public double NativeFps { get; set; } = 24;
    public List<double> AllowedFps { get; set; } = [];
    public bool ExactFrameCount { get; set; }
    public int ExecutionFrameOffset { get; set; }
    public int GuideFrameOffset { get; set; }
    public bool RequiresGuide { get; set; }
    public bool PreserveAudio { get; set; }
}

public sealed class WorkflowDimensionDefinition
{
    public int Width { get; set; }
    public int Height { get; set; }
}

public sealed record WorkflowNodeSnapshot(string Role, string NodeId, string ClassType, string? InputName);
public sealed record WorkflowSlotSnapshot(string Role, string NodeId, string ClassType, string InputName, bool Required);
public sealed record WorkflowNormalization(string Field, object? Requested, object? Applied, string Reason);

/// <summary>
/// Caches model content hashes for inventory/admission checks, while allowing
/// execution and release gates to force a fresh read. File size and mtime are
/// useful cache hints but are not an integrity proof because an in-place
/// replacement can preserve both values.
/// </summary>
public sealed class ModelFingerprintCache
{
    private sealed record Entry(long Length, DateTime LastWriteUtc, string Sha256);
    private readonly ConcurrentDictionary<string, Entry> _entries = new(StringComparer.OrdinalIgnoreCase);

    public string Get(string path, bool forceRefresh = false)
    {
        var info = new FileInfo(path);
        if (!forceRefresh
            && _entries.TryGetValue(path, out var cached)
            && cached.Length == info.Length
            && cached.LastWriteUtc == info.LastWriteTimeUtc)
            return cached.Sha256;

        using var stream = File.OpenRead(path);
        var hash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        var refreshed = new FileInfo(path);
        _entries[path] = new Entry(refreshed.Length, refreshed.LastWriteTimeUtc, hash);
        return hash;
    }
}

public sealed class WorkflowExecutionPlan
{
    public string ContractId { get; init; } = "";
    public string ContractVersion { get; init; } = "";
    public string WorkflowFileName { get; init; } = "";
    public string WorkflowPath { get; init; } = "";
    public string WorkflowSha256 { get; init; } = "";
    public string RuntimeDependencyFingerprint { get; init; } = "";
    public bool ProductionEligible { get; init; }
    public bool Experimental { get; init; }
    public string LicenseStatus { get; init; } = "";
    public string WorkflowType { get; init; } = "";
    public int Width { get; init; }
    public int Height { get; init; }
    public double Fps { get; init; }
    public int? RequestedFrameCount { get; init; }
    public int? ExecutionLength { get; init; }
    public int? GuideFrameIndex { get; init; }
    public IReadOnlyDictionary<string, string> SlotPaths { get; init; } = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    public IReadOnlyDictionary<string, string> ModelPaths { get; init; } = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    public IReadOnlyDictionary<string, string> ModelFingerprints { get; init; } = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    public IReadOnlySet<string> DeclaredSlotRoles { get; init; } = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    public IReadOnlyList<WorkflowNodeSnapshot> Nodes { get; init; } = [];
    public IReadOnlyList<WorkflowSlotSnapshot> Slots { get; init; } = [];
    public IReadOnlyList<WorkflowNormalization> Normalizations { get; init; } = [];
    public JsonElement RequestedParameters { get; init; }
    public JsonElement ExecutionParameters { get; init; }
}

public sealed record WorkflowInventoryItem(
    string ContractId,
    string Version,
    string FileName,
    string Status,
    bool FileExists,
    bool HashMatches,
    string? ActualSha256,
    bool ProductionEligible,
    bool Experimental,
    string LicenseStatus,
    IReadOnlyList<string> Issues);

public sealed class WorkflowContractException : InvalidOperationException
{
    public string Code { get; }

    public WorkflowContractException(string code, string message) : base(message) => Code = code;
}

/// <summary>
/// The contract is the admission boundary for ComfyUI workflows. It deliberately
/// does not rewrite a workflow or pick a fallback route. A route must be selected
/// before execution and must remain reproducible for the life of the task.
/// </summary>
public sealed class WorkflowContractService
{
    private readonly StudioSettings _settings;
    private readonly ILogger<WorkflowContractService> _logger;
    private readonly WorkflowContractDocument _document;
    private readonly ModelFingerprintCache _modelHashCache = new();

    private sealed record ModelResolution(
        IReadOnlyDictionary<string, string> Paths,
        IReadOnlyDictionary<string, string> Hashes,
        IReadOnlyList<(string Code, string Message)> Issues);

    public WorkflowContractService(StudioSettings settings, ILogger<WorkflowContractService> logger)
    {
        _settings = settings;
        _logger = logger;
        var path = Path.Combine(settings.RootPath, "config", "workflow-contracts.json");
        if (!File.Exists(path))
        {
            _document = new WorkflowContractDocument();
            _logger.LogError("Workflow contract catalog is missing: {Path}", path);
        }
        else
        {
            try
            {
                _document = JsonSerializer.Deserialize<WorkflowContractDocument>(File.ReadAllText(path), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                    ?? new WorkflowContractDocument();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Workflow contract catalog cannot be read: {Path}", path);
                _document = new WorkflowContractDocument();
            }
        }
    }

    public IReadOnlyList<WorkflowContractDefinition> Contracts => _document.Contracts;

    public WorkflowContractDefinition? Find(string? workflowPath = null, string? requestedVersion = null)
    {
        var version = requestedVersion?.Trim();
        var fileName = string.IsNullOrWhiteSpace(workflowPath) ? null : Path.GetFileName(workflowPath);
        return _document.Contracts.FirstOrDefault(contract =>
            (string.IsNullOrWhiteSpace(version)
                || string.Equals(contract.Id, version, StringComparison.OrdinalIgnoreCase)
                || string.Equals(contract.Version, version, StringComparison.OrdinalIgnoreCase)
                || string.Equals(contract.FileName, version, StringComparison.OrdinalIgnoreCase))
            && (fileName is null || string.Equals(contract.FileName, fileName, StringComparison.OrdinalIgnoreCase)));
    }

    public WorkflowExecutionPlan Prepare(
        string workflowPath,
        string taskType,
        JsonElement parameters,
        IReadOnlyDictionary<string, string?>? resolvedSlotPaths = null,
        bool requireProductionRoute = false)
    {
        var fullPath = ResolveWorkflowPath(workflowPath);
        var requestedVersion = ReadString(parameters, "workflowVersion");
        var contract = Find(fullPath, requestedVersion);
        if (contract is null)
            throw new WorkflowContractException("WORKFLOW_UNCONTRACTED", $"工作流未登记契约：{Path.GetFileName(fullPath)}；必须先通过模型/节点/尺寸准入");
        if (!string.IsNullOrWhiteSpace(requestedVersion)
            && !string.Equals(contract.Id, requestedVersion, StringComparison.OrdinalIgnoreCase)
            && !string.Equals(contract.Version, requestedVersion, StringComparison.OrdinalIgnoreCase)
            && !string.Equals(contract.FileName, requestedVersion, StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("WORKFLOW_VERSION_MISMATCH", $"请求的工作流版本 {requestedVersion} 与文件 {contract.FileName} 不一致");
        if (requireProductionRoute && !contract.ProductionEligible)
            throw new WorkflowContractException("WORKFLOW_EXPERIMENTAL", $"工作流 {contract.Id} 仅为实验/旧路线，不能进入正式生产");
        if (contract.TaskTypes.Count > 0 && !contract.TaskTypes.Any(type => string.Equals(type, taskType, StringComparison.OrdinalIgnoreCase)))
            throw new WorkflowContractException("WORKFLOW_TASK_MISMATCH", $"工作流 {contract.Id} 不接受任务类型 {taskType}");

        var actualHash = ComputeSha256(fullPath);
        if (!string.Equals(actualHash, ExtractExpectedHash(contract), StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("WORKFLOW_HASH_DRIFT", $"工作流文件哈希发生变化：{contract.FileName}；请重新审查并更新契约");
        var models = ResolveModels(contract);
        if (models.Issues.Count > 0)
            throw new WorkflowContractException(models.Issues[0].Code, models.Issues[0].Message);

        var graph = ComfyUiClient.LoadWorkflow(fullPath);
        var snapshots = ValidateGraph(contract, graph);
        var requested = parameters.ValueKind == JsonValueKind.Object ? parameters.Clone() : JsonSerializer.SerializeToElement(new { });
        var effective = JsonNode.Parse(requested.GetRawText())?.AsObject() ?? new JsonObject();
        var normalizations = new List<WorkflowNormalization>();

        var width = ReadInt(requested, "width") ?? contract.Media.DefaultWidth;
        var height = ReadInt(requested, "height") ?? contract.Media.DefaultHeight;
        if (width <= 0 || height <= 0) throw new WorkflowContractException("MEDIA_DIMENSION_INVALID", "工作流执行尺寸必须为正整数");
        if (contract.Media.AllowedDimensions.Count > 0 && !contract.Media.AllowedDimensions.Any(d => d.Width == width && d.Height == height))
            throw new WorkflowContractException("MEDIA_DIMENSION_UNSUPPORTED", $"{contract.Id} 不允许执行尺寸 {width}x{height}；不会按首帧画幅静默改尺寸");
        if (ReadInt(requested, "width") is null) normalizations.Add(new("width", null, width, "contract-default"));
        if (ReadInt(requested, "height") is null) normalizations.Add(new("height", null, height, "contract-default"));
        effective["width"] = width;
        effective["height"] = height;

        var isVideo = contract.WorkflowType.Contains("video", StringComparison.OrdinalIgnoreCase)
            || contract.WorkflowType.Contains("i2v", StringComparison.OrdinalIgnoreCase)
            || taskType.Contains("video", StringComparison.OrdinalIgnoreCase)
            || taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase);
        var fps = ReadDouble(requested, "fps") ?? contract.Media.NativeFps;
        if (isVideo && contract.Media.AllowedFps.Count > 0 && !contract.Media.AllowedFps.Any(value => Math.Abs(value - fps) < .001))
            throw new WorkflowContractException("MEDIA_FPS_UNSUPPORTED", $"{contract.Id} 只接受 {string.Join(", ", contract.Media.AllowedFps)} fps，不会静默换帧率");
        if (isVideo)
        {
            if (ReadDouble(requested, "fps") is null) normalizations.Add(new("fps", null, fps, "contract-default"));
            effective["fps"] = fps;
        }

        int? requestedFrames = null;
        int? executionLength = null;
        int? guideFrameIndex = null;
        if (isVideo)
        {
            requestedFrames = ReadInt(requested, "frames") ?? ReadInt(requested, "length") ?? contract.Media.OutputFrames.FirstOrDefault();
            if (requestedFrames is null or <= 0) throw new WorkflowContractException("MEDIA_FRAMES_MISSING", "视频任务必须声明 output frames");
            if (contract.Media.OutputFrames.Count > 0 && !contract.Media.OutputFrames.Contains(requestedFrames.Value))
                throw new WorkflowContractException("MEDIA_FRAMES_UNSUPPORTED", $"{contract.Id} 不允许输出 {requestedFrames} 帧；不会按显存静默裁剪");
            if (ReadInt(requested, "frames") is null && ReadInt(requested, "length") is null)
                normalizations.Add(new("frames", null, requestedFrames, "contract-default"));
            effective["frames"] = requestedFrames.Value;
            var requestedDuration = ReadDouble(requested, "duration");
            var expectedDuration = requestedFrames.Value / fps;
            if (requestedDuration is > 0 && Math.Abs(requestedDuration.Value - expectedDuration) > .08)
                throw new WorkflowContractException("MEDIA_DURATION_MISMATCH", $"duration {requestedDuration:0.###} 与 {requestedFrames} 帧/{fps:0.###} fps 不一致");
            effective["duration"] = Math.Round(expectedDuration, 3);
            executionLength = Math.Max(1, requestedFrames.Value - contract.Media.ExecutionFrameOffset);
            if (contract.Media.RequiresGuide)
            {
                guideFrameIndex = requestedFrames.Value - contract.Media.GuideFrameOffset;
                if (guideFrameIndex < 0 || guideFrameIndex >= executionLength)
                    throw new WorkflowContractException("GUIDE_FRAME_INVALID", $"guide frame {guideFrameIndex} 不在执行 latent 的有效范围内");
                var suppliedGuide = ReadInt(requested, "guideFrameIndex");
                if (suppliedGuide is not null && suppliedGuide != guideFrameIndex)
                    throw new WorkflowContractException("GUIDE_FRAME_MISMATCH", $"请求 guideFrameIndex={suppliedGuide}，契约要求 {guideFrameIndex}");
                effective["guideFrameIndex"] = guideFrameIndex.Value;
                if (suppliedGuide is null) normalizations.Add(new("guideFrameIndex", null, guideFrameIndex, "latent-output-frame-mapping"));
            }
        }

        var declared = ReadDeclaredSlotRoles(requested);
        var slotPaths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var pair in ReadDeclaredSlotPaths(requested)) slotPaths[pair.Key] = pair.Value;
        if (resolvedSlotPaths is not null)
            foreach (var pair in resolvedSlotPaths)
                if (!string.IsNullOrWhiteSpace(pair.Value)) slotPaths[pair.Key] = pair.Value!;
        var knownRoles = contract.Slots.Select(slot => slot.Role).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var role in declared)
            if (!knownRoles.Contains(role)) throw new WorkflowContractException("SLOT_UNKNOWN", $"工作流 {contract.Id} 未声明输入槽位 {role}");
        if (contract.Slots.Count > 0 && HasLegacyReferenceInput(requested))
            throw new WorkflowContractException("SLOT_LEGACY_BINDING", "禁止使用 referenceImages/controlImages 的顺序绑定；请提交 inputSlots.role");
        foreach (var slot in contract.Slots.Where(slot => slot.Required))
            if (!declared.Contains(slot.Role) && !slotPaths.ContainsKey(slot.Role))
                throw new WorkflowContractException("SLOT_REQUIRED", $"缺少必需输入槽位 {slot.Role}");

        var outputParameters = JsonDocument.Parse(effective.ToJsonString()).RootElement.Clone();
        return new WorkflowExecutionPlan
        {
            ContractId = contract.Id,
            ContractVersion = contract.Version,
            WorkflowFileName = contract.FileName,
            WorkflowPath = fullPath,
            WorkflowSha256 = actualHash,
            RuntimeDependencyFingerprint = CurrentRuntimeDependencyFingerprint(),
            ProductionEligible = contract.ProductionEligible,
            Experimental = contract.Experimental,
            LicenseStatus = contract.LicenseStatus,
            WorkflowType = contract.WorkflowType,
            Width = width,
            Height = height,
            Fps = fps,
            RequestedFrameCount = requestedFrames,
            ExecutionLength = executionLength,
            GuideFrameIndex = guideFrameIndex,
            SlotPaths = slotPaths,
            ModelPaths = models.Paths,
            ModelFingerprints = models.Hashes,
            DeclaredSlotRoles = declared,
            Nodes = snapshots,
            Slots = contract.Slots.Select(slot => new WorkflowSlotSnapshot(slot.Role, slot.NodeId, slot.ClassType, slot.InputName, slot.Required)).ToArray(),
            Normalizations = normalizations,
            RequestedParameters = requested,
            ExecutionParameters = outputParameters
        };
    }

    public IReadOnlyList<WorkflowInventoryItem> Inventory()
    {
        var files = Directory.Exists(_settings.WorkflowsPath)
            ? Directory.EnumerateFiles(_settings.WorkflowsPath, "*.json", SearchOption.AllDirectories).ToArray()
            : [];
        var result = new List<WorkflowInventoryItem>();
        foreach (var file in files)
        {
            var contract = Find(file);
            if (contract is null)
            {
                result.Add(new("", "", Path.GetFileName(file), "Uncontracted", true, false, ComputeSha256(file), false, true, "UNREVIEWED", ["未登记工作流契约"]));
                continue;
            }
            var issues = new List<string>();
            var hash = ComputeSha256(file);
            if (!string.Equals(hash, ExtractExpectedHash(contract), StringComparison.OrdinalIgnoreCase)) issues.Add("文件哈希漂移");
            try { ValidateGraph(contract, ComfyUiClient.LoadWorkflow(file)); }
            catch (WorkflowContractException ex) { issues.Add(ex.Message); }
            try
            {
                var models = ResolveModels(contract);
                issues.AddRange(models.Issues.Select(issue => issue.Message));
            }
            catch (WorkflowContractException ex) { issues.Add(ex.Message); }
            var status = issues.Count == 0 ? "Passed" : "Failed";
            result.Add(new(contract.Id, contract.Version, contract.FileName, status, true, issues.Count == 0 && string.Equals(hash, ExtractExpectedHash(contract), StringComparison.OrdinalIgnoreCase), hash, contract.ProductionEligible, contract.Experimental, contract.LicenseStatus, issues));
        }
        foreach (var contract in _document.Contracts.Where(contract => !files.Any(file => string.Equals(Path.GetFileName(file), contract.FileName, StringComparison.OrdinalIgnoreCase))))
            result.Add(new(contract.Id, contract.Version, contract.FileName, "Failed", false, false, null, contract.ProductionEligible, contract.Experimental, contract.LicenseStatus, ["契约登记的工作流文件不存在"]));
        return result.OrderBy(item => item.FileName, StringComparer.OrdinalIgnoreCase).ToArray();
    }

    public object PublicCatalog()
        => new
        {
            schemaVersion = _document.SchemaVersion,
            contracts = _document.Contracts.Select(contract => new
            {
                id = contract.Id,
                version = contract.Version,
                fileName = contract.FileName,
                workflowType = contract.WorkflowType,
                taskTypes = contract.TaskTypes,
                productionEligible = contract.ProductionEligible,
                experimental = contract.Experimental,
                licenseStatus = contract.LicenseStatus,
                modelFiles = contract.ModelFiles,
                modelSha256 = contract.ModelSha256,
                slots = contract.Slots.Select(slot => new { role = slot.Role, nodeId = slot.NodeId, classType = slot.ClassType, inputName = slot.InputName, required = slot.Required }),
                media = new { contract.Media.DefaultWidth, contract.Media.DefaultHeight, contract.Media.AllowedDimensions, contract.Media.OutputFrames, contract.Media.NativeFps, contract.Media.AllowedFps, contract.Media.ExactFrameCount, contract.Media.ExecutionFrameOffset, contract.Media.GuideFrameOffset, contract.Media.RequiresGuide, contract.Media.PreserveAudio },
                notes = contract.Notes
            }),
            inventory = Inventory()
        };

    public static IReadOnlySet<string> ReadDeclaredSlotRoles(JsonElement parameters)
    {
        var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (parameters.ValueKind != JsonValueKind.Object || !TryGet(parameters, "inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object) return result;
        foreach (var property in slots.EnumerateObject()) result.Add(property.Name);
        return result;
    }

    public static IReadOnlyDictionary<string, string> ReadDeclaredSlotPaths(JsonElement parameters)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (parameters.ValueKind != JsonValueKind.Object || !TryGet(parameters, "inputSlots", out var slots) || slots.ValueKind != JsonValueKind.Object) return result;
        foreach (var property in slots.EnumerateObject())
        {
            if (property.Value.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(property.Value.GetString()))
                result[property.Name] = property.Value.GetString()!;
            else if (property.Value.ValueKind == JsonValueKind.Object && TryGet(property.Value, "path", out var path) && path.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(path.GetString()))
                result[property.Name] = path.GetString()!;
        }
        return result;
    }

    /// <summary>
    /// Re-checks the immutable execution trace against the current contract,
    /// workflow file and actual model bytes. This is intentionally separate
    /// from task admission so release validation cannot accept an empty trace.
    /// </summary>
    public IReadOnlyList<string> ValidateRuntimeTrace(JsonElement trace)
    {
        var issues = new List<string>();
        if (trace.ValueKind != JsonValueKind.Object || !trace.EnumerateObject().Any())
        {
            issues.Add("workflowContract 必须是非空对象");
            return issues;
        }

        var contractId = ReadString(trace, "contractId");
        var contractVersion = ReadString(trace, "contractVersion");
        var workflow = ReadString(trace, "workflow");
        var workflowSha = ReadString(trace, "sha256");
        var runtimeFingerprint = ReadString(trace, "runtimeDependencyFingerprint");
        if (string.IsNullOrWhiteSpace(contractId)) issues.Add("workflowContract.contractId 缺失");
        if (string.IsNullOrWhiteSpace(contractVersion)) issues.Add("workflowContract.contractVersion 缺失");
        if (string.IsNullOrWhiteSpace(workflow)) issues.Add("workflowContract.workflow 缺失");
        if (!IsSha256(workflowSha)) issues.Add("workflowContract.sha256 无效");
        if (string.IsNullOrWhiteSpace(runtimeFingerprint)) issues.Add("workflowContract.runtimeDependencyFingerprint 缺失");
        else if (!string.Equals(runtimeFingerprint, CurrentRuntimeDependencyFingerprint(), StringComparison.OrdinalIgnoreCase)) issues.Add("workflowContract.runtimeDependencyFingerprint 与当前运行依赖不一致");
        var contract = _document.Contracts.FirstOrDefault(candidate =>
            string.Equals(candidate.Id, contractId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(candidate.Version, contractVersion, StringComparison.OrdinalIgnoreCase));
        if (contract is null)
        {
            issues.Add("workflowContract 未匹配当前登记的契约版本");
            return issues;
        }
        if (!string.Equals(contract.FileName, workflow, StringComparison.OrdinalIgnoreCase))
            issues.Add("workflowContract.workflow 与契约文件不一致");
        try
        {
            var workflowPath = ResolveWorkflowPath(contract.FileName);
            var currentWorkflowSha = ComputeSha256(workflowPath);
            if (!string.Equals(currentWorkflowSha, workflowSha, StringComparison.OrdinalIgnoreCase))
                issues.Add("workflowContract.sha256 与当前工作流文件不一致");
        }
        catch (WorkflowContractException ex) { issues.Add(ex.Message); }

        ModelResolution? actualModels = null;
        if (!TryGet(trace, "modelFingerprints", out var modelFingerprints) || modelFingerprints.ValueKind != JsonValueKind.Object || !modelFingerprints.EnumerateObject().Any())
            issues.Add("workflowContract.modelFingerprints 缺失或为空");
        else
        {
            try
            {
                actualModels = ResolveModels(contract, forceRefresh: true);
                issues.AddRange(actualModels.Issues.Select(issue => issue.Message));
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or SecurityException)
            {
                issues.Add($"workflowContract 模型权重无法重新读取：{ex.GetType().Name}");
            }
            foreach (var model in contract.ModelFiles)
            {
                if (!modelFingerprints.TryGetProperty(model, out var value) || value.ValueKind != JsonValueKind.String || !IsSha256(value.GetString()))
                    issues.Add($"workflowContract 缺少模型 {model} 的有效哈希");
                else if (actualModels?.Hashes.TryGetValue(model, out var actual) == true && !string.Equals(actual, value.GetString(), StringComparison.OrdinalIgnoreCase))
                    issues.Add($"workflowContract 模型哈希漂移: {model}");
            }
        }
        if (!TryGet(trace, "modelPaths", out var modelPaths) || modelPaths.ValueKind != JsonValueKind.Object || !modelPaths.EnumerateObject().Any())
            issues.Add("workflowContract.modelPaths 缺失或为空");
        else
        {
            try
            {
                actualModels ??= ResolveModels(contract, forceRefresh: true);
                issues.AddRange(actualModels.Issues.Select(issue => issue.Message));
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or SecurityException)
            {
                issues.Add($"workflowContract 模型权重无法重新读取：{ex.GetType().Name}");
            }
            foreach (var model in contract.ModelFiles)
            {
                if (actualModels is null || !actualModels.Paths.TryGetValue(model, out var actualPath)) continue;
                var recordedPath = modelPaths.TryGetProperty(model, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
                if (string.IsNullOrWhiteSpace(recordedPath))
                {
                    issues.Add($"workflowContract 缺少模型 {model} 的解析路径");
                    continue;
                }
                var expectedPath = ModelTracePath(actualPath);
                try
                {
                    if (!string.Equals(recordedPath, expectedPath, StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(Path.GetFullPath(recordedPath), Path.GetFullPath(actualPath), StringComparison.OrdinalIgnoreCase))
                        issues.Add($"workflowContract 模型解析路径漂移: {model}");
                }
                catch (Exception ex) when (ex is ArgumentException or NotSupportedException or SecurityException)
                {
                    issues.Add($"workflowContract 模型解析路径无效: {model}");
                }
            }
        }
        return issues;
    }

    /// <summary>
    /// Re-reads every model weight immediately before a ComfyUI submission.
    /// This closes the same-size/same-mtime replacement gap left by the
    /// inventory cache and verifies the immutable execution plan still names
    /// the same resolved files and hashes.
    /// </summary>
    public IReadOnlyList<string> ValidateCurrentModelFingerprints(WorkflowExecutionPlan plan)
    {
        var contract = _document.Contracts.FirstOrDefault(candidate =>
            string.Equals(candidate.Id, plan.ContractId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(candidate.Version, plan.ContractVersion, StringComparison.OrdinalIgnoreCase));
        if (contract is null) return [$"工作流契约 {plan.ContractId}/{plan.ContractVersion} 不存在"];

        ModelResolution actual;
        try { actual = ResolveModels(contract, forceRefresh: true); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or SecurityException)
        {
            return [$"工作流契约模型权重无法在提交前重新读取：{ex.GetType().Name}"];
        }

        var issues = actual.Issues.Select(issue => issue.Message).ToList();
        foreach (var model in contract.ModelFiles.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (!plan.ModelFingerprints.TryGetValue(model, out var plannedHash) || !IsSha256(plannedHash))
            {
                issues.Add($"执行计划缺少模型 {model} 的有效哈希");
                continue;
            }
            if (!actual.Hashes.TryGetValue(model, out var actualHash) || !string.Equals(plannedHash, actualHash, StringComparison.OrdinalIgnoreCase))
                issues.Add($"执行前模型权重哈希漂移: {model}");
            if (!plan.ModelPaths.TryGetValue(model, out var plannedPath)
                || !actual.Paths.TryGetValue(model, out var actualPath)
                || !string.Equals(ModelTracePath(plannedPath), ModelTracePath(actualPath), StringComparison.OrdinalIgnoreCase))
                issues.Add($"执行前模型解析路径漂移: {model}");
        }
        return issues;
    }

    private string ResolveWorkflowPath(string path)
    {
        var fullPath = Path.GetFullPath(Path.IsPathRooted(path) ? path : Path.Combine(_settings.WorkflowsPath, path));
        var root = Path.GetFullPath(_settings.WorkflowsPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new WorkflowContractException("WORKFLOW_PATH_UNSAFE", "工作流不在受控工作流目录");
        if (!File.Exists(fullPath)) throw new WorkflowContractException("WORKFLOW_MISSING", $"工作流文件不存在：{Path.GetFileName(fullPath)}");
        return fullPath;
    }

    private IReadOnlyList<WorkflowNodeSnapshot> ValidateGraph(WorkflowContractDefinition contract, JsonObject graph)
    {
        var snapshots = new List<WorkflowNodeSnapshot>();
        foreach (var nodeContract in contract.Nodes)
        {
            if (!graph.TryGetPropertyValue(nodeContract.NodeId, out var node) || node is not JsonObject nodeObject)
            {
                if (nodeContract.Required) throw new WorkflowContractException("GRAPH_NODE_MISSING", $"工作流 {contract.Id} 缺少节点 {nodeContract.Role}({nodeContract.NodeId})");
                continue;
            }
            var classType = nodeObject["class_type"]?.GetValue<string>() ?? "";
            if (!string.Equals(classType, nodeContract.ClassType, StringComparison.OrdinalIgnoreCase))
                throw new WorkflowContractException("GRAPH_NODE_CLASS", $"节点 {nodeContract.Role} 应为 {nodeContract.ClassType}，实际为 {classType}");
            if (nodeContract.InputName is not null)
            {
                if (nodeObject["inputs"] is not JsonObject inputs)
                    throw new WorkflowContractException("GRAPH_INPUT_MISSING", $"节点 {nodeContract.Role} 缺少 inputs");
                if (!inputs.ContainsKey(nodeContract.InputName))
                    throw new WorkflowContractException("GRAPH_INPUT_MISSING", $"节点 {nodeContract.Role} 缺少输入 {nodeContract.InputName}");
            }
            snapshots.Add(new(nodeContract.Role, nodeContract.NodeId, classType, nodeContract.InputName));
        }
        foreach (var slot in contract.Slots)
        {
            if (!graph.TryGetPropertyValue(slot.NodeId, out var node) || node is not JsonObject nodeObject)
                throw new WorkflowContractException("SLOT_NODE_MISSING", $"输入槽位 {slot.Role} 节点不存在");
            var classType = nodeObject["class_type"]?.GetValue<string>() ?? "";
            if (!string.Equals(classType, slot.ClassType, StringComparison.OrdinalIgnoreCase))
                throw new WorkflowContractException("SLOT_NODE_CLASS", $"输入槽位 {slot.Role} 节点类型不匹配");
            if (nodeObject["inputs"] is not JsonObject inputs || !inputs.ContainsKey(slot.InputName))
                throw new WorkflowContractException("SLOT_INPUT_MISSING", $"输入槽位 {slot.Role} 缺少输入 {slot.InputName}");
        }
        return snapshots;
    }

    private IEnumerable<string> FindModel(string fileName)
    {
        if (!Directory.Exists(_settings.ModelsPath)) return [];
        return Directory.EnumerateFiles(_settings.ModelsPath, "*", SearchOption.AllDirectories)
            .Where(path => string.Equals(Path.GetFileName(path), Path.GetFileName(fileName), StringComparison.OrdinalIgnoreCase));
    }

    private ModelResolution ResolveModels(WorkflowContractDefinition contract, bool forceRefresh = false)
    {
        var paths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var hashes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var issues = new List<(string Code, string Message)>();
        foreach (var model in contract.ModelFiles.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (!contract.ModelSha256.TryGetValue(model, out var expected) || !IsSha256(expected))
            {
                issues.Add(("WORKFLOW_MODEL_FINGERPRINT_MISSING", $"工作流 {contract.Id} 未登记模型 {model} 的权重哈希"));
                continue;
            }
            var candidates = FindModel(model).Where(File.Exists).ToArray();
            if (candidates.Length == 0)
            {
                issues.Add(("WORKFLOW_MODEL_MISSING", $"工作流 {contract.Id} 缺少模型文件：{model}"));
                continue;
            }
            // ComfyUI receives a basename, not an absolute model path. Even if
            // exactly one copy has the expected hash, another same-named file
            // can win ComfyUI's search order. Fail closed on every duplicate.
            if (candidates.Length != 1)
            {
                issues.Add(("WORKFLOW_MODEL_AMBIGUOUS", $"工作流 {contract.Id} 的模型文件名对应多个解析路径，无法证明 ComfyUI 实际加载哪一份：{model}"));
                continue;
            }
            var actualPath = candidates[0];
            string actualHash;
            try { actualHash = _modelHashCache.Get(actualPath, forceRefresh); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or SecurityException)
            {
                issues.Add(("WORKFLOW_MODEL_READ_FAILED", $"工作流 {contract.Id} 的模型权重无法读取：{model}（{ex.GetType().Name}）"));
                continue;
            }
            if (!string.Equals(actualHash, expected, StringComparison.OrdinalIgnoreCase))
            {
                issues.Add(("WORKFLOW_MODEL_HASH_MISMATCH", $"工作流 {contract.Id} 的模型权重哈希不匹配：{model}"));
                continue;
            }
            paths[model] = actualPath;
            hashes[model] = actualHash;
        }
        return new ModelResolution(paths, hashes, issues);
    }

    private static bool HasLegacyReferenceInput(JsonElement parameters)
        => (TryGet(parameters, "referenceImages", out var refs) && refs.ValueKind != JsonValueKind.Null && (refs.ValueKind != JsonValueKind.Array || refs.GetArrayLength() > 0))
            || (TryGet(parameters, "controlImages", out var controls) && controls.ValueKind != JsonValueKind.Null && (controls.ValueKind != JsonValueKind.Array || controls.GetArrayLength() > 0))
            || TryGet(parameters, "controlImagePath", out var control) && control.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(control.GetString());

    private static string ExtractExpectedHash(WorkflowContractDefinition contract)
        => contract.Notes.Split('|', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
            .FirstOrDefault(value => value.StartsWith("sha256=", StringComparison.OrdinalIgnoreCase))?[7..] ?? "";

    private static string ComputeSha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private string ModelTracePath(string path)
    {
        var fullPath = Path.GetFullPath(path);
        var root = Path.GetFullPath(_settings.ModelsPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase)
            ? Path.GetRelativePath(_settings.ModelsPath, fullPath).Replace(Path.DirectorySeparatorChar, '/')
            : fullPath;
    }

    public string CurrentRuntimeDependencyFingerprint()
    {
        var versionFile = Path.Combine(_settings.ComfyRoot, "comfyui_version.py");
        var version = "unknown";
        if (File.Exists(versionFile))
        {
            var line = File.ReadLines(versionFile).FirstOrDefault(value => value.Contains("__version__", StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrWhiteSpace(line)) version = line.Trim();
        }
        var parts = new[]
        {
            $"server-runtime:{Environment.Version}",
            $"comfy-version:{version}",
            $"comfy-version-file:{OptionalFileSha(versionFile)}",
            $"comfy-requirements:{OptionalFileSha(Path.Combine(_settings.ComfyRoot, "requirements.txt"))}",
            $"comfy-pyproject:{OptionalFileSha(Path.Combine(_settings.ComfyRoot, "pyproject.toml"))}"
        };
        return Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(string.Join("|", parts)))).ToLowerInvariant();
    }

    private static string OptionalFileSha(string path)
    {
        if (!File.Exists(path)) return "missing";
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static bool IsSha256(string? value)
        => !string.IsNullOrWhiteSpace(value) && value.Length == 64 && value.All(character => Uri.IsHexDigit(character));

    private static int? ReadInt(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.TryGetInt32(out var result) ? result : null;

    private static double? ReadDouble(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.TryGetDouble(out var result) ? result : null;

    private static string? ReadString(JsonElement root, string name)
        => TryGet(root, name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static bool TryGet(JsonElement root, string name, out JsonElement value)
    {
        if (root.ValueKind == JsonValueKind.Object)
            foreach (var property in root.EnumerateObject())
                if (string.Equals(property.Name, name, StringComparison.OrdinalIgnoreCase)) { value = property.Value; return true; }
        value = default;
        return false;
    }
}
