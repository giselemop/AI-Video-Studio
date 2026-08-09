$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot
$AiRoot = 'C:\install\AI'
$python = 'C:\install\AI\ComfyUI\venv\Scripts\python.exe'
$ffmpeg = 'C:\install\FFmpeg\bin\ffmpeg.exe'
$ffprobe = 'C:\install\FFmpeg\bin\ffprobe.exe'
$comfyVersion = 'unknown'
$gitVersion = 'unknown'
$pythonVersion = if (Test-Path $python) { (& $python --version 2>&1 | Out-String).Trim() } else { 'missing' }
$torch = if (Test-Path $python) { (& $python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())" 2>$null | Out-String).Trim() } else { 'missing' }
$nvidia = (& nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits 2>$null | Out-String).Trim()
$disk = Get-PSDrive -Name C
$dataPath = Join-Path $AiRoot 'Data'
$tts = Test-Path (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe')
$health = $null
try { $health = Invoke-RestMethod 'http://127.0.0.1:18080/api/health' -TimeoutSec 3 } catch { }
$models = if (Test-Path $AiRoot) { @(Get-ChildItem (Join-Path $AiRoot 'Models') -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.safetensors','.ckpt','.gguf','.pt','.pth','.bin' }).Count } else { 0 }
$workflows = @(Get-ChildItem (Join-Path $AiRoot 'Workflows') -Recurse -Filter '*.json' -File -ErrorAction SilentlyContinue).Count
$report = [ordered]@{
    generatedAt = (Get-Date).ToString('o')
    computer = $env:COMPUTERNAME
    windows = (Get-CimInstance Win32_OperatingSystem).Caption
    cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)
    python = $pythonVersion
    pytorchCuda = $torch
    nvidiaSmi = $nvidia
    cFreeBytes = [int64]$disk.Free
    cFreeGiB = [math]::Round($disk.Free / 1GB, 2)
    dataPath = $dataPath
    dataFreeGiB = [math]::Round($disk.Free / 1GB, 2)
    diskWarning = if ($disk.Free -lt 20GB) { 'BLOCK_BATCH_BELOW_20GB' } elseif ($disk.Free -lt 50GB) { 'WARN_BELOW_50GB' } else { 'OK' }
    modelFileCount = $models
    workflowJsonCount = $workflows
    comfyUiOnline = [bool]($health -and $health.comfy.online)
    databaseOnline = [bool]($health -and $health.database.online)
    ffmpegAvailable = (Test-Path $ffmpeg) -and (Test-Path $ffprobe)
    ttsAvailable = $tts
    paths = [ordered]@{ studio = $Root; ai = $AiRoot; models = (Join-Path $AiRoot 'Models'); workflows = (Join-Path $AiRoot 'Workflows'); data = (Join-Path $AiRoot 'Data') }
}
$path = Join-Path $Root 'logs\environment_check.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $path
$report | ConvertTo-Json -Depth 8
