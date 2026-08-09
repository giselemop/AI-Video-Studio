using System.Text;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// 视频 QA 的兼容迁移。通过 information_schema 判断缺失列，适配已经存在的第二阶段数据库。
/// </summary>
public static class VideoQaSchemaMigrator
{
    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        await ExecuteAsync(connection, @"CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) NOT NULL PRIMARY KEY,
            applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci", ct);

        var columns = new (string Table, string Name, string Definition)[]
        {
            ("shots", "expected_action", "TEXT NULL"),
            ("shots", "required_props_json", "JSON NULL"),
            ("shots", "qa_status", "VARCHAR(32) NOT NULL DEFAULT 'NotChecked'"),
            ("shots", "qa_score", "DECIMAL(5,2) NULL"),
            ("shots", "qa_result", "JSON NULL"),
            ("shots", "qa_version", "INT NOT NULL DEFAULT 0"),
            ("shots", "qa_reviewer", "VARCHAR(120) NULL"),
            ("shots", "qa_review_time", "DATETIME(3) NULL"),
            ("shots", "character_consistency_score", "DECIMAL(5,2) NULL"),
            ("shots", "motion_quality_score", "DECIMAL(5,2) NULL"),
            ("shots", "temporal_stability_score", "DECIMAL(5,2) NULL"),
            ("shots", "semantic_match_score", "DECIMAL(5,2) NULL"),
            ("shots", "visual_quality_score", "DECIMAL(5,2) NULL"),
            ("shots", "composition_score", "DECIMAL(5,2) NULL"),
            ("shots", "scene_consistency_score", "DECIMAL(5,2) NULL"),
            ("shots", "audio_score", "DECIMAL(5,2) NULL"),
            ("shots", "qa_retry_count", "INT NOT NULL DEFAULT 0"),
            ("episodes", "qa_status", "VARCHAR(32) NOT NULL DEFAULT 'NotChecked'"),
            ("episodes", "overall_score", "DECIMAL(5,2) NULL"),
            ("episodes", "qa_result", "JSON NULL"),
            ("episodes", "qa_version", "INT NOT NULL DEFAULT 0"),
            ("episodes", "qa_preset", "VARCHAR(32) NOT NULL DEFAULT 'Standard'"),
            ("episodes", "qa_reviewer", "VARCHAR(120) NULL"),
            ("episodes", "qa_review_time", "DATETIME(3) NULL"),
            ("episodes", "qa_locked", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("episodes", "master_path", "VARCHAR(1024) NULL"),
            ("episodes", "qa_report_path", "VARCHAR(1024) NULL"),
            ("episodes", "qa_report_json_path", "VARCHAR(1024) NULL"),
            ("episodes", "qa_approved_at", "DATETIME(3) NULL")
        };

        foreach (var column in columns)
            if (!await ColumnExistsAsync(connection, column.Table, column.Name, ct))
                await ExecuteAsync(connection, $"ALTER TABLE `{column.Table}` ADD COLUMN `{column.Name}` {column.Definition}", ct);

        if (File.Exists(migrationPath))
        {
            foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
            {
                var trimmed = statement.Trim();
                var executable = Regex.Replace(trimmed, @"(?m)^\s*--[^\r\n]*(?:\r?\n|$)", "").Trim();
                if (Regex.IsMatch(executable, "^(CREATE TABLE|INSERT(?: IGNORE)? INTO)", RegexOptions.IgnoreCase)) await ExecuteAsync(connection, executable, ct);
            }
        }
        await ExecuteAsync(connection, "INSERT IGNORE INTO schema_migrations(version) VALUES('003_video_qa')", ct);
    }

    private static async Task<bool> ColumnExistsAsync(MySqlConnection connection, string table, string column, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema=DATABASE() AND table_name=@table AND column_name=@column", connection);
        command.Parameters.AddWithValue("@table", table);
        command.Parameters.AddWithValue("@column", column);
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
