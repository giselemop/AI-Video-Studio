[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowRoot = 'C:\install\AI\Workflows',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_v2',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$runStarted = Get-Date
$downloadRoot = Join-Path $OutputRoot 'comfy_outputs'
$resultPath = Join-Path $OutputRoot 'pose-v2-results.json'
New-Item -ItemType Directory -Force -Path $OutputRoot, $downloadRoot, $ComfyInput | Out-Null

function Copy-Input([string]$Source, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Missing input: $Source" }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $ComfyInput $Name) -Force
    return $Name
}
function Read-Workflow([string]$Name) { return (Get-Content -LiteralPath (Join-Path $WorkflowRoot $Name) -Raw -Encoding UTF8 | ConvertFrom-Json) }
function Clone-Workflow($Workflow) { return ($Workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }
function Submit($Workflow, [string]$CaseId, [string]$Kind, [int64]$Seed, [string]$Prefix) {
    $started = Get-Date
    try {
        $json = ([ordered]@{ prompt=$Workflow; client_id="codex-pose-v2-20260814-$CaseId-$Kind-$Seed" } | ConvertTo-Json -Depth 100 -Compress)
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType 'application/json'
        $promptId = [string]$response.prompt_id
        $deadline=(Get-Date).AddSeconds($TimeoutSeconds); $entry=$null
        do {
            Start-Sleep -Seconds 2
            try { $history=Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId"; $prop=$history.PSObject.Properties[$promptId]; if($prop){$entry=$prop.Value} } catch { }
        } while($null -eq $entry -and (Get-Date) -lt $deadline)
        if($null -eq $entry){throw "Timed out: $promptId"}
        if($entry.status.status_str -ne 'success'){throw "Comfy error ${promptId}: $($entry.status | ConvertTo-Json -Depth 20 -Compress)"}
        $items=@()
        foreach($node in $entry.outputs.PSObject.Properties){ foreach($name in @('images','gifs')) { $c=$node.Value.PSObject.Properties[$name]; if(-not $c){continue}; foreach($i in @($c.Value)){if($i.filename){$items += [pscustomobject]@{filename=[string]$i.filename;subfolder=[string]$i.subfolder;type=if($i.type){[string]$i.type}else{'output'};collection=$name;nodeId=[string]$node.Name}}}}}
        if($items.Count -eq 0){throw "No output for $promptId"}
        $caseDir=Join-Path $downloadRoot $CaseId; New-Item -ItemType Directory -Force -Path $caseDir | Out-Null; $downloaded=@(); $n=0
        foreach($i in $items){$n++;$q="filename=$([Uri]::EscapeDataString($i.filename))&subfolder=$([Uri]::EscapeDataString($i.subfolder))&type=$([Uri]::EscapeDataString($i.type))";$ext=[IO.Path]::GetExtension($i.filename);if(!$ext){$ext=if($i.collection -eq 'gifs'){'.webp'}else{'.png'}};$target=Join-Path $caseDir ("{0}_{1}_{2}{3}" -f $CaseId,$Kind,$Seed,$ext);Invoke-WebRequest -Uri "$ComfyUrl/view?$q" -OutFile $target -UseBasicParsing;$downloaded += [ordered]@{path=$target;sourceFile=$i.filename;bytes=(Get-Item -LiteralPath $target).Length;nodeId=$i.nodeId;collection=$i.collection}}
        $finished=Get-Date
        Write-Host "SUCCEEDED $Kind $CaseId seed=$Seed prompt=$promptId"
        return [ordered]@{caseId=$CaseId;kind=$Kind;seed=$Seed;promptId=$promptId;status='Succeeded';startedAt=$started.ToString('o');finishedAt=$finished.ToString('o');durationMs=[int]($finished-$started).TotalMilliseconds;filenamePrefix=$Prefix;outputs=@($downloaded);error=$null}
    } catch { $finished=Get-Date;Write-Host "FAILED $Kind $CaseId seed=${Seed}: $($_.Exception.Message)";return [ordered]@{caseId=$CaseId;kind=$Kind;seed=$Seed;promptId=$null;status='Failed';startedAt=$started.ToString('o');finishedAt=$finished.ToString('o');durationMs=[int]($finished-$started).TotalMilliseconds;filenamePrefix=$Prefix;outputs=@();error=$_.Exception.Message} }
}

$anchor = Copy-Input 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png' 'bench_pose_v2_identity_anchor.png'
$cases=@(
    [pscustomobject]@{code='B04';label='walking';prompt='walking two slow natural steps, arms relaxed, full body, coherent anatomy';seeds=@(982004,982104,982204)},
    [pscustomobject]@{code='B05';label='pick-up-cup';prompt='bending naturally to pick up a cup from a table, full body, hands coherent';seeds=@(982005,982105,982205)},
    [pscustomobject]@{code='B06';label='turn-sit';prompt='turning and beginning to sit down naturally, full body, coherent anatomy';seeds=@(982006,982106,982206)},
    [pscustomobject]@{code='B08';label='driving';prompt='seated in a car, both hands on the steering wheel, driving posture, coherent anatomy';seeds=@(982008,982108,982208)}
)
$results=[System.Collections.Generic.List[object]]::new()
foreach($c in $cases){
  foreach($seed in $c.seeds){
    $pose=Copy-Input "C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_controls\$($c.code)_openpose.png" "bench_pose_v2_$($c.code).png"
    $wf=Clone-Workflow (Read-Workflow '17_sd15_ipadapter_openpose_v2_api.json')
    $wf.'4'.inputs.image=$anchor;$wf.'12'.inputs.image=$pose;$wf.'2'.inputs.text="same adult person as the face reference, preserve exact facial identity, eye shape, pupils, eyelids, nose, lips, jawline, hairstyle and facial hair, photorealistic live-action, $($c.prompt), one person";$wf.'7'.inputs.seed=[int64]$seed;$wf.'9'.inputs.filename_prefix="video_studio/benchmark_pose_v2_$($c.code)"
    $key=Submit $wf $c.code 'PoseKeyframeV2' ([int64]$seed) "video_studio/benchmark_pose_v2_$($c.code)";$results.Add($key)
    if($key.status -eq 'Succeeded'){
        $guide=Copy-Input $key.outputs[0].path "bench_pose_v2_keyframe_$($c.code).png"
        $vwf=Clone-Workflow (Read-Workflow '12_ltx_face_stable_v3_api.json')
        $vwf.'6'.inputs.text="one adult person, preserve exact face, hairstyle and clothing from the guide image, photorealistic live-action, $($c.label), slow deliberate movement, stable identity, realistic temporal motion";$vwf.'7'.inputs.text='identity drift, changing person, changing face, changing hairstyle, face morphing, extra limbs, malformed hands, duplicate person, flicker, ghosting, motion smear, camera shake, fast motion, cartoon, CGI, text, watermark';$vwf.'78'.inputs.image=$guide;$vwf.'79'.inputs.image=$guide;$vwf.'72'.inputs.noise_seed=[int64]($seed+100000);$vwf.'41'.inputs.filename_prefix="video_studio/benchmark_pose_v2_video_$($c.code)"
        $results.Add((Submit $vwf $c.code 'PoseI2VV2' ([int64]($seed+100000)) "video_studio/benchmark_pose_v2_video_$($c.code)"))
    } else { $results.Add([ordered]@{caseId=$c.code;kind='PoseI2VV2';seed=[int64]($seed+100000);status='BlockedByKeyframe';outputs=@();error='keyframe failed'}) }
  }
}
$finished=Get-Date
$report=[ordered]@{schemaVersion='2026-08-14.pose-v2.v1';startedAt=$runStarted.ToString('o');finishedAt=$finished.ToString('o');results=@($results);summary=[ordered]@{totalRuns=$results.Count;succeeded=@($results|Where-Object status -eq 'Succeeded').Count;failed=@($results|Where-Object status -ne 'Succeeded').Count;keyframes=@($results|Where-Object kind -eq 'PoseKeyframeV2').Count;videos=@($results|Where-Object kind -eq 'PoseI2VV2').Count;manualVisualReviewRequired=$true}}
$report|ConvertTo-Json -Depth 50|Set-Content -LiteralPath $resultPath -Encoding UTF8
$report|ConvertTo-Json -Depth 8;Write-Host "REPORT=$resultPath"
if($report.summary.failed -gt 0){exit 2}
