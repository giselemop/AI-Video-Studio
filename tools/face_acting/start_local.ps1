$ErrorActionPreference='Stop'
$rootPath='C:\install\AI\VideoStudio'
$folder='C:\install\AI\Data\FaceActing20261024'
if (Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue) { throw 'Inspect existing API before starting another worker.' }
$candidateExe='C:\install\AI\Data\Deploy\SkinPilotFinal20261024\VideoStudio.Server.exe'
if (-not (Test-Path -LiteralPath $candidateExe)) { throw 'Existing verified local build is missing.' }
$env:VIDEO_STUDIO_ROOT=$rootPath
$env:AI_VIDEO_STUDIO_PREFER_ENV='1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED='1'
$env:AI_VIDEO_STUDIO_LISTEN_URL='http://127.0.0.1:18080'
$process=Start-Process -FilePath $candidateExe -WorkingDirectory $rootPath -WindowStyle Hidden `
 -RedirectStandardOutput (Join-Path $folder 'api.stdout.log') -RedirectStandardError (Join-Path $folder 'api.stderr.log') -PassThru
[pscustomobject]@{pid=$process.Id;executable=$candidateExe;url='http://127.0.0.1:18080';startedExistingVerifiedBuild=$true;previousListenersAbsent=$true} |
 ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'api-deployment.json') -Encoding utf8
Write-Output ('Restored local API PID '+$process.Id)
