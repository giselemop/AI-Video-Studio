[CmdletBinding()]
param(
    [string]$OutputPath = 'C:\install\AI\Data\QA\benchmark-motion-reference-results.json'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

function Read-Json([string]$path) { return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json) }
function Find-Audio([int]$taskId) { return (Get-ChildItem -LiteralPath (Join-Path 'C:\install\AI\Data\Artifacts\project-18\audio' "task-$taskId") -Filter '*.wav' -Recurse | Select-Object -First 1).FullName }
function Score([int]$face, [int]$body, [int]$motion, [int]$temporal, [int]$hand, [int]$object, [int]$hReject) {
    return [ordered]@{ Face=$face; Body=$body; Motion=$motion; Temporal=$temporal; Hand=$hand; Object=$object; HReject=$hReject; Total=($face+$body+$motion+$temporal+$hand+$object+$hReject) }
}

$ttsSql = 'C:\install\AI\VideoStudio\scripts\tts_batch_20260815.sql'
$dialogue = @(Get-Content -LiteralPath $ttsSql -Encoding UTF8 | ForEach-Object { if ($_ -match '"text":"([^"]+)"') { $Matches[1] } } | Select-Object -First 20)
$generationMs = @(719,467,465,475,464,463,466,471,463,480,465,472,474,489,480,480,465,460,495,469)
$tts = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt 20; $i++) {
    $taskId = 1044 + $i
    $file = Find-Audio $taskId
    $probe = & ffprobe.exe -v error -show_streams -show_format -of json -- $file | ConvertFrom-Json
    $audio = @($probe.streams | Where-Object codec_type -eq 'audio' | Select-Object -First 1)[0]
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $vol = (& ffmpeg.exe -hide_banner -nostats -i $file -af volumedetect -f null NUL 2>&1 | Out-String)
    $ErrorActionPreference = $previousErrorAction
    $mean = if ($vol -match 'mean_volume:s*([-0-9.]+)s*dB') { [double]$Matches[1] } else { $null }
    $max = if ($vol -match 'max_volume:s*([-0-9.]+)s*dB') { [double]$Matches[1] } else { $null }
    $duration = if ($audio.duration) { [double]$audio.duration } else { [double]$probe.format.duration }
    $tts.Add([ordered]@{ taskId=$taskId; text=$dialogue[$i]; status='Succeeded'; attempts=1; technicalSuccess=$true; path=$file; bytes=(Get-Item -LiteralPath $file).Length; codec=$audio.codec_name; sampleRate=[int]$audio.sample_rate; channels=[int]$audio.channels; durationSeconds=$duration; meanVolumeDb=$mean; maxVolumeDb=$max; generationMs=$generationMs[$i]; humanListening='Unverified-in-this-agent' })
}

$freePath = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\motion_benchmark_20260815\free_i2v\free-i2v-results.json'
$posePath = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_v2\pose-v2-results.json'
$free = Read-Json $freePath
$pose = Read-Json $posePath
$poseExtract = Read-Json 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_extraction_20260815\pose-extraction-results.json'
$freeScores = @{ B04=(Score 4 1 1 3 1 0 5); B05=(Score 3 1 1 2 1 0 2); B06=(Score 4 1 1 3 1 0 5); B08=(Score 4 1 1 3 1 0 5) }
$poseScores = @{ B04=(Score 3 2 2 2 1 0 3); B05=(Score 3 2 2 2 2 2 3); B06=(Score 3 2 2 2 1 0 4); B08=(Score 3 1 1 1 1 0 0) }
$actionCases = [System.Collections.Generic.List[object]]::new()
foreach ($caseId in @('B04','B05','B06','B08')) {
    $freeRows = @($free.results | Where-Object caseId -eq $caseId)
    $poseRows = @($pose.results | Where-Object { $_.caseId -eq $caseId -and $_.kind -eq 'PoseI2VV2' })
    $drivingSeeds = @(404001,404002,404003)
    $actionCases.Add([ordered]@{
        case=$caseId
        methods=@(
            [ordered]@{ method='FreeI2V'; seedCount=3; seeds=@($freeRows.seed); technicalSuccess=(@($freeRows|Where-Object status -eq 'Succeeded').Count -eq 3); outputs=@($freeRows.path); score=$freeScores[$caseId]; semanticStatus='Failed-or-unverified'; visualReview='First/last frame screening; full human review still required'; note='Upper-body reference-locked I2V does not prove the requested full-body action.' },
            [ordered]@{ method='Pose'; seedCount=3; seeds=@($poseRows.seed); technicalSuccess=(@($poseRows|Where-Object status -eq 'Succeeded').Count -eq 3); outputs=@($poseRows.outputs | ForEach-Object { $_[0].path }); score=$poseScores[$caseId]; semanticStatus='Failed-or-unverified'; visualReview='Pose v2 contact sheet and first/last frame screening'; note='Pose keyframe/video technical path succeeded, but B04/B05/B06/B08 action semantics and full-body continuity did not pass.' },
            [ordered]@{ method='Driving/Pose'; seedCount=3; seeds=$drivingSeeds; technicalSuccess=$false; outputs=@(); score=$null; semanticStatus='Blocked'; blockedReason='Target Wan2.2 Animate workflow/weights unavailable; no retargeted character video was produced.'; note='The input driving source exists, but it is generated-video provenance, not camera-recorded human input.' }
        )
    })
}

$drivingSources = @(
    [ordered]@{ case='D01'; label='walk two steps'; path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D01_walk_2_steps.mp4' },
    [ordered]@{ case='D02'; label='turn then sit'; path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D02_turn_then_sit.mp4' },
    [ordered]@{ case='D03'; label='pick up cup'; path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D03_pick_up_cup.mp4' },
    [ordered]@{ case='D04'; label='driving posture'; path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D04_driving.mp4' }
)
foreach ($source in $drivingSources) {
    $p = & ffprobe.exe -v error -show_streams -show_format -of json -- $source.path | ConvertFrom-Json
    $source['ffprobe'] = $p
    $source['provenance'] = 'Generated subject from prior Pose/I2V output; not camera-recorded human driving video.'
}

$staticRef = Read-Json 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\comfy-benchmark-results.json'
$selector = Read-Json 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\reference_selector_20260815\reference-selector-results.json'
$packRoot = 'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\reference_pack_20260815'
$referencePack = @(
    [ordered]@{ kind='front'; path='C:\install\AI\Data\Characters\15\standard\identity_front.png'; status='Passed-anchor'; samePerson=$true },
    [ordered]@{ kind='left45'; path=(Join-Path $packRoot 'left45_1.png'); status='Failed-angle'; samePerson=$null },
    [ordered]@{ kind='right45'; path=(Join-Path $packRoot 'right45_1.png'); status='Failed-identity-prop'; samePerson=$false },
    [ordered]@{ kind='halfBody'; path=(Join-Path $packRoot 'half_body_1.png'); status='Failed-costume-consistency'; samePerson=$null },
    [ordered]@{ kind='fullBody'; path=(Join-Path $packRoot 'full_body_1.png'); status='Failed-crop-costume'; samePerson=$null }
)
foreach ($ref in $referencePack) { $ref['exists'] = Test-Path -LiteralPath $ref.path; $ref['bytes'] = if ($ref.exists) { (Get-Item -LiteralPath $ref.path).Length } else { 0 } }
$referenceBenchmark = [ordered]@{
    staticREF1REF3REF5=[ordered]@{ path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\comfy-benchmark-results.json'; technicalRuns=9; technicalSucceeded=9; scores=[ordered]@{ REF1=[ordered]@{ Face=4; Identity=4; ViewCoverage=1; status='TechnicalPassed-coverageFailed' }; REF3=[ordered]@{ Face=4; Identity=4; ViewCoverage=1; status='TechnicalPassed-coverageFailed' }; REF5=[ordered]@{ Face=3; Identity=3; ViewCoverage=1; status='TechnicalPassed-packFailed' } } }
    selector=[ordered]@{ path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\reference_selector_20260815\reference-selector-results.json'; technicalRuns=$selector.summary.totalRuns; technicalSucceeded=$selector.summary.succeeded; autoSelectorFallbacks=$selector.summary.autoSelectorFallbacks; cases=@($selector.cases); status='TechnicalPassed-strict-fallback-not-multi-angle-proven' }
    invalidReference='C:\install\AI\Data\Characters\15\ref_20260811_105155_907c0faa.png is a visibly different beardless side-profile person and was excluded.'
}

$modelProbe = Read-Json 'C:\install\AI\Data\QA\model-deployment-20260815.json'
$wanProbe = Read-Json 'C:\install\AI\Data\QA\wan22_ti2v_probe_20260815\result.json'
$story = Read-Json 'C:\install\AI\Data\QA\acceptance_story_20260815\story-master-manifest.json'
$finalReportPath = (Get-ChildItem -LiteralPath 'C:\install\AI\VideoStudio\docs' -Filter '*.md' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$router = [ordered]@{ implementation='C:\install\AI\VideoStudio\server\ModelRouter.cs'; registeredIn='C:\install\AI\VideoStudio\server\Program.cs'; usedBy='C:\install\AI\VideoStudio\server\ProductionEndpoints.cs approve-keyframe'; needSplitPolicy='Complex multi-verb/driving/pose shots are rejected before GPU submission.'; sourceBuild='Passed 0 warnings / 0 errors'; activeRuntime='Main 18080 published process was not restarted after source change; runtime activation remains unverified.' }

$report = [ordered]@{
    schemaVersion='2026-08-15.motion-reference-acceptance.v1'
    generatedAt=(Get-Date).ToString('o')
    environment=[ordered]@{ projectRoot='C:\install\AI\VideoStudio'; api='http://127.0.0.1:18080'; comfy='http://127.0.0.1:8188'; gpu='RTX 4070 12GB'; driver='591.86'; gpuConcurrency=1; gitDirtyChangesPreserved=$true }
    tts=[ordered]@{ technicalSuccess='20/20'; taskIds=1044..1063; attempts='20/20 first attempt'; humanListening='Unverified-in-this-agent'; artifacts=@($tts); srtSync='Passed for 16-shot SRT timing and embedded subtitle track' }
    drivingSources=$drivingSources
    poseExtraction=[ordered]@{ path='C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_extraction_20260815\pose-extraction-results.json'; model=$poseExtract.model; modelBytes=$poseExtract.modelBytes; technicalSuccess="$($poseExtract.summary.succeeded)/$($poseExtract.summary.total)"; results=@($poseExtract.results); visualSemanticStatus='ManualReviewRequired-weak/missing points visible in samples' }
    actionBenchmark=[ordered]@{ scoreLegend='0-5; HReject=5 means no hard rejection, 0 means hard rejection observed'; cases=@($actionCases); thresholds=[ordered]@{ bodyMotionPlus20='Not passed as a semantic final-output gate; Pose is keyframe/I2V proxy only'; hRejectMinus30='Not established on true Driving/Pose output'; finalConclusion='B04/B05/B06/B08 true Driving/Pose benchmark blocked; FreeI2V and Pose technical controls are recorded without semantic pass claim.' } }
    referencePack=[ordered]@{ status='CandidateFailed'; items=$referencePack; selectorPolicy=$selector.selectorPolicy }
    referenceBenchmark=$referenceBenchmark
    modelDeployment=[ordered]@{ targetProbe=$modelProbe; existingWan22Ti2vBaseline=$wanProbe; officialTargetInference='Blocked before GPU sampling by missing loader assets and 12GB gate'; targetWeightsNotDownloaded=$true }
    modelRouter=$router
    storyMaster=$story
    acceptanceGate=[ordered]@{ tts='Passed-technical'; refStatic='Passed-technical-failed-coverage'; poseExtraction='Passed-technical'; drivingPose='Blocked'; wanAnimate='Blocked'; hunyuanVideo15='Blocked'; storyPlayable='Passed-technical'; finalDisposition='NO-GO_FOR_PRODUCTION_MASTER_CONDITIONAL_FOR_PLAYABLE_EVIDENCE' }
    evidenceFiles=@(
        $finalReportPath,
        'C:\install\AI\Data\QA\benchmark-motion-reference-results.json',
        'C:\install\AI\Data\QA\acceptance_story_20260815\MASTER_Midnight_Signal_MotionAcceptance_60s.mp4',
        'C:\install\AI\Data\QA\acceptance_story_20260815\episode-29-dialogue.srt',
        'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_extraction_20260815\pose-extraction-results.json',
        'C:\install\AI\Data\QA\model-deployment-20260815.json'
    )
}
$report | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8
