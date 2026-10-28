[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_extraction_20260815',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$runStarted = Get-Date
New-Item -ItemType Directory -Force -Path $ComfyInput, $OutputRoot | Out-Null

function Copy-DrivingInput([string]$source, [string]$name) {
    if (-not (Test-Path -LiteralPath $source)) { throw "Driving video does not exist: $source" }
    $target = Join-Path $ComfyInput $name
    if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $source -Destination $target }
    return $name
}

function Submit-PoseWorkflow($workflow, [string]$caseId, [string]$videoName) {
    $payload = @{ prompt = $workflow; client_id = "pose-extraction-20260815-$caseId" } | ConvertTo-Json -Depth 100 -Compress
    $started = Get-Date
    $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
    $promptId = [string]$response.prompt_id
    if ([string]::IsNullOrWhiteSpace($promptId)) { throw "No prompt_id for $caseId" }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $entry = $null
    do {
        Start-Sleep -Seconds 2
        try {
            $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId"
            $prop = $history.PSObject.Properties[$promptId]
            if ($prop) { $entry = $prop.Value }
        } catch { }
    } while ($null -eq $entry -and (Get-Date) -lt $deadline)
    if ($null -eq $entry) { throw "Timed out waiting for $caseId ($promptId)" }
    $status = if ($entry.status -and $entry.status.status_str) { [string]$entry.status.status_str } else { 'unknown' }
    if ($status -eq 'error') { throw "ComfyUI pose extraction failed for ${caseId}: $($entry.status | ConvertTo-Json -Depth 20 -Compress)" }

    $items = @()
    if ($entry.outputs) {
        foreach ($node in $entry.outputs.PSObject.Properties) {
            foreach ($collectionName in @('images', 'gifs')) {
                $collection = $node.Value.PSObject.Properties[$collectionName]
                if (-not $collection) { continue }
                foreach ($item in @($collection.Value)) {
                    if ($item -and $item.filename) {
                        $items += [pscustomobject]@{ filename = [string]$item.filename; subfolder = [string]$item.subfolder; type = [string]$item.type; nodeId = [string]$node.Name; collection = $collectionName }
                    }
                }
            }
        }
    }
    if ($items.Count -eq 0) { throw "ComfyUI returned no Pose Preview for $caseId" }

    $downloaded = @()
    $index = 0
    $caseDir = Join-Path $OutputRoot $caseId
    New-Item -ItemType Directory -Force -Path $caseDir | Out-Null
    foreach ($item in $items) {
        $index++
        $query = "filename=$([Uri]::EscapeDataString($item.filename))&subfolder=$([Uri]::EscapeDataString($item.subfolder))&type=$([Uri]::EscapeDataString($item.type))"
        $extension = [IO.Path]::GetExtension($item.filename)
        if ([string]::IsNullOrWhiteSpace($extension)) { $extension = if ($item.collection -eq 'gifs') { '.webp' } else { '.png' } }
        $target = Join-Path $caseDir ("{0}_PosePreview{1}" -f $caseId, $extension)
        Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $target -UseBasicParsing
        $downloaded += [pscustomobject]@{ path = $target; bytes = (Get-Item -LiteralPath $target).Length; sourceFile = $item.filename; collection = $item.collection; nodeId = $item.nodeId }
    }
    $finished = Get-Date
    return [ordered]@{
        caseId = $caseId
        status = 'Succeeded'
        promptId = $promptId
        inputVideo = $videoName
        nodeChain = @('LoadVideo', 'GetVideoComponents', 'SDPoseKeypointExtractor', 'SDPoseDrawKeypoints', 'SaveAnimatedWEBP')
        batchSize = 4
        startedAt = $started.ToString('o')
        finishedAt = $finished.ToString('o')
        durationMs = [int]($finished - $started).TotalMilliseconds
        outputs = @($downloaded)
        error = $null
    }
}

$specs = @(
    [pscustomobject]@{ code = 'D01'; source = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D01_walk_2_steps.mp4' },
    [pscustomobject]@{ code = 'D02'; source = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D02_turn_then_sit.mp4' },
    [pscustomobject]@{ code = 'D03'; source = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D03_pick_up_cup.mp4' },
    [pscustomobject]@{ code = 'D04'; source = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D04_driving.mp4' }
)

$results = [System.Collections.Generic.List[object]]::new()
foreach ($spec in $specs) {
    $videoName = Copy-DrivingInput $spec.source ("pose_driving_20260815_{0}.mp4" -f $spec.code)
    $workflow = [ordered]@{
        '1' = @{ class_type = 'CheckpointLoaderSimple'; inputs = @{ ckpt_name = 'sdpose_wholebody_fp16.safetensors' } }
        '2' = @{ class_type = 'LoadVideo'; inputs = @{ file = $videoName } }
        '3' = @{ class_type = 'GetVideoComponents'; inputs = @{ video = @('2', 0) } }
        '4' = @{ class_type = 'SDPoseKeypointExtractor'; inputs = @{ model = @('1', 0); vae = @('1', 2); image = @('3', 0); batch_size = 4 } }
        '5' = @{ class_type = 'SDPoseDrawKeypoints'; inputs = @{ keypoints = @('4', 0); draw_body = $true; draw_hands = $true; draw_face = $true; draw_feet = $true; stick_width = 4; face_point_size = 3; score_threshold = 0.3; draw_head = $true } }
        '6' = @{ class_type = 'SaveAnimatedWEBP'; inputs = @{ images = @('5', 0); filename_prefix = "video_studio/pose_preview_$($spec.code)"; fps = 24.0; lossless = $false; quality = 85; method = 'default' } }
    }
    try { $results.Add((Submit-PoseWorkflow $workflow $spec.code $videoName)) }
    catch { $results.Add([ordered]@{ caseId = $spec.code; status = 'Failed'; inputVideo = $videoName; nodeChain = @('LoadVideo', 'GetVideoComponents', 'SDPoseKeypointExtractor', 'SDPoseDrawKeypoints', 'SaveAnimatedWEBP'); error = $_.Exception.Message; outputs = @() }) }
}

$report = [ordered]@{
    schemaVersion = '2026-08-15.pose-extraction.v1'
    startedAt = $runStarted.ToString('o')
    finishedAt = (Get-Date).ToString('o')
    model = 'C:\install\AI\Models\checkpoints\sdpose_wholebody_fp16.safetensors'
    modelBytes = (Get-Item -LiteralPath 'C:\install\AI\Models\checkpoints\sdpose_wholebody_fp16.safetensors').Length
    results = @($results)
    summary = [ordered]@{ total = $results.Count; succeeded = @($results | Where-Object status -eq 'Succeeded').Count; failed = @($results | Where-Object status -ne 'Succeeded').Count; manualPoseReviewRequired = $true }
}
$report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OutputRoot 'pose-extraction-results.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 20
