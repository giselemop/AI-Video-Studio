using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

public sealed class WorkflowCatalog
{
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly WorkflowContractService _contracts;
    private readonly ILogger<WorkflowCatalog> _logger;

    public WorkflowCatalog(StudioSettings settings, StudioRepository repository, WorkflowContractService contracts, ILogger<WorkflowCatalog> logger)
    {
        _settings = settings;
        _repository = repository;
        _contracts = contracts;
        _logger = logger;
    }

    public async Task<int> ScanAsync(CancellationToken ct = default)
    {
        var count = 0;
        if (Directory.Exists(_settings.WorkflowsPath))
        {
            foreach (var file in Directory.EnumerateFiles(_settings.WorkflowsPath, "*.json", SearchOption.AllDirectories))
            {
                try
                {
                    var name = Path.GetFileNameWithoutExtension(file);
                    var type = _contracts.Find(file)?.WorkflowType ?? InferType(name);
                    var model = ExtractModel(file);
                    await _repository.UpsertWorkflowAsync(name, type, file, model, MappingFor(type), ct);
                    count++;
                }
                catch (Exception ex) { _logger.LogWarning("扫描工作流失败 {File}: {Message}", file, ex.Message); }
            }
        }
        if (Directory.Exists(_settings.ModelsPath))
        {
            foreach (var file in Directory.EnumerateFiles(_settings.ModelsPath, "*.*", SearchOption.AllDirectories).Where(IsModelFile))
            {
                try { await _repository.UpsertModelAsync(Path.GetFileName(file), InferModelType(file), file, new FileInfo(file).Length, ct); } catch (Exception ex) { _logger.LogDebug(ex, "扫描模型失败"); }
            }
        }
        var loraRoot = Path.Combine(_settings.ModelsPath, "loras");
        if (Directory.Exists(loraRoot))
        {
            foreach (var file in Directory.EnumerateFiles(loraRoot, "*.*", SearchOption.AllDirectories).Where(IsModelFile))
            {
                try { await _repository.UpsertLoraAsync(Path.GetFileName(file), file, ct); }
                catch (Exception ex) { _logger.LogDebug(ex, "LoRA catalog scan failed"); }
            }
        }
        return count;
    }

    private static string InferType(string name)
    {
        var n = name.ToLowerInvariant();
        if (n.Contains("i2v") || n.Contains("image to video") || n.Contains("video") || n.Contains("character_lock") || n.Contains("face_stable")) return "ImageToVideo";
        if (n.Contains("controlnet")) return "Image";
        if (n.Contains("upscale") || n.Contains("enhance")) return "Enhancement";
        if (n.Contains("pose") || n.Contains("motion")) return "Motion";
        if (n.Contains("inpaint") || n.Contains("edit")) return "ImageEdit";
        return "Image";
    }

    private static string? ExtractModel(string file)
    {
        try
        {
            var root = JsonNode.Parse(File.ReadAllText(file));
            foreach (var node in Enumerate(root))
                if (node is JsonValue value && value.TryGetValue<string>(out var text) && (text.EndsWith(".safetensors", StringComparison.OrdinalIgnoreCase) || text.EndsWith(".gguf", StringComparison.OrdinalIgnoreCase) || text.EndsWith(".ckpt", StringComparison.OrdinalIgnoreCase) || text.EndsWith(".pth", StringComparison.OrdinalIgnoreCase) || text.EndsWith(".bin", StringComparison.OrdinalIgnoreCase))) return text;
        }
        catch { }
        return null;
    }

    private static IEnumerable<JsonNode?> Enumerate(JsonNode? node)
    {
        if (node is null) yield break;
        yield return node;
        if (node is JsonObject obj) foreach (var item in obj) foreach (var child in Enumerate(item.Value)) yield return child;
        if (node is JsonArray array) foreach (var item in array) foreach (var child in Enumerate(item)) yield return child;
    }

    private static string MappingFor(string type) => type switch
    {
        "ImageToVideo" => "{\"positiveNode\":\"6\",\"negativeNode\":\"7\",\"imageNode\":\"78\",\"seedNodes\":[\"72\",\"5\"],\"outputNodes\":[\"41\"]}",
        "Image" => "{\"positiveNode\":\"2\",\"negativeNode\":\"3\",\"seedNodes\":[\"5\"],\"outputNodes\":[\"7\"]}",
        _ => "{}"
    };

    private static bool IsModelFile(string path) => new[] { ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx" }.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase);
    private static string InferModelType(string path) => new DirectoryInfo(Path.GetDirectoryName(path)!).Name.ToLowerInvariant() switch { "checkpoints" => "checkpoint", "diffusion_models" => "diffusion", "vae" => "vae", "text_encoders" => "text_encoder", "loras" => "lora", "ipadapter" => "ipadapter", "controlnet" => "controlnet", "video_models" => "video", _ => "model" };
}
