param([string]$BuildDirectory='C:\install\AI\Data\Deploy\VisualValidation20261024')
$ErrorActionPreference='Stop'
$rootPath='C:\install\AI\VideoStudio'
$folder='C:\install\AI\Data\VisualValidation20261024'
$buildRoot=[IO.Path]::GetFullPath($BuildDirectory)
if (-not $buildRoot.StartsWith('C:\install\AI\Data\Deploy\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected preview build path' }
if (Get-NetTCPConnection -State Listen -LocalPort 18081 -ErrorAction SilentlyContinue) { throw 'Inspect existing 18081 process before restarting' }
$candidateExe=Join-Path $buildRoot 'VideoStudio.Server.exe'
if (-not(Test-Path -LiteralPath $candidateExe)){throw 'Publish the isolated build first'}
$env:VIDEO_STUDIO_ROOT=$rootPath
$env:AI_VIDEO_STUDIO_PREFER_ENV='1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED='1'
$env:AI_VIDEO_STUDIO_LISTEN_URL='http://127.0.0.1:18081'
$env:AI_VIDEO_STUDIO_LOG_DIRECTORY=Join-Path $folder 'isolated-server-logs'
$preview=Start-Process -FilePath $candidateExe -WorkingDirectory $rootPath -WindowStyle Hidden -PassThru `
 -RedirectStandardOutput (Join-Path $folder 'preview.stdout.log') -RedirectStandardError (Join-Path $folder 'preview.stderr.log')
[pscustomobject]@{pid=$preview.Id;executable=$candidateExe;url='http://127.0.0.1:18081';originalApiPreserved=$true}|ConvertTo-Json|Set-Content (Join-Path $folder 'deployment.json') -Encoding utf8
Write-Output ('Started isolated preview process '+$preview.Id)
