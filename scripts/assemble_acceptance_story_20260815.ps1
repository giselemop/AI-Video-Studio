[CmdletBinding()]
param(
    [string]$OutputRoot = 'C:\install\AI\Data\QA\acceptance_story_20260815',
    [int]$ProjectId = 19,
    [int]$EpisodeId = 29
)

$ErrorActionPreference = 'Stop'
$runStarted = Get-Date
New-Item -ItemType Directory -Force -Path $OutputRoot, (Join-Path $OutputRoot 'shots') | Out-Null

function Run-Ffmpeg([string[]]$ffmpegArgs) {
    & ffmpeg.exe @ffmpegArgs
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed with exit code $LASTEXITCODE" }
}
function SrtTime([double]$seconds) {
    $ts = [TimeSpan]::FromSeconds($seconds)
    return ('{0:00}:{1:00}:{2:00},{3:000}' -f [int]$ts.TotalHours, $ts.Minutes, $ts.Seconds, $ts.Milliseconds)
}
function Find-Audio([int]$taskId) {
    $file = Get-ChildItem -LiteralPath (Join-Path 'C:\install\AI\Data\Artifacts\project-18\audio' "task-$taskId") -Filter '*.wav' -Recurse | Select-Object -First 1
    if (-not $file) { throw "Missing TTS artifact for task $taskId" }
    return $file.FullName
}

$sourceMap = @(
    'C:\install\AI\Data\Videos\task_986_task_986_00001_.mp4',
    'C:\install\AI\Data\Videos\task_987_task_987_00001_.mp4',
    'C:\install\AI\Data\Videos\task_988_task_988_00001_.mp4',
    'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D01_walk_2_steps.mp4',
    'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D02_turn_then_sit.mp4',
    'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D03_pick_up_cup.mp4',
    'C:\install\AI\Data\QA\benchmarks\action_identity_20260814\driving_sources_20260815\D04_driving.mp4',
    'C:\install\AI\Data\Videos\task_993_task_993_00001_.mp4',
    'C:\install\AI\Data\Videos\task_994_task_994_00001_.mp4',
    'C:\install\AI\Data\Videos\task_995_task_995_00001_.mp4',
    'C:\install\AI\Data\Videos\task_996_task_996_00001_.mp4',
    'C:\install\AI\Data\Videos\task_997_task_997_00001_.mp4',
    'C:\install\AI\Data\Videos\task_998_task_998_00001_.mp4',
    'C:\install\AI\Data\Videos\task_999_task_999_00001_.mp4',
    'C:\install\AI\Data\Videos\task_1000_task_1000_00001_.mp4',
    'C:\install\AI\Data\Videos\task_1005_task_1005_00001_.mp4'
)
$dialogue = @(Get-Content -LiteralPath 'C:\install\AI\VideoStudio\scripts\tts_batch_20260815.sql' -Encoding UTF8 | ForEach-Object { if ($_ -match '"text":"([^"]+)"') { $Matches[1] } } | Select-Object -First 16)
if ($dialogue.Count -ne 16) { throw "Expected 16 UTF-8 dialogue lines, got $($dialogue.Count)" }
if ($sourceMap.Count -ne 16) { throw "Expected 16 story sources, got $($sourceMap.Count)" }
foreach ($source in $sourceMap) { if (-not (Test-Path -LiteralPath $source)) { throw "Missing story source: $source" } }

$normalized = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt $sourceMap.Count; $i++) {
    $shotNumber = $i + 1
    $target = Join-Path $OutputRoot ("shots\shot-{0:00}.mp4" -f $shotNumber)
    $filter = 'fps=30,scale=720:720:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'
    Run-Ffmpeg @('-y','-hide_banner','-loglevel','error','-stream_loop','-1','-i',$sourceMap[$i],'-t','3.75','-vf',$filter,'-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',$target)
    $provenance = if ($i -ge 3 -and $i -le 6) { 'Driving source generated from prior Pose/I2V benchmark; not camera-recorded human' } else { 'Existing local Episode 28 video reused as continuity placeholder' }
    $normalized.Add([ordered]@{ shotNumber=$shotNumber; source=$sourceMap[$i]; normalized=$target; durationSeconds=3.75; provenance=$provenance })
}

$concatVideo = Join-Path $OutputRoot 'video-concat.txt'
($normalized | ForEach-Object { "file '$($_.normalized)'" }) | Set-Content -LiteralPath $concatVideo -Encoding ASCII
$videoOnly = Join-Path $OutputRoot 'video-only.mp4'
Run-Ffmpeg @('-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',$concatVideo,'-c','copy','-movflags','+faststart',$videoOnly)

$audioList = Join-Path $OutputRoot 'audio-concat.txt'
$audioFiles = for ($i = 0; $i -lt 16; $i++) { Find-Audio (1044 + $i) }
($audioFiles | ForEach-Object { "file '$($_)'" }) | Set-Content -LiteralPath $audioList -Encoding ASCII
$dialogueWav = Join-Path $OutputRoot 'dialogue-raw.wav'
Run-Ffmpeg @('-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',$audioList,'-ar','22050','-ac','1','-c:a','pcm_s16le',$dialogueWav)
$audio60 = Join-Path $OutputRoot 'dialogue-60s.wav'
Run-Ffmpeg @('-y','-hide_banner','-loglevel','error','-i',$dialogueWav,'-af','apad=pad_dur=60,atrim=0:60','-ar','48000','-ac','2','-c:a','pcm_s16le',$audio60)

$srtPath = Join-Path $OutputRoot 'episode-29-dialogue.srt'
$srtLines = [System.Collections.Generic.List[string]]::new()
for ($i = 0; $i -lt $dialogue.Count; $i++) {
    $start = $i * 3.75
    $end = [Math]::Min($start + 3.55, 60.0)
    $srtLines.Add([string]($i + 1)); $srtLines.Add("$(SrtTime $start) --> $(SrtTime $end)"); $srtLines.Add($dialogue[$i]); $srtLines.Add('')
}
$srtLines | Set-Content -LiteralPath $srtPath -Encoding UTF8

$master = Join-Path $OutputRoot 'MASTER_Midnight_Signal_MotionAcceptance_60s.mp4'
Run-Ffmpeg @('-y','-hide_banner','-loglevel','error','-i',$videoOnly,'-i',$audio60,'-i',$srtPath,'-map','0:v:0','-map','1:a:0','-map','2:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-c:s','mov_text','-metadata:s:s:0','language=chi','-t','60','-movflags','+faststart',$master)

$probe = & ffprobe.exe -v error -show_streams -show_format -of json -- $master | ConvertFrom-Json
$manifest = [ordered]@{
    schemaVersion='2026-08-15.story-master.v1'
    projectId=$ProjectId
    episodeId=$EpisodeId
    startedAt=$runStarted.ToString('o')
    finishedAt=(Get-Date).ToString('o')
    shotCount=16
    targetDurationSeconds=60
    masterPath=$master
    subtitlePath=$srtPath
    dialogueSourceTasks=1044..1059
    technicalStatus='PlayableMasterCreated'
    qualityStatus='ConditionalOnly_ActionAndIdentityManualGateFailedOrUnverified'
    notes=@(
        'New Project and Episode records were created; the Master uses real local videos and this run''s Driving sources as continuity material.',
        'D01-D04 are not camera-recorded human Driving Video; they came from prior generated videos, so action semantics are not claimed as passed.',
        'The 320x416 portrait sources are padded to 1920x1080; this is a playable acceptance cut, not final image-quality Master.',
        'The first 16 lines from the 20/20 technical-passed Chinese TTS batch are used for the dialogue track.'
    )
    shots=@($normalized)
    ffprobe=$probe
}
$manifest | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $OutputRoot 'story-master-manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 8
