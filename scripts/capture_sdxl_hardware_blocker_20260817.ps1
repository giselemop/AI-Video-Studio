$ErrorActionPreference = 'Continue'
$runRoot = 'C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01'
$modelsRoot = 'C:\install\AI\Models'
$outPath = Join-Path $runRoot '18-sdxl-hardware-blocker.json'

function Get-AssetRecord {
    param([string]$Name, [string]$Path, [int64]$ExpectedBytes, [string]$Url)
    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    $rangeFiles = @(Get-ChildItem -LiteralPath (Split-Path -Parent $Path) -Filter ((Split-Path -Leaf $Path) + '.range*') -File -ErrorAction SilentlyContinue)
    $nonEmpty = @($rangeFiles | Where-Object { $_.Length -gt 0 })
    [pscustomobject]@{
        name = $Name
        path = $Path
        url = $Url
        expectedBytes = $ExpectedBytes
        actualBytes = if ($item) { [int64]$item.Length } else { 0 }
        completeBySize = [bool]($item -and $item.Length -eq $ExpectedBytes)
        rangeFileCount = $rangeFiles.Count
        nonEmptyRangeFileCount = $nonEmpty.Count
        rangeBytes = [int64](($rangeFiles | Measure-Object -Property Length -Sum).Sum)
    }
}

$assets = @(
    (Get-AssetRecord 'SDXL base checkpoint' (Join-Path $modelsRoot 'checkpoints\sdxl\sd_xl_base_1.0.safetensors') 6938078334 'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors'),
    (Get-AssetRecord 'InstantID adapter' (Join-Path $modelsRoot 'instantid\ip-adapter.bin') 1691134141 'https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin'),
    (Get-AssetRecord 'InstantID ControlNet' (Join-Path $modelsRoot 'controlnet\instantid\diffusion_pytorch_model.safetensors') 2502139136 'https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors'),
    (Get-AssetRecord 'PuLID adapter' (Join-Path $modelsRoot 'pulid\ip-adapter_pulid_sdxl_fp16.safetensors') 791372856 'https://huggingface.co/huchenlei/ipadapter_pulid/resolve/main/ip-adapter_pulid_sdxl_fp16.safetensors'),
    (Get-AssetRecord 'antelopev2 archive' (Join-Path $modelsRoot 'InsightFace\downloads\antelopev2.zip') 360662982 'https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip')
)

$gpu = @()
$nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvidia) {
    $gpu = @((& $nvidia.Source '--query-gpu=name,memory.total,memory.used,memory.free' '--format=csv,noheader,nounits' 2>&1 | Out-String).Trim())
}

$comfyStats = $null
try { $comfyStats = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 10 } catch { $comfyStats = @{ error = $_.Exception.Message } }
$downloadProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'parallel_download_asset' } | ForEach-Object { [pscustomobject]@{ pid = $_.ProcessId; parentPid = $_.ParentProcessId; name = $_.Name; creationDate = $_.CreationDate; commandLine = $_.CommandLine } })
$drive = New-Object System.IO.DriveInfo('C')

$rangeProbeUrl = 'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors'
$rangeProbe = $null
$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) {
    $probeOutput = (& $curl.Source '-sS' '-L' '-r' '0-1048575' '--max-time' '30' '-o' 'NUL' '-w' 'http=%{http_code} bytes=%{size_download} speed=%{speed_download} time=%{time_total}' $rangeProbeUrl 2>&1 | Out-String).Trim()
    $rangeProbe = [pscustomobject]@{ command = 'curl.exe -L -r 0-1048575 -o NUL'; url = $rangeProbeUrl; exitCode = $LASTEXITCODE; output = $probeOutput; interpretation = 'A successful 206/1048576-byte response proves range access, not that the multi-gigabyte model can finish within this run.' }
}

$probePath = Join-Path $runRoot 'adapter-asset-probe.json'
$probe = if (Test-Path -LiteralPath $probePath) { Get-Content -LiteralPath $probePath -Raw | ConvertFrom-Json } else { $null }
$totalKnownBytes = ($assets | Measure-Object -Property expectedBytes -Sum).Sum
$complete = @($assets | Where-Object completeBySize).Count
$status = if ($complete -eq $assets.Count) { 'ASSETS_COMPLETE_READY_FOR_RUNTIME_PROBE' } else { 'BLOCKED_PREGENERATION_INCOMPLETE_SDXL_OR_INSTANTID_ASSETS' }

$report = [ordered]@{
    schemaVersion = '2026-08-17.sdxl-hardware-blocker.v1'
    capturedAt = (Get-Date).ToUniversalTime().ToString('o')
    runRoot = $runRoot
    status = $status
    hardware = [ordered]@{
        nvidiaSmi = $gpu
        comfySystemStats = $comfyStats
        diskC = [ordered]@{ availableBytes = [int64]$drive.AvailableFreeSpace; availableGiB = [math]::Round($drive.AvailableFreeSpace / 1GB, 2) }
    }
    assets = $assets
    knownAssetBytesIncludingEVAEstimate = [ordered]@{ bytes = [int64]($totalKnownBytes + 856MB); gib = [math]::Round(($totalKnownBytes + 856MB) / 1GB, 2); evaEstimate = '~856 MiB, not downloaded by controlled probe' }
    rangeProbe = $rangeProbe
    downloadProcesses = $downloadProcesses
    loaderProbe = if ($probe) { $probe.probes } else { @() }
    actualGenerationAttempted = $false
    actualGenerationResult = 'NOT_ATTEMPTED: full SDXL checkpoint and InstantID ControlNet were not complete; PuLID also lacks EVA CLIP.'
    hardwareBoundary = 'The RTX 4070 reports 12282 MiB total in ComfyUI. No CUDA OOM was observed in this run because no valid SDXL workflow was started. SDXL peak VRAM remains unmeasured; this record is an asset/pre-generation block, not an invented OOM result.'
    preservation = 'Partial files and range fragments are retained as resumable evidence; no existing model, QA output, or user work was deleted or overwritten.'
}
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $outPath -Encoding utf8
$report | ConvertTo-Json -Depth 12
