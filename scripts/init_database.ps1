$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Config = Join-Path $Root 'config\local.env'
$Schema = Join-Path $Root 'database\database.sql'
$BackupScript = Join-Path $Root 'scripts\backup.ps1'
$Mysql = 'C:\install\mysql8.0.22\bin\mysql.exe'
if (-not (Test-Path -LiteralPath $Config)) { throw "Missing $Config. Copy local.env.example to local.env and fill the existing MySQL credentials." }
if (-not (Test-Path -LiteralPath $Mysql)) { throw "Missing MySQL client: $Mysql" }
$values = @{}
foreach ($line in Get-Content -LiteralPath $Config) {
    $trimmed = $line.Trim()
    if ($trimmed -and -not $trimmed.StartsWith('#') -and $trimmed.Contains('=')) { $pair = $trimmed -split '=', 2; $values[$pair[0].Trim()] = $pair[1].Trim().Trim('"').Trim("'") }
}
$oldPwd = $env:MYSQL_PWD
try {
    $env:MYSQL_PWD = $values['AI_VIDEO_STUDIO_DB_PASSWORD']
    if ([string]::IsNullOrWhiteSpace($env:MYSQL_PWD)) { throw 'AI_VIDEO_STUDIO_DB_PASSWORD is empty; database initialization was not run.' }
    if (Test-Path -LiteralPath $BackupScript) { & $BackupScript | Out-Host }
    $hostName = if ($values['AI_VIDEO_STUDIO_DB_HOST']) { $values['AI_VIDEO_STUDIO_DB_HOST'] } else { '127.0.0.1' }
    $port = if ($values['AI_VIDEO_STUDIO_DB_PORT']) { $values['AI_VIDEO_STUDIO_DB_PORT'] } else { '3306' }
    $user = if ($values['AI_VIDEO_STUDIO_DB_USER']) { $values['AI_VIDEO_STUDIO_DB_USER'] } else { 'root' }
    $sourceCommand = 'source ' + ($Schema -replace '\\', '/')
    & $Mysql --protocol=TCP -h $hostName -P $port -u $user --default-character-set=utf8mb4 -e $sourceCommand
    if ($LASTEXITCODE -ne 0) { throw "MySQL exit code: $LASTEXITCODE" }
    Write-Host 'Database schema initialized.' -ForegroundColor Green
} finally {
    if ($null -eq $oldPwd) { Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue } else { $env:MYSQL_PWD = $oldPwd }
}
