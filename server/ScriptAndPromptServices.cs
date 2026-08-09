using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace VideoStudio.Server;

public interface ILLMProvider
{
    string Name { get; }
    Task<string> CompleteAsync(string systemPrompt, string userPrompt, decimal temperature, int maxTokens, CancellationToken ct = default);
}

/// <summary>
/// OpenAI、DeepSeek 和本地 OpenAI-compatible 服务共用这一适配器。
/// API Key 只在请求头中使用，不进入返回值、日志或前端。
/// </summary>
public sealed class OpenAiCompatibleLlmProvider : ILLMProvider
{
    private readonly HttpClient _client;
    private readonly string _baseUrl;
    private readonly string _model;
    private readonly string _apiKey;

    public OpenAiCompatibleLlmProvider(HttpClient client, string baseUrl, string model, string apiKey, string name)
    {
        _client = client;
        _baseUrl = baseUrl.TrimEnd('/');
        _model = model;
        _apiKey = apiKey;
        Name = name;
    }

    public string Name { get; }

    public async Task<string> CompleteAsync(string systemPrompt, string userPrompt, decimal temperature, int maxTokens, CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl}/chat/completions");
        if (!string.IsNullOrWhiteSpace(_apiKey)) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
        request.Content = new StringContent(JsonSerializer.Serialize(new
        {
            model = _model,
            temperature,
            max_tokens = maxTokens,
            messages = new[] { new { role = "system", content = systemPrompt }, new { role = "user", content = userPrompt } }
        }), Encoding.UTF8, "application/json");
        using var response = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        var body = await response.Content.ReadAsStringAsync(ct);
        if (!response.IsSuccessStatusCode) throw new InvalidOperationException($"LLM 请求失败 HTTP {(int)response.StatusCode}: {TrimMessage(body)}");
        using var document = JsonDocument.Parse(body);
        var content = document.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString();
        if (string.IsNullOrWhiteSpace(content)) throw new InvalidOperationException("LLM 返回内容为空");
        return content;
    }

    private static string TrimMessage(string body) => body.Length > 500 ? body[..500] : body;
}

public sealed class LlmProviderFactory
{
    private readonly StudioRepository _repository;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<LlmProviderFactory> _logger;

    public LlmProviderFactory(StudioRepository repository, IHttpClientFactory httpClientFactory, ILogger<LlmProviderFactory> logger)
    {
        _repository = repository;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task<ILLMProvider?> CreateAsync(CancellationToken ct = default)
    {
        var baseUrl = await _repository.GetSettingAsync("llm.base_url", ct);
        var model = await _repository.GetSettingAsync("llm.model", ct);
        var apiKey = await _repository.GetSettingAsync("llm.api_key", ct);
        var provider = await _repository.GetSettingAsync("llm.provider", ct) ?? "OpenAICompatible";
        if (string.IsNullOrWhiteSpace(baseUrl) || string.IsNullOrWhiteSpace(model)) return null;
        _logger.LogInformation("LLM provider ready: {Provider}, model configured: {HasModel}", provider, !string.IsNullOrWhiteSpace(model));
        return new OpenAiCompatibleLlmProvider(_httpClientFactory.CreateClient("llm"), baseUrl, model, apiKey ?? "", provider);
    }

    public async Task<(decimal Temperature, int MaxTokens)> OptionsAsync(CancellationToken ct = default)
    {
        var temperature = decimal.TryParse(await _repository.GetSettingAsync("llm.temperature", ct), out var t) ? t : 0.2m;
        var maxTokens = int.TryParse(await _repository.GetSettingAsync("llm.max_tokens", ct), out var m) ? m : 3000;
        return (Math.Clamp(temperature, 0, 2), Math.Clamp(maxTokens, 256, 16000));
    }
}

public sealed class ScriptAnalyzer
{
    private static readonly Regex Speaker = new(@"^\s*(?<name>[\p{L}\p{N}_]{1,24})\s*[:：]\s*(?<text>.+)$", RegexOptions.Compiled);
    private readonly LlmProviderFactory _llmFactory;
    private readonly ILogger<ScriptAnalyzer> _logger;

    public ScriptAnalyzer(LlmProviderFactory llmFactory, ILogger<ScriptAnalyzer> logger)
    {
        _llmFactory = llmFactory;
        _logger = logger;
    }

    public async Task<ScriptAnalysisResult> AnalyzeAsync(string content, IReadOnlyList<Dictionary<string, object?>> characters, IReadOnlyList<Dictionary<string, object?>> scenes, bool useLlm, CancellationToken ct = default)
    {
        if (useLlm)
        {
            var provider = await _llmFactory.CreateAsync(ct);
            if (provider is not null)
            {
                try
                {
                    var options = await _llmFactory.OptionsAsync(ct);
                    var response = await provider.CompleteAsync(SystemPrompt, BuildUserPrompt(content), options.Temperature, options.MaxTokens, ct);
                    var parsed = ParseLlmResponse(response, characters, scenes);
                    if (parsed.Shots.Count > 0) return parsed with { Provider = provider.Name, RawLlmResponse = response };
                }
                catch (Exception ex) { _logger.LogWarning("LLM 解析失败，回退本地解析: {Message}", ex.Message); }
            }
        }
        return RuleBased(content, characters, scenes);
    }

    private static string BuildUserPrompt(string content) => $"请把下面的中文短剧剧本拆成可制作的镜头 JSON。只返回 JSON，不要 Markdown。\n剧本：\n{content}";

    private static readonly string SystemPrompt = """
        你是影视分镜解析器。输出 JSON 对象：{"shots":[{"shotNumber":1,"title":"","description":"","sceneName":"","characterNames":[],"action":"","dialogue":"","narration":"","cameraType":"","cameraMotion":"","emotion":"","durationSeconds":5}],"missingCharacters":[],"missingScenes":[]}。
        保留原剧本信息；durationSeconds 为 3-10 的数字；cameraType 用 close-up/medium shot/wide shot，cameraMotion 用 static/pan/tilt/dolly/track/orbit；characterNames 只填明确出现的人物。
        """;

    private static ScriptAnalysisResult ParseLlmResponse(string raw, IReadOnlyList<Dictionary<string, object?>> characters, IReadOnlyList<Dictionary<string, object?>> scenes)
    {
        var json = raw.Trim();
        if (json.StartsWith("```", StringComparison.Ordinal)) json = Regex.Replace(json, "^```(?:json)?\\s*|\\s*```$", "", RegexOptions.IgnoreCase);
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        var knownCharacters = characters.Select(x => x.Text("name") ?? "").Where(x => x.Length > 0).ToArray();
        var knownScenes = scenes.Select(x => x.Text("name") ?? "").Where(x => x.Length > 0).ToArray();
        var shots = new List<ScriptShotDraft>();
        if (root.TryGetProperty("shots", out var shotArray) && shotArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in shotArray.EnumerateArray())
            {
                var names = item.TryGetProperty("characterNames", out var people) && people.ValueKind == JsonValueKind.Array ? people.EnumerateArray().Select(x => x.GetString() ?? "").Where(x => x.Length > 0).ToArray() : [];
                shots.Add(new ScriptShotDraft(
                    item.TryGetProperty("shotNumber", out var no) && no.TryGetInt32(out var n) ? n : shots.Count + 1,
                    Text(item, "title") ?? $"镜头 {shots.Count + 1}", Text(item, "description") ?? "", Text(item, "sceneName"), names,
                    Text(item, "action") ?? Text(item, "description") ?? "", Text(item, "dialogue"), Text(item, "narration"), Text(item, "cameraType") ?? "medium shot", Text(item, "cameraMotion") ?? "static", Text(item, "emotion") ?? "neutral", Number(item, "durationSeconds", 5)));
            }
        }
        var missingCharacters = knownCharacters.Length == 0 ? [] : root.TryGetProperty("missingCharacters", out var missing) && missing.ValueKind == JsonValueKind.Array ? missing.EnumerateArray().Select(x => x.GetString() ?? "").Where(x => x.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToArray() : [];
        var missingScenes = root.TryGetProperty("missingScenes", out var missingScenesValue) && missingScenesValue.ValueKind == JsonValueKind.Array ? missingScenesValue.EnumerateArray().Select(x => x.GetString() ?? "").Where(x => x.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToArray() : [];
        return new ScriptAnalysisResult(shots, missingCharacters, missingScenes, "LLM");
    }

    private static ScriptAnalysisResult RuleBased(string content, IReadOnlyList<Dictionary<string, object?>> characters, IReadOnlyList<Dictionary<string, object?>> scenes)
    {
        var knownCharacters = characters.Select(x => x.Text("name") ?? "").Where(x => x.Length > 0).ToArray();
        var knownScenes = scenes.Select(x => x.Text("name") ?? "").Where(x => x.Length > 0).ToArray();
        var blocks = SplitBlocks(content);
        var drafts = new List<ScriptShotDraft>();
        var speakerNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var sceneNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < blocks.Count; i++)
        {
            var block = blocks[i];
            var lines = block.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            var title = lines.FirstOrDefault(x => Regex.IsMatch(x, "镜头|SHOT|场景", RegexOptions.IgnoreCase)) ?? $"镜头 {i + 1}";
            var scene = knownScenes.FirstOrDefault(x => block.Contains(x, StringComparison.OrdinalIgnoreCase));
            var explicitScene = lines.FirstOrDefault(x => x.StartsWith("场景", StringComparison.OrdinalIgnoreCase) || x.StartsWith("SCENE", StringComparison.OrdinalIgnoreCase));
            if (scene is null && explicitScene is not null) scene = explicitScene[(explicitScene.IndexOf(':') >= 0 ? explicitScene.IndexOf(':') + 1 : 2)..].Trim();
            if (!string.IsNullOrWhiteSpace(scene)) sceneNames.Add(scene);
            var dialogue = new List<string>();
            var action = new List<string>();
            string? narration = null;
            foreach (var line in lines)
            {
                if (line.StartsWith("旁白", StringComparison.OrdinalIgnoreCase)) { narration = line[(line.IndexOfAny([':', '：']) + 1)..].Trim(); continue; }
                var match = Speaker.Match(line);
                if (match.Success) { speakerNames.Add(match.Groups["name"].Value); dialogue.Add(line); continue; }
                if (!line.StartsWith("镜头", StringComparison.OrdinalIgnoreCase) && !line.StartsWith("SHOT", StringComparison.OrdinalIgnoreCase) && !line.StartsWith("场景", StringComparison.OrdinalIgnoreCase)) action.Add(line);
            }
            if (action.Count == 0) action.Add(block);
            var cameraType = block.Contains("近景") || block.Contains("特写") ? "close-up" : block.Contains("远景") || block.Contains("全景") ? "wide shot" : "medium shot";
            var cameraMotion = block.Contains("推") || block.Contains("靠近") ? "dolly in" : block.Contains("拉") || block.Contains("后退") ? "dolly out" : block.Contains("跟随") ? "track" : block.Contains("环绕") ? "orbit" : block.Contains("摇") ? "pan" : "static";
            var emotion = block.Contains("紧张") || block.Contains("恐惧") ? "tense" : block.Contains("开心") || block.Contains("微笑") ? "warm" : block.Contains("悲伤") || block.Contains("哭") ? "sad" : "neutral";
            var durationMatch = Regex.Match(block, @"(?<seconds>\d+(?:\.\d+)?)\s*秒");
            var duration = durationMatch.Success && decimal.TryParse(durationMatch.Groups["seconds"].Value, out var parsedDuration) ? Math.Clamp(parsedDuration, 3, 10) : 5;
            var names = knownCharacters.Where(x => block.Contains(x, StringComparison.OrdinalIgnoreCase)).ToArray();
            drafts.Add(new ScriptShotDraft(i + 1, title, block, scene, names, string.Join(" ", action), dialogue.Count == 0 ? null : string.Join("\n", dialogue), narration, cameraType, cameraMotion, emotion, duration));
        }
        var missingCharacters = speakerNames.Where(x => !knownCharacters.Any(k => string.Equals(k, x, StringComparison.OrdinalIgnoreCase))).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        var missingScenes = sceneNames.Where(x => !knownScenes.Any(k => string.Equals(k, x, StringComparison.OrdinalIgnoreCase))).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        return new ScriptAnalysisResult(drafts, missingCharacters, missingScenes, "RuleBased");
    }

    private static List<string> SplitBlocks(string content)
    {
        var paragraphs = Regex.Split(content.Replace("\r\n", "\n"), "\n\\s*\n").Select(x => x.Trim()).Where(x => x.Length > 0).ToList();
        if (paragraphs.Count > 1) return paragraphs;
        var lines = content.Replace("\r\n", "\n").Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var blocks = new List<string>();
        var current = new List<string>();
        foreach (var line in lines)
        {
            if (current.Count > 0 && (Regex.IsMatch(line, "^(镜头|SHOT|场景|SCENE)\\s*\\d*", RegexOptions.IgnoreCase) || current.Count >= 4)) { blocks.Add(string.Join("\n", current)); current.Clear(); }
            current.Add(line);
        }
        if (current.Count > 0) blocks.Add(string.Join("\n", current));
        return blocks.Count == 0 ? ["空剧本"] : blocks;
    }

    private static string? Text(JsonElement item, string name) => item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
    private static decimal Number(JsonElement item, string name, decimal fallback) => item.TryGetProperty(name, out var value) && value.TryGetDecimal(out var result) ? Math.Clamp(result, 3, 10) : fallback;
}

public sealed class PromptEngine
{
    public PromptComposition Compose(IReadOnlyList<Dictionary<string, object?>> characters, Dictionary<string, object?>? scene, IReadOnlyDictionary<string, object?> shot)
    {
        var characterPrompt = string.Join(", ", characters.Select(EnglishizeCharacter).Where(x => x.Length > 0));
        var scenePrompt = scene is null ? "cinematic environment" : string.Join(", ", new[] { scene.Text("fixedPrompt"), scene.Text("description"), scene.Text("style"), scene.Text("lighting"), scene.Text("timeOfDay"), scene.Text("weather"), scene.Text("architecture") }.Where(x => !string.IsNullOrWhiteSpace(x)).Select(Englishize));
        var actionPrompt = Englishize(string.Join(", ", new[] { shot.Text("action"), shot.Text("emotion"), shot.Text("dialogue") }.Where(x => !string.IsNullOrWhiteSpace(x))));
        var cameraPrompt = Englishize(string.Join(", ", new[] { shot.Text("cameraType"), shot.Text("cameraMotion"), shot.Text("cameraPreset"), shot.Text("motionPreset") }.Where(x => !string.IsNullOrWhiteSpace(x))));
        if (string.IsNullOrWhiteSpace(cameraPrompt)) cameraPrompt = "medium shot, stable cinematic camera";
        var lightingPrompt = scene?.Text("lighting") is { Length: > 0 } lighting ? Englishize(lighting) : "soft cinematic lighting, natural shadows";
        var stylePrompt = scene?.Text("style") is { Length: > 0 } style ? Englishize(style) : "cinematic photorealistic, coherent art direction";
        var qualityPrompt = "high detail, realistic skin texture, stable face, consistent identity, natural hands, temporal consistency, sharp focus, 4k detail";
        var prompt = string.Join(", ", new[] { characterPrompt, scenePrompt, actionPrompt, cameraPrompt, lightingPrompt, stylePrompt, qualityPrompt }.Where(x => !string.IsNullOrWhiteSpace(x)));
        var negative = "low quality, blurry, deformed face, extra fingers, bad hands, duplicate person, flicker, frame warping, text, watermark, oversaturated";
        return new PromptComposition(characterPrompt, scenePrompt, actionPrompt, cameraPrompt, lightingPrompt, stylePrompt, qualityPrompt, prompt, negative);
    }

    private static string EnglishizeCharacter(IReadOnlyDictionary<string, object?> row)
    {
        var name = row.Text("name");
        var fields = new[] { row.Text("ageSetting"), row.Text("faceFeatures"), row.Text("hair"), row.Text("clothes"), row.Text("bodyRatio"), row.Text("fixedPrompt") }.Where(x => !string.IsNullOrWhiteSpace(x));
        return Englishize(string.Join(", ", new[] { name }.Concat(fields)));
    }

    public static string Englishize(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "";
        var output = value;
        var replacements = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["女性"] = "woman", ["男人"] = "man", ["男性"] = "man", ["女孩"] = "girl", ["男孩"] = "boy", ["年轻"] = "young", ["黑色"] = "black", ["白色"] = "white", ["红色"] = "red", ["蓝色"] = "blue", ["长发"] = "long hair", ["短发"] = "short hair", ["室内"] = "interior", ["室外"] = "exterior", ["夜晚"] = "night", ["白天"] = "day", ["雨天"] = "rainy weather", ["雪天"] = "snowy weather", ["列车"] = "train", ["驾驶室"] = "cockpit", ["车厢"] = "train carriage", ["城市"] = "city", ["房间"] = "room", ["走路"] = "walking", ["跑步"] = "running", ["转身"] = "turning around", ["挥手"] = "waving", ["微笑"] = "smiling", ["紧张"] = "tense", ["悲伤"] = "sad", ["近景"] = "close-up", ["中景"] = "medium shot", ["远景"] = "wide shot", ["推镜头"] = "dolly in", ["拉镜头"] = "dolly out", ["固定镜头"] = "static camera", ["电影感"] = "cinematic"
        };
        foreach (var pair in replacements) output = output.Replace(pair.Key, pair.Value, StringComparison.OrdinalIgnoreCase);
        return output;
    }
}
