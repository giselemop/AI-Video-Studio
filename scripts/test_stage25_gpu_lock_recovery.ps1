[CmdletBinding()]
param([string]$DataRoot = '')

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$serverDll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
if (-not (Test-Path -LiteralPath $serverDll -PathType Leaf)) { throw "Missing built server: $serverDll" }
if ([string]::IsNullOrWhiteSpace($DataRoot)) { $DataRoot = Join-Path ([IO.Path]::GetTempPath()) ("ai-video-studio-stage25-gpu-recovery-" + [Guid]::NewGuid().ToString('N')) }
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
$crashOut = Join-Path $DataRoot 'crash-worker.stdout.log'
$crashErr = Join-Path $DataRoot 'crash-worker.stderr.log'
$recoveryOut = Join-Path $DataRoot 'recovery-worker.stdout.log'
$recoveryErr = Join-Path $DataRoot 'recovery-worker.stderr.log'
$crash = $null
$recovery = $null
try {
    $crash = Start-Process -FilePath 'dotnet.exe' -ArgumentList @($serverDll, '--stage12-gpu-probe', $DataRoot, 'crash-worker', 'crash') -RedirectStandardOutput $crashOut -RedirectStandardError $crashErr -PassThru -WindowStyle Hidden
    $entered = Join-Path $DataRoot 'crash-worker.entered'
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-Path -LiteralPath $entered -PathType Leaf) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (-not (Test-Path -LiteralPath $entered -PathType Leaf)) { throw 'Crash probe did not enter the GPU critical section' }
    $crash.Refresh()
    if ($crash.HasExited) { throw 'Crash probe exited before forced termination' }
    $crashPid = $crash.Id
    Stop-Process -Id $crashPid -Force
    $crash.WaitForExit(10000) | Out-Null

    $recovery = Start-Process -FilePath 'dotnet.exe' -ArgumentList @($serverDll, '--stage12-gpu-probe', $DataRoot, 'recovery-worker') -RedirectStandardOutput $recoveryOut -RedirectStandardError $recoveryErr -PassThru -WindowStyle Hidden
    if (-not $recovery.WaitForExit(30000)) { throw 'Recovery GPU probe did not exit within 30 seconds' }
    $recovery.Refresh()
    if (-not (Test-Path -LiteralPath (Join-Path $DataRoot 'recovery-worker.entered') -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $DataRoot 'recovery-worker.exited') -PathType Leaf)) { throw 'Recovery probe did not acquire and release the GPU lock' }
    if (-not [string]::IsNullOrWhiteSpace((Get-Content -LiteralPath $crashErr -Raw))) { throw 'Crash probe wrote stderr' }
    if (-not [string]::IsNullOrWhiteSpace((Get-Content -LiteralPath $recoveryErr -Raw))) { throw 'Recovery probe wrote stderr' }
    Write-Output ("PASS cross-process GPU lock recovery: killedPid={0}; recoveryPid={1}; fixture={2}" -f $crashPid, $recovery.Id, $DataRoot)
}
finally {
    foreach ($process in @($crash, $recovery)) {
        if ($null -ne $process) {
            try { $process.Refresh() } catch { }
            try { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } } catch { }
        }
    }
}
