[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [string]$InputImagePath = 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png',
    [long]$ProjectId = 17,
    [long]$EpisodeId = 27,
    [long]$SceneProjectId = 15,
    [int]$TimeoutMinutes = 90,
    [int]$SeedStart = 941000,
    [string]$WorkflowFile = '09_character_master_reference_v2_api.json',
    [string]$IdentityControlMode = 'character-anchor-img2img'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runTag = Get-Date -Format 'yyyyMMdd_HHmmss'
$reportPath = Join-Path $root "logs\identity_consistency_matrix_$runTag.json"
$experimentName = "Identity consistency 10 actions x 5 scenes 20260811 [$IdentityControlMode]"
$workflowVersion = [System.IO.Path]::GetFileNameWithoutExtension($WorkflowFile)
$modelName = 'v1-5-pruned-emaonly-fp16.safetensors'

$actions = @(
    [pscustomobject]@{ code = 'blink_breathe'; label = 'blink-breathe'; prompt = 'one natural blink, subtle breathing, head nearly still' },
    [pscustomobject]@{ code = 'turn_left'; label = 'turn-left'; prompt = 'slowly turn the head less than 8 degrees to the left, keep eyes and face natural' },
    [pscustomobject]@{ code = 'turn_right'; label = 'turn-right'; prompt = 'slowly turn the head less than 8 degrees to the right, keep eyes and face natural' },
    [pscustomobject]@{ code = 'small_nod'; label = 'small-nod'; prompt = 'one small deliberate nod less than 6 degrees, keep jawline and hairstyle unchanged' },
    [pscustomobject]@{ code = 'look_left'; label = 'look-left'; prompt = 'look briefly to the left with the head nearly still, natural pupils and eyelids' },
    [pscustomobject]@{ code = 'look_right'; label = 'look-right'; prompt = 'look briefly to the right with the head nearly still, natural pupils and eyelids' },
    [pscustomobject]@{ code = 'soft_smile'; label = 'soft-smile'; prompt = 'change from neutral to a restrained closed-mouth soft smile, no teeth' },
    [pscustomobject]@{ code = 'quiet_speech'; label = 'quiet-speech'; prompt = 'quietly mouth a short phrase with lips mostly closed, no teeth or tongue visible' },
    [pscustomobject]@{ code = 'hand_raise'; label = 'hand-raise'; prompt = 'raise one hand near the shoulder and keep it out of the face, chest-up portrait' },
    [pscustomobject]@{ code = 'step_forward'; label = 'step-forward'; prompt = 'take one slow small step forward while keeping the face and hairstyle unchanged' }
)

$report = [ordered]@{
    startedAt = (Get-Date).ToString('o')
    runTag = $runTag
    baseUrl = $BaseUrl
    inputImagePath = $InputImagePath
    projectId = $ProjectId
    episodeId = $EpisodeId
    sceneProjectId = $SceneProjectId
    requestedActions = $actions.Count
    requestedScenes = 5
    requestedCells = $actions.Count * 5
    workflowVersion = $workflowVersion
    modelName = $modelName
    identityControl = [ordered]@{
        characterAnchor = $InputImagePath
        characterReferenceInjection = $IdentityControlMode
        sceneReferenceInjection = 'not-applied-current-workflow-no-ip-adapter'
        lora = 'not-configured'
        ipAdapter = if ($IdentityControlMode -like '*ipadapter*') { 'IPAdapterUnifiedLoader PLUS FACE with character anchor' } else { 'not-configured-in-this-matrix' }
        controlNet = 'not-configured'
    }
    scenes = @()
    actions = $actions
    tasks = @()
    details = @()
    summary = $null
    errors = @()
}

function Invoke-Api([string]$Path, [string]$Method = 'GET', $Body = $null) {
    $request = @{ Uri = "$BaseUrl$Path"; Method = $Method; UseBasicParsing = $true }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json; charset=utf-8'
        $request.Body = $Body | ConvertTo-Json -Depth 30 -Compress
    }
    try {
        $response = Invoke-WebRequest @request
        if ([string]::IsNullOrWhiteSpace($response.Content)) { return $null }
        $parsed = $response.Content | ConvertFrom-Json
        if ($parsed -is [System.Array]) {
            foreach ($item in $parsed) { Write-Output $item }
        } else {
            Write-Output $parsed
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
    $report | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

try {
    if (-not (Test-Path -LiteralPath $InputImagePath)) { throw "Input reference does not exist: $InputImagePath" }
    $health = Invoke-Api '/api/health'
    if (-not $health.database.online -or -not $health.comfy.online -or -not $health.ffmpeg.available) { throw 'Health check failed.' }

    $workflows = @(Invoke-Api '/api/workflows')
    $workflow = $workflows | Where-Object { [System.IO.Path]::GetFileName($_.path) -ieq $WorkflowFile } | Select-Object -First 1
    if (-not $workflow) { throw "Workflow $WorkflowFile was not found." }

    $allScenes = @(Invoke-Api "/api/scenes?projectId=$SceneProjectId")
    $scenes = @($allScenes | Where-Object {
        $_.projectId -eq $SceneProjectId -and
        -not [string]::IsNullOrWhiteSpace($_.fixedPrompt) -and
        -not [string]::IsNullOrWhiteSpace($_.referencePath) -and
        (Test-Path -LiteralPath $_.referencePath)
    } | Sort-Object id | Select-Object -First 5)
    if ($scenes.Count -ne 5) { throw "Expected 5 usable scenes in project $SceneProjectId, found $($scenes.Count)." }

    $report.scenes = @($scenes | ForEach-Object {
        [ordered]@{
            id = $_.id
            name = $_.name
            fixedPrompt = $_.fixedPrompt
            style = $_.style
            negativePrompt = $_.negativePrompt
            referencePath = $_.referencePath
            referenceInjection = 'recorded-only; current workflow has no IP-Adapter scene branch'
        }
    })

    $experiment = @(Invoke-Api '/api/quality/experiments') | Where-Object { $_.name -eq $experimentName } | Select-Object -First 1
    if (-not $experiment) {
        $experiment = Invoke-Api '/api/quality/experiments' 'POST' @{
            name = $experimentName
            experimentType = 'IdentityConsistencyMatrix'
            baselineId = '09-character-master-reference-v2'
            controlledVariable = 'action,scenePrompt,seed'
            status = 'Open'
            description = 'Same character anchor across 10 action prompts and 5 real scene prompts on RTX 4070 12GB.'
        }
    }

    $created = @()
    $cellIndex = 0
    for ($sceneIndex = 0; $sceneIndex -lt $scenes.Count; $sceneIndex++) {
        $scene = $scenes[$sceneIndex]
        foreach ($action in $actions) {
            $cellIndex++
            $seed = $SeedStart + ($sceneIndex * 100) + ($cellIndex - 1)
            $positive = "same adult person as the input reference, preserve exact facial identity, eye shape, pupils, eyelids, nose, lips, jawline, hairstyle and facial hair, single person, medium close-up chest-up portrait, face clearly visible, realistic human skin, photorealistic live-action film still, $($scene.fixedPrompt), $($scene.style), $($action.prompt), stable identity across scenes"
            $negative = "multiple people, duplicate person, extra face, collage, contact sheet, split screen, extra eyes, asymmetrical eyes, crossed eyes, malformed pupils, deformed eyelids, warped mouth, fused lips, distorted jaw, bad anatomy, cropped face, changing hairstyle, face morphing, identity drift, flicker, ghosting, motion blur, low resolution, blurry, cartoon, anime, CGI, text, logo, watermark, $($scene.negativePrompt)"
            $body = @{
                projectId = $ProjectId
                episodeId = $EpisodeId
                taskType = 'Image'
                workflowId = $workflow.id
                inputImagePath = $InputImagePath
                priority = 1
                maxRetries = 0
                idempotencyKey = "identity-matrix-$runTag-$cellIndex"
                parameters = @{
                    positive = $positive
                    negative = $negative
                    seed = $seed
                    width = 640
                    height = 832
                    workflowVersion = $workflowVersion
                    referenceProfile = 'character'
                    referenceRequired = $false
                    qualityReferenceImagePath = $InputImagePath
                    candidateIndex = $cellIndex
                    identityMatrix = $true
                    identityMatrixAction = $action.code
                    identityMatrixSceneId = [long]$scene.id
                    identityMatrixSceneReferencePath = $scene.referencePath
                    qualityExperiment = $experimentName
                    qualityRunTag = $runTag
                    identityControlMode = $IdentityControlMode
                }
            }
            # The single LoadImage slot is reserved for the character anchor.
            # Scene references remain metadata until a two-reference scene branch is selected.
            $createdTask = Invoke-Api '/api/tasks' 'POST' $body
            $created += [pscustomobject]@{
                cell = $cellIndex
                sceneIndex = $sceneIndex
                sceneId = [long]$scene.id
                sceneName = $scene.name
                sceneReferencePath = $scene.referencePath
                actionCode = $action.code
                actionLabel = $action.label
                actionPrompt = $action.prompt
                seed = $seed
                taskId = [long]$createdTask.id
                status = 'Pending'
                progress = 0
            }
            Write-Host ("Queued identity matrix {0}/{1}: scene={2}, action={3}, task={4}, seed={5}" -f $cellIndex, $report.requestedCells, $scene.name, $action.code, $createdTask.id, $seed)
        }
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
        Write-Host ("Progress: {0}/{1} terminal; running={2}" -f $terminal, $created.Count, ($created.Count - $terminal))
        if ($terminal -lt $created.Count) { Start-Sleep -Seconds 5 }
    } while ($terminal -lt $created.Count -and (Get-Date) -lt $deadline)
    if (@($created | Where-Object { $_.status -notin @('Succeeded', 'Failed', 'Cancelled') }).Count -gt 0) { throw "Timed out after $TimeoutMinutes minutes." }

    $details = @()
    foreach ($item in $created) {
        $taskDetail = Invoke-Api "/api/tasks/$($item.taskId)"
        $task = $taskDetail.task
        $imageResult = @($taskDetail.results | Where-Object { $_.resultType -eq 'image' }) | Select-Object -Last 1
        $face = $null
        if ($imageResult -and (Test-Path -LiteralPath $imageResult.path)) {
            try { $face = Invoke-Api '/api/qa/face-image-check' 'POST' @{ path = $imageResult.path; referenceImagePath = $InputImagePath; portraitPreferred = $true } }
            catch { $report.errors += "task $($item.taskId) face-image-check: $($_.Exception.Message)" }
        }
        $hash = if ($imageResult -and (Test-Path -LiteralPath $imageResult.path)) { (Get-FileHash -LiteralPath $imageResult.path -Algorithm SHA256).Hash } else { $null }
        $detailRow = [ordered]@{
            cell = $item.cell
            taskId = $item.taskId
            sceneId = $item.sceneId
            sceneName = $item.sceneName
            sceneReferencePath = $item.sceneReferencePath
            actionCode = $item.actionCode
            actionLabel = $item.actionLabel
            actionPrompt = $item.actionPrompt
            seed = $item.seed
            status = $task.status
            durationMs = $task.durationMs
            vramPeakMib = $task.vramPeakMib
            outputPath = if ($imageResult) { $imageResult.path } else { $null }
            imageHash = $hash
            technicalQualityScore = if ($imageResult) { $imageResult.qualityScore } else { $null }
            faceStatus = if ($face) { $face.status } else { $null }
            faceScore = if ($face) { $face.score } else { $null }
            faceIssues = if ($face) { @($face.issues) } else { @() }
            faceMetrics = if ($face) { $face.metrics } else { $null }
        }
        $details += [pscustomobject]$detailRow
        try {
            Invoke-Api "/api/quality/experiments/$($experiment.id)/runs" 'POST' @{
                testCase = "identity-$($item.sceneId)-$($item.actionCode)-$runTag"
                taskId = $item.taskId
                workflowVersion = $workflowVersion
                modelName = $modelName
                status = if ($task.status -ne 'Succeeded') { 'Failed' } elseif ($face -and $face.status -eq 'Rejected') { 'Rejected' } else { 'NeedReview' }
                parameters = @{ sceneId = $item.sceneId; sceneName = $item.sceneName; actionCode = $item.actionCode; seed = $item.seed; identityAnchor = $InputImagePath; sceneReferencePath = $item.sceneReferencePath; sceneReferenceInjection = 'not-applied-current-workflow-no-ip-adapter' }
                metrics = $detailRow
                notes = 'Static identity matrix cell. CPU face proxy is a filter only; manual review is required.'
            } | Out-Null
        } catch { $report.errors += "task $($item.taskId) experiment-run: $($_.Exception.Message)" }
    }

    $report.details = $details
    $scores = @($details | Where-Object { $null -ne $_.faceScore } | ForEach-Object { [double]$_.faceScore })
    $similarities = @($details | Where-Object { $null -ne $_.faceMetrics -and $null -ne $_.faceMetrics.referenceSimilarityProxy } | ForEach-Object { [double]$_.faceMetrics.referenceSimilarityProxy })
    $hashes = @($details | Where-Object { $_.imageHash } | ForEach-Object { $_.imageHash })
    $succeeded = @($details | Where-Object status -eq 'Succeeded')
    $rejected = @($details | Where-Object faceStatus -eq 'Rejected')
    $report.summary = [ordered]@{
        requestedCells = $report.requestedCells
        succeeded = $succeeded.Count
        failed = @($details | Where-Object status -eq 'Failed').Count
        cancelled = @($details | Where-Object status -eq 'Cancelled').Count
        faceRejected = $rejected.Count
        faceReviewRequired = @($details | Where-Object faceStatus -eq 'NeedReview').Count
        averageFaceScore = if ($scores.Count) { [math]::Round(($scores | Measure-Object -Average).Average, 2) } else { $null }
        minimumFaceScore = if ($scores.Count) { [math]::Round(($scores | Measure-Object -Minimum).Minimum, 2) } else { $null }
        averageReferenceSimilarityProxy = if ($similarities.Count) { [math]::Round(($similarities | Measure-Object -Average).Average, 2) } else { $null }
        minimumReferenceSimilarityProxy = if ($similarities.Count) { [math]::Round(($similarities | Measure-Object -Minimum).Minimum, 2) } else { $null }
        uniqueImageHashes = @($hashes | Sort-Object -Unique).Count
        allCellsSucceeded = $succeeded.Count -eq $report.requestedCells
        noFaceRejection = $rejected.Count -eq 0
        actionCoverage = @($details | Group-Object actionCode | ForEach-Object { [pscustomobject]@{ actionCode = $_.Name; cells = $_.Count; succeeded = @($_.Group | Where-Object status -eq 'Succeeded').Count; faceRejected = @($_.Group | Where-Object faceStatus -eq 'Rejected').Count } })
        sceneCoverage = @($details | Group-Object sceneId | ForEach-Object { [pscustomobject]@{ sceneId = $_.Name; cells = $_.Count; succeeded = @($_.Group | Where-Object status -eq 'Succeeded').Count; faceRejected = @($_.Group | Where-Object faceStatus -eq 'Rejected').Count } })
        manualReviewRequired = $true
        gatePassed = $succeeded.Count -eq $report.requestedCells -and $rejected.Count -eq 0
    }
    Write-JsonReport
    $report | ConvertTo-Json -Depth 40
    if (-not $report.summary.gatePassed) { exit 2 }
} catch {
    $report.errors += $_.Exception.Message
    Write-JsonReport
    $report | ConvertTo-Json -Depth 40
    exit 1
}
