using System.Globalization;
using System.Text.Json;

namespace VideoStudio.Server;

public static class RowExtensions
{
    public static string? Text(this IReadOnlyDictionary<string, object?> row, string key) => row.TryGetValue(key, out var value) && value is not null ? Convert.ToString(value, CultureInfo.InvariantCulture) : null;
    public static long Long(this IReadOnlyDictionary<string, object?> row, string key, long fallback = 0) => row.TryGetValue(key, out var value) && value is not null && long.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var result) ? result : fallback;
    public static long? LongOrNull(this IReadOnlyDictionary<string, object?> row, string key) => row.TryGetValue(key, out var value) && value is not null && long.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var result) ? result : null;
    public static int Int(this IReadOnlyDictionary<string, object?> row, string key, int fallback = 0) => (int)row.Long(key, fallback);
    public static decimal Decimal(this IReadOnlyDictionary<string, object?> row, string key, decimal fallback = 0) => row.TryGetValue(key, out var value) && value is not null && decimal.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var result) ? result : fallback;
    public static bool Bool(this IReadOnlyDictionary<string, object?> row, string key)
    {
        if (!row.TryGetValue(key, out var value) || value is null) return false;
        if (value is bool boolean) return boolean;
        if (value is string text && bool.TryParse(text, out var parsed)) return parsed;
        return long.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var number) && number != 0;
    }
    public static JsonDocument Json(this IReadOnlyDictionary<string, object?> row, string key) => JsonDocument.Parse(row.Text(key) ?? "{}");
}
