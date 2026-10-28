using System.Text;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// 第一阶段可靠性迁移。只增加幂等、租约、状态版本和任务事件，兼容已有任务数据。
/// </summary>
public static class ReliabilitySchemaMigrator
{
    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        await ExecuteAsync(connection, @"CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) NOT NULL PRIMARY KEY,
            applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci", ct);

        var columns = new (string Table, string Name, string Definition)[]
        {
            ("generation_tasks", "request_id", "VARCHAR(128) NULL"),
            ("generation_tasks", "idempotency_key", "VARCHAR(191) NULL"),
            ("generation_tasks", "state_version", "INT NOT NULL DEFAULT 0"),
            ("generation_tasks", "lease_owner", "VARCHAR(128) NULL"),
            ("generation_tasks", "lease_expires_at", "DATETIME(3) NULL"),
            ("generation_tasks", "heartbeat_at", "DATETIME(3) NULL"),
            ("generation_tasks", "cancel_requested_at", "DATETIME(3) NULL"),
            ("generation_tasks", "deadline_at", "DATETIME(3) NULL"),
            ("generation_tasks", "timed_out_at", "DATETIME(3) NULL"),
            ("generation_tasks", "failure_code", "VARCHAR(64) NULL"),
            ("generation_tasks", "input_fingerprint", "CHAR(64) NULL"),
            ("generation_tasks", "production_run_id", "BIGINT UNSIGNED NULL"),
            ("production_runs", "idempotency_key", "VARCHAR(191) NULL")
        };

        foreach (var column in columns)
            if (!await ColumnExistsAsync(connection, column.Table, column.Name, ct))
                await ExecuteAsync(connection, $"ALTER TABLE `{column.Table}` ADD COLUMN `{column.Name}` {column.Definition}", ct);

        if (!await IndexExistsAsync(connection, "generation_tasks", "uq_generation_tasks_idempotency", ct))
            await ExecuteAsync(connection, "ALTER TABLE generation_tasks ADD UNIQUE KEY uq_generation_tasks_idempotency (idempotency_key)", ct);
        if (!await IndexExistsAsync(connection, "production_runs", "uq_production_runs_idempotency", ct))
            await ExecuteAsync(connection, "ALTER TABLE production_runs ADD UNIQUE KEY uq_production_runs_idempotency (idempotency_key)", ct);

        if (File.Exists(migrationPath))
        {
            foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
            {
                var executable = Regex.Replace(statement.Trim(), @"(?m)^\s*--[^\r\n]*(?:\r?\n|$)", "").Trim();
                if (Regex.IsMatch(executable, "^CREATE TABLE", RegexOptions.IgnoreCase)) await ExecuteAsync(connection, executable, ct);
            }
        }
        await ExecuteAsync(connection, "INSERT IGNORE INTO schema_migrations(version) VALUES('004_reliability_references_audio')", ct);
    }

    private static async Task<bool> ColumnExistsAsync(MySqlConnection connection, string table, string column, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema=DATABASE() AND table_name=@table AND column_name=@column", connection);
        command.Parameters.AddWithValue("@table", table);
        command.Parameters.AddWithValue("@column", column);
        return Convert.ToInt32(await command.ExecuteScalarAsync(ct)) > 0;
    }

    private static async Task<bool> IndexExistsAsync(MySqlConnection connection, string table, string index, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema=DATABASE() AND table_name=@table AND index_name=@index", connection);
        command.Parameters.AddWithValue("@table", table);
        command.Parameters.AddWithValue("@index", index);
        return Convert.ToInt32(await command.ExecuteScalarAsync(ct)) > 0;
    }

    private static async Task ExecuteAsync(MySqlConnection connection, string sql, CancellationToken ct)
    {
        await using var command = new MySqlCommand(sql, connection) { CommandTimeout = 120 };
        await command.ExecuteNonQueryAsync(ct);
    }

    private static IEnumerable<string> SplitSql(string sql)
    {
        var current = new StringBuilder();
        var inString = false;
        var quote = '\0';
        for (var i = 0; i < sql.Length; i++)
        {
            var ch = sql[i];
            if ((ch == '\'' || ch == '"') && (i == 0 || sql[i - 1] != '\\'))
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
