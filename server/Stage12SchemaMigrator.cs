using System.Text;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Applies the additive stage 1/2 production-core schema. The caller must opt
/// in through AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA; normal startup never invokes
/// this migrator while the flag remains disabled.
/// </summary>
public static class Stage12SchemaMigrator
{
    public const string Version = "008_stage12_production_core";

    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        const string lockName = "ai-video-studio:stage12-schema";
        await using var acquire = new MySqlCommand("SELECT GET_LOCK(@name,30)", connection);
        acquire.Parameters.AddWithValue("@name", lockName);
        if (Convert.ToInt32(await acquire.ExecuteScalarAsync(ct)) != 1)
            throw new TimeoutException("Stage12 schema migration lock could not be acquired");

        try
        {
            await ExecuteAsync(connection, @"CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) NOT NULL PRIMARY KEY,
            applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci", ct);

        if (await MigrationExistsAsync(connection, Version, ct)) return;
        if (!File.Exists(migrationPath)) throw new FileNotFoundException("Stage 1/2 migration file is missing", migrationPath);

        foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
        {
            var executable = Regex.Replace(statement.Trim(), @"(?m)^\s*--[^\r\n]*(?:\r?\n|$)", "").Trim();
            if (Regex.IsMatch(executable, "^CREATE TABLE", RegexOptions.IgnoreCase))
                await ExecuteAsync(connection, executable, ct);
        }

        var columns = new (string Table, string Name, string Definition)[]
        {
            ("generation_tasks", "production_profile_id", "BIGINT UNSIGNED NULL"),
            ("generation_tasks", "shot_plan_id", "BIGINT UNSIGNED NULL"),
            ("generation_tasks", "input_asset_id", "BIGINT UNSIGNED NULL"),
            ("generation_tasks", "active_attempt_id", "BIGINT UNSIGNED NULL"),
            ("generation_tasks", "lease_token", "CHAR(36) NULL"),
            ("generation_tasks", "output_manifest_id", "BIGINT UNSIGNED NULL"),
            ("generation_results", "attempt_id", "BIGINT UNSIGNED NULL"),
            ("generation_results", "manifest_id", "BIGINT UNSIGNED NULL"),
            ("task_events", "attempt_id", "BIGINT UNSIGNED NULL"),
            ("task_events", "lease_token", "CHAR(36) NULL"),
            ("task_events", "output_manifest_id", "BIGINT UNSIGNED NULL"),
            ("assets", "manifest_id", "BIGINT UNSIGNED NULL"),
            ("assets", "purpose", "VARCHAR(64) NULL"),
            ("assets", "version", "INT UNSIGNED NOT NULL DEFAULT 1"),
            ("assets", "status", "VARCHAR(32) NOT NULL DEFAULT 'Ready'"),
            ("assets", "source_attempt_id", "BIGINT UNSIGNED NULL"),
            ("assets", "immutable_path", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("llm_egress_audit", "redacted_preview", "TEXT NULL"),
            ("llm_egress_audit", "redirect_count", "TINYINT UNSIGNED NOT NULL DEFAULT 0"),
            ("llm_egress_audit", "timeout_ms", "INT UNSIGNED NULL")
        };
        foreach (var column in columns)
            if (!await ColumnExistsAsync(connection, column.Table, column.Name, ct))
                await ExecuteAsync(connection, $"ALTER TABLE `{column.Table}` ADD COLUMN `{column.Name}` {column.Definition}", ct);

        var indexes = new (string Table, string Name, string Definition)[]
        {
            ("generation_tasks", "ix_tasks_active_attempt", "KEY ix_tasks_active_attempt (active_attempt_id)"),
            ("generation_tasks", "ix_tasks_input_asset", "KEY ix_tasks_input_asset (input_asset_id)"),
            ("generation_tasks", "ix_tasks_profile_plan", "KEY ix_tasks_profile_plan (production_profile_id, shot_plan_id)"),
            ("generation_results", "ix_results_attempt", "KEY ix_results_attempt (attempt_id)"),
            ("generation_results", "uq_results_manifest", "UNIQUE KEY uq_results_manifest (manifest_id)"),
            ("task_events", "ix_task_events_attempt", "KEY ix_task_events_attempt (attempt_id, created_at)"),
            ("assets", "uq_assets_manifest", "UNIQUE KEY uq_assets_manifest (manifest_id)"),
            ("assets", "ix_assets_project_purpose_status", "KEY ix_assets_project_purpose_status (project_id, purpose, status, created_at)")
        };
        foreach (var index in indexes)
            if (!await IndexExistsAsync(connection, index.Table, index.Name, ct))
                await ExecuteAsync(connection, $"ALTER TABLE `{index.Table}` ADD {index.Definition}", ct);

        var foreignKeys = new (string Table, string Name, string Definition)[]
        {
            ("generation_tasks", "fk_tasks_active_attempt", "FOREIGN KEY (active_attempt_id) REFERENCES task_attempts(id) ON DELETE RESTRICT"),
            ("generation_tasks", "fk_tasks_output_manifest", "FOREIGN KEY (output_manifest_id) REFERENCES asset_manifests(id) ON DELETE RESTRICT"),
            ("generation_results", "fk_results_attempt_stage12", "FOREIGN KEY (attempt_id) REFERENCES task_attempts(id) ON DELETE RESTRICT"),
            ("generation_results", "fk_results_manifest_stage12", "FOREIGN KEY (manifest_id) REFERENCES asset_manifests(id) ON DELETE RESTRICT"),
            ("task_events", "fk_task_events_attempt_stage12", "FOREIGN KEY (attempt_id) REFERENCES task_attempts(id) ON DELETE RESTRICT"),
            ("task_events", "fk_task_events_manifest_stage12", "FOREIGN KEY (output_manifest_id) REFERENCES asset_manifests(id) ON DELETE RESTRICT"),
            ("assets", "fk_assets_manifest_stage12", "FOREIGN KEY (manifest_id) REFERENCES asset_manifests(id) ON DELETE RESTRICT"),
            ("assets", "fk_assets_attempt_stage12", "FOREIGN KEY (source_attempt_id) REFERENCES task_attempts(id) ON DELETE RESTRICT")
        };
        foreach (var foreignKey in foreignKeys)
            if (!await ForeignKeyExistsAsync(connection, foreignKey.Table, foreignKey.Name, ct))
                await ExecuteAsync(connection, $"ALTER TABLE `{foreignKey.Table}` ADD CONSTRAINT `{foreignKey.Name}` {foreignKey.Definition}", ct);

            await ExecuteAsync(connection, $"INSERT INTO schema_migrations(version) VALUES('{Version}')", ct);
        }
        finally
        {
            try
            {
                await using var release = new MySqlCommand("SELECT RELEASE_LOCK(@name)", connection);
                release.Parameters.AddWithValue("@name", lockName);
                await release.ExecuteScalarAsync(CancellationToken.None);
            }
            catch { }
        }
    }

    private static async Task<bool> MigrationExistsAsync(MySqlConnection connection, string version, CancellationToken ct)
    {
        await using var command = new MySqlCommand("SELECT COUNT(*) FROM schema_migrations WHERE version=@version", connection);
        command.Parameters.AddWithValue("@version", version);
        return Convert.ToInt32(await command.ExecuteScalarAsync(ct)) > 0;
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

    private static async Task<bool> ForeignKeyExistsAsync(MySqlConnection connection, string table, string name, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE constraint_schema=DATABASE() AND table_name=@table AND constraint_name=@name AND constraint_type='FOREIGN KEY'", connection);
        command.Parameters.AddWithValue("@table", table);
        command.Parameters.AddWithValue("@name", name);
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
