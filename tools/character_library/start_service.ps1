param([string]$BuildDirectory='C:\install\AI\Data\Deploy\CharacterLibrary20261026V1')
$ErrorActionPreference='Stop'
$taskRoot='C:\install\AI\VideoStudio'
$taskFolder='C:\install\AI\Data\CharacterLibrary20261026'
$buildPath=[IO.Path]::GetFullPath($BuildDirectory)
if(-not $buildPath.StartsWith('C:\install\AI\Data\Deploy\',[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected build root'}
$newExecutable=Join-Path $buildPath 'VideoStudio.Server.exe'
if(-not(Test-Path -LiteralPath $newExecutable)){throw 'Published executable missing'}
$comfy=Invoke-RestMethod 'http://127.0.0.1:8188/queue'
if($comfy.queue_running.Count -or $comfy.queue_pending.Count){throw 'Comfy tasks are still active; service was not replaced'}
$oldListener=Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue
if($oldListener){
    $oldProcess=Get-Process -Id $oldListener.OwningProcess
    if($oldProcess.ProcessName -ne 'VideoStudio.Server' -or -not $oldProcess.Path.StartsWith('C:\install\AI\Data\Deploy\',[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected original API process'}
    $webSession=New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $status=Invoke-RestMethod 'http://127.0.0.1:18080/api/auth/status' -WebSession $webSession
    if($status.loginRequired){throw 'User login required; no auth was changed'}
    $headers=@{'X-CSRF-Token'=$status.csrfToken}
    $queueStatus=Invoke-RestMethod 'http://127.0.0.1:18080/api/minimax/local/status' -WebSession $webSession
    if($queueStatus.queue.activeTasks -ne 0){throw 'Existing business tasks are active'}
    $previewStatus=Invoke-RestMethod 'http://127.0.0.1:18081/api/minimax/local/status'
    if(-not $previewStatus.queue.paused -or $previewStatus.queue.activeTasks -ne 0){throw 'Existing preview worker must remain paused and idle'}
    $deploymentFile=Join-Path $taskFolder 'deployment.json'
    if(-not(Test-Path -LiteralPath $deploymentFile)){
        [pscustomobject]@{originalPid=$oldProcess.Id;originalExecutable=$oldProcess.Path;originalQueue=$queueStatus.queue;preservedPreviewQueue=$previewStatus.queue;newExecutable=$newExecutable;url='http://127.0.0.1:18080'}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $deploymentFile -Encoding utf8
    }
    Invoke-RestMethod 'http://127.0.0.1:18080/api/production/pause' -Method Post -Headers $headers -WebSession $webSession | Out-Null
    Stop-Process -Id $oldProcess.Id
    Start-Sleep -Seconds 1
}
$env:VIDEO_STUDIO_ROOT=$taskRoot
$env:AI_VIDEO_STUDIO_PREFER_ENV='1'
$env:AI_VIDEO_STUDIO_WORKER_ENABLED='1'
$env:AI_VIDEO_STUDIO_LISTEN_URL='http://127.0.0.1:18080'
$env:AI_VIDEO_STUDIO_LOG_DIRECTORY=Join-Path $taskFolder 'server-logs'
$logPrefix=(Split-Path $buildPath -Leaf)+'-'+(Get-Date -Format 'HHmmss')
$newProcess=Start-Process -FilePath $newExecutable -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskFolder ($logPrefix+'.stdout.log')) -RedirectStandardError (Join-Path $taskFolder ($logPrefix+'.stderr.log'))
$newProcess.Id|Set-Content (Join-Path $taskFolder 'server.pid')
Write-Output ('Started character library API '+$newProcess.Id)
