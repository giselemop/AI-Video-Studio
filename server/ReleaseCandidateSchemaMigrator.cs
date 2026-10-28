using System.Text;
using MySqlConnector;

namespace VideoStudio.Server;

public static class ReleaseCandidateSchemaMigrator
{
    public const string Version = "009_release_candidate_packages";

    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        await using var exists = new MySqlCommand("SELECT COUNT(*) FROM schema_migrations WHERE version=@version", connection);
        exists.Parameters.AddWithValue("@version", Version);
        if (Convert.ToInt32(await exists.ExecuteScalarAsync(ct)) > 0) return;
        if (!File.Exists(migrationPath)) throw new FileNotFoundException("Release candidate migration file is missing", migrationPath);
        foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
        {
            var sql = statement.Trim();
            if (string.IsNullOrWhiteSpace(sql)) continue;
            await using var command = new MySqlCommand(sql, connection) { CommandTimeout = 120 };
            await command.ExecuteNonQueryAsync(ct);
        }
        await using var mark = new MySqlCommand("INSERT INTO schema_migrations(version) VALUES(@version)", connection);
        mark.Parameters.AddWithValue("@version", Version);
        await mark.ExecuteNonQueryAsync(ct);
    }

    private static IEnumerable<string> SplitSql(string sql)
    {
        var current = new StringBuilder();
        var inString = false;
        var quote = '\0';
        foreach (var ch in sql)
        {
            if ((ch == '\'' || ch == '"') && (current.Length == 0 || current[^1] != '\\'))
            {
                if (!inString) { inString = true; quote = ch; }
                else if (quote == ch) inString = false;
            }
            if (ch == ';' && !inString) { yield return current.ToString(); current.Clear(); }
            else current.Append(ch);
        }
        if (current.Length > 0) yield return current.ToString();
    }
}
