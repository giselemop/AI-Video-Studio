using System.Text.Json;
using System.Text.Json.Nodes;

namespace VideoStudio.Server;

// Initial admission is deliberately limited to short native fl2va experiments.
public static class H3WorkflowPolicy
{
    public static bool IsH3(JsonObject workflow) => workflow.Any(pair =>
        pair.Value is JsonObject node &&
        (node["class_type"]?.GetValue<string>() ?? "").Contains("MiniMaxH3", StringComparison.OrdinalIgnoreCase));

    public static void Validate(JsonObject workflow, JsonElement parameters)
    {
        if (!IsH3(workflow)) return;
        var conditioningCount = workflow.Count(pair => pair.Value is JsonObject node &&
            node["class_type"]?.GetValue<string>() == "MiniMaxH3ImageToVideo");
        if (conditioningCount != 1)
            throw new InvalidOperationException("H3 首轮需要且仅允许一个原生图生/文生条件节点");
        var firstLast = parameters.ValueKind == JsonValueKind.Object
            && parameters.TryGetProperty("profile", out var frameProfile) && frameProfile.ValueKind == JsonValueKind.String
            && frameProfile.GetString() == MiniMaxLocalService.FirstLastProfile;
        var conditioningInputs = workflow.Select(pair => pair.Value).OfType<JsonObject>()
            .Single(node => node["class_type"]?.GetValue<string>() == "MiniMaxH3ImageToVideo")["inputs"]!.AsObject();
        if (firstLast)
        {
            bool Bound(string input, string id) => conditioningInputs[input] is JsonArray link && link.Count == 2
                && link[0]?.GetValue<string>() == id && link[1]?.GetValue<int>() == 0
                && workflow[id]?["class_type"]?.GetValue<string>() == "LoadImage";
            if (!Bound("first_frame", "5") || !Bound("last_frame", "16")
                || workflow.Count(pair => pair.Value?["class_type"]?.GetValue<string>() == "LoadImage") != 2)
                throw new InvalidOperationException("H3首尾双帧必须由独立LoadImage节点5/16明确连接first_frame/last_frame，禁止节点漂移或顺序猜测");
        }
        else if (conditioningInputs.ContainsKey("last_frame"))
            throw new InvalidOperationException("H3尾帧节点只允许用于显式firstlast480实验");
        (int Width, int Height, int Length)? canvas = null;
        foreach (var pair in workflow)
        {
            if (pair.Value is not JsonObject node) continue;
            var type = node["class_type"]?.GetValue<string>() ?? "";
            if (type.Contains("MiniMaxH3", StringComparison.OrdinalIgnoreCase) &&
                type is not ("MiniMaxH3ImageToVideo" or "EmptyMiniMaxH3LatentAV" or "MiniMaxH3SigmaShift"))
                throw new InvalidOperationException("H3 首轮仅开放原生图生/文生实验；参考生、引导和第三方节点尚未验收");
            if (type is not ("MiniMaxH3ImageToVideo" or "EmptyMiniMaxH3LatentAV")) continue;
            var inputs = node["inputs"]?.AsObject() ?? throw new InvalidOperationException("H3 节点缺少输入");
            int Read(string name, string? alias = null)
            {
                if (parameters.ValueKind == JsonValueKind.Object)
                {
                    if (parameters.TryGetProperty(alias ?? name, out var value)) return value.GetInt32();
                    if (parameters.TryGetProperty(name, out value)) return value.GetInt32();
                }
                if (inputs[name] is JsonValue scalar && scalar.TryGetValue<int>(out var number)) return number;
                throw new InvalidOperationException($"H3 {name} 必须为明确数值或显式任务参数");
            }
            var width = Read("width");
            var height = Read("height");
            var length = Read("length", "frames");
            if (firstLast && (width != 864 || height != 480))
                throw new InvalidOperationException("H3首尾双帧实验固定864×480，不隐式套用其他原生规格");
            if (canvas is { } previous && previous != (width, height, length))
                throw new InvalidOperationException("H3 条件节点与音视频latent尺寸或帧数不一致");
            canvas = (width, height, length);
            var native1080 = parameters.ValueKind == JsonValueKind.Object
                && parameters.TryGetProperty("profile", out var selectedProfile)
                && selectedProfile.ValueKind == JsonValueKind.String
                && selectedProfile.GetString() == "native1080";
            var acceptedArea = native1080 ? width == 1920 && height == 1088 : (long)width * height <= 1376 * 768;
            if (width < 32 || height < 32 || width % 32 != 0 || height % 32 != 0 || !acceptedArea)
                throw new InvalidOperationException("H3 尺寸必须按32对齐；常规上限1376×768，native1080实验只允许1920×1088");
            if (length != 124)
                throw new InvalidOperationException("H3 首轮固定124帧（24fps，约5.167秒），禁止套用LTX帧数或隐式取整");
        }
        if (parameters.ValueKind == JsonValueKind.Object && parameters.TryGetProperty("fps", out var fps) && fps.GetDouble() != 24)
            throw new InvalidOperationException("H3 原生采样固定24fps；交付帧率请在后期单独设置");
        if (parameters.ValueKind == JsonValueKind.Object && parameters.TryGetProperty("profile", out var profile)
            && profile.ValueKind == JsonValueKind.String && profile.GetString() == "native1080")
        {
            var save = workflow.Select(pair => pair.Value).OfType<JsonObject>()
                .SingleOrDefault(node => node["class_type"]?.GetValue<string>() == "SaveVideo")?["inputs"]?.AsObject();
            if (save?["codec"] is not JsonValue codec || !codec.TryGetValue<string>(out var name) || name != "h264"
                || save["codec.encoding"]?.GetValue<string>() != "re-encode"
                || save["codec.encoding.crf"]?.GetValue<double>() != 16)
                throw new InvalidOperationException("原生1080p保存节点必须使用已验证的V3展开参数：codec=h264、codec.encoding=re-encode、codec.encoding.crf=16");
        }
    }

    public static void BindCopiedFrames(JsonObject workflow, JsonElement parameters, string? firstFrame, string? lastFrame)
    {
        Validate(workflow, parameters);
        if (!parameters.TryGetProperty("profile", out var profile) || profile.GetString() != MiniMaxLocalService.FirstLastProfile)
        {
            if (lastFrame is not null) throw new InvalidOperationException("尾帧不能绑定到非双帧工作流");
            return;
        }
        if (string.IsNullOrWhiteSpace(firstFrame) || string.IsNullOrWhiteSpace(lastFrame))
            throw new InvalidOperationException("H3首尾帧复制未完成，不能执行GPU任务");
        workflow["5"]!["inputs"]!["image"] = Path.GetFileName(firstFrame);
        workflow["16"]!["inputs"]!["image"] = Path.GetFileName(lastFrame);
    }
}
