[CmdletBinding()]
param([switch]$KeepRunning)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw "Missing built server: $dll" }
if (Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18080 is already in use.' }

$outFile = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-api-' + [Guid]::NewGuid().ToString('N') + '.stdout.log')
$errFile = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-api-' + [Guid]::NewGuid().ToString('N') + '.stderr.log')
$api = $null
$healthy = $false
try {
    $api = Start-Process -FilePath 'dotnet.exe' -ArgumentList @($dll) -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru -WindowStyle Hidden
    $health = $null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18080/api/health' -TimeoutSec 3
            if ($health.StatusCode -eq 200) { break }
        } catch { }
        $api.Refresh()
        if ($api.HasExited) { break }
    }
    $api.Refresh()
    if ($api.HasExited) { throw 'API exited before loopback health became available.' }
    if ($null -eq $health -or $health.StatusCode -ne 200) { throw 'API loopback health did not return HTTP 200.' }
    $healthJson = $health.Content | ConvertFrom-Json
    if (-not $healthJson.database.online) { throw 'API health reports database offline.' }
    if (-not $healthJson.ffmpeg.available) { throw 'API health reports FFmpeg unavailable.' }
    $listeners = @(Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction Stop)
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw 'API listener is not exactly 127.0.0.1:18080.' }
    $healthy = $true
    Write-Output ("PASS api-loopback status={0} databaseOnline={1} ffmpegAvailable={2} comfyReported={3} worker=0 autoApply=0" -f $health.StatusCode, $healthJson.database.online, $healthJson.ffmpeg.available, $healthJson.comfy.available)
    Write-Output ("PID={0} OUT={1} ERR={2}" -f $api.Id, $outFile, $errFile)
    if ($KeepRunning) { $api = $null }
}
finally {
    if ($null -ne $api) {
        try { $api.Refresh() } catch { }
        try { if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue } } catch { }
    }
    if (-not $healthy -and (Test-Path -LiteralPath $errFile)) {
        Write-Output 'API stderr tail:'
        Get-Content -LiteralPath $errFile -Tail 30
    }
}
