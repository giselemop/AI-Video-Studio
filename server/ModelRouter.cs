namespace VideoStudio.Server;

public sealed record ModelRouteDecision(
    string ModelFamily,
    string WorkflowVersion,
    bool NeedSplit,
    string EvidenceStatus,
    string Reason,
    string? Blocker,
    IReadOnlyList<string> RequiredControls,
    string OriginalAction = "",
    IReadOnlyList<string>? DetectedActions = null,
    string Complexity = "Simple",
    IReadOnlyList<MotionSubShot>? SuggestedSubShots = null,
    string? BlockingReason = null);

/// <summary>
/// Routes shots using capabilities proven on this workstation. Complex,
/// multi-verb and high-risk actions are never silently sent through
/// small-motion I2V.
/// </summary>
public sealed class ModelRouter
{
    public ModelRouteDecision Resolve(IReadOnlyDictionary<string, object?> shot, int referenceCount)
    {
        var action = string.Join(" ", new[]
        {
            shot.Text("action"), shot.Text("description"), shot.Text("dialogue"),
            shot.Text("narration"), shot.Text("cameraMotion"), shot.Text("motionPreset")
        }.Where(value => !string.IsNullOrWhiteSpace(value)));
        var analysis = MotionComplexityAnalyzer.Analyze(action);
        var hasReference = referenceCount > 0 || shot.Bool("referenceRequired");

        if (analysis.NeedSplit)
        {
            var driving = analysis.DetectedActions.Contains("drive", StringComparer.OrdinalIgnoreCase);
            return new ModelRouteDecision(
                driving ? "Driving/Pose" : "Split-shot gated motion",
                driving ? "wan2.2-animate" : "split-shot-gated",
                true,
                driving ? "Blocked-target-pipeline" : "NeedSplit-before-small-motion-I2V",
                analysis.BlockingReason ?? "当前动作必须拆成短子镜头后逐镜验收。",
                driving ? "Wan2.2 Animate 目标权重与完整 Driving/Pose 工作流未在本机可用。" : null,
                driving
                    ? ["真实 Driving Video", "Pose/face control video", "人物参考图", "人工动作 QA"]
                    : ["拆分为 1.0–2.5 秒子镜头", "单动作控制输入", "人物参考图", "人工动作 QA"],
                analysis.OriginalAction,
                analysis.DetectedActions,
                analysis.Complexity,
                analysis.SuggestedSubShots,
                analysis.BlockingReason);
        }

        if (hasReference)
        {
            return new ModelRouteDecision(
                "LTX reference-locked I2V",
                "12_ltx_face_stable_v3",
                false,
                "Passed-small-motion-only",
                "有可用人物参考且动作未超过当前本机已验证的小动作范围。",
                null,
                ["单一人物参考图", "3–5 秒 Draft", "人工身份/身体 QA"],
                analysis.OriginalAction,
                analysis.DetectedActions,
                analysis.Complexity,
                analysis.SuggestedSubShots,
                null);
        }

        return new ModelRouteDecision(
            "Wan2.2 TI2V 5B",
            "05_wan22_ti2v_5b",
            false,
            "Technical-only",
            "无人物参考且动作不复杂，使用本机现有 Wan2.2 TI2V 5B 基线。",
            null,
            ["首帧输入", "3–5 秒 Draft", "人工 QA"],
            analysis.OriginalAction,
            analysis.DetectedActions,
            analysis.Complexity,
            analysis.SuggestedSubShots,
            null);
    }
}
