using System.Text;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// 第二阶段 schema 的兼容迁移。MySQL 8.0.22 对 ADD COLUMN IF NOT EXISTS 支持不一致，
/// 所以先查询 information_schema，再执行固定 SQL；不删除任何已有用户数据。
/// </summary>
public static class ProductionSchemaMigrator
{
    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        await ExecuteAsync(connection, @"CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) NOT NULL PRIMARY KEY,
            applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci", ct);

        var columns = new (string Table, string Name, string Definition)[]
        {
            ("projects", "aspect_ratio", "VARCHAR(8) NOT NULL DEFAULT '16:9'"), ("projects", "style", "VARCHAR(160) NULL"), ("projects", "default_model_id", "BIGINT UNSIGNED NULL"), ("projects", "default_workflow_id", "BIGINT UNSIGNED NULL"), ("projects", "default_fps", "INT NOT NULL DEFAULT 30"), ("projects", "default_width", "INT NOT NULL DEFAULT 1920"), ("projects", "default_height", "INT NOT NULL DEFAULT 1080"), ("projects", "prompt_style", "VARCHAR(255) NULL"), ("projects", "bgm_path", "VARCHAR(1024) NULL"), ("projects", "bgm_volume", "DECIMAL(5,2) NOT NULL DEFAULT 0.18"),
            ("characters", "voice_id", "VARCHAR(120) NULL"), ("characters", "voice_speed", "DECIMAL(5,2) NOT NULL DEFAULT 1.00"), ("characters", "voice_pitch", "DECIMAL(5,2) NOT NULL DEFAULT 0.00"),
            ("scenes", "lighting", "VARCHAR(160) NULL"), ("scenes", "time_of_day", "VARCHAR(80) NULL"), ("scenes", "weather", "VARCHAR(80) NULL"), ("scenes", "architecture", "TEXT NULL"),
            ("episodes", "script_id", "BIGINT UNSIGNED NULL"), ("episodes", "production_mode", "VARCHAR(32) NOT NULL DEFAULT 'ManualReview'"), ("episodes", "narrator_voice_id", "VARCHAR(120) NULL"), ("episodes", "voice_volume", "DECIMAL(5,2) NOT NULL DEFAULT 1.00"), ("episodes", "bgm_volume", "DECIMAL(5,2) NOT NULL DEFAULT 0.18"), ("episodes", "sfx_volume", "DECIMAL(5,2) NOT NULL DEFAULT 0.60"), ("episodes", "subtitle_path", "VARCHAR(1024) NULL"), ("episodes", "cover_path", "VARCHAR(1024) NULL"), ("episodes", "total_duration_seconds", "DECIMAL(12,3) NULL"),
            ("shots", "action", "TEXT NULL"), ("shots", "dialogue", "TEXT NULL"), ("shots", "narration", "TEXT NULL"), ("shots", "emotion", "VARCHAR(160) NULL"), ("shots", "camera_type", "VARCHAR(120) NULL"), ("shots", "camera_motion", "VARCHAR(160) NULL"), ("shots", "duration_seconds", "DECIMAL(8,3) NOT NULL DEFAULT 5.00"), ("shots", "character_prompt", "TEXT NULL"), ("shots", "scene_prompt", "TEXT NULL"), ("shots", "action_prompt", "TEXT NULL"), ("shots", "camera_prompt", "TEXT NULL"), ("shots", "lighting_prompt", "TEXT NULL"), ("shots", "style_prompt", "TEXT NULL"), ("shots", "quality_prompt", "TEXT NULL"), ("shots", "prompt_version", "INT NOT NULL DEFAULT 1"), ("shots", "prompt_locked", "TINYINT(1) NOT NULL DEFAULT 0"), ("shots", "prompt_source_language", "VARCHAR(32) NOT NULL DEFAULT 'zh-CN'"), ("shots", "selected_keyframe_path", "VARCHAR(1024) NULL"), ("shots", "video_path", "VARCHAR(1024) NULL"), ("shots", "final_video_path", "VARCHAR(1024) NULL"), ("shots", "quality_score", "DECIMAL(5,2) NULL"), ("shots", "user_rating", "TINYINT NULL"), ("shots", "video_qc_json", "JSON NULL"), ("shots", "audio_status", "VARCHAR(32) NOT NULL DEFAULT 'Pending'"), ("shots", "subtitle_status", "VARCHAR(32) NOT NULL DEFAULT 'Pending'"), ("shots", "generation_profile_json", "JSON NULL"),
            ("generation_tasks", "error_type", "VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN'"), ("generation_tasks", "resource_class", "VARCHAR(16) NOT NULL DEFAULT 'GPU'"), ("generation_tasks", "stage", "VARCHAR(64) NULL"), ("generation_tasks", "dependency_task_id", "BIGINT UNSIGNED NULL"), ("generation_tasks", "paused", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("generation_results", "candidate_index", "INT NULL"), ("generation_results", "is_selected", "TINYINT(1) NOT NULL DEFAULT 0"), ("generation_results", "quality_score", "DECIMAL(5,2) NULL"), ("generation_results", "user_rating", "TINYINT NULL"), ("generation_results", "qc_json", "JSON NULL"), ("generation_results", "prompt_version", "INT NULL"), ("generation_results", "seed", "BIGINT NULL")
        };

        foreach (var column in columns)
            if (!await ColumnExistsAsync(connection, column.Table, column.Name, ct)) await ExecuteAsync(connection, $"ALTER TABLE `{column.Table}` ADD COLUMN `{column.Name}` {column.Definition}", ct);

        if (File.Exists(migrationPath))
        {
            foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
            {
                var trimmed = statement.Trim();
                if (Regex.IsMatch(trimmed, "^CREATE TABLE", RegexOptions.IgnoreCase)) await ExecuteAsync(connection, trimmed, ct);
            }
        }
        await ExecuteAsync(connection, "INSERT IGNORE INTO schema_migrations(version) VALUES('002_production_pipeline')", ct);
    }

    private static async Task<bool> ColumnExistsAsync(MySqlConnection connection, string table, string column, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=@table AND column_name=@column", connection);
        command.Parameters.AddWithValue("@table", table); command.Parameters.AddWithValue("@column", column);
        return Convert.ToInt32(await command.ExecuteScalarAsync(ct)) > 0;
    }

    private static async Task ExecuteAsync(MySqlConnection connection, string sql, CancellationToken ct)
    {
        await using var command = new MySqlCommand(sql, connection) { CommandTimeout = 120 }; await command.ExecuteNonQueryAsync(ct);
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
