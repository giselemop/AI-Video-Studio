[CmdletBinding()]
param(
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

if (-not $Apply) {
    throw '此脚本会修复数据库中的不可逆乱码。请在确认后使用 -Apply 运行。'
}

$root = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $root 'config\local.env'
$migrationPath = Join-Path $root 'database\migrations\006_repair_garbled_text.sql'
$mysql = 'C:\install\mysql8.0.22\bin\mysql.exe'

if (-not (Test-Path -LiteralPath $configPath)) { throw "未找到本地数据库配置：$configPath" }
if (-not (Test-Path -LiteralPath $migrationPath)) { throw "未找到修复迁移：$migrationPath" }
if (-not (Test-Path -LiteralPath $mysql)) { throw "未找到 MySQL 客户端：$mysql" }

$values = @{}
foreach ($line in Get-Content -LiteralPath $configPath) {
    if ($line -match '^\s*([^#=]+)=(.*)$') {
        $values[$Matches[1].Trim()] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}

$dbHost = if ($values['AI_VIDEO_STUDIO_DB_HOST']) { $values['AI_VIDEO_STUDIO_DB_HOST'] } else { '127.0.0.1' }
$dbPort = if ($values['AI_VIDEO_STUDIO_DB_PORT']) { $values['AI_VIDEO_STUDIO_DB_PORT'] } else { '3306' }
$dbUser = if ($values['AI_VIDEO_STUDIO_DB_USER']) { $values['AI_VIDEO_STUDIO_DB_USER'] } else { 'root' }
$dbName = if ($values['AI_VIDEO_STUDIO_DB_NAME']) { $values['AI_VIDEO_STUDIO_DB_NAME'] } else { 'ai_video_studio' }
$previousPassword = $env:MYSQL_PWD

try {
    $env:MYSQL_PWD = $values['AI_VIDEO_STUDIO_DB_PASSWORD']

    # Always create a fresh recovery point immediately before applying the data repair.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'backup.ps1')
    if ($LASTEXITCODE -ne 0) { throw "备份失败，退出码：$LASTEXITCODE" }

    $mysqlSourcePath = (Resolve-Path -LiteralPath $migrationPath).Path.Replace('\', '/')
    & $mysql --protocol=TCP --default-character-set=utf8mb4 -h $dbHost -P $dbPort -u $dbUser $dbName -e "source $mysqlSourcePath"
    if ($LASTEXITCODE -ne 0) { throw "乱码修复迁移失败，退出码：$LASTEXITCODE" }

    $remaining = (& $mysql --protocol=TCP --default-character-set=utf8mb4 -h $dbHost -P $dbPort -u $dbUser -N -B $dbName -e @"
SELECT
    (SELECT COUNT(*) FROM audio_cache WHERE LOCATE('??', text_content) > 0)
  + (SELECT COUNT(*) FROM characters WHERE LOCATE('??', CONCAT_WS('', name, age_setting, face_features, hair, clothes, body_ratio, fixed_prompt, negative_prompt)) > 0)
  + (SELECT COUNT(*) FROM episodes WHERE LOCATE('??', CONVERT(qa_result USING utf8mb4)) > 0)
  + (SELECT COUNT(*) FROM generation_tasks WHERE LOCATE('??', CONCAT_WS('', CONVERT(input_json USING utf8mb4), error_message)) > 0)
  + (SELECT COUNT(*) FROM operation_logs WHERE LOCATE('??', message) > 0)
  + (SELECT COUNT(*) FROM projects WHERE LOCATE('??', CONCAT_WS('', description, style, prompt_style)) > 0)
  + (SELECT COUNT(*) FROM prompt_history WHERE LOCATE('??', CONCAT_WS('', prompt, negative_prompt, CONVERT(components_json USING utf8mb4))) > 0)
  + (SELECT COUNT(*) FROM qa_runs WHERE LOCATE('??', CONVERT(result_json USING utf8mb4)) > 0)
  + (SELECT COUNT(*) FROM quality_experiment_runs WHERE LOCATE('??', CONCAT_WS('', CONVERT(metrics_json USING utf8mb4), notes)) > 0)
  + (SELECT COUNT(*) FROM quality_experiments WHERE LOCATE('??', description) > 0)
  + (SELECT COUNT(*) FROM scenes WHERE LOCATE('??', CONCAT_WS('', name, description, fixed_prompt, negative_prompt, style)) > 0)
  + (SELECT COUNT(*) FROM script_versions WHERE LOCATE('??', CONCAT_WS('', title, content)) > 0)
  + (SELECT COUNT(*) FROM scripts WHERE LOCATE('??', CONCAT_WS('', title, content, CONVERT(analysis_json USING utf8mb4))) > 0)
  + (SELECT COUNT(*) FROM shots WHERE LOCATE('??', CONCAT_WS('', description, prompt, negative_prompt, action, CONVERT(qa_result USING utf8mb4))) > 0);
"@).Trim()

    if ([int]$remaining -ne 0) {
        throw "乱码修复后的扫描仍发现 $remaining 条记录。数据库已保留刚才的备份，未标记为通过。"
    }

    Write-Host '乱码修复完成：后端可见数据扫描为 0，备份与迁移均已保留。' -ForegroundColor Green
}
finally {
    if ($null -eq $previousPassword) {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
    else {
        $env:MYSQL_PWD = $previousPassword
    }
}
