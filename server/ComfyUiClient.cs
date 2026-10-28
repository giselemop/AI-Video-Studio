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
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
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
                    var temporary = $"{target}.part-{Guid.NewGuid():N}";
                    try
                    {
                        string? contentType;
                        // Close the HTTP response and the temporary file before publishing.
                        // Windows will otherwise keep the destination move locked even after
                        // the bytes have been copied, which makes every real ComfyUI result
                        // fail during the download/publish boundary.
                        using (var response = await _http.GetAsync(query, HttpCompletionOption.ResponseHeadersRead, ct))
                        {
                            if (!response.IsSuccessStatusCode) throw new InvalidOperationException($"下载 ComfyUI 输出失败 HTTP {(int)response.StatusCode}");
                            contentType = response.Content.Headers.ContentType?.MediaType;
                            await using (var stream = await response.Content.ReadAsStreamAsync(ct))
                            await using (var outputStream = File.Create(temporary))
                            {
                                await stream.CopyToAsync(outputStream, ct);
                                await outputStream.FlushAsync(ct);
                            }
                        }
                        if (!File.Exists(temporary) || new FileInfo(temporary).Length == 0) throw new InvalidDataException("ComfyUI output download was empty");
                        File.Move(temporary, target, false);
                        files.Add(new GenerationFile(target, safeName, collectionName, contentType));
                    }
                    finally
                    {
                        try { if (File.Exists(temporary)) File.Delete(temporary); } catch { }
                    }
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

    public async Task EnsureIdleForExternalGpuAsync(CancellationToken ct = default)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(8));
        try
        {
            using var response = await _http.GetAsync("/queue", timeout.Token);
            response.EnsureSuccessStatusCode();
            var queue = JsonNode.Parse(await response.Content.ReadAsStringAsync(timeout.Token));
            if (queue?["queue_running"] is not JsonArray running || queue["queue_pending"] is not JsonArray pending)
                throw new InvalidOperationException("无法确认 ComfyUI 队列状态，尚未启动 Qwen3-TTS");
            if (running.Count > 0 || pending.Count > 0)
                throw new InvalidOperationException("ComfyUI 仍有运行或等待中的任务，请空闲后再生成 Qwen3-TTS 配音");
        }
        catch (HttpRequestException ex) when (ex.HttpRequestError == HttpRequestError.ConnectionError)
        {
            // Qwen also works when ComfyUI is stopped; CUDA memory is checked in the child process.
        }
    }

    public static JsonObject LoadWorkflow(string path)
    {
        var root = JsonNode.Parse(File.ReadAllText(path))?.AsObject() ?? throw new InvalidDataException("工作流 JSON 不是对象");
        if (root["prompt"] is JsonObject prompt) return prompt;
        return root;
    }

    public static int PatchWorkflow(JsonObject workflow, string taskType, string? positive, string? negative, string? inputImage, IReadOnlyList<string>? referenceImages, IReadOnlyList<LoraBinding>? loras, JsonElement parameters, string outputPrefix, WorkflowExecutionPlan? contractPlan = null)
    {
        var values = parameters.ValueKind == JsonValueKind.Object ? parameters : JsonDocument.Parse("{}").RootElement;
        H3WorkflowPolicy.Validate(workflow, values);
        if (H3WorkflowPolicy.IsH3(workflow))
        {
            // Slot ordering is not an identity-role contract. Do not silently bind
            // multiple references to first/last frames during the initial trial.
            var referenceCount = referenceImages?.Count(x => !string.IsNullOrWhiteSpace(x)) ?? 0;
            if (referenceCount > 1 || (inputImage is not null && referenceCount > 0))
                throw new InvalidOperationException("H3 首轮只接受一张首帧；多参考和首尾帧角色绑定尚未验收");
        }
        var prompt = FirstString(values, "positive", "prompt") ?? positive;
        var neg = FirstString(values, "negative", "negativePrompt") ?? negative;
        var seed = FirstLong(values, "seed");
        var width = FirstInt(values, "width");
        var height = FirstInt(values, "height");
        var frames = contractPlan?.ExecutionLength ?? FirstInt(values, "frames", "length");
        var cfg = FirstDouble(values, "cfg", "cfgScale");
        var steps = FirstInt(values, "steps");
        var fps = FirstDouble(values, "fps");
        var denoise = FirstDouble(values, "denoise");
        var inputStrength = FirstDouble(values, "inputStrength", "i2vStrength");
        var guideStrength = FirstDouble(values, "guideStrength", "referenceStrength");
        var identityStrength = FirstDouble(values, "identityControlStrength", "ipAdapterWeight");
        var guideFrameIndex = contractPlan?.GuideFrameIndex ?? FirstInt(values, "guideFrameIndex");
        // Shot records are shared by landscape video jobs and portrait image
        // jobs. Do not let a landscape shot size overwrite the native portrait
        // latent; that creates cropped faces and contact-sheet-like outputs.
        var nativePortraitCanvas = contractPlan is null
            && !taskType.Contains("video", StringComparison.OrdinalIgnoreCase)
            && !taskType.Contains("i2v", StringComparison.OrdinalIgnoreCase)
            && workflow.Any(pair => pair.Value is JsonObject candidate
                && string.Equals(candidate["class_type"]?.GetValue<string>(), "EmptyLatentImage", StringComparison.OrdinalIgnoreCase)
                && candidate["inputs"] is JsonObject latentInputs
                && (latentInputs["width"]?.GetValue<int>() ?? 0) >= 576
                && (latentInputs["height"]?.GetValue<int>() ?? 0) >= 768);
        if (nativePortraitCanvas)
        {
            width = null;
            height = null;
        }
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
        if (contractPlan is not null)
        {
            foreach (var promptNode in contractPlan.Nodes.Where(node => node.Role is "positivePrompt" or "negativePrompt"))
            {
                if (workflow[promptNode.NodeId] is not JsonObject node || node["inputs"] is not JsonObject inputs) continue;
                var text = promptNode.Role == "positivePrompt" ? prompt : neg;
                if (text is not null && promptNode.InputName is not null) Set(inputs, promptNode.InputName, text);
            }
        }
        var loadImageInputs = workflow
            .Where(pair => pair.Value is JsonObject candidate && candidate["inputs"] is JsonObject && string.Equals(candidate["class_type"]?.GetValue<string>(), "LoadImage", StringComparison.OrdinalIgnoreCase))
            .Select(pair => pair.Value!["inputs"]!.AsObject())
            .ToList();
        var references = referenceImages?.Where(x => !string.IsNullOrWhiteSpace(x)).ToList() ?? [];
        var appliedReferences = 0;
        if (contractPlan is not null)
        {
            foreach (var slot in contractPlan.Slots)
            {
                if (!contractPlan.SlotPaths.TryGetValue(slot.Role, out var slotPath) || string.IsNullOrWhiteSpace(slotPath))
                {
                    if (slot.Required) throw new InvalidOperationException($"工作流契约槽位 {slot.Role} 没有可绑定文件");
                    continue;
                }
                if (workflow[slot.NodeId] is not JsonObject node || node["inputs"] is not JsonObject inputs || !inputs.ContainsKey(slot.InputName))
                    throw new InvalidOperationException($"工作流契约槽位 {slot.Role} 的节点输入发生漂移");
                Set(inputs, slot.InputName, Path.GetFileName(slotPath));
                appliedReferences++;
            }
        }
        else if (loadImageInputs.Count > 0)
        {
            if (inputImage is not null) Set(loadImageInputs[0], "image", Path.GetFileName(inputImage));
            var referenceStart = inputImage is null ? 0 : 1;
            for (var i = 0; i < references.Count && referenceStart + i < loadImageInputs.Count; i++)
            {
                Set(loadImageInputs[referenceStart + i], "image", Path.GetFileName(references[i]));
                appliedReferences++;
            }
        }
        ApplyLoras(workflow, loras);
        foreach (var node in workflow)
        {
            if (node.Value is not JsonObject obj || obj["inputs"] is not JsonObject inputs) continue;
            var classType = obj["class_type"]?.GetValue<string>() ?? "";
            if (classType == "MiniMaxH3ImageToVideo" && prompt is not null) Set(inputs, "prompt", prompt);
            if (seed.HasValue && (inputs.ContainsKey("seed") || inputs.ContainsKey("noise_seed") || classType.Contains("KSampler", StringComparison.OrdinalIgnoreCase)))
            {
                if (inputs.ContainsKey("seed")) Set(inputs, "seed", seed.Value);
                if (inputs.ContainsKey("noise_seed")) Set(inputs, "noise_seed", seed.Value);
            }
            // The native-1080 experiment samples 1088 rows and crops four rows at each edge.
            // Task canvas parameters must not replace the crop's delivery geometry.
            var fixedNativeCrop = classType == "ImageCrop" && parameters.ValueKind == JsonValueKind.Object
                && parameters.TryGetProperty("profile", out var cropProfile) && cropProfile.ValueKind == JsonValueKind.String
                && cropProfile.GetString() == "native1080";
            if (!fixedNativeCrop && width.HasValue && inputs.ContainsKey("width")) Set(inputs, "width", width.Value);
            if (!fixedNativeCrop && height.HasValue && inputs.ContainsKey("height")) Set(inputs, "height", height.Value);
            if (frames.HasValue && (inputs.ContainsKey("length") || classType.Contains("ImgToVideo", StringComparison.OrdinalIgnoreCase)))
            {
                if (inputs.ContainsKey("length")) Set(inputs, "length", frames.Value);
                if (inputs.ContainsKey("num_frames")) Set(inputs, "num_frames", frames.Value);
            }
            if (inputs.ContainsKey("frame_idx"))
            {
                var resolvedGuideFrame = guideFrameIndex ?? (frames.HasValue ? Math.Max(1, frames.Value - 1) : (int?)null);
                if (resolvedGuideFrame.HasValue && classType.Contains("AddGuide", StringComparison.OrdinalIgnoreCase))
                    Set(inputs, "frame_idx", Math.Clamp(resolvedGuideFrame.Value, 1, Math.Max(1, (frames ?? resolvedGuideFrame.Value + 1) - 1)));
            }
            if (cfg.HasValue && inputs.ContainsKey("cfg")) Set(inputs, "cfg", cfg.Value);
            if (steps.HasValue && inputs.ContainsKey("steps")) Set(inputs, "steps", steps.Value);
            if (fps.HasValue && inputs.ContainsKey("fps")) Set(inputs, "fps", fps.Value);
            if (denoise.HasValue && inputs.ContainsKey("denoise")) Set(inputs, "denoise", denoise.Value);
            if (inputStrength.HasValue && classType.Contains("ImgToVideo", StringComparison.OrdinalIgnoreCase) && inputs.ContainsKey("strength")) Set(inputs, "strength", inputStrength.Value);
            if (guideStrength.HasValue && classType.Contains("AddGuide", StringComparison.OrdinalIgnoreCase) && inputs.ContainsKey("strength")) Set(inputs, "strength", guideStrength.Value);
            if (identityStrength.HasValue && classType.Contains("IPAdapter", StringComparison.OrdinalIgnoreCase) && inputs.ContainsKey("weight")) Set(inputs, "weight", identityStrength.Value);
            if (classType.Contains("Save", StringComparison.OrdinalIgnoreCase) || classType.Contains("Preview", StringComparison.OrdinalIgnoreCase))
                if (inputs.ContainsKey("filename_prefix")) Set(inputs, "filename_prefix", outputPrefix);
        }
        CharacterSceneService.ApplyGeometry(workflow,values,contractPlan);
        return appliedReferences;
    }

    private static void ApplyLoras(JsonObject workflow, IReadOnlyList<LoraBinding>? bindings)
    {
        if (bindings is null || bindings.Count == 0) return;
        var existing = workflow
            .Where(pair => pair.Value is JsonObject candidate && string.Equals(candidate["class_type"]?.GetValue<string>(), "LoraLoader", StringComparison.OrdinalIgnoreCase))
            .Select(pair => pair.Value!.AsObject())
            .ToList();
        if (existing.Count > 0)
        {
            if (existing.Count < bindings.Count) throw new InvalidOperationException("当前工作流中的 LoRA 节点数量不足，不能安全叠加所选 LoRA");
            for (var i = 0; i < bindings.Count; i++)
            {
                var inputs = existing[i]["inputs"]?.AsObject() ?? throw new InvalidOperationException("LoRA 节点缺少 inputs");
                Set(inputs, "lora_name", bindings[i].Name);
                Set(inputs, "strength_model", bindings[i].StrengthModel);
                Set(inputs, "strength_clip", bindings[i].StrengthClip);
            }
            return;
        }

        var checkpoint = workflow.FirstOrDefault(pair => pair.Value is JsonObject candidate && string.Equals(candidate["class_type"]?.GetValue<string>(), "CheckpointLoaderSimple", StringComparison.OrdinalIgnoreCase));
        if (checkpoint.Value is not JsonObject) throw new InvalidOperationException("当前工作流没有 CheckpointLoaderSimple，不能自动接入 LoRA");
        var nextId = workflow.Select(pair => pair.Key).Select(key => int.TryParse(key, out var id) ? id : 0).DefaultIfEmpty(0).Max() + 1;
        var modelNode = checkpoint.Key;
        var clipNode = checkpoint.Key;
        foreach (var binding in bindings)
        {
            var nodeId = nextId++.ToString(System.Globalization.CultureInfo.InvariantCulture);
            workflow[nodeId] = new JsonObject
            {
                ["class_type"] = "LoraLoader",
                ["inputs"] = new JsonObject
                {
                    ["model"] = Link(modelNode, 0),
                    ["clip"] = Link(clipNode, 1),
                    ["lora_name"] = binding.Name,
                    ["strength_model"] = JsonValue.Create(binding.StrengthModel),
                    ["strength_clip"] = JsonValue.Create(binding.StrengthClip)
                }
            };
            ReplaceLinks(workflow, modelNode, 0, nodeId, 0, nodeId);
            ReplaceLinks(workflow, clipNode, 1, nodeId, 1, nodeId);
            modelNode = nodeId;
            clipNode = nodeId;
        }
    }

    private static JsonArray Link(string nodeId, int port) => new(JsonValue.Create(nodeId), JsonValue.Create(port));

    private static void ReplaceLinks(JsonObject workflow, string sourceNode, int sourcePort, string targetNode, int targetPort, string excludedNode)
    {
        foreach (var pair in workflow)
        {
            if (pair.Key == excludedNode || pair.Value is not JsonObject node || node["inputs"] is not JsonObject inputs) continue;
            foreach (var input in inputs.ToList())
            {
                if (input.Value is not JsonArray link || link.Count < 2) continue;
                if (!string.Equals(link[0]?.ToString(), sourceNode, StringComparison.Ordinal) || !int.TryParse(link[1]?.ToString(), out var port) || port != sourcePort) continue;
                inputs[input.Key] = Link(targetNode, targetPort);
            }
        }
    }

    private static void Set(JsonObject inputs, string key, object? value)
    {
        inputs[key] = JsonValue.Create(value);
    }

    private static string? FirstString(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null).FirstOrDefault(v => !string.IsNullOrWhiteSpace(v));
    private static long? FirstLong(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.TryGetInt64(out var result) ? result : (long?)null).FirstOrDefault(v => v.HasValue);
    private static int? FirstInt(JsonElement values, params string[] names) => names.Select(n => values.TryGetProperty(n, out var v) && v.TryGetInt32(out var result) ? result : (int?)null).FirstOrDefault(v => v.HasValue);
    private static double? FirstDouble(JsonElement values, params string[] names) => names
        .Select(n => values.TryGetProperty(n, out var v)
            && v.ValueKind == JsonValueKind.Number
            && v.TryGetDouble(out var result)
                ? result
                : (double?)null)
        .FirstOrDefault(v => v.HasValue);
    private static long ToLong(JsonNode? node) => node is null ? 0 : node.GetValue<long>() / (1024 * 1024);
    private static double ToDouble(JsonNode? node) => node is null ? 0 : node.GetValue<double>();
    private static string SanitizeFileName(string value) => string.Join('_', value.Split(Path.GetInvalidFileNameChars(), StringSplitOptions.RemoveEmptyEntries));
    private static string TrimError(string text) => text.Length > 1000 ? text[..1000] : text;
}
