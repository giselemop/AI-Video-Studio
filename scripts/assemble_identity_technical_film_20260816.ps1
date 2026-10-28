[CmdletBinding()]
param(
    [string]$SimpleRoot = 'C:\install\AI\Data\QA\simple_motion_benchmark_20260816',
    [string]$SplitRoot = 'C:\install\AI\Data\QA\walk_sit_pick_benchmark_20260816',
    [string]$AudioPath = 'C:\install\AI\Data\QA\acceptance_story_20260815\dialogue-60s.wav',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\identity_technical_film_20260816',
    [string]$Ffmpeg = 'C:\install\FFmpeg\bin\ffmpeg.exe',
    [string]$Ffprobe = 'C:\install\FFmpeg\bin\ffprobe.exe'
)

$ErrorActionPreference = 'Stop'
if(-not (Test-Path -LiteralPath $Ffmpeg)){throw "ffmpeg missing: $Ffmpeg"}
if(-not (Test-Path -LiteralPath $Ffprobe)){throw "ffprobe missing: $Ffprobe"}
if(-not (Test-Path -LiteralPath $AudioPath)){throw "audio missing: $AudioPath"}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$stageRoot = Join-Path $OutputRoot 'staged-shots'
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

$subtitleMap = @'
{"T01":"\u4eba\u7269\u8eab\u4efd\u951a\u5b9a\uff1a\u5355\u4eba\u6b63\u9762\u8fd1\u666f\u3002","T02":"\u5fae\u7b11\uff1a\u5355\u4e00\u5fae\u52a8\u4f5c\u6280\u672f\u6837\u672c\u3002","T03":"\u5411\u5de6\u5fae\u8f6c\uff1a\u52a8\u4f5c\u8bed\u4e49\u5f85\u4eba\u5de5\u590d\u6838\u3002","T04":"\u5411\u53f3\u5fae\u8f6c\uff1a\u52a8\u4f5c\u8bed\u4e49\u5f85\u4eba\u5de5\u590d\u6838\u3002","T05":"\u4f4e\u5934\u4fdd\u6301\uff1a\u5355\u4e00\u5fae\u52a8\u4f5c\u6280\u672f\u6837\u672c\u3002","T06":"\u62ac\u5934\u4fdd\u6301\uff1a\u5355\u4e00\u5fae\u52a8\u4f5c\u6280\u672f\u6837\u672c\u3002","T07":"\u80a9\u90e8\u5fae\u52a8\uff1a\u8eab\u4efd\u4e0e\u65f6\u5e8f\u5f85\u4eba\u5de5\u590d\u6838\u3002","T08":"\u62ac\u624b\u4fdd\u6301\uff1a\u624b\u90e8\u8bed\u4e49\u5f85\u4eba\u5de5\u590d\u6838\u3002","T09":"Walk-Step-1\uff1a\u62c6\u5206\u955c\u5934\u6280\u672f\u6837\u672c\u3002","T10":"Pick-Lift\uff1a\u624b\u7269\u5173\u7cfb\u5f85\u4eba\u5de5\u590d\u6838\u3002"}
'@ | ConvertFrom-Json
$shots = @(
    [ordered]@{id='T01';label='Blink';source=(Join-Path $SimpleRoot 'S01\S01_501001.webp');subtitle=$subtitleMap.T01},
    [ordered]@{id='T02';label='Smile';source=(Join-Path $SimpleRoot 'S02\S02_502001.webp');subtitle=$subtitleMap.T02},
    [ordered]@{id='T03';label='Turn-Left';source=(Join-Path $SimpleRoot 'S03\S03_503001.webp');subtitle=$subtitleMap.T03},
    [ordered]@{id='T04';label='Turn-Right';source=(Join-Path $SimpleRoot 'S04\S04_504001.webp');subtitle=$subtitleMap.T04},
    [ordered]@{id='T05';label='Look-Down';source=(Join-Path $SimpleRoot 'S05\S05_505001.webp');subtitle=$subtitleMap.T05},
    [ordered]@{id='T06';label='Look-Up';source=(Join-Path $SimpleRoot 'S06\S06_506001.webp');subtitle=$subtitleMap.T06},
    [ordered]@{id='T07';label='Shoulder';source=(Join-Path $SimpleRoot 'S07\S07_507001.webp');subtitle=$subtitleMap.T07},
    [ordered]@{id='T08';label='Raise-Hand';source=(Join-Path $SimpleRoot 'S08\S08_508001.webp');subtitle=$subtitleMap.T08},
    [ordered]@{id='T09';label='Walk-Step-1';source=(Join-Path $SplitRoot 'C01-W1\C01-W1_601001.webp');subtitle=$subtitleMap.T09},
    [ordered]@{id='T10';label='Pick-Lift';source=(Join-Path $SplitRoot 'C03-P3\C03-P3_603201.webp');subtitle=$subtitleMap.T10}
)
foreach($shot in $shots){if(-not (Test-Path -LiteralPath $shot.source)){throw "shot source missing: $($shot.source)"}}

$staged = [System.Collections.Generic.List[object]]::new()
foreach($shot in $shots){
    $target = Join-Path $stageRoot "$($shot.id).mp4"
    & $Ffmpeg -hide_banner -loglevel error -y -i $shot.source -t 2.5 -vf "fps=30,scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p" -an -c:v libx264 -preset fast -crf 20 -movflags +faststart $target
    if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $target)){throw "failed to stage $($shot.id)"}
    $staged.Add([ordered]@{id=$shot.id;label=$shot.label;source=$shot.source;staged=$target;subtitle=$shot.subtitle})
}

$concatPath = Join-Path $OutputRoot 'concat.txt'
$concatLines = $staged | ForEach-Object { "file '$($_.staged.Replace("'", "'\''"))'" }
[IO.File]::WriteAllLines($concatPath, [string[]]$concatLines, [Text.UTF8Encoding]::new($false))
$srtPath = Join-Path $OutputRoot 'subtitles.srt'
$srtLines = [System.Collections.Generic.List[string]]::new()
for($i=0;$i -lt $staged.Count;$i++){
    $start = [TimeSpan]::FromSeconds($i * 2.5).ToString('hh\:mm\:ss\,fff')
    $end = [TimeSpan]::FromSeconds(($i + 1) * 2.5).ToString('hh\:mm\:ss\,fff')
    $srtLines.Add([string]($i + 1)); $srtLines.Add("$start --> $end"); $srtLines.Add($staged[$i].subtitle); $srtLines.Add('')
}
[IO.File]::WriteAllLines($srtPath, [string[]]$srtLines, [Text.UTF8Encoding]::new($false))
$subtitleFilterPath = $srtPath.Replace('\','/').Replace(':','\:')
$filmPath = Join-Path $OutputRoot 'identity-technical-film-25s.mp4'
& $Ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $concatPath -i $AudioPath -t 25 -vf "scale=1920:1080:flags=lanczos,subtitles='$subtitleFilterPath':force_style='FontName=Microsoft YaHei,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=48'" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart $filmPath
if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $filmPath)){throw 'failed to assemble technical film'}

$probeJson = (& $Ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,channels,sample_rate -of json $filmPath | Out-String | ConvertFrom-Json)
$video = @($probeJson.streams | Where-Object codec_type -eq 'video' | Select-Object -First 1)[0]
$audio = @($probeJson.streams | Where-Object codec_type -eq 'audio' | Select-Object -First 1)[0]
$report = [ordered]@{
    schemaVersion='2026-08-16.identity-technical-film.v1'
    generatedAt=(Get-Date).ToString('o')
    output=$filmPath
    durationSeconds=[math]::Round([double]$probeJson.format.duration,3)
    sizeBytes=[int64]$probeJson.format.size
    video=[ordered]@{codec=$video.codec_name;width=$video.width;height=$video.height;frameRate=$video.r_frame_rate}
    audio=[ordered]@{codec=$audio.codec_name;channels=$audio.channels;sampleRate=$audio.sample_rate}
    shotCount=$staged.Count
    technicalStatus='Passed'
    identityStatus='Unverified'
    actionSemanticStatus='Unverified'
    manualReviewRequired=$true
    note='Technical playable film only. Several source samples are close-up outputs despite full-body/action prompts; no semantic or human acceptance is claimed.'
    shots=@($staged)
}
$reportPath = Join-Path $OutputRoot 'identity-technical-film-results.json'
$report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Output "FILM=$filmPath"
Write-Output "REPORT=$reportPath"
Write-Output ("DURATION={0}s VIDEO={1}x{2} {3} AUDIO={4} {5}Hz" -f $report.durationSeconds,$video.width,$video.height,$video.codec_name,$audio.codec_name,$audio.sample_rate)
