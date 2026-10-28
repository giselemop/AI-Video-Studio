[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowPath = 'C:\install\AI\Workflows\12_ltx_face_stable_v3_api.json',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\reference_selector_20260815',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$runStarted = Get-Date
$downloadRoot = Join-Path $OutputRoot 'outputs'
$resultPath = Join-Path $OutputRoot 'reference-selector-results.json'
New-Item -ItemType Directory -Force -Path $ComfyInput, $downloadRoot | Out-Null

function Copy-Input([string]$source, [string]$name) {
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing reference input: $source" }
    $target = Join-Path $ComfyInput $name
    if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $source -Destination $target }
    return $name
}
function Clone-Workflow($workflow) { return ($workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }
function Read-Error($errorRecord) {
    $text = $errorRecord.ErrorDetails.Message
    if ([string]::IsNullOrWhiteSpace($text)) { $text = $errorRecord.Exception.Message }
    return $text
}
function Submit($workflow, [string]$caseId, [string]$method, [int64]$seed, [string]$reference, [string]$fallbackReason, [string]$promptText) {
    $started = Get-Date
    try {
        $payload = @{ prompt = $workflow; client_id = "reference-selector-20260815-$caseId-$method-$seed" } | ConvertTo-Json -Depth 100 -Compress
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
        $promptId = [string]$response.prompt_id
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds); $entry = $null
        do {
            Start-Sleep -Seconds 2
            try { $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId"; $prop = $history.PSObject.Properties[$promptId]; if ($prop) { $entry = $prop.Value } } catch { }
        } while ($null -eq $entry -and (Get-Date) -lt $deadline)
        if ($null -eq $entry) { throw "Timed out waiting for $promptId" }
        $status = if ($entry.status -and $entry.status.status_str) { [string]$entry.status.status_str } else { 'unknown' }
        if ($status -eq 'error') { throw ($entry.status | ConvertTo-Json -Depth 30 -Compress) }
        $items = @()
        foreach ($node in $entry.outputs.PSObject.Properties) {
            foreach ($collectionName in @('images','gifs')) {
                $collection = $node.Value.PSObject.Properties[$collectionName]
                if (-not $collection) { continue }
                foreach ($item in @($collection.Value)) {
                    if ($item.filename) { $items += [pscustomobject]@{ filename=[string]$item.filename; subfolder=[string]$item.subfolder; type=if($item.type){[string]$item.type}else{'output'}; collection=$collectionName; nodeId=[string]$node.Name } }
                }
            }
        }
        if ($items.Count -eq 0) { throw "No output for $promptId" }
        $caseDir = Join-Path $downloadRoot "$caseId-$method"; New-Item -ItemType Directory -Force -Path $caseDir | Out-Null
        $downloaded = @(); $index = 0
        foreach ($item in $items) {
            $index++; $query = "filename=$([Uri]::EscapeDataString($item.filename))&subfolder=$([Uri]::EscapeDataString($item.subfolder))&type=$([Uri]::EscapeDataString($item.type))"
            $ext = [IO.Path]::GetExtension($item.filename); if ([string]::IsNullOrWhiteSpace($ext)) { $ext = '.webp' }
            $target = Join-Path $caseDir ("{0}_{1}{2}" -f $caseId, $index, $ext)
            Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $target -UseBasicParsing
            $downloaded += [ordered]@{ path=$target; sourceFile=$item.filename; bytes=(Get-Item -LiteralPath $target).Length; collection=$item.collection; nodeId=$item.nodeId }
        }
        return [ordered]@{ caseId=$caseId; method=$method; seed=$seed; status='Succeeded'; reference=$reference; fallbackReason=$fallbackReason; promptText=$promptText; promptId=$promptId; durationMs=[int]((Get-Date)-$started).TotalMilliseconds; outputs=@($downloaded); error=$null; manualVisualScoreRequired=$true }
    } catch {
        return [ordered]@{ caseId=$caseId; method=$method; seed=$seed; status='Failed'; reference=$reference; fallbackReason=$fallbackReason; promptText=$promptText; promptId=$null; durationMs=[int]((Get-Date)-$started).TotalMilliseconds; outputs=@(); error=(Read-Error $_); manualVisualScoreRequired=$true }
    }
}

$anchorSource = 'C:\install\AI\Data\Characters\15\standard\identity_front.png'
$anchor = Copy-Input $anchorSource 'selector_front_anchor_20260815.png'
$packRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\reference_pack_20260815'
$candidateFiles = @{
    left45 = Join-Path $packRoot 'left45_1.png'
    right45 = Join-Path $packRoot 'right45_1.png'
    halfBody = Join-Path $packRoot 'half_body_1.png'
    fullBody = Join-Path $packRoot 'full_body_1.png'
}
$cases = @(
    [pscustomobject]@{ code='R01'; label='front close-up'; selected=$anchorSource; reason=$null; seed=20258101 },
    [pscustomobject]@{ code='R02'; label='left 45 degree'; selected=$anchorSource; reason='left45 candidate failed angle/pack QA; strict selector fallback to front'; seed=20258102 },
    [pscustomobject]@{ code='R03'; label='right 45 degree'; selected=$anchorSource; reason='right45 candidate failed identity/prop QA; strict selector fallback to front'; seed=20258103 },
    [pscustomobject]@{ code='R04'; label='medium half body'; selected=$anchorSource; reason='half-body candidate changed clothing; strict selector fallback to front'; seed=20258104 },
    [pscustomobject]@{ code='R05'; label='full body'; selected=$anchorSource; reason='full-body candidate cropped head and changed clothing; strict selector fallback to front'; seed=20258105 },
    [pscustomobject]@{ code='R06'; label='expression and object gesture'; selected=$anchorSource; reason='no validated multi-angle/gesture reference; strict selector fallback to front'; seed=20258106 }
)
$workflowBase = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
$results = [System.Collections.Generic.List[object]]::new()
foreach ($case in $cases) {
    foreach ($method in @('FrontAlways','AutoSelector')) {
        $wf = Clone-Workflow $workflowBase
        $input = if ($method -eq 'FrontAlways') { $anchor } else { Copy-Input $case.selected ("selector_{0}_{1}.png" -f $case.code, $method) }
        $wf.'78'.inputs.image = $input
        $wf.'79'.inputs.image = $input
        $wf.'6'.inputs.text = "one adult person, preserve exact face, hair, facial hair and clothing from the selected reference, photorealistic live-action, $($case.label), restrained motion, stable identity throughout, one person"
        $wf.'7'.inputs.text = 'identity drift, changing person, different face, changing hairstyle, changing clothing, face morphing, extra eyes, malformed hands, extra limbs, duplicate person, flicker, jitter, ghosting, motion smear, camera shake, fast zoom, pan, orbit, low quality, cartoon, CGI, text, watermark'
        $wf.'72'.inputs.noise_seed = [int64]$case.seed
        $wf.'41'.inputs.filename_prefix = "video_studio/reference_selector_20260815_$($case.code)_$method"
        $results.Add((Submit $wf $case.code $method ([int64]$case.seed) $input $case.reason "$($case.code): $($case.label)"))
    }
}
$report = [ordered]@{
    schemaVersion='2026-08-15.reference-selector.v1'
    startedAt=$runStarted.ToString('o')
    finishedAt=(Get-Date).ToString('o')
    packStatus='candidate_failed_strict_selector_fallback'
    selectorPolicy='Use only a same-person, same-costume, angle-valid reference; otherwise fallback to verified front anchor.'
    cases=@($cases | ForEach-Object { [ordered]@{ code=$_.code; label=$_.label; autoSelectorReference=$_.selected; fallbackReason=$_.reason } })
    results=@($results)
    summary=[ordered]@{ totalRuns=$results.Count; succeeded=@($results|Where-Object status -eq 'Succeeded').Count; failed=@($results|Where-Object status -eq 'Failed').Count; autoSelectorFallbacks=@($results|Where-Object method -eq 'AutoSelector'|Where-Object { -not [string]::IsNullOrWhiteSpace($_.fallbackReason) }).Count; manualVisualReviewRequired=$true; identityScoreNotAutoInferred=$true }
}
$report | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8
if ($report.summary.failed -gt 0) { exit 2 }
