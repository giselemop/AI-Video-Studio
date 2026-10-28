$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$BackupRoot = Join-Path $Root 'backup'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Target = Join-Path $BackupRoot $Stamp
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item (Join-Path $Root 'config\appsettings.json') $Target -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Root 'config\local.env.example') $Target -Force -ErrorAction SilentlyContinue
foreach ($source in @('C:\install\AI\Characters','C:\install\AI\Scenes','C:\install\AI\Workflows')) {
    if (Test-Path -LiteralPath $source) { Copy-Item $source (Join-Path $Target (Split-Path $source -Leaf)) -Recurse -Force }
}
foreach ($source in @((Join-Path $Root 'database\database.sql'), (Join-Path $Root 'database\migrations'), (Join-Path $Root 'scripts'))) {
    if (Test-Path -LiteralPath $source) { Copy-Item $source (Join-Path $Target (Split-Path $source -Leaf)) -Recurse -Force -ErrorAction SilentlyContinue }
}
$MysqlDump = 'C:\install\mysql8.0.22\bin\mysqldump.exe'
$Mysql = 'C:\install\mysql8.0.22\bin\mysql.exe'
$Config = Join-Path $Root 'config\local.env'
if ((Test-Path $MysqlDump) -and (Test-Path $Config)) {
    $values = @{}
    foreach ($line in Get-Content $Config) { if ($line -match '^\s*([^#=]+)=(.*)$') { $values[$Matches[1].Trim()] = $Matches[2].Trim().Trim('"').Trim("'") } }
    $oldPwd = $env:MYSQL_PWD
    try {
        $env:MYSQL_PWD = $values['AI_VIDEO_STUDIO_DB_PASSWORD']
        if (-not [string]::IsNullOrWhiteSpace($env:MYSQL_PWD)) {
            $hostName = if ($values['AI_VIDEO_STUDIO_DB_HOST']) { $values['AI_VIDEO_STUDIO_DB_HOST'] } else { '127.0.0.1' }
            $port = if ($values['AI_VIDEO_STUDIO_DB_PORT']) { $values['AI_VIDEO_STUDIO_DB_PORT'] } else { '3306' }
            $user = if ($values['AI_VIDEO_STUDIO_DB_USER']) { $values['AI_VIDEO_STUDIO_DB_USER'] } else { 'root' }
            $databaseName = if ($values['AI_VIDEO_STUDIO_DB_NAME']) { $values['AI_VIDEO_STUDIO_DB_NAME'] } else { 'ai_video_studio' }
            $databaseExists = $false
            if (Test-Path -LiteralPath $Mysql) {
                $databaseList = @(& $Mysql --protocol=TCP -h $hostName -P $port -u $user -N -B -e 'SHOW DATABASES;' 2>$null)
                if ($LASTEXITCODE -ne 0) { throw "mysql database precheck exit code: $LASTEXITCODE" }
                $databaseExists = $databaseList -contains $databaseName
            }
            if ($databaseExists) {
                $dumpFile = Join-Path $Target 'ai_video_studio.sql'
                # The least-privileged application DB user cannot read tablespaces or events.
                # Keep the backup usable without requesting broader database privileges.
                & $MysqlDump --protocol=TCP -h $hostName -P $port -u $user --single-transaction --no-tablespaces --skip-events $databaseName "--result-file=$dumpFile"
                if ($LASTEXITCODE -ne 0) { throw "mysqldump exit code: $LASTEXITCODE" }
                if (-not (Test-Path -LiteralPath $dumpFile -PathType Leaf) -or (Get-Item -LiteralPath $dumpFile).Length -lt 128) { throw "mysqldump produced no usable output" }
                $dumpHash = (Get-FileHash -LiteralPath $dumpFile -Algorithm SHA256).Hash.ToLowerInvariant()
                Set-Content -LiteralPath (Join-Path $Target 'backup-manifest.txt') -Encoding UTF8 -Value @(
                    "backup_created_at=$([DateTimeOffset]::Now.ToString('o'))",
                    "database_name=$databaseName",
                    "database_dump=ai_video_studio.sql",
                    "database_dump_sha256=$dumpHash",
                    "database_dump_bytes=$((Get-Item -LiteralPath $dumpFile).Length)"
                )
            } else {
                Write-Host "Database backup skipped: $databaseName does not exist yet; configuration and migration files were preserved." -ForegroundColor Yellow
            }
        }
    } finally { if ($null -eq $oldPwd) { Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue } else { $env:MYSQL_PWD = $oldPwd } }
}
Write-Host "Backup completed: $Target" -ForegroundColor Green
