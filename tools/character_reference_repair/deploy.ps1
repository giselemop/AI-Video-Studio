$ErrorActionPreference='Stop'
$taskRoot='C:\install\AI\VideoStudio'
$evidenceRoot='C:\install\AI\Data\CharacterReferenceRepair20261027'
$runtime=Invoke-RestMethod 'http://127.0.0.1:18080/api/minimax/local/status'
$tasks=Invoke-RestMethod 'http://127.0.0.1:18080/api/tasks?limit=500'
$comfyQueue=Invoke-RestMethod 'http://127.0.0.1:8188/queue'
if($runtime.queue.activeTasks -ne 0 -or @($tasks | Where-Object { $_.status -in @('Pending','Running') }).Count -ne 0 -or @($comfyQueue.queue_running).Count -ne 0 -or @($comfyQueue.queue_pending).Count -ne 0){throw 'Queue is not idle; preserve running work and do not deploy'}
$listener=Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction Stop | Select-Object -First 1
$oldProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
$publishRoot=Join-Path $taskRoot 'server\publish'
$expected=Join-Path $publishRoot 'VideoStudio.Server.exe'
if($oldProcess.ExecutablePath -ne $expected){throw 'Unexpected server process; do not stop it'}
$saved=Join-Path $evidenceRoot 'server-before'
if(-not(Test-Path -LiteralPath $saved)){Copy-Item -LiteralPath $publishRoot -Destination $saved -Recurse}
$receipt=@{oldPid=$listener.OwningProcess;oldExecutable=$oldProcess.ExecutablePath;oldDllSha256=(Get-FileHash -LiteralPath (Join-Path $publishRoot 'VideoStudio.Server.dll')).Hash.ToLowerInvariant();backup=$saved;queueIdle=$true;comfyRestarted=$false}
Stop-Process -Id $listener.OwningProcess -ErrorAction Stop
Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
$staging=Join-Path $evidenceRoot 'deploy'
foreach($item in Get-ChildItem -LiteralPath $staging -File){
    $destination=Join-Path $publishRoot $item.Name
    if((Test-Path -LiteralPath $destination) -and (Get-FileHash -LiteralPath $destination).Hash -eq (Get-FileHash -LiteralPath $item.FullName).Hash){continue}
    for($attempt=1;$attempt -le 3;$attempt++){
        try{Copy-Item -LiteralPath $item.FullName -Destination $publishRoot -Force;break}
        catch{if($attempt -eq 3){throw};Start-Sleep -Milliseconds 750}
    }
}
$newProcess=Start-Process -FilePath $expected -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidenceRoot 'server.stdout.log') -RedirectStandardError (Join-Path $evidenceRoot 'server.stderr.log')
$receipt.newPid=$newProcess.Id;$receipt.newDllSha256=(Get-FileHash -LiteralPath (Join-Path $publishRoot 'VideoStudio.Server.dll')).Hash.ToLowerInvariant()
$receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceRoot 'deployment.json') -Encoding UTF8
Set-Content -LiteralPath (Join-Path $taskRoot 'logs\studio.pid') -Value $newProcess.Id -Encoding ascii
Write-Output "Deployed to the original local service path; PID $($newProcess.Id). ComfyUI unchanged."
