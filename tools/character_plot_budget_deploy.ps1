$ErrorActionPreference='Stop'
$taskRoot='C:\install\AI\VideoStudio'
$evidenceRoot='C:\install\AI\Data\CharacterPlotPreview20261027'
$runtime=Invoke-RestMethod 'http://127.0.0.1:18080/api/minimax/local/status'
$taskListFallback=$false
try{$tasks=Invoke-RestMethod 'http://127.0.0.1:18080/api/tasks?limit=500'}
catch{
    if([int]$_.Exception.Response.StatusCode -ne 503){throw}
    $queueCheckCode=@'
import sys
sys.path.insert(0,'C:/install/AI/VideoStudio/tools/character_scene')
from common import mysql
print(mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Running','Pending');"))
'@
    $activeSql=$queueCheckCode | & 'C:\install\AI\ComfyUI\venv\Scripts\python.exe' -X utf8 -
    if($LASTEXITCODE -ne 0 -or "$activeSql".Trim() -ne '0'){throw 'Read-only SQL cannot prove queue idle; do not deploy'}
    $tasks=@();$taskListFallback=$true
}
$comfyQueue=Invoke-RestMethod 'http://127.0.0.1:8188/queue'
if($runtime.queue.paused -or $runtime.queue.activeTasks -ne 0 -or @($tasks | Where-Object { $_.status -in @('Pending','Running') }).Count -ne 0 -or @($comfyQueue.queue_running).Count -ne 0 -or @($comfyQueue.queue_pending).Count -ne 0){throw 'Queue is not idle; preserve running work and do not deploy'}
$listener=Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction Stop | Select-Object -First 1
$oldProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
$publishRoot=Join-Path $taskRoot 'server\publish'
$expected=Join-Path $publishRoot 'VideoStudio.Server.exe'
if($oldProcess.ExecutablePath -ne $expected){throw 'Unexpected server process; do not stop it'}
$saved=Join-Path $evidenceRoot 'server-before-budget'
if(-not(Test-Path -LiteralPath $saved)){Copy-Item -LiteralPath $publishRoot -Destination $saved -Recurse}
$receipt=@{oldPid=$listener.OwningProcess;oldExecutable=$oldProcess.ExecutablePath;oldDllSha256=(Get-FileHash -LiteralPath (Join-Path $publishRoot 'VideoStudio.Server.dll')).Hash.ToLowerInvariant();backup=$saved;queueIdle=$true;comfyRestarted=$false;taskList503IdleVerifiedByReadOnlySql=$taskListFallback}
Stop-Process -Id $listener.OwningProcess -ErrorAction Stop
Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
$staging=Join-Path $evidenceRoot 'server-deploy-v3'
foreach($item in Get-ChildItem -LiteralPath $staging -File){
    $destination=Join-Path $publishRoot $item.Name
    if((Test-Path -LiteralPath $destination) -and (Get-FileHash -LiteralPath $destination).Hash -eq (Get-FileHash -LiteralPath $item.FullName).Hash){continue}
    for($attempt=1;$attempt -le 3;$attempt++){
        try{Copy-Item -LiteralPath $item.FullName -Destination $publishRoot -Force;break}
        catch{if($attempt -eq 3){throw};Start-Sleep -Milliseconds 750}
    }
}
$logStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$stdoutPath=Join-Path $evidenceRoot "server-$logStamp.stdout.log"
$stderrPath=Join-Path $evidenceRoot "server-$logStamp.stderr.log"
$newProcess=Start-Process -FilePath $expected -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
$receipt.stdoutPath=$stdoutPath;$receipt.stderrPath=$stderrPath
$receipt.newPid=$newProcess.Id;$receipt.newDllSha256=(Get-FileHash -LiteralPath (Join-Path $publishRoot 'VideoStudio.Server.dll')).Hash.ToLowerInvariant()
$receiptFile=Join-Path $evidenceRoot 'deployment-budget.json'
if(Test-Path -LiteralPath $receiptFile){Copy-Item -LiteralPath $receiptFile -Destination (Join-Path $evidenceRoot "deployment-before-$logStamp.json")}
$receipt | ConvertTo-Json | Set-Content -LiteralPath $receiptFile -Encoding UTF8
Set-Content -LiteralPath (Join-Path $taskRoot 'logs\studio.pid') -Value $newProcess.Id -Encoding ascii
Write-Output "Deployed to the original local service path; PID $($newProcess.Id). ComfyUI unchanged."
