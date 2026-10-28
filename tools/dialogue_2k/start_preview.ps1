param([string]$BuildDirectory = 'C:\install\AI\Data\Deploy\Seed2K20261024')
$ErrorActionPreference = 'Stop'
$rootPath = 'C:\install\AI\VideoStudio'
$runFolder = 'C:\install\AI\Data\Dialogue2KSeedVR220261024'
$buildRoot = [IO.Path]::GetFullPath($BuildDirectory)
$allowedRoot = 'C:\install\AI\Data\Deploy\'
if (-not $buildRoot.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Preview build must stay in central Data/Deploy.' }
$candidateExe = Join-Path $buildRoot 'VideoStudio.Server.exe'
if (Get-NetTCPConnection -State Listen -LocalPort 18081 -ErrorAction SilentlyContinue) {
    throw 'Port 18081 is occupied; inspect the existing listener before starting another preview service.'
}
if (-not (Test-Path -LiteralPath $candidateExe)) { throw 'Build the isolated preview service first.' }
$env:VIDEO_STUDIO_ROOT = $rootPath
$env:AI_VIDEO_STUDIO_PREFER_ENV = '1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED = '1'
$env:AI_VIDEO_STUDIO_LISTEN_URL = 'http://127.0.0.1:18081'
$logTag = Split-Path -Leaf $buildRoot
$previewProcess = Start-Process -FilePath $candidateExe -WorkingDirectory $rootPath -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runFolder ($logTag + '.stdout.log')) `
    -RedirectStandardError (Join-Path $runFolder ($logTag + '.stderr.log')) -PassThru
$previousDeployment = Join-Path $runFolder 'deployment.json'
if (Test-Path -LiteralPath $previousDeployment) {
    $oldDeployment = Get-Content -LiteralPath $previousDeployment -Raw | ConvertFrom-Json
    $archive = Join-Path $runFolder ('deployment-' + $oldDeployment.previewPid + '.json')
    if (-not (Test-Path -LiteralPath $archive)) { Copy-Item -LiteralPath $previousDeployment -Destination $archive }
}
[pscustomobject]@{
    previewPid = $previewProcess.Id
    previewExecutable = $candidateExe
    previewUrl = 'http://127.0.0.1:18081'
    originalApiPreserved = $true
    deployment = 'Isolated local preview service; original binaries were not replaced'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runFolder 'deployment.json') -Encoding UTF8
Write-Output ('Started isolated local preview API, PID ' + $previewProcess.Id)
