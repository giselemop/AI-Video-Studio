[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowRoot = 'C:\install\AI\Workflows',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$runStarted = Get-Date
$resultPath = Join-Path $OutputRoot 'comfy-benchmark-results.json'
$downloadRoot = Join-Path $OutputRoot 'comfy_outputs'
New-Item -ItemType Directory -Force -Path $OutputRoot, $downloadRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ComfyInput | Out-Null

function Copy-Input([string]$Source, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Benchmark input does not exist: $Source" }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $ComfyInput $Name) -Force
    return $Name
}

function Read-Workflow([string]$Name) {
    $path = Join-Path $WorkflowRoot $Name
    if (-not (Test-Path -LiteralPath $path)) { throw "Workflow does not exist: $path" }
    return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Submit-Comfy($Workflow, [string]$CaseId, [string]$Kind, [int64]$Seed, [string]$PromptText, [string]$Prefix) {
    $payload = [ordered]@{ prompt = $Workflow; client_id = "codex-benchmark-20260814-$CaseId-$Seed" }
    $json = $payload | ConvertTo-Json -Depth 100 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $started = Get-Date
    try {
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body $bytes -ContentType 'application/json'
        $promptId = [string]$response.prompt_id
        if ([string]::IsNullOrWhiteSpace($promptId)) { throw "ComfyUI did not return a prompt_id: $($response | ConvertTo-Json -Depth 10 -Compress)" }
        Write-Host ("QUEUED kind={0} case={1} seed={2} prompt={3}" -f $Kind, $CaseId, $Seed, $promptId)

        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        $entry = $null
        do {
            Start-Sleep -Seconds 2
            try {
                $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId" -Method Get
                $prop = $history.PSObject.Properties[$promptId]
                if ($prop) { $entry = $prop.Value }
            } catch { }
        } while ($null -eq $entry -and (Get-Date) -lt $deadline)
        if ($null -eq $entry) { throw "Timed out waiting for ComfyUI history: $promptId" }

        $statusText = if ($entry.status -and $entry.status.status_str) { [string]$entry.status.status_str } else { 'unknown' }
        $statusJson = if ($entry.status) { $entry.status | ConvertTo-Json -Depth 20 -Compress } else { $null }
        if ($statusText -eq 'error' -or ($entry.status -and $entry.status.completed -eq $false -and -not $entry.outputs)) {
            throw "ComfyUI execution failed for ${promptId}: $statusJson"
        }

        $items = @()
        if ($entry.outputs) {
            foreach ($node in $entry.outputs.PSObject.Properties) {
                foreach ($collectionName in @('images', 'gifs')) {
                    $collection = $node.Value.PSObject.Properties[$collectionName]
                    if (-not $collection) { continue }
                    foreach ($item in @($collection.Value)) {
                        if ($item -and $item.filename) {
                            $items += [pscustomobject]@{
                                filename = [string]$item.filename
                                subfolder = [string]$item.subfolder
                                type = if ($item.type) { [string]$item.type } else { 'output' }
                                nodeId = [string]$node.Name
                                collection = $collectionName
                            }
                        }
                    }
                }
            }
        }
        if ($items.Count -eq 0) { throw "ComfyUI completed without image/gif output for ${promptId}: $statusJson" }

        $caseDir = Join-Path $downloadRoot $CaseId
        New-Item -ItemType Directory -Force -Path $caseDir | Out-Null
        $downloaded = @()
        $index = 0
        foreach ($item in $items) {
            $index++
            $query = "filename=$([Uri]::EscapeDataString($item.filename))&subfolder=$([Uri]::EscapeDataString($item.subfolder))&type=$([Uri]::EscapeDataString($item.type))"
            $extension = [System.IO.Path]::GetExtension($item.filename)
            if ([string]::IsNullOrWhiteSpace($extension)) { $extension = if ($item.collection -eq 'gifs') { '.webp' } else { '.png' } }
            $target = Join-Path $caseDir ("{0}_{1}{2}" -f $CaseId, $index, $extension)
            Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $target -UseBasicParsing
            $downloaded += [pscustomobject]@{
                path = $target
                filename = $item.filename
                subfolder = $item.subfolder
                type = $item.type
                bytes = (Get-Item -LiteralPath $target).Length
                nodeId = $item.nodeId
                collection = $item.collection
            }
        }
        $finished = Get-Date
        return [pscustomobject][ordered]@{
            caseId = $CaseId
            kind = $Kind
            seed = $Seed
            promptText = $PromptText
            filenamePrefix = $Prefix
            promptId = $promptId
            status = 'Succeeded'
            startedAt = $started.ToString('o')
            finishedAt = $finished.ToString('o')
            durationMs = [int]($finished - $started).TotalMilliseconds
            outputs = @($downloaded)
            error = $null
        }
    } catch {
        $finished = Get-Date
        Write-Host ("FAILED kind={0} case={1} seed={2}: {3}" -f $Kind, $CaseId, $Seed, $_.Exception.Message)
        return [pscustomobject][ordered]@{
            caseId = $CaseId
            kind = $Kind
            seed = $Seed
            promptText = $PromptText
            filenamePrefix = $Prefix
            promptId = $null
            status = 'Failed'
            startedAt = $started.ToString('o')
            finishedAt = $finished.ToString('o')
            durationMs = [int]($finished - $started).TotalMilliseconds
            outputs = @()
            error = $_.Exception.Message
        }
    }
}

function Clone-Workflow($Workflow) {
    return ($Workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json)
}

$results = [System.Collections.Generic.List[object]]::new()
$referenceDir = Join-Path $OutputRoot 'references'
$poseDir = Join-Path $OutputRoot 'pose_controls'

$identityRef1 = Copy-Input (Join-Path $referenceDir 'identity_ref5_crop.png') 'bench_identity_ref1.png'
$identityRef3 = @(
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_102554_f6ea3a88.png' 'bench_identity_ref1.png'
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_105155_5b33ff21.png' 'bench_identity_ref2.png'
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png' 'bench_identity_ref3.png'
)
$identityRef5 = @(
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_102554_f6ea3a88.png' 'bench_identity_ref1.png'
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_105155_5b33ff21.png' 'bench_identity_ref2.png'
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png' 'bench_identity_ref3.png'
    Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_105155_907c0faa.png' 'bench_identity_ref4.png'
    Copy-Input (Join-Path $referenceDir 'identity_ref5_crop.png') 'bench_identity_ref5.png'
)

$referenceCases = @(
    [pscustomobject]@{ code = 'REF1'; workflow = '13_sd15_ipadapter_face_v1_api.json'; promptNode = '2'; imageNodes = @('4'); seedNode = '7'; saveNode = '9'; refs = @('bench_identity_ref1.png'); seeds = @(961001, 961002, 961003); prefix = 'video_studio/benchmark_ref1' },
    [pscustomobject]@{ code = 'REF3'; workflow = '15_sd15_ipadapter_ref3_api.json'; promptNode = '2'; imageNodes = @('4','15','16'); seedNode = '7'; saveNode = '9'; refs = @('bench_identity_ref1.png','bench_identity_ref2.png','bench_identity_ref3.png'); seeds = @(963001, 963002, 963003); prefix = 'video_studio/benchmark_ref3' },
    [pscustomobject]@{ code = 'REF5'; workflow = '16_sd15_ipadapter_ref5_api.json'; promptNode = '2'; imageNodes = @('4','15','16','17','18'); seedNode = '7'; saveNode = '9'; refs = @('bench_identity_ref1.png','bench_identity_ref2.png','bench_identity_ref3.png','bench_identity_ref4.png','bench_identity_ref5.png'); seeds = @(965001, 965002, 965003); prefix = 'video_studio/benchmark_ref5' }
)
$referencePrompts = @(
    'same adult person, preserve exact face and hairstyle, photorealistic live-action, neutral expression, front-facing chest-up portrait, clean studio light, one person',
    'same adult person, preserve exact face and hairstyle, photorealistic live-action, three-quarter view, subtle turn to camera left, chest-up portrait, one person',
    'same adult person, preserve exact face and hairstyle, photorealistic live-action, medium half-body portrait, one hand raised away from face, one person'
)

foreach ($spec in $referenceCases) {
    foreach ($name in $spec.refs) { if (-not (Test-Path -LiteralPath (Join-Path $ComfyInput $name))) { throw "Missing copied reference input $name" } }
    for ($i = 0; $i -lt $spec.seeds.Count; $i++) {
        $seed = [int64]$spec.seeds[$i]
        $wf = Clone-Workflow (Read-Workflow $spec.workflow)
        foreach ($node in $spec.imageNodes) { $wf.$node.inputs.image = $spec.refs[[array]::IndexOf($spec.imageNodes, $node)] }
        $wf.$($spec.promptNode).inputs.text = $referencePrompts[$i]
        $wf.$($spec.seedNode).inputs.seed = $seed
        $wf.$($spec.saveNode).inputs.filename_prefix = "$($spec.prefix)_$($i + 1)"
        $results.Add((Submit-Comfy $wf $spec.code $spec.code $seed $referencePrompts[$i] "$($spec.prefix)_$($i + 1)"))
    }
}

$identityAnchorSource = 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png'
$identityAnchor = Copy-Input $identityAnchorSource 'bench_identity_anchor.png'
$poseCases = @(
    [pscustomobject]@{ code = 'B04'; label = 'walking'; prompt = 'same adult person, preserve exact face and hairstyle, photorealistic live-action, full body, walking two slow natural steps, arms relaxed, coherent anatomy, one person'; seed = 974001 },
    [pscustomobject]@{ code = 'B05'; label = 'pick-up-cup'; prompt = 'same adult person, preserve exact face and hairstyle, photorealistic live-action, full body, bending naturally to pick up a cup from a table, hands coherent, one person'; seed = 975001 },
    [pscustomobject]@{ code = 'B06'; label = 'turn-sit'; prompt = 'same adult person, preserve exact face and hairstyle, photorealistic live-action, full body, turning and beginning to sit down naturally, coherent anatomy, one person'; seed = 976001 },
    [pscustomobject]@{ code = 'B08'; label = 'driving'; prompt = 'same adult person, preserve exact face and hairstyle, photorealistic live-action, seated in a car, both hands on the steering wheel, driving posture, coherent anatomy, one person'; seed = 978001 }
)

foreach ($spec in $poseCases) {
    $poseInput = Copy-Input (Join-Path $poseDir "$($spec.code)_openpose.png") "bench_pose_$($spec.code).png"
    $wf = Clone-Workflow (Read-Workflow '14_sd15_controlnet_openpose_v1_api.json')
    $wf.'4'.inputs.image = $identityAnchor
    $wf.'12'.inputs.image = $poseInput
    $wf.'2'.inputs.text = $spec.prompt
    $wf.'7'.inputs.seed = [int64]$spec.seed
    $wf.'9'.inputs.filename_prefix = "video_studio/benchmark_pose_$($spec.code)"
    $keyframe = Submit-Comfy $wf $spec.code 'PoseKeyframe' $spec.seed $spec.prompt "video_studio/benchmark_pose_$($spec.code)"
    $results.Add($keyframe)

    if ($keyframe.status -eq 'Succeeded' -and @($keyframe.outputs).Count -gt 0) {
        $keyframePath = $keyframe.outputs[0].path
        $guideName = Copy-Input $keyframePath "bench_pose_keyframe_$($spec.code).png"
        $videoWf = Clone-Workflow (Read-Workflow '12_ltx_face_stable_v3_api.json')
        $videoWf.'6'.inputs.text = "one adult person, preserve the face and hairstyle from the guide image, photorealistic live-action, $($spec.label), slow deliberate movement, stable identity, realistic temporal motion"
        $videoWf.'7'.inputs.text = 'identity drift, changing person, changing face, changing hairstyle, face morphing, extra limbs, malformed hands, duplicate person, flicker, ghosting, motion smear, camera shake, fast motion, cartoon, CGI, text, watermark'
        $videoWf.'78'.inputs.image = $guideName
        $videoWf.'79'.inputs.image = $guideName
        $videoWf.'72'.inputs.noise_seed = [int64]($spec.seed + 100000)
        $videoWf.'41'.inputs.filename_prefix = "video_studio/benchmark_pose_video_$($spec.code)"
        $results.Add((Submit-Comfy $videoWf $spec.code 'PoseI2V' ([int64]($spec.seed + 100000)) $spec.prompt "video_studio/benchmark_pose_video_$($spec.code)"))
    } else {
        $results.Add([pscustomobject][ordered]@{ caseId = $spec.code; kind = 'PoseI2V'; seed = [int64]($spec.seed + 100000); promptText = $spec.prompt; filenamePrefix = "video_studio/benchmark_pose_video_$($spec.code)"; promptId = $null; status = 'BlockedByKeyframe'; startedAt = (Get-Date).ToString('o'); finishedAt = (Get-Date).ToString('o'); durationMs = 0; outputs = @(); error = 'Pose keyframe did not succeed.' })
    }
}

$finishedAt = Get-Date
$report = [ordered]@{
    schemaVersion = '2026-08-14.comfy-benchmark.v1'
    startedAt = $runStarted.ToString('o')
    finishedAt = $finishedAt.ToString('o')
    comfyUrl = $ComfyUrl
    workflowRoot = $WorkflowRoot
    gpuRoute = 'direct ComfyUI REST queue; no application API auth required'
    referencePacks = [ordered]@{ REF1 = 'one reference'; REF3 = 'three references averaged by IPAdapterAdvanced'; REF5 = 'five references averaged by IPAdapterAdvanced; fifth is deterministic crop of verified reference' }
    poseCases = @('B04','B05','B06','B08')
    results = @($results)
    summary = [ordered]@{
        totalRuns = $results.Count
        succeeded = @($results | Where-Object status -eq 'Succeeded').Count
        failed = @($results | Where-Object status -eq 'Failed').Count
        blocked = @($results | Where-Object status -ne 'Succeeded' -and status -ne 'Failed').Count
        referenceSucceeded = @($results | Where-Object { $_.kind -in @('REF1','REF3','REF5') -and $_.status -eq 'Succeeded' }).Count
        poseKeyframeSucceeded = @($results | Where-Object { $_.kind -eq 'PoseKeyframe' -and $_.status -eq 'Succeeded' }).Count
        poseI2VSucceeded = @($results | Where-Object { $_.kind -eq 'PoseI2V' -and $_.status -eq 'Succeeded' }).Count
        manualVisualReviewRequired = $true
    }
}
$report | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $resultPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8
Write-Host "REPORT=$resultPath"
if ($report.summary.failed -gt 0 -or $report.summary.blocked -gt 0) { exit 2 }
