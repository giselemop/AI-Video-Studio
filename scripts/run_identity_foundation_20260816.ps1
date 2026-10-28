[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$RunRoot = 'C:\install\AI\Data\QA\identity_foundation_20260816\run_02',
    [string]$FoundationScript = 'C:\install\AI\VideoStudio\tools\identity_foundation\identity_foundation.py',
    [string]$IdentityPython = 'C:\install\AI\IdentityWorker\venv\Scripts\python.exe',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$startedAt = Get-Date
$ComfyInput = 'C:\install\AI\ComfyUI\input'
$WorkerUrl = 'http://127.0.0.1:18084'
$WorkerRun = Join-Path $RunRoot 'worker'
New-Item -ItemType Directory -Force -Path $RunRoot,$ComfyInput,$WorkerRun | Out-Null

function Clone-Workflow($Workflow) {
    return ($Workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json)
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
    } catch { return $null }
    return $null
}

function Ensure-Worker {
    try {
        $health = Invoke-RestMethod -Uri "$WorkerUrl/health" -TimeoutSec 5
        return [ordered]@{ status = 'already-running'; pid = $null; health = $health }
    } catch { }
    $stdout = Join-Path $WorkerRun 'identity-worker.stdout.log'
    $stderr = Join-Path $WorkerRun 'identity-worker.stderr.log'
    $args = @($FoundationScript,'--mode','serve','--run-root',$RunRoot,'--host','127.0.0.1','--port','18084')
    $process = Start-Process -WindowStyle Hidden -WorkingDirectory 'C:\install\AI\VideoStudio' -FilePath $IdentityPython -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $deadline = (Get-Date).AddSeconds(120)
    $health = $null
    do {
        Start-Sleep -Seconds 2
        try { $health = Invoke-RestMethod -Uri "$WorkerUrl/health" -TimeoutSec 5 } catch { }
    } while ($null -eq $health -and (Get-Date) -lt $deadline)
    if ($null -eq $health) { throw "Identity Worker did not become healthy on 127.0.0.1:18084; see $stderr" }
    return [ordered]@{ status = 'started'; pid = $process.Id; health = $health; stdout = $stdout; stderr = $stderr }
}

function Copy-Input([string]$Source, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Missing Comfy input source: $Source" }
    $target = Join-Path $ComfyInput $Name
    Copy-Item -LiteralPath $Source -Destination $target -Force
    return $Name
}

function Submit-Candidate($Workflow, [string]$Method, [string]$View, [int64]$Seed, [string]$Prompt, [string]$Target, [string]$PoseTemplate) {
    $runStarted = Get-Date
    $beforeVram = Get-Vram
    try {
        $body = @{ prompt = $Workflow; client_id = "identity-foundation-20260816-$Method-$View-$Seed" } | ConvertTo-Json -Depth 100 -Compress
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
            method = $Method; requestedView = $View; seed = $Seed; status = 'Succeeded'; technicalSuccess = $true
            promptId = $promptId; prompt = $Prompt; poseTemplate = $PoseTemplate; sourceFile = [string]$item.filename
            path = $Target; bytes = (Get-Item -LiteralPath $Target).Length; startedAt = $runStarted.ToString('o')
            finishedAt = (Get-Date).ToString('o'); durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds
            vramBefore = $beforeVram; vramAfter = Get-Vram; error = $null
        }
    } catch {
        return [ordered]@{
            method = $Method; requestedView = $View; seed = $Seed; status = 'Failed'; technicalSuccess = $false
            promptId = $null; prompt = $Prompt; poseTemplate = $PoseTemplate; sourceFile = $null; path = $null; bytes = 0
            startedAt = $runStarted.ToString('o'); finishedAt = (Get-Date).ToString('o')
            durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds; vramBefore = $beforeVram; vramAfter = Get-Vram
            error = $_.Exception.Message
        }
    }
}

# Rebuild the additive run manifest before generation; no previous run directory
# is touched.  This also keeps the script reproducible after a source change.
& $IdentityPython $FoundationScript --mode bootstrap --run-root $RunRoot | Set-Content -LiteralPath (Join-Path $RunRoot 'bootstrap.stdout.log') -Encoding UTF8
$worker = Ensure-Worker

$masterInput = Copy-Input 'C:\install\AI\Data\Characters\15\standard\identity_front.png' 'identity_master_foundation_20260816.png'
$poseNames = @{
    front = 'front_20260816.png'
    front_left_30 = 'front_left_30_20260816.png'
    front_right_30 = 'front_right_30_20260816.png'
    left_45 = 'left_45_20260816.png'
    right_45 = 'right_45_20260816.png'
    half_body_front = 'half_body_front_20260816.png'
    full_body_front = 'full_body_front_20260816.png'
}
$poseInputs = @{}
foreach ($view in $poseNames.Keys) {
    $source = Join-Path $RunRoot "pose_templates\$($poseNames[$view])"
    $poseInputs[$view] = Copy-Input $source "identity_pose_$($poseNames[$view])"
}

$baselineBase = Get-Content -LiteralPath 'C:\install\AI\Workflows\17_sd15_ipadapter_openpose_v2_api.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$faceIdBase = Get-Content -LiteralPath 'C:\install\AI\Workflows\18_sd15_faceid_openpose_v1_api.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$negative = 'different person, identity drift, changing face, changing hairstyle, changing hair color, changing clothes, multiple people, duplicate person, extra eyes, malformed eyes, deformed mouth, extra limbs, missing limbs, cropped head, cropped feet, blocked face, hands over face, blurry, low resolution, cartoon, anime, CGI, text, logo, watermark'
$basePrompt = 'same adult East Asian man as the identity master, preserve exact face, eye shape, eyelids, nose, lips, jawline, short black hair, trimmed mustache and goatee, same dark navy collared shirt, photorealistic live-action, neutral studio lighting, one person'
$viewPrompts = @{
    front = 'front view, neutral standing pose, centered'
    front_left_30 = 'front-left 30 degree head direction, neutral standing pose'
    front_right_30 = 'front-right 30 degree head direction, neutral standing pose'
    left_45 = 'left 45 degree head direction, neutral standing pose'
    right_45 = 'right 45 degree head direction, neutral standing pose'
    half_body_front = 'half-body framing from head to waist, front direction, arms relaxed'
    full_body_front = 'full-body framing from head to feet, front direction, arms relaxed'
}
$views = @('front','front_left_30','front_right_30','left_45','right_45','half_body_front','full_body_front')
$methods = @(
    [pscustomobject]@{ name = 'Baseline'; base = $baselineBase },
    [pscustomobject]@{ name = 'FaceID'; base = $faceIdBase }
)
$generationResults = [System.Collections.Generic.List[object]]::new()
$candidates = [System.Collections.Generic.List[object]]::new()
$methodSummary = [ordered]@{}
foreach ($method in $methods) {
    $methodRows = [System.Collections.Generic.List[object]]::new()
    foreach ($view in $views) {
        foreach ($seed in @(240101,240102,240103)) {
            $workflow = Clone-Workflow $method.base
            $prompt = "$basePrompt, $($viewPrompts[$view])"
            $workflow.'4'.inputs.image = $masterInput
            $workflow.'12'.inputs.image = $poseInputs[$view]
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
            $workflow.'9'.inputs.filename_prefix = "video_studio/identity_foundation_20260816_$($method.name)_$view_$seed"
            $targetRoot = Join-Path $RunRoot "generated\$($method.name)\$view"
            New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
            $target = Join-Path $targetRoot "$($method.name)_$view_$seed.png"
            $row = Submit-Candidate $workflow $method.name $view ([int64]$seed) $prompt $target $poseInputs[$view]
            $generationResults.Add($row)
            $methodRows.Add($row)
            if ($row.status -eq 'Succeeded') {
                $candidates.Add([ordered]@{
                    method = $method.name; requestedView = $view; seed = [int64]$seed; path = $target
                    prompt = $prompt; poseTemplate = $poseInputs[$view]; identityMaster = $masterInput
                    controlNet = 'control_v11p_sd15_openpose.pth'; technicalSuccess = $true
                })
            }
            Write-Output ("{0} {1} seed={2} {3} {4}ms" -f $method.name,$view,$seed,$row.status,$row.durationMs)
        }
    }
    $methodSummary[$method.name] = [ordered]@{
        requested = $methodRows.Count; succeeded = @($methodRows | Where-Object status -eq 'Succeeded').Count
        failed = @($methodRows | Where-Object status -eq 'Failed').Count
        blocked = @($methodRows | Where-Object status -eq 'Failed' | Select-Object -ExpandProperty error -Unique)
    }
}

$manifest = [ordered]@{
    schemaVersion = '2026-08-16.identity-foundation-generation-manifest.v2'
    startedAt = $startedAt.ToString('o'); finishedAt = (Get-Date).ToString('o')
    runRoot = $RunRoot; identityMaster = 'C:\install\AI\Data\Characters\15\standard\identity_front.png'
    worker = $worker; comfyUrl = $ComfyUrl
    oneVariablePrinciple = [ordered]@{ baseCheckpoint = 'v1-5-pruned-emaonly-fp16.safetensors'; resolution = '512x768'; steps = 28; cfg = 5.8; sampler = 'dpmpp_2m'; scheduler = 'karras'; seeds = @(240101,240102,240103); poseControl = 'OpenPose ControlNet'; promptFixedExceptView = $true }
    methods = $methodSummary; candidates = @($candidates); generationResults = @($generationResults)
    vram = @($generationResults | ForEach-Object { if ($_.vramBefore -or $_.vramAfter) { [ordered]@{ method = $_.method; view = $_.requestedView; seed = $_.seed; before = $_.vramBefore; after = $_.vramAfter } } })
}
$manifest | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath (Join-Path $RunRoot 'generation-manifest.json') -Encoding UTF8
& $IdentityPython $FoundationScript --mode evaluate --run-root $RunRoot | Set-Content -LiteralPath (Join-Path $RunRoot 'evaluate.stdout.log') -Encoding UTF8
Write-Output ("GENERATION_MANIFEST={0}" -f (Join-Path $RunRoot 'generation-manifest.json'))
Write-Output ("WORKER={0}" -f ($worker | ConvertTo-Json -Depth 20 -Compress))
Write-Output ("SUMMARY={0}" -f ($methodSummary | ConvertTo-Json -Depth 20 -Compress))
