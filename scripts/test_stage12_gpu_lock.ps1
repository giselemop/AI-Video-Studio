[CmdletBinding()]
param(
    [string]$DataRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$serverDll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
if (-not (Test-Path -LiteralPath $serverDll -PathType Leaf)) { throw "Missing built server: $serverDll" }

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = Join-Path ([IO.Path]::GetTempPath()) ("ai-video-studio-stage12-gpu-" + [Guid]::NewGuid().ToString('N'))
}
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
$outOne = Join-Path $DataRoot 'worker-one.stdout.log'
$outTwo = Join-Path $DataRoot 'worker-two.stdout.log'
$errOne = Join-Path $DataRoot 'worker-one.stderr.log'
$errTwo = Join-Path $DataRoot 'worker-two.stderr.log'

function Start-Probe {
    param([string]$Id, [string]$Stdout, [string]$Stderr)
    $arguments = @($serverDll, '--stage12-gpu-probe', $DataRoot, $Id)
    return Start-Process -FilePath 'dotnet.exe' -ArgumentList $arguments -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -PassThru -WindowStyle Hidden
}

$one = Start-Probe 'worker-one' $outOne $errOne
Start-Sleep -Milliseconds 100
$two = Start-Probe 'worker-two' $outTwo $errTwo
try {
    if (-not $one.WaitForExit(30000)) { throw 'First GPU probe did not exit within 30 seconds' }
    if (-not $two.WaitForExit(30000)) { throw 'Second GPU probe did not exit within 30 seconds' }
    $one.Refresh()
    $two.Refresh()
    if (-not $one.HasExited -or -not $two.HasExited) { throw 'GPU probe process did not reach a terminal state' }
    $stderr = @((Get-Content -LiteralPath $errOne -Raw), (Get-Content -LiteralPath $errTwo -Raw)) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if ($stderr.Count -gt 0) { throw ("GPU probe stderr: " + ($stderr -join " | ")) }
} finally {
    foreach ($process in @($one, $two)) {
        if ($null -ne $process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
}

$enteredOne = [DateTimeOffset]::Parse((Get-Content -LiteralPath (Join-Path $DataRoot 'worker-one.entered') -Raw).Trim())
$exitedOne = [DateTimeOffset]::Parse((Get-Content -LiteralPath (Join-Path $DataRoot 'worker-one.exited') -Raw).Trim())
$enteredTwo = [DateTimeOffset]::Parse((Get-Content -LiteralPath (Join-Path $DataRoot 'worker-two.entered') -Raw).Trim())
$exitedTwo = [DateTimeOffset]::Parse((Get-Content -LiteralPath (Join-Path $DataRoot 'worker-two.exited') -Raw).Trim())
$disjoint = ($enteredTwo -ge $exitedOne) -or ($enteredOne -ge $exitedTwo)
if (-not $disjoint) { throw "GPU critical sections overlapped: one=$enteredOne..$exitedOne; two=$enteredTwo..$exitedTwo" }

Write-Output ("Cross-process GPU lock test passed: worker-one={0}..{1}; worker-two={2}..{3}; fixture={4}" -f $enteredOne, $exitedOne, $enteredTwo, $exitedTwo, $DataRoot)
