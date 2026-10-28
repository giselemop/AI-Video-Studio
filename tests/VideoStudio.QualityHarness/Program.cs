using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

var arguments = ParseArgs(args);
if (arguments.ContainsKey("caption-single-pass-regression"))
{
    await CaptionSinglePassRegression.Run();
    return;
}
if (arguments.ContainsKey("visual-acting-regression"))
{
    await VisualActingRegression.Run();
    return;
}
if (arguments.ContainsKey("seedvr2-regression"))
{
    await SeedVr2Regression.Run();
    return;
}
if (arguments.ContainsKey("qwen3-tts-regression"))
{
    await Qwen3TtsRegression.Run();
    return;
}
if (arguments.ContainsKey("local-only-access-regression"))
{
    await LocalOnlyAccessRegression.Run();
    return;
}
if (arguments.ContainsKey("minimax-local-regression"))
{
    await MiniMaxLocalRegression.Run();
    return;
}
if (arguments.TryGetValue("delivery-regression", out var deliveryFfmpeg))
{
    await DeliveryRegression.Run(deliveryFfmpeg);
    return;
}
if (arguments.ContainsKey("h3-regression"))
{
    H3Regression.Run();
    return;
}
if (arguments.ContainsKey("self-test"))
{
    await RunSelfTest();
    return;
}
if (arguments.ContainsKey("atomic-download"))
{
    await RunAtomicDownloadRegressionAsync();
    return;
}

if (arguments.TryGetValue("video-input", out var videoInputPath) && arguments.TryGetValue("video-output", out var videoOutputPath))
{
    await RunVideoQaAsync(videoInputPath, videoOutputPath, arguments.GetValueOrDefault("reference"));
    return;
}

if (arguments.TryGetValue("selector-input", out var selectorInputPath) && arguments.TryGetValue("selector-output", out var selectorOutputPath))
{
    await RunSelectorBenchmarkAsync(selectorInputPath, selectorOutputPath);
    return;
}

if (!arguments.TryGetValue("input", out var inputPath) || !arguments.TryGetValue("output", out var outputPath))
    throw new ArgumentException("Usage: --input <manifest.json> --output <result.json>");

var manifest = JsonSerializer.Deserialize<IdentityManifest>(await File.ReadAllTextAsync(inputPath), JsonOptions())
    ?? throw new InvalidOperationException("Identity manifest is empty.");
var settings = new StudioSettings();
var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
var paths = new AssetPathPolicy(settings, ffmpeg, NullLogger<AssetPathPolicy>.Instance);
var face = new FaceQualityService(settings, ffmpeg, paths, NullLogger<FaceQualityService>.Instance);
var quality = new CharacterQualityService(settings, ffmpeg, face, paths, NullLogger<CharacterQualityService>.Instance);
var results = await quality.EvaluateBatchAsync(new CharacterQaBatchInput
{
    MasterPath = manifest.MasterPath,
    IdentityThreshold = manifest.IdentityThreshold,
    Candidates = manifest.Candidates
        .Select(x => new CharacterQaCandidateInput
        {
            Path = x.Path,
            CandidateId = x.CandidateId,
            RequestedView = x.RequestedView,
            SourcePrompt = x.SourcePrompt,
            Seed = x.Seed
        }).ToList()
});
var pack = CharacterQualityService.BuildGoldenPack(manifest.CharacterId, manifest.MasterPath, manifest.IdentityThreshold, results);
var report = new
{
    schemaVersion = "2026-08-16.character-identity-qa.v1",
    generatedAt = DateTimeOffset.Now,
    characterId = manifest.CharacterId,
    master = manifest.MasterPath,
    embeddingModel = pack.EmbeddingModel,
    scoreRange = pack.ScoreRange,
    identityThreshold = manifest.IdentityThreshold,
    calibrationCases = manifest.CalibrationCases,
    candidates = results,
    goldenPack = pack,
    loraStatus = pack.LoraStatus,
    manualReviewRequired = true
};
Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? ".");
await File.WriteAllTextAsync(outputPath, JsonSerializer.Serialize(report, JsonOptions()));
Console.WriteLine(JsonSerializer.Serialize(new
{
    output = outputPath,
    total = results.Count,
    accepted = results.Count(x => x.Accepted),
    hardRejected = results.Count(x => x.HardRejects.Count > 0),
    detectedViews = results.GroupBy(x => x.DetectedView).ToDictionary(x => x.Key, x => x.Count()),
    goldenStatus = pack.Validation.Status,
    loraStatus = pack.LoraStatus
}, JsonOptions()));

static Dictionary<string, string> ParseArgs(string[] args)
{
    var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    for (var i = 0; i < args.Length; i++)
    {
        if (!args[i].StartsWith("--", StringComparison.Ordinal)) continue;
        var key = args[i][2..];
        result[key] = i + 1 < args.Length && !args[i + 1].StartsWith("--", StringComparison.Ordinal) ? args[++i] : "true";
    }
    return result;
}

static JsonSerializerOptions JsonOptions() => new(JsonSerializerDefaults.Web)
{
    WriteIndented = true,
    Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
};

static async Task RunSelfTest()
{
    Require(ManualQaGate.Validate("Passed", "NeedReview", 1, "{\"status\":\"Rejected\"}", false, "note") is not null, "intermediate NeedReview must not erase automatic rejection");
    Require(ManualQaGate.Validate("Approved", "NeedReview", 0, "{}", true, "note") is not null, "unverified episode must not approve");
    Require(ManualQaGate.Validate("Passed", "Rejected", 1, "{\"status\":\"Rejected\",\"technical\":{\"hardFailure\":true}}", true, "note") is not null, "technical hard failure must not be overridden");
    Require(ManualQaGate.Validate("Passed", "NeedReview", 1, "invalid", true, "note") is not null, "corrupt evidence must fail closed");
    Require(ManualQaGate.Validate("Passed", "AutoChecking", 2, "{\"status\":\"Passed\"}", false, null) is not null, "old result must not pass during active QA");
    Require(ManualQaGate.Validate("Passed", "NeedReview", 1, "{\"status\":\"NeedReview\"}", false, "reviewed") is null, "completed reviewable evidence must allow human decision");
    var complex = MotionComplexityAnalyzer.Analyze("女人走到桌边，转身坐下，拿起杯子喝水");
    Require(complex.NeedSplit && complex.Complexity == "Complex", "multi-verb action must require split");
    Require(complex.SuggestedSubShots.Count >= 2, "complex action must have suggested subshots");
    var walk = MotionComplexityAnalyzer.Analyze("walk one step");
    Require(walk.NeedSplit && walk.DetectedActions.Contains("walk"), "walk must require split");

    var router = new ModelRouter();
    var simple = router.Resolve(new Dictionary<string, object?> { ["action"] = "blink and breathe", ["referenceRequired"] = true }, 1);
    Require(!simple.NeedSplit && simple.WorkflowVersion == "12_ltx_face_stable_v3", "simple reference route must use LTX");
    var routedComplex = router.Resolve(new Dictionary<string, object?> { ["action"] = "turn then sit", ["referenceRequired"] = true }, 1);
    Require(routedComplex.NeedSplit && routedComplex.WorkflowVersion == "split-shot-gated", "complex route must be gated");
    var driving = router.Resolve(new Dictionary<string, object?> { ["action"] = "driving posture" }, 0);
    Require(driving.NeedSplit && driving.WorkflowVersion == "wan2.2-animate", "driving must target blocked Animate route");

    var front = new GoldenReference("front.png", "Front", .95, .9, 0, .9, .9, .8, true, [], "");
    var left = new GoldenReference("left.png", "Left45", .93, .9, 45, .9, .9, .8, true, [], "");
    var direct = ReferenceSelectorV2.Select(new ReferenceSelectorRequest("Left45", "Medium"), [front, left]);
    Require(!direct.Fallback && direct.SelectedView == "Left45", "selector must prefer qualified requested view");
    var fallback = ReferenceSelectorV2.Select(new ReferenceSelectorRequest("Right45", "Medium"), [front, left]);
    Require(fallback.Fallback && fallback.SelectedView == "Front" && !string.IsNullOrWhiteSpace(fallback.FallbackReason), "selector fallback must be explicit");

    var validation = CharacterQualityService.ValidateGoldenPack([front]);
    Require(!validation.Passed && validation.MissingViews.Contains("Left45"), "incomplete golden pack must not pass");

    var manifest = new ReleaseSourceManifest
    {
        EpisodeId = 7,
        EpisodeQaVersion = 3,
        QaLocked = true,
        Shots =
        [
            new ReleaseShotSnapshot
            {
                ShotId = 11,
                QaVersion = 4,
                WorkflowContractId = "05-wan22-ti2v-5b-v1",
                WorkflowContractVersion = "v1",
                WorkflowSha256 = new string('a', 64),
                ModelFiles = ["model.safetensors"],
                ModelFingerprints = new Dictionary<string, string> { ["model.safetensors"] = new string('b', 64) },
                SlotBindings = [new ReleaseSlotBindingSnapshot { Role = "firstFrame", RelativePath = "Images/first.png", Sha256 = new string('c', 64), AssetId = 31, ManifestId = 41, AssetVersion = 2 }],
                CharacterReferences = [new ReleaseCharacterSnapshot { CharacterId = 3, ReferenceId = 4, RelativePath = "Images/character.png", AssetVersion = 5, AssetSha256 = new string('d', 64), ReviewStatus = "Approved", Reviewer = "reviewer" }]
            }
        ]
    };
    var manifestHash = ReleaseEligibilityService.ComputeSourceManifestSha256(manifest);
    Require(ReleaseCandidatePolicy.SourceSnapshotMatches(manifest, manifestHash), "unchanged release source manifest must match its digest");
    manifest.Shots[0].QaVersion++;
    Require(!ReleaseCandidatePolicy.SourceSnapshotMatches(manifest, manifestHash), "changed shot QA version must invalidate the candidate snapshot");
    Require(QaRetryPolicy.SelectTarget("temporal flicker") == QaRetryParameterTarget.Seed, "temporal failure must target seed only");
    Require(QaRetryPolicy.SelectTarget("identity drift") == QaRetryParameterTarget.ReferenceStrength, "identity failure must target reference strength only");
    Require(QaRetryPolicy.SelectTarget("动作不符合镜头要求") == QaRetryParameterTarget.None, "unmapped action failure must go to explicit human/alternative review");

    var fingerprintDirectory = Path.Combine(Path.GetTempPath(), $"videostudio-model-fingerprint-{Guid.NewGuid():N}");
    Directory.CreateDirectory(fingerprintDirectory);
    var fingerprintPath = Path.Combine(fingerprintDirectory, "same-size-model.bin");
    try
    {
        await File.WriteAllBytesAsync(fingerprintPath, System.Text.Encoding.UTF8.GetBytes("model-v1"));
        var cache = new ModelFingerprintCache();
        var initialHash = cache.Get(fingerprintPath);
        var originalTimestamp = File.GetLastWriteTimeUtc(fingerprintPath);
        await File.WriteAllBytesAsync(fingerprintPath, System.Text.Encoding.UTF8.GetBytes("model-v2"));
        File.SetLastWriteTimeUtc(fingerprintPath, originalTimestamp);
        var refreshedHash = cache.Get(fingerprintPath, forceRefresh: true);
        Require(new FileInfo(fingerprintPath).Length == 8 && !string.Equals(initialHash, refreshedHash, StringComparison.OrdinalIgnoreCase), "forced model fingerprint refresh must detect a same-size/same-mtime replacement");
    }
    finally
    {
        try { if (Directory.Exists(fingerprintDirectory)) Directory.Delete(fingerprintDirectory, true); } catch { }
    }
    Console.WriteLine("VideoStudio quality harness self-test: Passed");
}

static async Task RunAtomicDownloadRegressionAsync()
{
    var payload = System.Text.Encoding.UTF8.GetBytes("atomic-download-regression");
    var targetDirectory = Path.Combine(Path.GetTempPath(), $"videostudio-atomic-{Guid.NewGuid():N}");
    Directory.CreateDirectory(targetDirectory);
    try
    {
        using var http = new HttpClient(new StaticOutputHandler(payload))
        {
            BaseAddress = new Uri("http://127.0.0.1:8188")
        };
        var client = new ComfyUiClient(http, new StudioSettings(), NullLogger<ComfyUiClient>.Instance);
        var history = JsonNode.Parse("{\"outputs\":{\"1\":{\"images\":[{\"filename\":\"sample.png\",\"subfolder\":\"\",\"type\":\"output\"}]}}}")!.AsObject();
        var files = await client.DownloadOutputsAsync(history, targetDirectory, "atomic");
        Require(files.Count == 1, "one ComfyUI output must be published");
        Require(File.Exists(files[0].Path), "published ComfyUI output must exist");
        Require((await File.ReadAllBytesAsync(files[0].Path)).SequenceEqual(payload), "published bytes must match the streamed response");
        Require(!Directory.EnumerateFiles(targetDirectory, "*.part-*", SearchOption.TopDirectoryOnly).Any(), "temporary download files must not remain");
        Console.WriteLine("ComfyUI atomic download/publish regression: Passed");
    }
    finally
    {
        try { if (Directory.Exists(targetDirectory)) Directory.Delete(targetDirectory, true); } catch { }
    }
}

static async Task RunVideoQaAsync(string inputPath, string outputPath, string? referencePath)
{
    var document = JsonSerializer.Deserialize<VideoBenchmarkDocument>(await File.ReadAllTextAsync(inputPath), JsonOptions())
        ?? throw new InvalidOperationException("Video benchmark document is empty.");
    var settings = new StudioSettings();
    var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
    var paths = new AssetPathPolicy(settings, ffmpeg, NullLogger<AssetPathPolicy>.Instance);
    var face = new FaceQualityService(settings, ffmpeg, paths, NullLogger<FaceQualityService>.Instance);
    var rows = new List<object>();
    foreach (var item in document.Results.Where(x => !string.IsNullOrWhiteSpace(x.Path)))
    {
        var evaluation = await face.AnalyzeVideoAsync(item.Path!, referencePath);
        var identity = TryMetric(evaluation.Metrics, "referenceSimilarityProxy");
        var faceStability = TryMetric(evaluation.Metrics, "faceSimilarityToFirstFrame");
        var temporal = TryMetric(evaluation.Metrics, "adjacentFaceSimilarity");
        rows.Add(new
        {
            caseId = item.CaseId,
            seed = item.Seed,
            path = item.Path,
            technicalStatus = item.Status,
            faceProxyStatus = evaluation.Rejected ? "Rejected" : "NeedReview",
            identity = identity is null ? (double?)null : identity.Value / 100d,
            faceStability = faceStability is null ? (double?)null : faceStability.Value / 100d,
            motionSemantic = (string?)null,
            bodyIntegrity = (string?)null,
            temporalStability = temporal is null ? (double?)null : temporal.Value / 100d,
            hReject = evaluation.Issues,
            hardReject = evaluation.Rejected,
            proxyScore = Math.Round((double)evaluation.Score / 100d, 4),
            issues = evaluation.Issues,
            semanticStatus = "Unverified",
            manualReview = "CPU face-region proxy only; motion meaning, body/hand/object continuity and fine identity require human review."
        });
    }
    var report = new
    {
        schemaVersion = "2026-08-16.video-proxy-qa.v1",
        generatedAt = DateTimeOffset.Now,
        input = inputPath,
        reference = referencePath,
        detector = "cpu-face-roi-proxy-no-landmark-model",
        results = rows,
        summary = new
        {
            technicalRows = rows.Count,
            semanticPasses = 0,
            bestOf3Usable = (bool?)null,
            gate = "Unverified-until-human-review",
            manualReviewRequired = true
        }
    };
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? ".");
    await File.WriteAllTextAsync(outputPath, JsonSerializer.Serialize(report, JsonOptions()));
    Console.WriteLine(JsonSerializer.Serialize(new { output = outputPath, rows = rows.Count, semanticPasses = 0, gate = "Unverified-until-human-review" }, JsonOptions()));
}

static async Task RunSelectorBenchmarkAsync(string inputPath, string outputPath)
{
    var document = JsonSerializer.Deserialize<SelectorBenchmarkDocument>(await File.ReadAllTextAsync(inputPath), JsonOptions())
        ?? throw new InvalidOperationException("Selector benchmark document is empty.");
    var rows = document.Cases.Select(item =>
    {
        var selection = ReferenceSelectorV2.Select(
            new ReferenceSelectorRequest(item.RequestedView, item.ShotSize, Action: item.Action),
            document.References);
        var passed = string.Equals(selection.SelectedView, item.ExpectedView, StringComparison.OrdinalIgnoreCase)
            && selection.Fallback == item.ExpectedFallback;
        return new
        {
            caseId = item.CaseId,
            seed = item.Seed,
            requestedView = item.RequestedView,
            shotSize = item.ShotSize,
            action = item.Action,
            expectedView = item.ExpectedView,
            expectedFallback = item.ExpectedFallback,
            selectedReference = selection.SelectedReference,
            selectedView = selection.SelectedView,
            selectionScore = selection.SelectionScore,
            fallback = selection.Fallback,
            fallbackReason = selection.FallbackReason,
            policy = selection.Policy,
            candidateScores = selection.CandidateScores,
            passed
        };
    }).ToList();
    var summary = new
    {
        totalCases = rows.Count,
        passedCases = rows.Count(x => x.passed),
        failedCases = rows.Count(x => !x.passed),
        directRequestedViewCases = rows.Count(x => !x.expectedFallback),
        explicitFallbackCases = rows.Count(x => x.expectedFallback),
        manualReviewRequired = true,
        gate = document.References.Any(x => x.View.Equals("FrontLeft30", StringComparison.OrdinalIgnoreCase)
            || x.View.Equals("FrontRight30", StringComparison.OrdinalIgnoreCase)
            || x.View.Equals("Left45", StringComparison.OrdinalIgnoreCase)
            || x.View.Equals("Right45", StringComparison.OrdinalIgnoreCase)
            || x.View.Equals("HalfBody", StringComparison.OrdinalIgnoreCase)
            || x.View.Equals("FullBody", StringComparison.OrdinalIgnoreCase))
            ? "Conditional-until-human-review"
            : "Blocked-incomplete-golden-pack"
    };
    var report = new
    {
        schemaVersion = "2026-08-16.reference-selector-v2-benchmark.v1",
        generatedAt = DateTimeOffset.Now,
        input = inputPath,
        references = document.References,
        results = rows,
        summary
    };
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? ".");
    await File.WriteAllTextAsync(outputPath, JsonSerializer.Serialize(report, JsonOptions()));
    Console.WriteLine(JsonSerializer.Serialize(new { output = outputPath, summary }, JsonOptions()));
}

static double? TryMetric(Dictionary<string, object?> metrics, string key)
{
    if (!metrics.TryGetValue(key, out var value) || value is null) return null;
    if (value is double d) return d;
    if (value is decimal m) return (double)m;
    if (value is int i) return i;
    return double.TryParse(Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture), out var parsed) ? parsed : null;
}

static void Require(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

sealed class IdentityManifest
{
    public string CharacterId { get; set; } = "15";
    public string MasterPath { get; set; } = "";
    public double IdentityThreshold { get; set; } = .85;
    public List<CalibrationCase> CalibrationCases { get; set; } = [];
    public List<IdentityCandidate> Candidates { get; set; } = [];
}

sealed class CalibrationCase
{
    public string Name { get; set; } = "";
    public string Path { get; set; } = "";
    public string Expected { get; set; } = "";
}

sealed class IdentityCandidate
{
    public string Path { get; set; } = "";
    public string? CandidateId { get; set; }
    public string? RequestedView { get; set; }
    public string? SourcePrompt { get; set; }
    public long? Seed { get; set; }
}

sealed class VideoBenchmarkDocument
{
    public List<VideoBenchmarkRow> Results { get; set; } = [];
}

sealed class VideoBenchmarkRow
{
    public string CaseId { get; set; } = "";
    public long Seed { get; set; }
    public string? Path { get; set; }
    public string Status { get; set; } = "";
}

sealed class SelectorBenchmarkDocument
{
    public List<GoldenReference> References { get; set; } = [];
    public List<SelectorBenchmarkCase> Cases { get; set; } = [];
}

sealed class SelectorBenchmarkCase
{
    public string CaseId { get; set; } = "";
    public int Seed { get; set; }
    public string RequestedView { get; set; } = "Front";
    public string ShotSize { get; set; } = "CloseUp";
    public string? Action { get; set; }
    public string ExpectedView { get; set; } = "Front";
    public bool ExpectedFallback { get; set; }
}

sealed class StaticOutputHandler : HttpMessageHandler
{
    private readonly byte[] _payload;

    public StaticOutputHandler(byte[] payload) => _payload = payload;

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var content = new ByteArrayContent(_payload);
        content.Headers.ContentType = new MediaTypeHeaderValue("image/png");
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = content });
    }
}
