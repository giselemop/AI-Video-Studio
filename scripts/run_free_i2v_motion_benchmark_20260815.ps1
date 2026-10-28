[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowPath = 'C:\install\AI\Workflows\12_ltx_face_stable_v3_api.json',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\motion_benchmark_20260815\free_i2v',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$runStarted = Get-Date
New-Item -ItemType Directory -Force -Path $ComfyInput, $OutputRoot | Out-Null
$source = 'C:\install\AI\Data\Characters\15\standard\identity_front.png'
$inputName = 'motion_free_i2v_anchor_20260815.png'
if (-not (Test-Path -LiteralPath (Join-Path $ComfyInput $inputName))) { Copy-Item -LiteralPath $source -Destination (Join-Path $ComfyInput $inputName) }
$base = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Clone-Workflow($workflow) { return ($workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }
function Submit($workflow, [string]$caseId, [int64]$seed, [string]$promptText) {
    $started = Get-Date
    try {
        $payload = @{ prompt = $workflow; client_id = "free-i2v-motion-20260815-$caseId-$seed" } | ConvertTo-Json -Depth 100 -Compress
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
        $promptId = [string]$response.prompt_id; $deadline = (Get-Date).AddSeconds($TimeoutSeconds); $entry = $null
        do { Start-Sleep -Seconds 2; try { $h=Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId"; $p=$h.PSObject.Properties[$promptId]; if($p){$entry=$p.Value} } catch {} } while($null -eq $entry -and (Get-Date) -lt $deadline)
        if($null -eq $entry){throw "Timed out waiting for $promptId"}
        $status=if($entry.status -and $entry.status.status_str){[string]$entry.status.status_str}else{'unknown'}
        if($status -eq 'error'){throw ($entry.status|ConvertTo-Json -Depth 30 -Compress)}
        $items=@(); foreach($node in $entry.outputs.PSObject.Properties){$c=$node.Value.PSObject.Properties['images'];if($c){foreach($i in @($c.Value)){if($i.filename){$items += [pscustomobject]@{filename=[string]$i.filename;subfolder=[string]$i.subfolder;type=if($i.type){[string]$i.type}else{'output'}}}}}}
        if($items.Count -eq 0){throw "No output for $promptId"}
        $i=$items[0];$q="filename=$([Uri]::EscapeDataString($i.filename))&subfolder=$([Uri]::EscapeDataString($i.subfolder))&type=$([Uri]::EscapeDataString($i.type))";$target=Join-Path $OutputRoot ("{0}_{1}.webp" -f $caseId,$seed);Invoke-WebRequest -Uri "$ComfyUrl/view?$q" -OutFile $target -UseBasicParsing
        return [ordered]@{caseId=$caseId;method='FreeI2V';seed=$seed;status='Succeeded';promptId=$promptId;promptText=$promptText;path=$target;bytes=(Get-Item -LiteralPath $target).Length;durationMs=[int]((Get-Date)-$started).TotalMilliseconds;error=$null;manualVisualReviewRequired=$true}
    } catch { return [ordered]@{caseId=$caseId;method='FreeI2V';seed=$seed;status='Failed';promptId=$null;promptText=$promptText;path=$null;bytes=0;durationMs=[int]((Get-Date)-$started).TotalMilliseconds;error=$_.Exception.Message;manualVisualReviewRequired=$true} }
}

$cases=@(
    [pscustomobject]@{code='B04';label='walking two slow natural steps, arms relaxed, one person';seeds=@(304004,304104,304204)},
    [pscustomobject]@{code='B05';label='bending to pick up a cup from a table, coherent hands, one person';seeds=@(305005,305105,305205)},
    [pscustomobject]@{code='B06';label='turning and beginning to sit down naturally, one person';seeds=@(306006,306106,306206)},
    [pscustomobject]@{code='B08';label='seated in a car, both hands on the steering wheel, one person';seeds=@(308008,308108,308208)}
)
$results=[System.Collections.Generic.List[object]]::new()
foreach($case in $cases){foreach($seed in $case.seeds){$wf=Clone-Workflow $base;$wf.'78'.inputs.image=$inputName;$wf.'79'.inputs.image=$inputName;$prompt="same adult person, preserve exact face, eye shape, nose, lips, jawline, hairstyle and facial hair from the reference, photorealistic live-action, $($case.label), stable identity, slow deliberate motion";$wf.'6'.inputs.text=$prompt;$wf.'72'.inputs.noise_seed=[int64]$seed;$wf.'41'.inputs.filename_prefix="video_studio/motion_free_i2v_20260815_$($case.code)";$results.Add((Submit $wf $case.code ([int64]$seed) $prompt))}}
$report=[ordered]@{schemaVersion='2026-08-15.motion-free-i2v.v1';startedAt=$runStarted.ToString('o');finishedAt=(Get-Date).ToString('o');source=$source;results=@($results);summary=[ordered]@{totalRuns=$results.Count;succeeded=@($results|Where-Object status -eq 'Succeeded').Count;failed=@($results|Where-Object status -eq 'Failed').Count;manualVisualReviewRequired=$true}}
$report|ConvertTo-Json -Depth 40|Set-Content -LiteralPath (Join-Path $OutputRoot 'free-i2v-results.json') -Encoding UTF8;$report|ConvertTo-Json -Depth 8
if($report.summary.failed -gt 0){exit 2}
