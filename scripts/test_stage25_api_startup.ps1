[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$SecretConfig)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
$SecretConfig = [IO.Path]::GetFullPath($SecretConfig)
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw "Missing built server: $dll" }
if (-not (Test-Path -LiteralPath $SecretConfig -PathType Leaf)) { throw 'Missing exact stage25 secure config' }

$before = (& dotnet.exe $dll --stage25-structure $SecretConfig | Out-String).Trim()
if ($before -notmatch '^PASS structure') { throw 'pre-start structure check failed' }
$config = Get-Content -LiteralPath $SecretConfig -Raw | ConvertFrom-Json
$api = $null
$outFile = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage25-api-' + [Guid]::NewGuid().ToString('N') + '.stdout.log')
$errFile = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage25-api-' + [Guid]::NewGuid().ToString('N') + '.stderr.log')
try {
    $env:VIDEO_STUDIO_ROOT = $repoRoot
    $env:AI_VIDEO_STUDIO_PREFER_ENV = '1'
    $env:AI_VIDEO_STUDIO_DB_HOST = $config.Host
    $env:AI_VIDEO_STUDIO_DB_PORT = [string]$config.Port
    $env:AI_VIDEO_STUDIO_DB_NAME = $config.Database
    $env:AI_VIDEO_STUDIO_DB_USER = $config.AppUser
    $env:AI_VIDEO_STUDIO_DB_PASSWORD = $config.AppPassword
    $env:AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA = '0'
    $env:AI_VIDEO_STUDIO_ALLOW_DATABASE_CREATE = '0'
    $env:AI_VIDEO_STUDIO_WORKER_ENABLED = '0'

    $api = Start-Process -FilePath 'dotnet.exe' -ArgumentList @($dll) -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru -WindowStyle Hidden
    $health = $null
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Milliseconds 250
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18080/api/health' -TimeoutSec 10
            if ($health.StatusCode -eq 200) { break }
        }
        catch { }
        $api.Refresh()
        if ($api.HasExited) { throw 'isolated API exited before health check' }
    }
    if ($null -eq $health -or $health.StatusCode -ne 200) { throw 'isolated API loopback health check did not return HTTP 200' }
    $healthJson = $health.Content | ConvertFrom-Json
    if (-not $healthJson.database.online) { throw 'isolated API health did not report database online' }
    Write-Output ("PASS api-loopback status={0} databaseOnline={1} autoApply=0 worker=0" -f $health.StatusCode, $healthJson.database.online)
}
finally {
    if ($null -ne $api) {
        try { $api.Refresh() } catch { }
        try { if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue } } catch { }
    }
    foreach ($name in @('AI_VIDEO_STUDIO_DB_PASSWORD','AI_VIDEO_STUDIO_DB_USER','AI_VIDEO_STUDIO_DB_NAME','AI_VIDEO_STUDIO_DB_PORT','AI_VIDEO_STUDIO_DB_HOST','AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA','AI_VIDEO_STUDIO_ALLOW_DATABASE_CREATE','AI_VIDEO_STUDIO_WORKER_ENABLED','AI_VIDEO_STUDIO_PREFER_ENV','VIDEO_STUDIO_ROOT')) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
}
$after = (& dotnet.exe $dll --stage25-structure $SecretConfig | Out-String).Trim()
if ($after -ne $before) { throw 'schema structure summary changed across AUTO_APPLY_SCHEMA=0 startup' }
Write-Output 'PASS api-auto-apply-off schema-unchanged=true'
