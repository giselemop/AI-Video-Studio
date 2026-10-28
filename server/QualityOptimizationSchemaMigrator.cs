using System.Text;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Additive quality-lab schema and versioned production presets. No existing
/// media, task, character or workflow row is deleted or overwritten.
/// </summary>
public static class QualityOptimizationSchemaMigrator
{
    public static async Task ApplyAsync(MySqlConnection connection, string migrationPath, CancellationToken ct = default)
    {
        if (File.Exists(migrationPath))
        {
            foreach (var statement in SplitSql(await File.ReadAllTextAsync(migrationPath, Encoding.UTF8, ct)))
            {
                var executable = statement.Trim();
                if (Regex.IsMatch(executable, "^CREATE TABLE", RegexOptions.IgnoreCase)) await ExecuteAsync(connection, executable, ct);
            }
        }

        var presets = new (string Name, string Type, string Parameters, string Description)[]
        {
            ("Portrait_CloseUp_v2", "Image", "JSON_OBJECT('workflow','08_portrait_quality_v2_api.json','model','v1-5-pruned-emaonly-fp16.safetensors','width',640,'height',832,'steps',30,'cfg',5.8,'sampler','dpmpp_2m','scheduler','karras','candidateCount',2)", "人物近景基线：优先五官和眼睛，单人正面或轻微三分之四。"),
            ("Portrait_HalfBody_v2", "Image", "JSON_OBJECT('workflow','08_portrait_quality_v2_api.json','model','v1-5-pruned-emaonly-fp16.safetensors','width',640,'height',832,'steps',30,'cfg',5.8,'sampler','dpmpp_2m','scheduler','karras','candidateCount',2)", "人物半身：先保证脸部清晰，再保留上半身服装和构图。"),
            ("Portrait_FullBody_v1", "Image", "JSON_OBJECT('workflow','08_portrait_quality_v2_api.json','model','v1-5-pruned-emaonly-fp16.safetensors','width',640,'height',832,'steps',30,'cfg',5.8,'sampler','dpmpp_2m','scheduler','karras','candidateCount',1)", "全身构图参考：全身只负责比例、服装和姿态，脸部以 Master Face 为准。"),
            ("I2V_SubtleMotion_v2", "ImageToVideo", "JSON_OBJECT('workflow','10_ltx_face_stable_v2_api.json','model','ltxv-2b-0.9.8-distilled-fp8.safetensors','width',320,'height',416,'frames',73,'fps',24,'duration',3.042,'referenceStrength',0.55,'inputStrength',1.0,'motionLevel',1,'camera','Static')", "角色参考优先的 3 秒 Draft：眨眼、呼吸和极小转头。"),
            ("I2V_TurnHead_v2", "ImageToVideo", "JSON_OBJECT('workflow','10_ltx_face_stable_v2_api.json','model','ltxv-2b-0.9.8-distilled-fp8.safetensors','width',320,'height',416,'frames',121,'fps',24,'duration',5.0,'referenceStrength',0.60,'inputStrength',1.0,'motionLevel',2,'camera','Static')", "5 秒 Motion Level 2：慢速小角度转头，必须先通过 SubtleMotion。"),
            ("I2V_NoReference_Wan_v1", "ImageToVideo", "JSON_OBJECT('workflow','05_wan22_ti2v_5b_api.json','model','wan2.2_ti2v_5B_fp16.safetensors','width',320,'height',416,'frames',49,'fps',24,'duration',2.042,'motionLevel',1,'camera','Static')", "无角色参考时的 Wan 保守路线；不作为人物身份稳定默认路线。"),
            ("Camera_Static_v1", "Camera", "JSON_OBJECT('cameraMotion','locked-off','motionLevel',1)", "固定镜头，作为人物稳定回归基线。"),
            ("Camera_SlowPush_v1", "Camera", "JSON_OBJECT('cameraMotion','slow push in','motionLevel',1)", "只有 Static 通过后才启用的极慢推镜头。"),
            ("Enhance_Safe_24fps_v1", "Enhancement", "JSON_OBJECT('width',1920,'height',1080,'fps',24,'deflicker',false,'interpolate',false,'scale','lanczos')", "安全增强：先放大和转码，不默认插帧，避免脸部鬼影。")
        };

        foreach (var preset in presets)
        {
            await ExecuteAsync(connection, $@"
                INSERT INTO generation_presets(name,preset_type,parameters_json,description)
                VALUES(@name,@type,{preset.Parameters},@description)
                ON DUPLICATE KEY UPDATE parameters_json=VALUES(parameters_json),description=VALUES(description)", ct, ("@name", preset.Name), ("@type", preset.Type), ("@description", preset.Description));
        }

        await ExecuteAsync(connection, @"
            INSERT INTO generation_presets(name,preset_type,parameters_json,description)
            VALUES('I2V_SubtleMotion_v3','ImageToVideo',JSON_OBJECT('workflow','12_ltx_face_stable_v3_api.json','model','ltxv-2b-0.9.8-distilled-fp8.safetensors','width',320,'height',416,'frames',73,'fps',24,'duration',3.042,'referenceStrength',0.45,'guideFrameIndex',72,'inputStrength',1.0,'allowLongVideo',false,'motionLevel',1,'camera','Static'),@description)
            ON DUPLICATE KEY UPDATE parameters_json=VALUES(parameters_json),description=VALUES(description)", ct, ("@description", "已验证的人物 I2V 默认：3 秒、320x416、guide 0.45，只做自然眨眼和呼吸；必须人工复核。"));

        await ExecuteAsync(connection, "INSERT IGNORE INTO schema_migrations(version) VALUES('005_quality_optimization')", ct);
    }

    private static async Task ExecuteAsync(MySqlConnection connection, string sql, CancellationToken ct, params (string Name, object? Value)[] parameters)
    {
        await using var command = new MySqlCommand(sql, connection) { CommandTimeout = 120 };
        foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter.Name, parameter.Value ?? DBNull.Value);
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
