[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$RunRoot = 'C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01',
    [string]$IdentityPython = 'C:\install\AI\IdentityWorker\venv\Scripts\python.exe',
    [string]$FoundationScript = 'C:\install\AI\VideoStudio\tools\identity_foundation\identity_foundation.py',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$startedAt = Get-Date
$comfyInput = 'C:\install\AI\ComfyUI\input'
$workerUrl = 'http://127.0.0.1:18084'
$workflowPath = 'C:\install\AI\Workflows\19_sd15_faceid_headpose_openpose_v1_api.json'
New-Item -ItemType Directory -Force -Path $RunRoot,$comfyInput,(Join-Path $RunRoot 'headpose_generated') | Out-Null

function Clone-Workflow($Workflow) { return ($Workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }

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
    } catch { return $null }
    return $null
}

function Ensure-Worker {
    try {
        $health = Invoke-RestMethod -Uri "$workerUrl/health" -TimeoutSec 5
        return [ordered]@{ status = 'already-running'; pid = $null; health = $health }
    } catch { }
    $stdout = Join-Path $RunRoot 'identity-worker.stdout.log'
    $stderr = Join-Path $RunRoot 'identity-worker.stderr.log'
    $args = @($FoundationScript,'--mode','serve','--run-root',$RunRoot,'--host','127.0.0.1','--port','18084')
    $process = Start-Process -WindowStyle Hidden -WorkingDirectory 'C:\install\AI\VideoStudio' -FilePath $IdentityPython -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $deadline = (Get-Date).AddSeconds(120)
    $health = $null
    do {
        Start-Sleep -Seconds 2
        try { $health = Invoke-RestMethod -Uri "$workerUrl/health" -TimeoutSec 5 } catch { }
    } while ($null -eq $health -and (Get-Date) -lt $deadline)
    if ($null -eq $health) { throw "Identity Worker did not become healthy; see $stderr" }
    return [ordered]@{ status = 'started'; pid = $process.Id; health = $health; stdout = $stdout; stderr = $stderr }
}

function Copy-Input([string]$Source, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Missing input source: $Source" }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $comfyInput $Name) -Force
    return $Name
}

function Submit-Image($Workflow, [string]$View, [int64]$Seed, [string]$Prompt, [string]$Target, [string]$HeadTemplate, [double]$ControlWeight) {
    $runStarted = Get-Date
    $beforeVram = Get-Vram
    try {
        $body = @{ prompt = $Workflow; client_id = "multiview-identity-20260817-headpose-$View-$Seed" } | ConvertTo-Json -Depth 100 -Compress
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
            method = 'FaceID+HeadPose'; requestedView = $View; targetYaw = $script:targetYaw[$View]; seed = $Seed
            headPoseTemplate = $HeadTemplate; headPoseWeight = $ControlWeight; faceIdWeight = 1.0; openPoseWeight = $ControlWeight
            status = 'Succeeded'; technicalSuccess = $true; promptId = $promptId; prompt = $Prompt; sourceFile = [string]$item.filename
            path = $Target; bytes = (Get-Item -LiteralPath $Target).Length; startedAt = $runStarted.ToString('o')
            finishedAt = (Get-Date).ToString('o'); durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds
            vramBefore = $beforeVram; vramAfter = Get-Vram; error = $null
        }
    } catch {
        return [ordered]@{
            method = 'FaceID+HeadPose'; requestedView = $View; targetYaw = $script:targetYaw[$View]; seed = $Seed
            headPoseTemplate = $HeadTemplate; headPoseWeight = $ControlWeight; faceIdWeight = 1.0; openPoseWeight = $ControlWeight
            status = 'Failed'; technicalSuccess = $false; promptId = $null; prompt = $Prompt; sourceFile = $null
            path = $null; bytes = 0; startedAt = $runStarted.ToString('o'); finishedAt = (Get-Date).ToString('o')
            durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds; vramBefore = $beforeVram; vramAfter = Get-Vram
            error = $_.Exception.Message
        }
    }
}

$worker = Ensure-Worker
$masterInput = Copy-Input 'C:\install\AI\Data\Characters\15\standard\identity_front.png' 'multiview_20260817_identity_master.png'
$headFiles = @{
    head_front = 'head_front_20260817.png'
    head_left_30 = 'head_left_30_20260817.png'
    head_right_30 = 'head_right_30_20260817.png'
    head_left_45 = 'head_left_45_20260817.png'
    head_right_45 = 'head_right_45_20260817.png'
}
$headInputs = @{}
foreach ($view in $headFiles.Keys) {
    $headInputs[$view] = Copy-Input (Join-Path $RunRoot "head_pose_templates\$($headFiles[$view])") "multiview_20260817_$($headFiles[$view])"
}
$script:targetYaw = @{ head_front = 0; head_left_30 = -30; head_right_30 = 30; head_left_45 = -45; head_right_45 = 45 }
$workflowBase = Get-Content -LiteralPath $workflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
$negative = 'different person, identity drift, changing face, changing hairstyle, changing hair color, changing clothes, multiple people, duplicate person, extra eyes, malformed eyes, deformed mouth, extra limbs, missing limbs, cropped head, cropped feet, blocked face, hands over face, blurry, low resolution, cartoon, anime, CGI, text, logo, watermark'
$prompt = 'same adult East Asian man as the identity master, preserve exact face, eye shape, eyelids, nose, lips, jawline, short black hair, trimmed mustache and goatee, same dark navy collared shirt, photorealistic live-action, neutral studio lighting, one person, neutral standing pose'
$views = @('head_front','head_left_30','head_right_30','head_left_45','head_right_45')
$seeds = @(310101,310102,310103)
$controlWeight = 0.95
$results = [System.Collections.Generic.List[object]]::new()
foreach ($view in $views) {
    foreach ($seed in $seeds) {
        $workflow = Clone-Workflow $workflowBase
        $workflow.'4'.inputs.image = $masterInput
        $workflow.'12'.inputs.image = $headInputs[$view]
        $workflow.'2'.inputs.text = $prompt
        $workflow.'3'.inputs.text = $negative
        $workflow.'6'.inputs.width = 512
        $workflow.'6'.inputs.height = 768
        $workflow.'6'.inputs.batch_size = 1
        $workflow.'7'.inputs.seed = [int64]$seed
        $workflow.'7'.inputs.steps = 28
        $workflow.'7'.inputs.cfg = 5.8
        $workflow.'7'.inputs.sampler_name = 'dpmpp_2m'
        $workflow.'7'.inputs.scheduler = 'karras'
        $workflow.'14'.inputs.strength = $controlWeight
        $workflow.'9'.inputs.filename_prefix = "video_studio/multiview_identity_generation_20260817_headpose_$($view)_$($seed)"
        $targetRoot = Join-Path $RunRoot "headpose_generated\$view"
        New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
        $target = Join-Path $targetRoot "FaceID_HeadPose_$($view)_$($seed).png"
        $row = Submit-Image $workflow $view ([int64]$seed) $prompt $target $headInputs[$view] $controlWeight
        $results.Add($row)
        Write-Output ("{0} seed={1} {2} {3}ms" -f $view,$seed,$row.status,$row.durationMs)
    }
}
$manifest = [ordered]@{
    schemaVersion = '2026-08-17.faceid-headpose-generation-manifest.v1'
    startedAt = $startedAt.ToString('o'); finishedAt = (Get-Date).ToString('o'); runRoot = $RunRoot
    identityMaster = 'C:\install\AI\Data\Characters\15\standard\identity_front.png'; worker = $worker; comfyUrl = $ComfyUrl
    method = 'FaceID+HeadPose'; workflow = $workflowPath; controlNet = 'control_v11p_sd15_openpose.pth'
    fixed = [ordered]@{ resolution = '512x768'; steps = 28; cfg = 5.8; sampler = 'dpmpp_2m'; scheduler = 'karras'; seeds = $seeds; faceIdWeight = 1.0; headPoseWeight = $controlWeight; openPoseWeight = $controlWeight; promptFixed = $true }
    requested = 15; results = @($results); vram = @($results | ForEach-Object { [ordered]@{ view = $_.requestedView; seed = $_.seed; before = $_.vramBefore; after = $_.vramAfter } })
}
$manifest | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath (Join-Path $RunRoot 'headpose-generation-manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 10
