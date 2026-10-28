param([string]$BuildDirectory='C:\install\AI\Data\Deploy\VisualTargeted20261024V1')
$ErrorActionPreference='Stop'
$pilotRoot='C:\install\AI\VideoStudio'
$pilotFolder='C:\install\AI\Data\VisualTargeted20261024'
$pilotBuild=[IO.Path]::GetFullPath($BuildDirectory)
if(-not $pilotBuild.StartsWith('C:\install\AI\Data\Deploy\',[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected build root'}
if(Get-NetTCPConnection -State Listen -LocalPort 18081 -ErrorAction SilentlyContinue){throw 'Inspect existing service before starting'}
$pilotExe=Join-Path $pilotBuild 'VideoStudio.Server.exe'
if(-not(Test-Path -LiteralPath $pilotExe)){throw 'Published build missing'}
$env:VIDEO_STUDIO_ROOT=$pilotRoot
$env:AI_VIDEO_STUDIO_PREFER_ENV='1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED='1'
$env:AI_VIDEO_STUDIO_LISTEN_URL='http://127.0.0.1:18081'
$env:AI_VIDEO_STUDIO_LOG_DIRECTORY=Join-Path $pilotFolder 'isolated-server-logs'
$pilotProcess=Start-Process -FilePath $pilotExe -WorkingDirectory $pilotRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $pilotFolder 'preview.stdout.log') -RedirectStandardError (Join-Path $pilotFolder 'preview.stderr.log')
[pscustomobject]@{pid=$pilotProcess.Id;executable=$pilotExe;url='http://127.0.0.1:18081';originalApiPreserved=$true}|ConvertTo-Json|Set-Content (Join-Path $pilotFolder 'deployment.json') -Encoding utf8
Write-Output ('Started dedicated repair service '+$pilotProcess.Id)
