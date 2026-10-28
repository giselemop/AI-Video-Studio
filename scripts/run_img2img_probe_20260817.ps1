[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$RunRoot = 'C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$startedAt = Get-Date
$comfyInput = 'C:\install\AI\ComfyUI\input'
$workflowDir = 'C:\install\AI\Workflows'
$identitySource = 'C:\install\AI\Data\Characters\15\standard\identity_front.png'
$identityInput = 'multiview_20260817_identity_master.png'
$controlNetName = 'control_v11p_sd15_openpose.pth'
$negative = 'different person, identity drift, changing face, changing hairstyle, changing hair color, changing clothes, multiple people, duplicate person, extra eyes, malformed eyes, deformed mouth, extra limbs, missing limbs, cropped head, cropped feet, blocked face, hands over face, blurry, low resolution, cartoon, anime, CGI, text, logo, watermark'
$prompt = 'same adult East Asian man as the identity master, preserve exact face, eye shape, eyelids, nose, lips, jawline, short black hair, trimmed mustache and goatee, same dark navy collared shirt, photorealistic live-action, neutral studio lighting, one person, neutral standing pose'
$views = [ordered]@{
    head_left_30 = [ordered]@{ targetYaw = -30; input = 'multiview_20260817_head_left_30_20260817.png' }
    head_right_45 = [ordered]@{ targetYaw = 45; input = 'multiview_20260817_head_right_45_20260817.png' }
}
$methods = @('A_Img2Img_Pose','B_Img2Img_FaceID_Pose','C_Img2Img_HeadPose','D_Img2Img_FaceID_HeadPose')
$denoiseLevels = @(0.35,0.55,0.75)
$seed = [int64]320001
$controlWeight = 0.85

New-Item -ItemType Directory -Force -Path $RunRoot,(Join-Path $RunRoot 'img2img_generated'),$comfyInput,$workflowDir | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $comfyInput $identityInput))) { Copy-Item -LiteralPath $identitySource -Destination (Join-Path $comfyInput $identityInput) }
foreach ($viewName in $views.Keys) {
    $source = Join-Path $RunRoot ("head_pose_templates\head_{0}_20260817.png" -f ($viewName -replace '^head_',''))
    $destination = Join-Path $comfyInput $views[$viewName].input
    if (-not (Test-Path -LiteralPath $destination)) { Copy-Item -LiteralPath $source -Destination $destination }
}

function Get-Vram {
    try {
        $stats = Invoke-RestMethod -Uri "$ComfyUrl/system_stats" -TimeoutSec 10
        $device = @($stats.devices | Select-Object -First 1)[0]
        if ($device) {
            return [ordered]@{
                totalMiB = [math]::Round([double]$device.vram_total / 1MB, 0)
                freeMiB = [math]::Round([double]$device.vram_free / 1MB, 0)
                torchFreeMiB = [math]::Round([double]$device.torch_vram_free / 1MB, 0)
            }
        }
    } catch { }
    return $null
}

function New-Workflow([string]$Method, [string]$ViewInput, [double]$Denoise, [int64]$RunSeed, [string]$Prefix) {
    $wf = [ordered]@{
        '1' = [ordered]@{ class_type = 'CheckpointLoaderSimple'; inputs = [ordered]@{ ckpt_name = 'v1-5-pruned-emaonly-fp16.safetensors' } }
        '2' = [ordered]@{ class_type = 'CLIPTextEncode'; inputs = [ordered]@{ text = $prompt; clip = @('1',1) } }
        '3' = [ordered]@{ class_type = 'CLIPTextEncode'; inputs = [ordered]@{ text = $negative; clip = @('1',1) } }
        '4' = [ordered]@{ class_type = 'LoadImage'; inputs = [ordered]@{ image = $identityInput } }
        '5' = [ordered]@{ class_type = 'ImageScale'; inputs = [ordered]@{ image = @('4',0); upscale_method = 'bicubic'; width = 512; height = 768; crop = 'center' } }
        '6' = [ordered]@{ class_type = 'VAEEncode'; inputs = [ordered]@{ pixels = @('5',0); vae = @('1',2) } }
        '7' = [ordered]@{ class_type = 'LoadImage'; inputs = [ordered]@{ image = $ViewInput } }
        '8' = [ordered]@{ class_type = 'ControlNetLoader'; inputs = [ordered]@{ control_net_name = $controlNetName } }
        '9' = [ordered]@{ class_type = 'ControlNetApplyAdvanced'; inputs = [ordered]@{ positive = @('2',0); negative = @('3',0); control_net = @('8',0); image = @('7',0); strength = $controlWeight; start_percent = 0.0; end_percent = 0.95; vae = @('1',2) } }
        '10' = [ordered]@{ class_type = 'KSampler'; inputs = [ordered]@{ seed = $RunSeed; steps = 28; cfg = 5.8; sampler_name = 'dpmpp_2m'; scheduler = 'karras'; denoise = $Denoise; model = @('1',0); positive = @('9',0); negative = @('9',1); latent_image = @('6',0) } }
        '11' = [ordered]@{ class_type = 'VAEDecode'; inputs = [ordered]@{ samples = @('10',0); vae = @('1',2) } }
        '12' = [ordered]@{ class_type = 'SaveImage'; inputs = [ordered]@{ filename_prefix = $Prefix; images = @('11',0) } }
    }
    if ($Method -in @('B_Img2Img_FaceID_Pose','D_Img2Img_FaceID_HeadPose')) {
        $wf['13'] = [ordered]@{ class_type = 'IPAdapterUnifiedLoaderFaceID'; inputs = [ordered]@{ model = @('1',0); preset = 'FACEID PLUS V2'; lora_strength = 0.6; provider = 'CPU' } }
        $wf['14'] = [ordered]@{ class_type = 'IPAdapterFaceID'; inputs = [ordered]@{ model = @('13',0); ipadapter = @('13',1); image = @('4',0); weight = 1.0; weight_faceidv2 = 1.0; weight_type = 'linear'; combine_embeds = 'concat'; start_at = 0.0; end_at = 1.0; embeds_scaling = 'K+V' } }
        $wf['10'].inputs.model = @('14',0)
    }
    return $wf
}

function Submit-Image($Workflow, [string]$Method, [string]$View, [int64]$RunSeed, [double]$Denoise, [string]$Target, [string]$WorkflowPath) {
    $runStarted = Get-Date
    $beforeVram = Get-Vram
    try {
        $body = @{ prompt = $Workflow; client_id = "multiview-identity-20260817-img2img-$Method-$View-$Denoise" } | ConvertTo-Json -Depth 100 -Compress
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json'
        $promptId = [string]$response.prompt_id
        if ([string]::IsNullOrWhiteSpace($promptId)) { throw 'ComfyUI did not return prompt_id' }
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        $entry = $null
        do {
            Start-Sleep -Seconds 2
            try {
                $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId" -TimeoutSec 10
                $property = $history.PSObject.Properties[$promptId]
                if ($property) { $entry = $property.Value }
            } catch { }
        } while ($null -eq $entry -and (Get-Date) -lt $deadline)
        if ($null -eq $entry) { throw "Timed out waiting for $promptId" }
        $status = if ($entry.status -and $entry.status.status_str) { [string]$entry.status.status_str } else { 'unknown' }
        if ($status -eq 'error') { throw ($entry.status | ConvertTo-Json -Depth 30 -Compress) }
        $items = @()
        foreach ($node in $entry.outputs.PSObject.Properties) {
            $images = $node.Value.PSObject.Properties['images']
            if (-not $images) { continue }
            foreach ($item in @($images.Value)) { if ($item -and $item.filename) { $items += $item } }
        }
        if ($items.Count -eq 0) { throw 'ComfyUI completed without an image output' }
        $item = $items | Select-Object -First 1
        $query = "filename=$([Uri]::EscapeDataString([string]$item.filename))&subfolder=$([Uri]::EscapeDataString([string]$item.subfolder))&type=$([Uri]::EscapeDataString([string]$item.type))"
        Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $Target -UseBasicParsing
        if (-not (Test-Path -LiteralPath $Target) -or (Get-Item -LiteralPath $Target).Length -le 0) { throw 'Downloaded image is empty' }
        return [ordered]@{
            method = $Method; requestedView = $View; targetYaw = $views[$View].targetYaw; seed = $RunSeed; denoise = $Denoise; controlWeight = $controlWeight
            status = 'Succeeded'; technicalSuccess = $true; promptId = $promptId; workflow = $WorkflowPath; sourceFile = [string]$item.filename; path = $Target
            bytes = (Get-Item -LiteralPath $Target).Length; startedAt = $runStarted.ToString('o'); finishedAt = (Get-Date).ToString('o'); durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds
            vramBefore = $beforeVram; vramAfter = Get-Vram; error = $null
        }
    } catch {
        return [ordered]@{
            method = $Method; requestedView = $View; targetYaw = $views[$View].targetYaw; seed = $RunSeed; denoise = $Denoise; controlWeight = $controlWeight
            status = 'Failed'; technicalSuccess = $false; promptId = $null; workflow = $WorkflowPath; sourceFile = $null; path = $null; bytes = 0
            startedAt = $runStarted.ToString('o'); finishedAt = (Get-Date).ToString('o'); durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds
            vramBefore = $beforeVram; vramAfter = Get-Vram; error = $_.Exception.Message
        }
    }
}

$results = [System.Collections.Generic.List[object]]::new()
$workflowPaths = [ordered]@{}
foreach ($method in $methods) {
    foreach ($viewName in $views.Keys) {
        foreach ($denoise in $denoiseLevels) {
            $denoiseTag = ('{0:0.00}' -f $denoise).Replace('.','p')
            $prefix = "video_studio/multiview_identity_generation_20260817_img2img_$($method)_$($viewName)_d$denoiseTag"
            $workflow = New-Workflow $method $views[$viewName].input $denoise $seed $prefix
            $workflowPath = Join-Path $workflowDir ("20_sd15_img2img_{0}_v1_api.json" -f $method)
            if (-not $workflowPaths.Contains($method)) { $workflowPaths[$method] = $workflowPath; $workflow | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $workflowPath -Encoding UTF8 }
            $targetRoot = Join-Path $RunRoot "img2img_generated\$method\$viewName"
            New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
            $target = Join-Path $targetRoot "img2img_${method}_${viewName}_d${denoiseTag}.png"
            $row = Submit-Image $workflow $method $viewName $seed $denoise $target $workflowPath
            $results.Add($row)
            Write-Output ("{0} {1} denoise={2} {3} {4}ms" -f $method,$viewName,$denoise,$row.status,$row.durationMs)
        }
    }
}

$manifest = [ordered]@{
    schemaVersion = '2026-08-17.img2img-generation-manifest.v1'; startedAt = $startedAt.ToString('o'); finishedAt = (Get-Date).ToString('o'); runRoot = $RunRoot
    identityMaster = $identitySource; identityInput = $identityInput; comfyUrl = $ComfyUrl; controlNet = $controlNetName
    methods = $methods; views = $views; denoiseLevels = $denoiseLevels; fixed = [ordered]@{ resolution = '512x768'; steps = 28; cfg = 5.8; sampler = 'dpmpp_2m'; scheduler = 'karras'; seed = $seed; controlWeight = $controlWeight; promptFixed = $true }
    requested = $methods.Count * $views.Count * $denoiseLevels.Count; workflowPaths = $workflowPaths; results = @($results)
}
$manifest | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $RunRoot 'img2img-generation-manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 10
