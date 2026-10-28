$ErrorActionPreference = 'Stop'
$rootPath = 'C:\install\AI\VideoStudio'
$runFolder = 'C:\install\AI\Data\SkinPilot20261024'
$candidateExe = 'C:\install\AI\Data\Deploy\SkinPilotFinal20261024\VideoStudio.Server.exe'
if (Get-NetTCPConnection -State Listen -LocalPort 18081 -ErrorAction SilentlyContinue) { throw 'Inspect occupied port 18081 before launching.' }
if (-not (Test-Path -LiteralPath $candidateExe)) { throw 'The isolated preview build is missing.' }
$env:VIDEO_STUDIO_ROOT = $rootPath
$env:AI_VIDEO_STUDIO_PREFER_ENV = '1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED = '1'
$env:AI_VIDEO_STUDIO_LISTEN_URL = 'http://127.0.0.1:18081'
$logTag = Split-Path -Leaf (Split-Path -Parent $candidateExe)
$previewProcess = Start-Process -FilePath $candidateExe -WorkingDirectory $rootPath -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runFolder ($logTag + '.stdout.log')) `
    -RedirectStandardError (Join-Path $runFolder ($logTag + '.stderr.log')) -PassThru
[pscustomobject]@{ pid=$previewProcess.Id; executable=$candidateExe; url='http://127.0.0.1:18081'; primaryServicePreserved=$true } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runFolder 'deployment.json') -Encoding UTF8
Write-Output ('Started local preview PID ' + $previewProcess.Id)
