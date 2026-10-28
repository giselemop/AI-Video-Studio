$ErrorActionPreference='Stop'
$packFolder='C:\install\AI\Data\CharacterReferencePack20261026'
if(Get-NetTCPConnection -State Listen -LocalPort 8188 -ErrorAction SilentlyContinue){throw 'Existing Comfy listener preserved'}
if(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*ComfyUI*main.py*' }){throw 'Existing Comfy process preserved'}
$runtime=Invoke-RestMethod 'http://127.0.0.1:18080/api/minimax/local/status'
$preview=Invoke-RestMethod 'http://127.0.0.1:18081/api/minimax/local/status'
if($runtime.queue.activeTasks -or $preview.queue.activeTasks -or -not $preview.queue.paused){throw 'Business workers must be idle; old preview must remain paused'}
$previous=Get-Content 'C:\install\AI\Data\VisualValidation20261024\comfy-deployment.json' -Raw|ConvertFrom-Json
$arguments=@($previous.arguments)+@('--disable-mmap')
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item -LiteralPath 'C:\install\AI\Data\VisualValidation20261024\comfy.stderr.log' -Destination (Join-Path $packFolder ($stamp+'-comfy-crash-retained.log'))
$env:PYTHONNOUSERSITE='1'
$started=Start-Process -FilePath $previous.python -ArgumentList $arguments -WorkingDirectory 'C:\install\AI\ComfyUI' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $packFolder ($stamp+'-comfy.stdout.log')) -RedirectStandardError (Join-Path $packFolder ($stamp+'-comfy.stderr.log'))
[pscustomobject]@{launcherPid=$started.Id;python=$previous.python;arguments=$arguments;reason='Recover terminated process; torch storage access violation while loading safetensors. Installed --disable-mmap copies tensors away from memory-mapped storage. No model/core/package changes.';previousTask=1452;previousTaskStatus='Failed';gpuConcurrency=1}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $packFolder 'comfy-recovery.json') -Encoding utf8
Write-Output ('Recovered Comfy launcher '+$started.Id+'; original failure log retained')
