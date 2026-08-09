[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [string]$TrainVideoPath = 'C:\install\AI\Projects\doomsday_train\output\episode_final_1080p_30fps.mp4'
)

$ErrorActionPreference = 'Stop'
$root = 'C:\install\AI\VideoStudio'
$ffmpeg = 'C:\install\FFmpeg\bin\ffmpeg.exe'
$testRoot = Join-Path 'C:\install\AI\Data\QA\TestCases' (Get-Date -Format 'yyyyMMdd_HHmmss')
$logPath = Join-Path $root 'logs\qa_test.log'
$reportPath = Join-Path $root 'logs\qa_test_report.json'
New-Item -ItemType Directory -Force -Path $testRoot, (Split-Path $logPath) | Out-Null
Start-Transcript -Path $logPath -Append | Out-Null

function Run-Ffmpeg([string[]]$ArgList) {
    & $ffmpeg @ArgList
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg 测试素材生成失败，退出码 $LASTEXITCODE" }
}

function New-Clip([string]$Path, [string]$Video, [string]$Duration, [bool]$Audio) {
    $separator = if ($Video -like 'color=*') { '\:' } else { '=' }
    $ffArgs = @('-y','-hide_banner','-loglevel','error','-f','lavfi','-i',"${Video}${separator}size=1920x1080\:rate=30\:duration=$Duration")
    if ($Audio) { $ffArgs += @('-f','lavfi','-i',"sine=frequency=440\:sample_rate=48000\:duration=$Duration") }
    $ffArgs += @('-t',$Duration,'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p')
    if ($Audio) { $ffArgs += @('-c:a','aac','-shortest') } else { $ffArgs += @('-an') }
    $ffArgs += $Path
    Run-Ffmpeg $ffArgs
}

function Invoke-Qa([string]$Name, [string]$Path, [string]$Expected, [hashtable]$Overrides = @{}) {
    $body = @{ path = $Path; expectedWidth = 1920; expectedHeight = 1080; expectedFps = 30; expectedDuration = 3; requireAudio = $false; requireSubtitle = $false; durationTolerancePercent = 10; fpsTolerance = 1; blackFrameMaxPercent = 2 }
    foreach ($key in $Overrides.Keys) { $body[$key] = $Overrides[$key] }
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/qa/technical-check" -Method Post -ContentType 'application/json; charset=utf-8' -Body ($body | ConvertTo-Json -Depth 5)
    $passed = $response.status -eq $Expected
    [pscustomobject]@{ name = $Name; expected = $Expected; actual = $response.status; score = $response.score; issueCount = @($response.issues).Count; passed = $passed; details = $response }
}

try {
    if (-not (Test-Path $ffmpeg)) { throw "FFmpeg 不存在：$ffmpeg" }
    $normal = Join-Path $testRoot 'normal.mp4'; New-Clip $normal 'testsrc2' '3' $true
    $black = Join-Path $testRoot 'black.mp4'; New-Clip $black 'color=c=black' '3' $true
    $short = Join-Path $testRoot 'short.mp4'; New-Clip $short 'testsrc2' '1' $true
    $wrong = Join-Path $testRoot 'wrong_resolution.mp4'
    Run-Ffmpeg @('-y','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=1280x720\:rate=30\:duration=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-an',$wrong)
    $warning = Join-Path $testRoot 'temporal_warning.mp4'
    $colors = @('red','blue','green','yellow','red','blue'); $warningArgs = @('-y','-hide_banner','-loglevel','error')
    foreach ($color in $colors) { $warningArgs += @('-f','lavfi','-i',"color=c=$color\:size=1920x1080\:rate=30\:duration=0.5") }
    $warningArgs += @('-filter_complex','[0:v][1:v][2:v][3:v][4:v][5:v]concat=n=6:v=1:a=0[out]','-map','[out]','-t','3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-an',$warning)
    Run-Ffmpeg $warningArgs
    $noAudio = Join-Path $testRoot 'no_audio.mp4'; New-Clip $noAudio 'testsrc2' '3' $false
    $corrupt = Join-Path $testRoot 'corrupt.mp4'; Copy-Item $normal $corrupt; $corruptStream = [System.IO.File]::Open($corrupt, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None); $corruptStream.SetLength([int64]($corruptStream.Length * .25)); $corruptStream.Dispose()
    $srt = Join-Path $testRoot 'timeout.srt'; Set-Content -LiteralPath $srt -Value "1`n00:00:00,000 --> 00:00:05,000`n中文超时字幕`n" -Encoding UTF8

    $results = @()
    $results += Invoke-Qa 'normal-pass' $normal 'Passed'
    $results += Invoke-Qa 'black-reject' $black 'Rejected'
    $results += Invoke-Qa 'short-reject' $short 'Rejected'
    $results += Invoke-Qa 'wrong-resolution-reject' $wrong 'Rejected'
    $results += Invoke-Qa 'temporal-warning' $warning 'NeedReview'
    $results += Invoke-Qa 'corrupt-reject' $corrupt 'Rejected'
    $results += Invoke-Qa 'missing-audio-reject' $noAudio 'Rejected' @{ requireAudio = $true }
    $results += Invoke-Qa 'subtitle-timeout-reject' $normal 'Rejected' @{ requireSubtitle = $true; subtitlePath = $srt }

    if (Test-Path $TrainVideoPath) { $results += Invoke-Qa 'doomsday-train-technical' $TrainVideoPath 'Passed' @{ expectedDuration = $null } }
    $failed = @($results | Where-Object { -not $_.passed })
    $results | Select-Object name,expected,actual,score,issueCount,passed | Format-Table -AutoSize
    $results | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if ($failed.Count -gt 0) { throw "QA 测试失败：$($failed.name -join ', ')" }
    Write-Host "QA 技术验收测试全部通过。素材目录：$testRoot"
}
finally {
    Stop-Transcript | Out-Null
}
