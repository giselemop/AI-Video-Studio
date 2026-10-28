param([string]$BuildDirectory='C:\install\AI\Data\Deploy\CharacterReferencePack20261026V1')
$ErrorActionPreference='Stop'
$packRoot='C:\install\AI\VideoStudio'
$packFolder='C:\install\AI\Data\CharacterReferencePack20261026'
New-Item -ItemType Directory -Force -Path $packFolder | Out-Null
$buildPath=[IO.Path]::GetFullPath($BuildDirectory)
if(-not $buildPath.StartsWith('C:\install\AI\Data\Deploy\',[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected build root'}
$newExecutable=Join-Path $buildPath 'VideoStudio.Server.exe'
if(-not(Test-Path -LiteralPath $newExecutable)){throw 'Published executable missing'}
$q=Invoke-RestMethod 'http://127.0.0.1:8188/queue'
if($q.queue_running.Count -or $q.queue_pending.Count){throw 'Existing Comfy tasks are active'}
$preview=Invoke-RestMethod 'http://127.0.0.1:18081/api/minimax/local/status'
if(-not $preview.queue.paused -or $preview.queue.activeTasks){throw 'Preserve the existing preview worker; inspect before deploying'}
$listener=Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue
if($listener){
    $oldProcess=Get-Process -Id $listener.OwningProcess
    if($oldProcess.ProcessName -ne 'VideoStudio.Server' -or -not $oldProcess.Path.StartsWith('C:\install\AI\Data\Deploy\',[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected original API'}
    $session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $status=Invoke-RestMethod 'http://127.0.0.1:18080/api/auth/status' -WebSession $session
    if($status.loginRequired){throw 'User login required; no auth was changed'}
    $runtime=Invoke-RestMethod 'http://127.0.0.1:18080/api/minimax/local/status' -WebSession $session
    if($runtime.queue.activeTasks){throw 'Business tasks are still active'}
    if(-not(Test-Path -LiteralPath (Join-Path $packFolder 'deployment-before.json'))){
        [pscustomobject]@{pid=$oldProcess.Id;executable=$oldProcess.Path;primaryQueue=$runtime.queue;previewQueue=$preview.queue}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $packFolder 'deployment-before.json') -Encoding utf8
    }
    Invoke-RestMethod 'http://127.0.0.1:18080/api/production/pause' -Method Post -WebSession $session -Headers @{'X-CSRF-Token'=$status.csrfToken} | Out-Null
    Stop-Process -Id $oldProcess.Id
    Start-Sleep -Seconds 1
}
$env:VIDEO_STUDIO_ROOT=$packRoot
$env:AI_VIDEO_STUDIO_PREFER_ENV='1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED='1'
$env:AI_VIDEO_STUDIO_LISTEN_URL='http://127.0.0.1:18080'
$env:AI_VIDEO_STUDIO_LOG_DIRECTORY=Join-Path $packFolder 'server-logs'
$prefix=(Split-Path $buildPath -Leaf)+'-'+(Get-Date -Format 'HHmmss')
$started=Start-Process -FilePath $newExecutable -WorkingDirectory $packRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $packFolder ($prefix+'.stdout.log')) -RedirectStandardError (Join-Path $packFolder ($prefix+'.stderr.log'))
$started.Id|Set-Content -LiteralPath (Join-Path $packFolder 'server.pid') -Encoding ascii
$started.Id|Set-Content -LiteralPath (Join-Path $packRoot 'logs\studio.pid') -Encoding ascii
Write-Output ('Started character reference-pack API '+$started.Id)
