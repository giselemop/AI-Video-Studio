[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowPath = 'C:\install\AI\Workflows\12_ltx_face_stable_v3_api.json',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$AnchorPath = 'C:\install\AI\Data\Characters\15\standard\identity_front.png',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\simple_motion_benchmark_20260816',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$startedAt = Get-Date
New-Item -ItemType Directory -Force -Path $ComfyInput, $OutputRoot | Out-Null
$anchorName = 'simple_motion_anchor_20260816.png'
if (-not (Test-Path -LiteralPath (Join-Path $ComfyInput $anchorName))) { Copy-Item -LiteralPath $AnchorPath -Destination (Join-Path $ComfyInput $anchorName) }
$base = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Clone-Workflow($workflow) { return ($workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }
function Read-Vram {
    try { $stats=Invoke-RestMethod "$ComfyUrl/system_stats" -TimeoutSec 10; $d=@($stats.devices|Select-Object -First 1)[0]; if($d){return [ordered]@{totalMiB=[math]::Round([double]$d.vram_total/1MB,0);freeMiB=[math]::Round([double]$d.vram_free/1MB,0)}} } catch {}
    return $null
}
function Submit($workflow, [string]$caseId, [int64]$seed, [string]$prompt, [string]$targetPath) {
    $runStarted=Get-Date; $before=Read-Vram
    try {
        $payload=@{prompt=$workflow;client_id="simple-motion-20260816-$caseId-$seed"}|ConvertTo-Json -Depth 100 -Compress
        $r=Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
        $promptId=[string]$r.prompt_id; if([string]::IsNullOrWhiteSpace($promptId)){throw 'ComfyUI did not return prompt_id'}
        $deadline=(Get-Date).AddSeconds($TimeoutSeconds);$entry=$null
        do{Start-Sleep -Seconds 2;try{$h=Invoke-RestMethod "$ComfyUrl/history/$promptId" -TimeoutSec 10;$p=$h.PSObject.Properties[$promptId];if($p){$entry=$p.Value}}catch{}}while($null -eq $entry -and (Get-Date)-lt $deadline)
        if($null -eq $entry){throw "Timed out waiting for $promptId"}
        $status=if($entry.status -and $entry.status.status_str){[string]$entry.status.status_str}else{'unknown'}
        if($status -eq 'error'){throw ($entry.status|ConvertTo-Json -Depth 30 -Compress)}
        $items=@();foreach($node in $entry.outputs.PSObject.Properties){foreach($collectionName in @('images','gifs')){$collection=$node.Value.PSObject.Properties[$collectionName];if(-not $collection){continue};foreach($item in @($collection.Value)){if($item -and $item.filename){$items+=[pscustomobject]@{item=$item;collection=$collectionName}}}}}
        if($items.Count -eq 0){throw 'ComfyUI completed without media output'}
        $item=$items[0].item;$query="filename=$([Uri]::EscapeDataString([string]$item.filename))&subfolder=$([Uri]::EscapeDataString([string]$item.subfolder))&type=$([Uri]::EscapeDataString([string]$item.type))"
        Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $targetPath -UseBasicParsing
        if(-not(Test-Path -LiteralPath $targetPath)){throw 'Downloaded output missing'}
        return [ordered]@{caseId=$caseId;seed=$seed;status='Succeeded';promptId=$promptId;prompt=$prompt;path=$targetPath;bytes=(Get-Item -LiteralPath $targetPath).Length;durationMs=[int]((Get-Date)-$runStarted).TotalMilliseconds;vramBefore=$before;vramAfter=(Read-Vram);semanticStatus='ManualReviewRequired';identityStatus='Unverified';motionSemanticStatus='Unverified';bodyIntegrityStatus='Unverified';temporalStatus='ProxyPending';hardRejects=@();manualReview='Agent cannot reliably approve fine identity/action semantics from this run.';error=$null}
    }catch{return [ordered]@{caseId=$caseId;seed=$seed;status='Failed';promptId=$null;prompt=$prompt;path=$null;bytes=0;durationMs=[int]((Get-Date)-$runStarted).TotalMilliseconds;vramBefore=$before;vramAfter=(Read-Vram);semanticStatus='Blocked';identityStatus='Unverified';motionSemanticStatus='Unverified';bodyIntegrityStatus='Unverified';temporalStatus='Unverified';hardRejects=@();manualReview='Generation failed; no semantic pass claim.';error=$_.Exception.Message}}
}

$cases=@(
    [pscustomobject]@{code='S01';label='blink once';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, locked-off close-up, one natural blink, subtle breathing, stable identity';seeds=@(501001,501002,501003)},
    [pscustomobject]@{code='S02';label='smile';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, locked-off close-up, subtle natural smile, stable identity';seeds=@(502001,502002,502003)},
    [pscustomobject]@{code='S03';label='slight head turn left';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, close-up, slight head turn to the left only, slow restrained movement, stable identity';seeds=@(503001,503002,503003)},
    [pscustomobject]@{code='S04';label='slight head turn right';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, close-up, slight head turn to the right only, slow restrained movement, stable identity';seeds=@(504001,504002,504003)},
    [pscustomobject]@{code='S05';label='look down';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, close-up, look down slightly and hold, slow restrained movement, stable identity';seeds=@(505001,505002,505003)},
    [pscustomobject]@{code='S06';label='look up';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, close-up, look up slightly and hold, slow restrained movement, stable identity';seeds=@(506001,506002,506003)},
    [pscustomobject]@{code='S07';label='slight shoulder movement';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, medium close-up, subtle shoulder movement and breathing only, stable identity';seeds=@(507001,507002,507003)},
    [pscustomobject]@{code='S08';label='simple hand raise';prompt='one adult man, preserve exact face, hairstyle, facial hair and dark collared shirt from the reference, photorealistic live-action, medium close-up, slowly raise one hand away from the face and hold, stable identity, no object';seeds=@(508001,508002,508003)}
)
$results=[System.Collections.Generic.List[object]]::new();$counter=0
foreach($case in $cases){$caseRoot=Join-Path $OutputRoot $case.code;New-Item -ItemType Directory -Force -Path $caseRoot|Out-Null;foreach($seed in $case.seeds){$counter++;$wf=Clone-Workflow $base;$wf.'78'.inputs.image=$anchorName;$wf.'79'.inputs.image=$anchorName;$wf.'6'.inputs.text=$case.prompt;$wf.'7'.inputs.text='identity drift, changing face, changing hairstyle, changing clothing, face morphing, extra limbs, malformed hands, duplicate person, flicker, ghosting, motion smear, camera shake, fast motion, object, text, watermark, cartoon, CGI';$wf.'72'.inputs.noise_seed=[int64]$seed;$wf.'41'.inputs.filename_prefix="video_studio/simple_motion_20260816_$($case.code)";$target=Join-Path $caseRoot "$($case.code)_$seed.webp";$row=Submit $wf $case.code ([int64]$seed) $case.prompt $target;$results.Add($row);Write-Output("{0}/24 {1} {2} {3}ms" -f $counter,$case.code,$row.status,$row.durationMs)}}
$report=[ordered]@{schemaVersion='2026-08-16.simple-motion-benchmark.v1';startedAt=$startedAt.ToString('o');finishedAt=(Get-Date).ToString('o');anchor=$AnchorPath;workflow=$WorkflowPath;cases=@($cases|ForEach-Object{[ordered]@{caseId=$_.code;label=$_.label;seedCount=@($_.seeds).Count;seeds=@($_.seeds)}});results=@($results);summary=[ordered]@{totalRuns=$results.Count;technicalSucceeded=@($results|Where-Object status -eq 'Succeeded').Count;technicalFailed=@($results|Where-Object status -eq 'Failed').Count;manualReviewRequired=$true;semanticPasses=0;gate='Unverified-until-human-review'}}
$path=Join-Path $OutputRoot 'simple-motion-results.json';$report|ConvertTo-Json -Depth 60|Set-Content -LiteralPath $path -Encoding UTF8;Write-Output("REPORT=$path");if($report.summary.technicalFailed -gt 0){exit 2}
