[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814'
)

$ErrorActionPreference = 'Stop'
$downloadRoot = Join-Path $OutputRoot 'comfy_outputs'
$resultPath = Join-Path $OutputRoot 'comfy-benchmark-results.json'
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null

function Get-Node($Workflow, [string]$NodeId) {
    $prop = $Workflow.PSObject.Properties[$NodeId]
    if ($prop) { return $prop.Value }
    return $null
}

function Get-ExecutionTimestamp($Entry, [string]$MessageName) {
    if (-not $Entry.status -or -not $Entry.status.messages) { return $null }
    foreach ($message in @($Entry.status.messages)) {
        if ($message[0] -eq $MessageName -and $message[1].timestamp) { return [int64]$message[1].timestamp }
    }
    return $null
}

$history = Invoke-RestMethod -Uri "$ComfyUrl/history" -Method Get
$rows = @()
$historyProps = @($history.PSObject.Properties | Where-Object { $_.Value.prompt -and $_.Value.outputs })
foreach ($historyProp in $historyProps) {
    $promptId = [string]$historyProp.Name
    $entry = $historyProp.Value
    $workflow = $entry.prompt[2]
    $node9 = Get-Node $workflow '9'
    $node41 = Get-Node $workflow '41'
    $prefix = $null
    $kind = $null
    $caseId = $null
    $seed = $null
    $promptText = $null
    if ($node41 -and $node41.inputs.filename_prefix -match 'benchmark_pose_video_(B04|B05|B06|B08)') {
        $caseId = $Matches[1]; $kind = 'PoseI2V'; $prefix = [string]$node41.inputs.filename_prefix
        $node6 = Get-Node $workflow '6'; $node72 = Get-Node $workflow '72'
        $promptText = if ($node6) { [string]$node6.inputs.text } else { $null }
        $seed = if ($node72) { [int64]$node72.inputs.noise_seed } else { $null }
    } elseif ($node9 -and $node9.inputs.filename_prefix -match 'benchmark_(ref1|ref3|ref5)') {
        $caseId = $Matches[1].ToUpperInvariant(); $kind = $caseId; $prefix = [string]$node9.inputs.filename_prefix
        $node2 = Get-Node $workflow '2'; $node7 = Get-Node $workflow '7'
        $promptText = if ($node2) { [string]$node2.inputs.text } else { $null }
        $seed = if ($node7) { [int64]$node7.inputs.seed } else { $null }
    } elseif ($node9 -and $node9.inputs.filename_prefix -match 'benchmark_pose_(B04|B05|B06|B08)') {
        $caseId = $Matches[1]; $kind = 'PoseKeyframe'; $prefix = [string]$node9.inputs.filename_prefix
        $node2 = Get-Node $workflow '2'; $node7 = Get-Node $workflow '7'
        $promptText = if ($node2) { [string]$node2.inputs.text } else { $null }
        $seed = if ($node7) { [int64]$node7.inputs.seed } else { $null }
    } else { continue }

    $startedMs = Get-ExecutionTimestamp $entry 'execution_start'
    $finishedMs = Get-ExecutionTimestamp $entry 'execution_success'
    $outputItems = @()
    foreach ($node in $entry.outputs.PSObject.Properties) {
        foreach ($collectionName in @('images','gifs')) {
            $collection = $node.Value.PSObject.Properties[$collectionName]
            if (-not $collection) { continue }
            foreach ($item in @($collection.Value)) {
                if ($item -and $item.filename) { $outputItems += [pscustomobject]@{ filename=[string]$item.filename; subfolder=[string]$item.subfolder; type=if($item.type){[string]$item.type}else{'output'}; collection=$collectionName; nodeId=[string]$node.Name } }
            }
        }
    }
    $downloaded = @()
    $caseDir = Join-Path $downloadRoot $caseId
    New-Item -ItemType Directory -Force -Path $caseDir | Out-Null
    foreach ($item in $outputItems) {
        $query = "filename=$([Uri]::EscapeDataString($item.filename))&subfolder=$([Uri]::EscapeDataString($item.subfolder))&type=$([Uri]::EscapeDataString($item.type))"
        $ext = [System.IO.Path]::GetExtension($item.filename); if ([string]::IsNullOrWhiteSpace($ext)) { $ext = if ($item.collection -eq 'gifs') { '.webp' } else { '.png' } }
        $target = Join-Path $caseDir ("{0}_{1}{2}" -f $caseId, $seed, $ext)
        Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $target -UseBasicParsing
        $downloaded += [ordered]@{ path=$target; sourceFile=$item.filename; sourceSubfolder=$item.subfolder; sourceType=$item.type; collection=$item.collection; bytes=(Get-Item -LiteralPath $target).Length; nodeId=$item.nodeId }
    }
    $rows += [ordered]@{
        caseId = $caseId
        kind = $kind
        seed = $seed
        promptId = $promptId
        status = if ($entry.status.status_str -eq 'success') { 'Succeeded' } else { [string]$entry.status.status_str }
        startedAt = if ($startedMs) { [DateTimeOffset]::FromUnixTimeMilliseconds($startedMs).ToString('o') } else { $null }
        finishedAt = if ($finishedMs) { [DateTimeOffset]::FromUnixTimeMilliseconds($finishedMs).ToString('o') } else { $null }
        durationMs = if ($startedMs -and $finishedMs) { [int]($finishedMs - $startedMs) } else { $null }
        filenamePrefix = $prefix
        promptText = $promptText
        workflowNodes = @($workflow.PSObject.Properties | ForEach-Object { $_.Value.class_type } | Sort-Object -Unique)
        outputs = @($downloaded)
        error = if ($entry.status.status_str -ne 'success') { $entry.status | ConvertTo-Json -Depth 20 -Compress } else { $null }
    }
}

$rows = @($rows | Sort-Object @{Expression={ if($_.kind -in @('REF1','REF3','REF5')){0}else{1} }}, caseId, seed)
$report = [ordered]@{
    schemaVersion = '2026-08-14.comfy-benchmark.v1'
    collectedAt = (Get-Date).ToString('o')
    comfyUrl = $ComfyUrl
    referencePacks = [ordered]@{
        REF1 = [ordered]@{ count = 1; source = 'C:\install\AI\Data\Characters\15\ref_20260811_102554_f6ea3a88.png' }
        REF3 = [ordered]@{ count = 3; source = @('ref_20260811_102554_f6ea3a88.png','ref_20260811_105155_5b33ff21.png','ref_20260811_105155_701f4554.png') }
        REF5 = [ordered]@{ count = 5; source = @('ref_20260811_102554_f6ea3a88.png','ref_20260811_105155_5b33ff21.png','ref_20260811_105155_701f4554.png','ref_20260811_105155_907c0faa.png','identity_ref5_crop.png') }
    }
    poseCases = @('B04','B05','B06','B08')
    results = $rows
    summary = [ordered]@{
        totalRuns = $rows.Count
        succeeded = @($rows | Where-Object status -eq 'Succeeded').Count
        failed = @($rows | Where-Object status -ne 'Succeeded').Count
        referenceRuns = @($rows | Where-Object kind -in @('REF1','REF3','REF5')).Count
        referenceSucceeded = @($rows | Where-Object { $_.kind -in @('REF1','REF3','REF5') -and $_.status -eq 'Succeeded' }).Count
        poseKeyframeRuns = @($rows | Where-Object kind -eq 'PoseKeyframe').Count
        poseKeyframeSucceeded = @($rows | Where-Object { $_.kind -eq 'PoseKeyframe' -and $_.status -eq 'Succeeded' }).Count
        poseI2VRuns = @($rows | Where-Object kind -eq 'PoseI2V').Count
        poseI2VSucceeded = @($rows | Where-Object { $_.kind -eq 'PoseI2V' -and $_.status -eq 'Succeeded' }).Count
        manualVisualReviewRequired = $true
        technicalGatePassed = $rows.Count -eq 17 -and @($rows | Where-Object status -ne 'Succeeded').Count -eq 0
    }
    notes = @(
        'Direct ComfyUI REST execution against local RTX 4070 12GB runtime.',
        'REF3/REF5 use IPAdapterAdvanced average embeds; REF5 fifth input is a deterministic crop variant, not a new identity.',
        'B04/B05/B06/B08 are pose-conditioned SD1.5 keyframes followed by LTXV 3-second I2V; semantic action and identity still require visual/manual review.',
        'This is not evidence that Wan2.2 Animate or HunyuanVideo-1.5 was deployed.'
    )
}
$report | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $resultPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8
Write-Host "REPORT=$resultPath"
if (-not $report.summary.technicalGatePassed) { exit 2 }
