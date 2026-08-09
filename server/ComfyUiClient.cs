using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

public sealed class ComfyUiClient
{
    private readonly HttpClient _http;
    private readonly StudioSettings _settings;
    private readonly ILogger<ComfyUiClient> _logger;

    public ComfyUiClient(HttpClient http, StudioSettings settings, ILogger<ComfyUiClient> logger)
    {
        _http = http;
        _settings = settings;
        _logger = logger;
    }

    public async Task<ComfySnapshot> CheckAsync(CancellationToken ct = default)
    {
        try
        {
            using var response = await _http.GetAsync("/system_stats", ct);
            if (!response.IsSuccessStatusCode) return new ComfySnapshot(false, null, $"HTTP {(int)response.StatusCode}", null);
            var json = JsonNode.Parse(await response.Content.ReadAsStringAsync(ct));
            var device = json?["devices"]?.AsArray().FirstOrDefault();
            var gpu = device is null ? null : new GpuSnapshot(
                device["name"]?.GetValue<string>() ?? "CUDA",
                ToLong(device["vram_total"]), ToLong(device["vram_free"]), ToDouble(device["utilization"]));
            return new ComfySnapshot(true, json?["system"]?["python_version"]?.GetValue<string>(), null, gpu);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "ComfyUI health check failed");
            return new ComfySnapshot(false, null, ex.Message, null);
        }
    }

    public async Task<string> QueueAsync(JsonObject workflow, CancellationToken ct = default)
    {
        var body = new JsonObject
        {
            ["prompt"] = workflow,
            ["client_id"] = "video-studio"
        };
        using var response = await _http.PostAsJsonAsync("/prompt", body, cancellationToken: ct);
        var text = await response.Content.ReadAsStringAsync(ct);
        if (!response.IsSuccessStatusCode) throw new InvalidOperationException($"ComfyUI 提交失败 HTTP {(int)response.StatusCode}: {TrimError(text)}");
        var result = JsonNode.Parse(text);
        var promptId = result?["prompt_id"]?.GetValue<string>();
        if (string.IsNullOrWhiteSpace(promptId)) throw new InvalidOperationException($"ComfyUI 未返回 prompt_id: {TrimError(text)}");
        return promptId;
    }

    public async Task<JsonObject> WaitForHistoryAsync(string promptId, Action<ComfySnapshot>? sample, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var snapshot = await CheckAsync(ct);
            sample?.Invoke(snapshot);
            using var response = await _http.GetAsync($"/history/{Uri.EscapeDataString(promptId)}", ct);
            if (response.IsSuccessStatusCode)
            {
                var root = JsonNode.Parse(await response.Content.ReadAsStringAsync(ct))?.AsObject();
                if (root?[promptId] is JsonObject history)
                {
                    var status = history["status"]?.AsObject();
                    var completed = status?["completed"]?.GetValue<bool>() ?? false;
                    var statusStr = status?["status_str"]?.GetValue<string>();
                    if (completed || history["outputs"] is JsonObject)
                    {
                        var messages = status?["messages"]?.ToJsonString() ?? "";
                        if (string.Equals(statusStr, "error", StringComparison.OrdinalIgnoreCase) || messages.Contains("error", StringComparison.OrdinalIgnoreCase))
                            throw new InvalidOperationException($"ComfyUI 任务失败: {TrimError(messages)}");
                        return history;
                    }
                }
            }
            await Task.Delay(_settings.QueuePollMilliseconds, ct);
        }
        throw new OperationCanceledException(ct);
    }

    public async Task<List<GenerationFile>> DownloadOutputsAsync(JsonObject history, string targetDirectory, string prefix, CancellationToken ct = default)
    {
        Directory.CreateDirectory(targetDirectory);
        var files = new List<GenerationFile>();
        var outputs = history["outputs"]?.AsObject();
        if (outputs is null) return files;
        foreach (var node in outputs)
        {
            if (node.Value is not JsonObject output) continue;
            foreach (var collectionName in new[] { "images", "gifs", "videos" })
            {
                if (output[collectionName] is not JsonArray collection) continue;
                foreach (var item in collection)
                {
                    if (item is not JsonObject file) continue;
                    var filename = file["filename"]?.GetValue<string>();
                    if (string.IsNullOrWhiteSpace(filename)) continue;
                    var subfolder = file["subfolder"]?.GetValue<string>() ?? "";
                    var type = file["type"]?.GetValue<string>() ?? "output";
                    var extension = Path.GetExtension(filename);
                    if (string.IsNullOrWhiteSpace(extension)) extension = collectionName == "images" ? ".png" : ".webp";
                    var safeName = SanitizeFileName($"{prefix}_{Path.GetFileNameWithoutExtension(filename)}{extension}");
                    var target = Path.Combine(targetDirectory, safeName);
                    var query = $"/view?filename={Uri.EscapeDataString(filename)}&subfolder={Uri.EscapeDataString(subfolder)}&type={Uri.EscapeDataString(type)}";
                    using var response = await _http.GetAsync(query, ct);
                    if (!response.IsSuccessStatusCode) throw new InvalidOperationException($"下载 ComfyUI 输出失败 HTTP {(int)response.StatusCode}");
                    await using var stream = await response.Content.ReadAsStreamAsync(ct);
                    await using var outputStream = File.Create(target);
                    await stream.CopyToAsync(outputStream, ct);
                    files.Add(new GenerationFile(target, safeName, collectionName, response.Content.Headers.ContentType?.MediaType));
                }
            }
        }
        return files;
    }

    public async Task InterruptAsync(CancellationToken ct = default)
    {
        using var response = await _http.PostAsync("/interrupt", null, ct);
        _logger.LogInformation("ComfyUI interrupt requested: {Status}", response.StatusCode);
    }

    public async Task TryFreeMemoryAsync(CancellationToken ct = default)
    {
        try
        {
            using var content = JsonContent.Create(new { unload_models = true, free_memory = true });
            using var response = await _http.PostAsync("/free", content, ct);
            _logger.LogDebug("ComfyUI memory release requested: {Status}", response.StatusCode);
        }
        catch (Exception ex) { _logger.LogDebug(ex, "ComfyUI memory release endpoint is unavailable"); }
    }

    public static JsonObject LoadWorkflow(string path)
    {
        var root = JsonNode.Parse(File.ReadAllText(path))?.AsObject() ?? throw new InvalidDataException("工作流 JSON 不是对象");
        if (root["prompt"] is JsonObject prompt) return prompt;
        return root;
    }

    public static void PatchWorkflow(JsonObject workflow, string taskType, string? positive, string? negative, string? inputImage, JsonElement parameters, string outputPrefix)
    {
        var values = parameters.ValueKind == JsonValueKind.Object ? parameters : JsonDocument.Parse("{}").RootElement;
        var prompt = FirstString(values, "positive", "prompt") ?? positive;
        var neg = FirstString(values, "negative", "negativePrompt") ?? negative;
        var seed = FirstLong(values, "seed");
        var width = FirstInt(values, "width");
        var height = FirstInt(values, "height");
        var frames = FirstInt(values, "frames", "length");
        var cfg = FirstDouble(values, "cfg", "cfgScale");
        var steps = FirstInt(values, "steps");
        var clipTextNodes = workflow
            .Where(pair => pair.Value is JsonObject candidate && string.Equals(candidate["class_type"]?.GetValue<string>(), "CLIPTextEncode", StringComparison.OrdinalIgnoreCase))
            .Select(pair => pair.Value!.AsObject())
            .ToList();
        for (var clipIndex = 0; clipIndex < clipTextNodes.Count; clipIndex++)
        {
            var inputs = clipTextNodes[clipIndex]["inputs"]?.AsObject();
            if (inputs is null) continue;
            if (clipIndex == 0 && prompt is not null) Set(inputs, "text", prompt);
            if (clipIndex > 0 && neg is not null) Set(inputs, "text", neg);
        }
        foreach (var node in workflow)
        {
            if (node.Value is not JsonObject obj || obj["inputs"] is not JsonObject inputs) continue;
            var classType = obj["class_type"]?.GetValue<string>() ?? "";
            if (inputImage is not null && classType.Contains("LoadImage", StringComparison.OrdinalIgnoreCase)) Set(inputs, "image", Path.GetFileName(inputImage));
            if (seed.HasValue && (inputs.ContainsKey("seed") || classType.Contains("KSampler", StringComparison.OrdinalIgnoreCase)))
            {
                if (inputs.ContainsKey("seed")) Set(inputs, "seed", seed.Value);
                if (inputs.ContainsKey("noise_seed")) Set(inputs, "noise_seed", seed.Value);
            }
            if (width.HasValue && inputs.ContainsKey("width")) Set(inputs, "width", width.Value);
            if (height.HasValue && inputs.ContainsKey("height")) Set(inputs, "height", height.Value);
            if (frames.HasValue && (inputs.ContainsKey("length") || classType.Contains("ImgToVideo", StringComparison.OrdinalIgnoreCase)))
            {
                if (inputs.ContainsKey("length")) Set(inputs, "length", frames.Value);
                if (inputs.ContainsKey("num_frames")) Set(inputs, "num_frames", frames.Value);
            }
            if (cfg.HasValue && inputs.ContainsKey("cfg")) Set(inputs, "cfg", cfg.Value);
            if (steps.HasValue && inputs.ContainsKey("steps")) Set(inputs, "steps", steps.Value);
            if (classType.Contains("Save", StringComparison.OrdinalIgnoreCase) || classType.Contains("Preview", StringComparison.OrdinalIgnoreCase))
                if (inputs.ContainsKey("filename_prefix")) Set(inputs, "filename_prefix", outputPrefix);
        }
    }

    private static void Set(JsonObject inputs, string key, object? value)
    {
        inputs[key] = JsonValue.Create(value);
    }

    private static string? FirstString(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null).FirstOrDefault(v => !string.IsNullOrWhiteSpace(v));
    private static long? FirstLong(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.TryGetInt64(out var result) ? result : (long?)null).FirstOrDefault(v => v.HasValue);
    private static int? FirstInt(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.TryGetInt32(out var result) ? result : (int?)null).FirstOrDefault(v => v.HasValue);
    private static double? FirstDouble(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.TryGetDouble(out var result) ? result : (double?)null).FirstOrDefault(v => v.HasValue);
    private static long ToLong(JsonNode? node) => node is null ? 0 : node.GetValue<long>() / (1024 * 1024);
    private static double ToDouble(JsonNode? node) => node is null ? 0 : node.GetValue<double>();
    private static string SanitizeFileName(string value) => string.Join('_', value.Split(Path.GetInvalidFileNameChars(), StringSplitOptions.RemoveEmptyEntries));
    private static string TrimError(string text) => text.Length > 1000 ? text[..1000] : text;
}
