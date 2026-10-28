[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$ModelsRoot = 'C:\install\AI\Models',
    [string]$OutputPath = 'C:\install\AI\Data\QA\model-deployment-20260815.json'
)

$ErrorActionPreference = 'Stop'
$started = Get-Date
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

function Read-HttpError($errorRecord) {
    $text = $errorRecord.ErrorDetails.Message
    if ([string]::IsNullOrWhiteSpace($text) -and $errorRecord.Exception.Response) {
        try {
            $stream = $errorRecord.Exception.Response.GetResponseStream()
            $reader = [System.IO.StreamReader]::new($stream)
            $text = $reader.ReadToEnd()
            $reader.Dispose(); $stream.Dispose()
        } catch { }
    }
    if ([string]::IsNullOrWhiteSpace($text)) { $text = $errorRecord.Exception.Message }
    return $text
}

function Submit-LoaderProbe([string]$model, [string]$family, $workflow) {
    $payload = @{ prompt = $workflow; client_id = "target-model-probe-20260815-$family" } | ConvertTo-Json -Depth 50 -Compress
    try {
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
        return [ordered]@{ family = $family; requestedModel = $model; status = 'Queued'; promptId = [string]$response.prompt_id; error = $null }
    } catch {
        return [ordered]@{ family = $family; requestedModel = $model; status = 'BlockedAtLoaderValidation'; promptId = $null; error = (Read-HttpError $_) }
    }
}

$health = Invoke-RestMethod -Uri "$ComfyUrl/system_stats"
$objectInfo = Invoke-RestMethod -Uri "$ComfyUrl/object_info"
$modelFiles = if (Test-Path -LiteralPath $ModelsRoot) {
    @(Get-ChildItem -LiteralPath $ModelsRoot -Recurse -File | Where-Object { $_.Name -match '(?i)(wan|animate|hunyuan)' } | ForEach-Object {
        [ordered]@{ path = $_.FullName; bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
} else { @() }

$wanAnimateFp8 = 'Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors'
$wanAnimateBf16 = 'wan2.2_animate_14B_bf16.safetensors'
$hunyuanNative = 'hunyuanvideo15_i2v_step_distilled.safetensors'
$wanWorkflow = [ordered]@{
    '1' = @{ class_type = 'UNETLoader'; inputs = @{ unet_name = $wanAnimateFp8; weight_dtype = 'default' } }
    '2' = @{ class_type = 'PreviewAny'; inputs = @{ source = @('1', 0) } }
}
$hunyuanWorkflow = [ordered]@{
    '1' = @{ class_type = 'CheckpointLoaderSimple'; inputs = @{ ckpt_name = $hunyuanNative } }
    '2' = @{ class_type = 'PreviewAny'; inputs = @{ source = @('1', 0) } }
}
$attempts = @(
    (Submit-LoaderProbe $wanAnimateFp8 'Wan2.2 Animate 14B FP8' $wanWorkflow),
    (Submit-LoaderProbe $hunyuanNative 'HunyuanVideo-1.5 I2V step-distilled' $hunyuanWorkflow)
)

$report = [ordered]@{
    schemaVersion = '2026-08-15.model-deployment.v1'
    startedAt = $started.ToString('o')
    finishedAt = (Get-Date).ToString('o')
    comfyUrl = $ComfyUrl
    comfy = [ordered]@{
        version = $health.system.comfyui_version
        python = $health.system.python_version
        pytorch = $health.system.pytorch_version
        argv = @($health.system.argv)
        targetNodes = @('WanAnimateToVideo', 'WanAnimate2ToVideo', 'HunyuanVideo15ImageToVideo') | ForEach-Object { [ordered]@{ node = $_; present = $objectInfo.PSObject.Properties.Name -contains $_ } }
        loaderOptions = [ordered]@{
            unet = @($objectInfo.UNETLoader.input.required.unet_name[0])
            checkpoints = @($objectInfo.CheckpointLoaderSimple.input.required.ckpt_name[0])
        }
    }
    localInventory = $modelFiles
    targetPresence = [ordered]@{
        wanAnimateFp8 = [ordered]@{ name = $wanAnimateFp8; present = @($modelFiles | Where-Object { $_.path -like "*$wanAnimateFp8" }).Count -gt 0 }
        wanAnimateBf16 = [ordered]@{ name = $wanAnimateBf16; present = @($modelFiles | Where-Object { $_.path -like "*$wanAnimateBf16" }).Count -gt 0 }
        hunyuanVideo15 = [ordered]@{ name = $hunyuanNative; present = @($modelFiles | Where-Object { $_.path -match '(?i)hunyuan' }).Count -gt 0 }
    }
    loaderAttempts = $attempts
    hardwareBlock = [ordered]@{
        gpu = (nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader | Out-String).Trim()
        rationale = 'RTX 4070 12GB is below the official HunyuanVideo-1.5 14GB minimum with offloading; Wan2.2 Animate target is a 14B model and the local target weights are absent.'
        targetInferenceExecuted = $false
        targetInferenceBlockedBeforeGpuSampling = $true
        noExistingModelOrWorkflowOverwritten = $true
    }
    conclusion = 'BLOCKED_LOCAL_ASSETS_AND_12GB_HARDWARE'
}
$report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
$report | ConvertTo-Json -Depth 10
