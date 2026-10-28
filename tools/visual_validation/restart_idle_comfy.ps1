$ErrorActionPreference='Stop'
$folder='C:\install\AI\Data\VisualValidation20261024'
$comfyRoot='C:\install\AI\ComfyUI'
$python=Join-Path $comfyRoot 'venv\Scripts\python.exe'
$queue=Invoke-RestMethod 'http://127.0.0.1:8188/queue' -TimeoutSec 10
if($queue.queue_running.Count -or $queue.queue_pending.Count){throw 'ComfyUI must be idle; no restart performed'}
$stats=Invoke-RestMethod 'http://127.0.0.1:8188/system_stats' -TimeoutSec 10
$listener=Get-NetTCPConnection -State Listen -LocalPort 8188
if(@($listener).Count -ne 1 -or $listener.LocalAddress -ne '127.0.0.1'){throw 'Unexpected Comfy listener'}
$comfyProcessId=$listener.OwningProcess
$process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$comfyProcessId)
$commandLine=$process.CommandLine -replace '\\{2,}','\'
if(-not $commandLine.Contains($python) -or -not $commandLine.Contains('main.py')){throw 'Unexpected Comfy process; preserved'}
$arguments=@('-u')+@($stats.system.argv)
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$retainedHistory=Invoke-RestMethod 'http://127.0.0.1:8188/history' -TimeoutSec 30
New-Item -ItemType Directory -Path (Join-Path $folder 'comfy-history') -Force | Out-Null
$retainedHistory|ConvertTo-Json -Depth 100|Set-Content (Join-Path $folder ('comfy-history\'+$stamp+'-live-history.json')) -Encoding utf8
foreach($name in @('comfy-before-restart.json','comfy-deployment.json','comfy.stdout.log','comfy.stderr.log')){
 if(Test-Path -LiteralPath (Join-Path $folder $name)){
  $archive=Join-Path $folder ('comfy-history\'+$stamp+'-'+$name)
  New-Item -ItemType Directory -Path (Split-Path $archive) -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $folder $name) -Destination $archive
 }
}
[pscustomobject]@{oldPid=$comfyProcessId;commandLine=$process.CommandLine;arguments=$arguments;version=$stats.system.comfyui_version;queueWasIdle=$true;reason='Load additive Klein model search paths; no core or package upgrade'}|ConvertTo-Json -Depth 4|Set-Content (Join-Path $folder 'comfy-before-restart.json') -Encoding utf8
Stop-Process -Id $comfyProcessId
Wait-Process -Id $comfyProcessId -Timeout 30 -ErrorAction SilentlyContinue
$newProcess=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $comfyRoot -WindowStyle Hidden -PassThru `
 -RedirectStandardOutput (Join-Path $folder 'comfy.stdout.log') -RedirectStandardError (Join-Path $folder 'comfy.stderr.log')
[pscustomobject]@{launcherPid=$newProcess.Id;python=$python;arguments=$arguments;coreVersionPreserved=$stats.system.comfyui_version}|ConvertTo-Json -Depth 4|Set-Content (Join-Path $folder 'comfy-deployment.json') -Encoding utf8
Write-Output ('Restarted only idle ComfyUI with the same runtime and flags, launcher '+$newProcess.Id)
