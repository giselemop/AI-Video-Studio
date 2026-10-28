[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [string]$InputImagePath = 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png',
    [long]$ProjectId = 17,
    [long]$EpisodeId = 27,
    [long]$PreflightShotId = 168,
    [int]$Runs = 20,
    [int]$SeedStart = 920101,
    [int]$TimeoutMinutes = 60,
    [double]$ReferenceStrength = 0.45,
    [string]$Action = 'one natural blink, subtle breathing',
    [ValidateSet('small', 'controlled-complex')]
    [string]$MotionProfile = 'small',
    [string]$CameraMotion = 'locked-off / micro motion only',
    [int]$GuideFrameIndex = 72,
    [int]$Frames = 73,
    [double]$Fps = 24,
    [double]$Duration = 3.042,
    [switch]$AllowLongVideo
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runTag = Get-Date -Format 'yyyyMMdd_HHmmss'
$reportPath = Join-Path $root "logs\quality_v3_i2v_regression_$runTag.json"
$framesRoot = Join-Path 'C:\install\AI\Data\QA' "quality-v3-i2v-$runTag"
$ffmpeg = 'C:\install\FFmpeg\bin\ffmpeg.exe'
if (-not (Test-Path -LiteralPath $ffmpeg)) { $ffmpeg = 'ffmpeg.exe' }

$workflowVersion = '12_ltx_face_stable_v3'
$modelName = 'ltxv-2b-0.9.8-distilled-fp8.safetensors'
$longVideoEnabled = [bool]$AllowLongVideo.IsPresent
$motionGuidance = if ($MotionProfile -eq 'controlled-complex') { 'controlled complex movement, preserve facial structure and hairstyle during motion, no abrupt acceleration' } else { 'minimal motion, preserve facial structure and hairstyle' }
$positive = "adult male virtual character, single person, identity locked to the reference image, realistic skin, symmetrical natural eyes, closed relaxed mouth, neutral expression, $Action, $CameraMotion, $motionGuidance, temporal consistency"
$negative = 'deformed face, asymmetrical eyes, extra pupils, crossed eyes, malformed mouth, open mouth, extra teeth, long tongue, warped jaw, changing face shape, duplicate person, ghost body, extra limbs, flicker, frame tearing, motion blur, camera shake, text, watermark, logo'

$report = [ordered]@{
    startedAt = (Get-Date).ToString('o')
    baseUrl = $BaseUrl
    runTag = $runTag
    inputImagePath = $InputImagePath
    projectId = $ProjectId
    episodeId = $EpisodeId
    preflightShotId = $PreflightShotId
    requestedRuns = $Runs
    workflowVersion = $workflowVersion
    modelName = $modelName
    parameters = [ordered]@{
        width = 320
        height = 416
        frames = $Frames
        fps = $Fps
        duration = $Duration
        referenceStrength = $ReferenceStrength
        guideFrameIndex = $GuideFrameIndex
        inputStrength = 1.0
        faceStabilityPriority = $true
        allowLongVideo = $longVideoEnabled
        motionProfile = $MotionProfile
        action = $Action
        cameraMotion = $CameraMotion
    }
    preflight = $null
    tasks = @()
    summary = $null
    errors = @()
}

function Invoke-Api([string]$Path, [string]$Method = 'GET', $Body = $null) {
    $request = @{ Uri = "$BaseUrl$Path"; Method = $Method; UseBasicParsing = $true }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json; charset=utf-8'
        $request.Body = $Body | ConvertTo-Json -Depth 20 -Compress
    }
    try {
        $response = Invoke-RestMethod @request
        if ($response -is [System.Array]) {
            foreach ($item in $response) { Write-Output $item }
        } elseif ($response.PSObject.Properties.Name -contains 'value' -and $null -ne $response.value) {
            foreach ($item in @($response.value)) { Write-Output $item }
        } else {
            Write-Output $response
        }
    } catch {
        $detail = $_.Exception.Message
        $webResponse = $_.Exception.Response
        if ($null -ne $webResponse) {
            try {
                $reader = [System.IO.StreamReader]::new($webResponse.GetResponseStream())
                $content = $reader.ReadToEnd()
                if (-not [string]::IsNullOrWhiteSpace($content)) { $detail = "$detail; response=$content" }
            } catch { }
        }
        throw $detail
    }
}

function Write-JsonReport {
    $report.finishedAt = (Get-Date).ToString('o')
    New-Item -ItemType Directory -Force -Path (Split-Path $reportPath) | Out-Null
    $report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

function Extract-Frames([string]$VideoPath, [long]$TaskId) {
    if (-not (Test-Path -LiteralPath $VideoPath)) { return @() }
    $directory = Join-Path $framesRoot "task_$TaskId"
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $outputs = @()
    $sampleFrames = @(
        0,
        [int][math]::Floor(($Frames - 1) / 2),
        [int]($Frames - 1)
    ) | Select-Object -Unique
    foreach ($frame in $sampleFrames) {
        $output = Join-Path $directory "frame_$frame.png"
        & $ffmpeg -y -hide_banner -loglevel error -i $VideoPath -vf "select=eq(n\,$frame)" -frames:v 1 $output
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $output)) { $outputs += $output }
    }
    return $outputs
}

try {
    if ($Runs -lt 1 -or $Runs -gt 50) { throw 'Runs must be between 1 and 50.' }
    if (-not (Test-Path -LiteralPath $InputImagePath)) { throw "Input reference does not exist: $InputImagePath" }

    $health = Invoke-Api '/api/health'
    if (-not $health.database.online -or -not $health.comfy.online -or -not $health.ffmpeg.available) {
        throw 'Health check failed: database, ComfyUI and FFmpeg must all be online.'
    }

    $workflows = @(Invoke-Api '/api/workflows')
    $workflow = $workflows | Where-Object { $_.path -match '12_ltx_face_stable_v3_api\.json$' } | Select-Object -First 1
    if (-not $workflow) { throw 'Workflow 12_ltx_face_stable_v3_api.json was not found in the catalog.' }

    $preflightBody = @{
        inputImagePath = $InputImagePath
        parameters = @{
            workflowVersion = $workflowVersion
            width = 320; height = 416; frames = $Frames; fps = $Fps; duration = $Duration
            referenceStrength = $ReferenceStrength; inputStrength = 1.0; faceStabilityPriority = $true
            allowLongVideo = $longVideoEnabled; motionProfile = $MotionProfile
            action = $Action
            cameraMotion = $CameraMotion
            guideFrameIndex = $GuideFrameIndex
        }
    }
    $preflight = Invoke-Api "/api/qa/shots/$PreflightShotId/i2v-preflight" 'POST' $preflightBody
    $report.preflight = $preflight
    if (-not $preflight.passed) { throw "I2V preflight failed: $($preflight.issues -join '; ')" }

    $experiments = @(Invoke-Api '/api/quality/experiments')
    $experiment = $experiments | Where-Object { $_.name -eq 'Adult face stability baseline vs optimized 20260811' } | Select-Object -First 1
    if (-not $experiment) {
        $experiment = Invoke-Api '/api/quality/experiments' 'POST' @{
            name = 'Adult face stability baseline vs optimized 20260811'
            experimentType = 'Baseline'
            baselineId = 'LTX-v1-character-lock'
            controlledVariable = 'workflowVersion,guideStrength,motionProfile,duration'
            status = 'Open'
            description = "Repeated v3 character I2V stability regression: $Frames frames / $Duration seconds on RTX 4070 12GB."
        }
    }

    $created = @()
    for ($index = 1; $index -le $Runs; $index++) {
        $seed = $SeedStart + $index - 1
        $body = @{
            projectId = $ProjectId
            episodeId = $EpisodeId
            taskType = 'ImageToVideo'
            workflowId = $workflow.id
            inputImagePath = $InputImagePath
            priority = 1
            maxRetries = 0
            idempotencyKey = "quality-v3-i2v-$runTag-$index"
            parameters = @{
                positive = $positive
                negative = $negative
                seed = $seed
                width = 320; height = 416; frames = $Frames; fps = $Fps; duration = $Duration
                workflowVersion = $workflowVersion
                referenceImages = @($InputImagePath)
                qualityReferenceImagePath = $InputImagePath
                referenceProfile = 'character'; referenceRequired = $true
                referenceStrength = $ReferenceStrength; inputStrength = 1.0
                guideFrameIndex = $GuideFrameIndex
                faceStabilityPriority = $true; allowLongVideo = $longVideoEnabled
                motionProfile = $MotionProfile; action = $Action
                cameraMotion = $CameraMotion
                qualityExperiment = 'Adult face stability baseline vs optimized 20260811'
                qualityRunTag = $runTag
            }
        }
        $createdTask = Invoke-Api '/api/tasks' 'POST' $body
        $created += [pscustomobject]@{ index = $index; seed = $seed; taskId = [long]$createdTask.id; status = 'Pending'; progress = 0 }
        Write-Host ("Queued v3 I2V {0}/{1}: task {2}, seed {3}" -f $index, $Runs, $createdTask.id, $seed)
    }
    $report.tasks = $created

    $ids = @($created | ForEach-Object { [long]$_.taskId })
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    do {
        $taskRows = @(Invoke-Api '/api/tasks?limit=500') | Where-Object { $ids -contains [long]$_.id }
        foreach ($item in $created) {
            $current = $taskRows | Where-Object { [long]$_.id -eq $item.taskId } | Select-Object -First 1
            if ($current) { $item.status = $current.status; $item.progress = $current.progress }
        }
        $terminal = @($created | Where-Object { $_.status -in @('Succeeded', 'Failed', 'Cancelled') }).Count
        Write-Host ("Progress: {0}/{1} terminal; running={2}" -f $terminal, $Runs, ($Runs - $terminal))
        if ($terminal -lt $Runs) { Start-Sleep -Seconds 5 }
    } while ($terminal -lt $Runs -and (Get-Date) -lt $deadline)

    if (@($created | Where-Object { $_.status -notin @('Succeeded', 'Failed', 'Cancelled') }).Count -gt 0) {
        throw "Timed out waiting for v3 I2V tasks after $TimeoutMinutes minutes."
    }

    $details = @()
    foreach ($item in $created) {
        $detail = Invoke-Api "/api/tasks/$($item.taskId)"
        $task = $detail.task
        $videoResult = @($detail.results | Where-Object { $_.resultType -eq 'video' }) | Select-Object -Last 1
        $face = $null
        $frameOutputs = @()
        if ($videoResult -and (Test-Path -LiteralPath $videoResult.path)) {
            $frameOutputs = Extract-Frames $videoResult.path $item.taskId
            try {
                $face = Invoke-Api '/api/qa/face-video-check' 'POST' @{ path = $videoResult.path; referenceImagePath = $InputImagePath }
            } catch {
                $report.errors += "task $($item.taskId) face-video-check: $($_.Exception.Message)"
            }
        }
        $detailRow = [ordered]@{
            index = $item.index
            taskId = $item.taskId
            seed = $item.seed
            status = $task.status
            durationMs = $task.durationMs
            vramPeakMib = $task.vramPeakMib
            vramFreeMib = $task.vramFreeMib
            outputPath = if ($videoResult) { $videoResult.path } else { $null }
            technicalQualityScore = if ($videoResult) { $videoResult.qualityScore } else { $null }
            qcJson = if ($videoResult) { $videoResult.qcJson } else { $null }
            faceStatus = if ($face) { $face.status } else { $null }
            faceScore = if ($face) { $face.score } else { $null }
            faceIssues = if ($face) { @($face.issues) } else { @() }
            frameOutputs = $frameOutputs
        }
        $details += [pscustomobject]$detailRow
        $runStatus = if ($task.status -ne 'Succeeded') { 'Failed' } elseif ($face -and $face.status -eq 'Rejected') { 'Rejected' } else { 'NeedReview' }
        try {
            Invoke-Api "/api/quality/experiments/$($experiment.id)/runs" 'POST' @{
                testCase = "v3-$($Frames)f-$($item.index.ToString('00'))-$runTag"
                taskId = $item.taskId
                workflowVersion = $workflowVersion
                modelName = $modelName
                status = $runStatus
                parameters = $report.parameters
                metrics = $detailRow
                notes = "Repeated v3 portrait I2V at $Frames frames / $Duration seconds; action=$Action; manual review required for face identity and temporal stability."
            } | Out-Null
        } catch {
            $report.errors += "task $($item.taskId) experiment-run: $($_.Exception.Message)"
        }
    }

    $report.details = $details
    $videoHashes = @()
    $midFrameHashes = @()
    foreach ($detail in $details) {
        if ($detail.outputPath -and (Test-Path -LiteralPath $detail.outputPath)) {
            $videoHashes += (Get-FileHash -LiteralPath $detail.outputPath -Algorithm SHA256).Hash
        }
        $framePaths = @($detail.frameOutputs)
        if ($framePaths.Count -gt 1) {
            $midFrameIndex = [int][math]::Floor(($Frames - 1) / 2)
            $midFrameName = "frame_$midFrameIndex.png"
            $midFramePath = $framePaths | Where-Object { [string]::Equals([System.IO.Path]::GetFileName($_), $midFrameName, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
            if ($midFramePath -and (Test-Path -LiteralPath $midFramePath)) {
                $midFrameHashes += (Get-FileHash -LiteralPath $midFramePath -Algorithm SHA256).Hash
            }
        }
    }
    $uniqueVideoHashes = @($videoHashes | Sort-Object -Unique).Count
    $uniqueMidFrameHashes = @($midFrameHashes | Sort-Object -Unique).Count
    $seedDiversityPassed = $Runs -le 1 -or $uniqueVideoHashes -gt 1
    $succeeded = @($details | Where-Object status -eq 'Succeeded')
    $rejected = @($details | Where-Object faceStatus -eq 'Rejected')
    $scores = @($details | Where-Object { $null -ne $_.faceScore } | ForEach-Object { [double]$_.faceScore })
    $report.summary = [ordered]@{
        requested = $Runs
        succeeded = $succeeded.Count
        failed = @($details | Where-Object status -eq 'Failed').Count
        cancelled = @($details | Where-Object status -eq 'Cancelled').Count
        faceRejected = $rejected.Count
        faceReviewRequired = @($details | Where-Object faceStatus -eq 'NeedReview').Count
        averageFaceScore = if ($scores.Count) { [math]::Round(($scores | Measure-Object -Average).Average, 2) } else { $null }
        minimumFaceScore = if ($scores.Count) { [math]::Round(($scores | Measure-Object -Minimum).Minimum, 2) } else { $null }
        maxVramPeakMib = if (@($details | Where-Object { $null -ne $_.vramPeakMib }).Count) { ($details | Where-Object { $null -ne $_.vramPeakMib } | Measure-Object vramPeakMib -Maximum).Maximum } else { $null }
        uniqueVideoHashes = $uniqueVideoHashes
        uniqueMidFrameHashes = $uniqueMidFrameHashes
        allTasksSucceeded = $succeeded.Count -eq $Runs
        noFaceRejection = $rejected.Count -eq 0
        seedDiversityPassed = $seedDiversityPassed
        manualReviewRequired = $true
    }
    Write-JsonReport
    $report | ConvertTo-Json -Depth 30
    if (-not $report.summary.allTasksSucceeded -or -not $report.summary.seedDiversityPassed -or -not $report.summary.noFaceRejection) { exit 2 }
} catch {
    $report.errors += $_.Exception.Message
    Write-JsonReport
    $report | ConvertTo-Json -Depth 30
    exit 1
}
