using System.Text;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Adds the local administrator session store and immutable security audit trail.
/// Existing media and production tables are intentionally untouched.
/// </summary>
public static class LocalAuthSchemaMigrator
{
    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        await ExecuteAsync(connection, @"CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) NOT NULL PRIMARY KEY,
            applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci", ct);

        if (File.Exists(migrationPath))
        {
            foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
            {
                var executable = Regex.Replace(statement.Trim(), @"(?m)^\s*--[^\r\n]*(?:\r?\n|$)", "").Trim();
                if (Regex.IsMatch(executable, "^CREATE TABLE", RegexOptions.IgnoreCase)) await ExecuteAsync(connection, executable, ct);
            }
        }

        await ExecuteAsync(connection, "INSERT IGNORE INTO schema_migrations(version) VALUES('007_local_auth_audit')", ct);
    }

    private static async Task ExecuteAsync(MySqlConnection connection, string sql, CancellationToken ct)
    {
        await using var command = new MySqlCommand(sql, connection) { CommandTimeout = 120 };
        await command.ExecuteNonQueryAsync(ct);
    }

    private static IEnumerable<string> SplitSql(string sql)
    {
        var current = new StringBuilder(); var inString = false; var quote = '\0';
        for (var i = 0; i < sql.Length; i++)
        {
            var ch = sql[i];
            if ((ch == '\'' || ch == '"') && (i == 0 || sql[i - 1] != '\\')) { if (!inString) { inString = true; quote = ch; } else if (quote == ch) inString = false; }
            if (ch == ';' && !inString) { yield return current.ToString(); current.Clear(); } else current.Append(ch);
        }
        if (current.Length > 0) yield return current.ToString();
    }
}
