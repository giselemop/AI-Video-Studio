[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowPath = 'C:\install\AI\Workflows\12_ltx_face_stable_v3_api.json',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$AnchorPath = 'C:\install\AI\Data\Characters\15\standard\identity_front.png',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\walk_sit_pick_benchmark_20260816',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$startedAt = Get-Date
New-Item -ItemType Directory -Force -Path $ComfyInput, $OutputRoot | Out-Null
$anchorName = 'walk_sit_pick_anchor_20260816.png'
if (-not (Test-Path -LiteralPath (Join-Path $ComfyInput $anchorName))) { Copy-Item -LiteralPath $AnchorPath -Destination (Join-Path $ComfyInput $anchorName) }
$base = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Clone-Workflow($workflow) { return ($workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }
function Submit($workflow, [string]$caseId, [int64]$seed, [string]$prompt, [string]$targetPath) {
    $runStarted=Get-Date
    try {
        $payload=@{prompt=$workflow;client_id="walk-sit-pick-20260816-$caseId-$seed"}|ConvertTo-Json -Depth 100 -Compress
        $r=Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
        $promptId=[string]$r.prompt_id; if([string]::IsNullOrWhiteSpace($promptId)){throw 'ComfyUI did not return prompt_id'}
        $deadline=(Get-Date).AddSeconds($TimeoutSeconds);$entry=$null
        do{Start-Sleep -Seconds 2;try{$h=Invoke-RestMethod "$ComfyUrl/history/$promptId" -TimeoutSec 10;$p=$h.PSObject.Properties[$promptId];if($p){$entry=$p.Value}}catch{}}while($null -eq $entry -and (Get-Date)-lt $deadline)
        if($null -eq $entry){throw "Timed out waiting for $promptId"}
        $status=if($entry.status -and $entry.status.status_str){[string]$entry.status.status_str}else{'unknown'};if($status -eq 'error'){throw ($entry.status|ConvertTo-Json -Depth 30 -Compress)}
        $items=@();foreach($node in $entry.outputs.PSObject.Properties){foreach($collectionName in @('images','gifs')){$collection=$node.Value.PSObject.Properties[$collectionName];if(-not $collection){continue};foreach($item in @($collection.Value)){if($item -and $item.filename){$items+=[pscustomobject]@{item=$item;collection=$collectionName}}}}}
        if($items.Count -eq 0){throw 'ComfyUI completed without media output'}
        $item=$items[0].item;$q="filename=$([Uri]::EscapeDataString([string]$item.filename))&subfolder=$([Uri]::EscapeDataString([string]$item.subfolder))&type=$([Uri]::EscapeDataString([string]$item.type))";Invoke-WebRequest -Uri "$ComfyUrl/view?$q" -OutFile $targetPath -UseBasicParsing
        if(-not(Test-Path -LiteralPath $targetPath)){throw 'Downloaded output missing'}
        return [ordered]@{caseId=$caseId;seed=$seed;status='Succeeded';promptId=$promptId;prompt=$prompt;path=$targetPath;bytes=(Get-Item -LiteralPath $targetPath).Length;durationMs=[int]((Get-Date)-$runStarted).TotalMilliseconds;technicalStatus='Succeeded';semanticStatus='ManualReviewRequired';identity='Unverified';motion='Unverified';body='Unverified';hand='Unverified';object='Unverified';temporal='Unverified';hardRejects=@();manualReview='Split-shot output is retained; full semantic and continuity review is still required.';error=$null}
    }catch{return [ordered]@{caseId=$caseId;seed=$seed;status='Failed';promptId=$null;prompt=$prompt;path=$null;bytes=0;durationMs=[int]((Get-Date)-$runStarted).TotalMilliseconds;technicalStatus='Failed';semanticStatus='Blocked';identity='Unverified';motion='Unverified';body='Unverified';hand='Unverified';object='Unverified';temporal='Unverified';hardRejects=@();manualReview='Generation failed; no semantic pass claim.';error=$_.Exception.Message}}
}

$cases=@(
    [pscustomobject]@{code='C01-W1';group='C01-Walk';label='Walk-Step-1';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, full body, take one slow natural step forward, feet visible, one person, coherent anatomy';seeds=@(601001,601002,601003)},
    [pscustomobject]@{code='C01-W2';group='C01-Walk';label='Walk-Step-2';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, full body, take the second slow natural step and arrive, feet visible, one person, coherent anatomy';seeds=@(601101,601102,601103)},
    [pscustomobject]@{code='C02-S1';group='C02-Sit';label='Sit-Prepare';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, full body, stand beside a chair, turn and prepare to sit, chair visible, one person';seeds=@(602001,602002,602003)},
    [pscustomobject]@{code='C02-S2';group='C02-Sit';label='Sit-Lower';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, full body, lower the body onto a chair, knees and feet visible, coherent anatomy, one person';seeds=@(602101,602102,602103)},
    [pscustomobject]@{code='C02-S3';group='C02-Sit';label='Sit-Hold';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, medium full shot, sit still on the chair and hold, stable identity, one person';seeds=@(602201,602202,602203)},
    [pscustomobject]@{code='C03-P1';group='C03-Pick';label='Pick-Reach';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, medium full shot, reach one hand toward a single paper cup on a table, hand and cup visible, one person';seeds=@(603001,603002,603003)},
    [pscustomobject]@{code='C03-P2';group='C03-Pick';label='Pick-Contact';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, medium full shot, one hand touches one paper cup on the table, clear hand-object contact, one person';seeds=@(603101,603102,603103)},
    [pscustomobject]@{code='C03-P3';group='C03-Pick';label='Pick-Lift';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, medium full shot, lift one paper cup just off the table, clear cup position, coherent hand, one person';seeds=@(603201,603202,603203)},
    [pscustomobject]@{code='C03-P4';group='C03-Pick';label='Pick-Chest';prompt='same adult man from the reference, exact face, hairstyle, facial hair and dark collared shirt, medium shot, hold the single paper cup at chest height and stop, stable identity, one person';seeds=@(603301,603302,603303)}
)
$results=[System.Collections.Generic.List[object]]::new();$counter=0
foreach($case in $cases){$dir=Join-Path $OutputRoot $case.code;New-Item -ItemType Directory -Force -Path $dir|Out-Null;foreach($seed in $case.seeds){$counter++;$wf=Clone-Workflow $base;$wf.'78'.inputs.image=$anchorName;$wf.'79'.inputs.image=$anchorName;$wf.'6'.inputs.text=$case.prompt;$wf.'7'.inputs.text='different person, identity drift, changing face, changing hairstyle, changing clothing, face morphing, extra limbs, malformed hands, extra fingers, duplicate person, multiple cups, floating cup, broken chair, broken legs, cropped feet, flicker, ghosting, motion smear, text, watermark, cartoon, CGI';$wf.'72'.inputs.noise_seed=[int64]$seed;$wf.'41'.inputs.filename_prefix="video_studio/walk_sit_pick_20260816_$($case.code)";$target=Join-Path $dir "$($case.code)_$seed.webp";$row=Submit $wf $case.code ([int64]$seed) $case.prompt $target;$results.Add($row);Write-Output("{0}/27 {1} {2} {3}ms" -f $counter,$case.code,$row.status,$row.durationMs)}}
$report=[ordered]@{schemaVersion='2026-08-16.walk-sit-pick-benchmark.v1';startedAt=$startedAt.ToString('o');finishedAt=(Get-Date).ToString('o');anchor=$AnchorPath;workflow=$WorkflowPath;splitPolicy='Each primary action is split into 1.0–2.5 second subshots; every subshot keeps all three seeds.';cases=@($cases|ForEach-Object{[ordered]@{caseId=$_.code;group=$_.group;label=$_.label;seedCount=@($_.seeds).Count;seeds=@($_.seeds)}});results=@($results);summary=[ordered]@{totalRuns=$results.Count;technicalSucceeded=@($results|Where-Object status -eq 'Succeeded').Count;technicalFailed=@($results|Where-Object status -eq 'Failed').Count;semanticPasses=0;manualReviewRequired=$true;gate='Unverified-until-human-review'}}
$reportPath=Join-Path $OutputRoot 'walk-sit-pick-results.json';$report|ConvertTo-Json -Depth 60|Set-Content -LiteralPath $reportPath -Encoding UTF8;Write-Output("REPORT=$reportPath");if($report.summary.technicalFailed -gt 0){exit 2}
