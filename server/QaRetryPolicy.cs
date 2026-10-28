namespace VideoStudio.Server;

public enum QaRetryParameterTarget
{
    None,
    Seed,
    ReferenceStrength
}

public static class QaRetryPolicy
{
    public const string RoutePolicy = "inherit-original-route; alternative-route-explicit-only";

    public static QaRetryParameterTarget SelectTarget(string? failureReason)
    {
        if (ContainsAny(failureReason, "temporal", "闪烁", "帧", "fps", "flicker", "decode")) return QaRetryParameterTarget.Seed;
        if (ContainsAny(failureReason, "face", "identity", "脸", "变脸", "drift", "身份")) return QaRetryParameterTarget.ReferenceStrength;
        return QaRetryParameterTarget.None;
    }

    private static bool ContainsAny(string? value, params string[] tokens)
        => !string.IsNullOrWhiteSpace(value) && tokens.Any(token => value.Contains(token, StringComparison.OrdinalIgnoreCase));
}
