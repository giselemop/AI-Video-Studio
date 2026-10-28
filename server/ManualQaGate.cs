using System.Text.Json;

namespace VideoStudio.Server;

public static class ManualQaGate
{
    public static string? Validate(string decision, string? currentStatus, int version, string? resultJson, bool overrideFailure, string? note)
    {
        if (decision is not ("Passed" or "Approved")) return null;
        if (version <= 0 || currentStatus is "Checking" or "AutoChecking" or "NotChecked")
            return "请先完成当前版本的自动 QA";
        try
        {
            using var document = JsonDocument.Parse(resultJson ?? "null");
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.String)
                return "缺少可追溯的自动 QA 结果，请重新验收";
            if (root.TryGetProperty("technical", out var technical) && technical.ValueKind == JsonValueKind.Object
                && technical.TryGetProperty("hardFailure", out var hard) && hard.ValueKind == JsonValueKind.True)
                return "技术硬失败必须修复并重新验收，不能人工覆盖";
            if ((string.Equals(status.GetString(), "Rejected", StringComparison.OrdinalIgnoreCase)
                || string.Equals(currentStatus, "Rejected", StringComparison.OrdinalIgnoreCase))
                && (!overrideFailure || string.IsNullOrWhiteSpace(note)))
                return "自动 QA 已拒绝；人工复核必须显式 Override 并填写说明";
            return null;
        }
        catch (JsonException) { return "自动 QA 结果损坏，请重新验收"; }
    }
}
