[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [string]$InputImagePath = 'C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png',
    [int]$FirstTaskId = 802,
    [int]$LastTaskId = 851,
    [long]$SceneProjectId = 15,
    [string]$WorkflowVersion = '09_character_master_reference_v2',
    [string]$IdentityControlMode = 'character-anchor-img2img'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runTag = Get-Date -Format 'yyyyMMdd_HHmmss'
$reportPath = Join-Path $root "logs\identity_consistency_matrix_${runTag}_final.json"

function Invoke-Api([string]$Path, [string]$Method = 'GET', $Body = $null) {
    $request = @{ Uri = "$BaseUrl$Path"; Method = $Method; UseBasicParsing = $true }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json; charset=utf-8'
        $request.Body = $Body | ConvertTo-Json -Depth 30 -Compress
    }
    $response = Invoke-WebRequest @request
    if ([string]::IsNullOrWhiteSpace($response.Content)) { return $null }
    $parsed = $response.Content | ConvertFrom-Json
    if ($parsed -is [System.Array]) { foreach ($item in $parsed) { Write-Output $item } }
    else { Write-Output $parsed }
}

if (-not (Test-Path -LiteralPath $InputImagePath)) { throw "Input reference does not exist: $InputImagePath" }
$health = Invoke-Api '/api/health'
if (-not $health.database.online -or -not $health.comfy.online -or -not $health.ffmpeg.available) { throw 'Health check failed.' }

$allTasks = @(Invoke-Api '/api/tasks?limit=500')
$tasks = @($allTasks | Where-Object { $id = [int]$_.id; $id -ge $FirstTaskId -and $id -le $LastTaskId } | Sort-Object id)
if ($tasks.Count -ne ($LastTaskId - $FirstTaskId + 1)) { throw "Expected $($LastTaskId - $FirstTaskId + 1) tasks, found $($tasks.Count)." }
if (@($tasks | Where-Object status -notin @('Succeeded', 'Failed', 'Cancelled')).Count -gt 0) { throw 'The selected task range is not terminal.' }

$sceneRows = @(Invoke-Api "/api/scenes?projectId=$SceneProjectId")
$sceneNames = @{}
foreach ($scene in $sceneRows) { $sceneNames[[string]$scene.id] = $scene.name }
$details = @()
foreach ($row in $tasks) {
    $taskDetail = Invoke-Api "/api/tasks/$($row.id)"
    $task = $taskDetail.task
    $taskInput = $task.inputJson | ConvertFrom-Json
    $parameters = $taskInput.parameters
    $imageResult = @($taskDetail.results | Where-Object resultType -eq 'image') | Select-Object -Last 1
    $face = $null
    if ($imageResult -and (Test-Path -LiteralPath $imageResult.path)) {
        try { $face = Invoke-Api '/api/qa/face-image-check' 'POST' @{ path = $imageResult.path; referenceImagePath = $InputImagePath; portraitPreferred = $true } }
        catch { Write-Warning "task $($row.id) face check failed: $($_.Exception.Message)" }
    }
    $hash = if ($imageResult -and (Test-Path -LiteralPath $imageResult.path)) { (Get-FileHash -LiteralPath $imageResult.path -Algorithm SHA256).Hash } else { $null }
    $details += [pscustomobject][ordered]@{
        taskId = [int]$row.id
        status = $task.status
        workflowId = $task.workflowId
        workflowName = $task.workflowName
        durationMs = $task.durationMs
        vramPeakMib = $task.vramPeakMib
        sceneId = $parameters.identityMatrixSceneId
        sceneName = $sceneNames[[string]$parameters.identityMatrixSceneId]
        sceneReferencePath = $parameters.identityMatrixSceneReferencePath
        actionCode = $parameters.identityMatrixAction
        seed = $parameters.seed
        outputPath = if ($imageResult) { $imageResult.path } else { $null }
        imageHash = $hash
        technicalQualityScore = if ($imageResult) { $imageResult.qualityScore } else { $null }
        faceStatus = if ($face) { $face.status } else { $null }
        faceScore = if ($face) { $face.score } else { $null }
        faceIssues = if ($face) { @($face.issues) } else { @() }
        faceMetrics = if ($face) { $face.metrics } else { $null }
    }
}

$scores = @($details | Where-Object { $null -ne $_.faceScore } | ForEach-Object { [double]$_.faceScore })
$similarities = @($details | Where-Object { $null -ne $_.faceMetrics -and $null -ne $_.faceMetrics.referenceSimilarityProxy } | ForEach-Object { [double]$_.faceMetrics.referenceSimilarityProxy })
$hashes = @($details | Where-Object { $_.imageHash } | ForEach-Object { $_.imageHash })
$succeeded = @($details | Where-Object status -eq 'Succeeded')
$rejected = @($details | Where-Object faceStatus -eq 'Rejected')
$report = [ordered]@{
    startedAt = (Get-Date).ToString('o')
    finishedAt = (Get-Date).ToString('o')
    runTag = $runTag
    baseUrl = $BaseUrl
    inputImagePath = $InputImagePath
    workflowVersion = $WorkflowVersion
    validity = 'valid-reconstruction-from-terminal-task-range'
    identityControl = [ordered]@{
        characterAnchor = $InputImagePath
        characterReferenceInjection = $IdentityControlMode
        sceneReferenceInjection = 'not-applied-current-workflow-has-one-character-LoadImage-slot'
        lora = 'not-configured'
        ipAdapter = if ($IdentityControlMode -like '*ipadapter*') { 'IPAdapterUnifiedLoader PLUS FACE with character anchor' } else { 'not-configured-in-this-matrix' }
        controlNet = 'not-configured-in-this-baseline'
    }
    requestedActions = 10
    requestedScenes = 5
    requestedCells = $details.Count
    taskRange = [ordered]@{ first = $FirstTaskId; last = $LastTaskId }
    details = $details
    summary = [ordered]@{
        requestedCells = $details.Count
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
        allCellsSucceeded = $succeeded.Count -eq $details.Count
        noFaceRejection = $rejected.Count -eq 0
        actionCoverage = @($details | Group-Object actionCode | ForEach-Object { [pscustomobject]@{ actionCode = $_.Name; cells = $_.Count; succeeded = @($_.Group | Where-Object status -eq 'Succeeded').Count; faceRejected = @($_.Group | Where-Object faceStatus -eq 'Rejected').Count } })
        sceneCoverage = @($details | Group-Object sceneId | ForEach-Object { [pscustomobject]@{ sceneId = $_.Name; sceneName = $sceneNames[[string]$_.Name]; cells = $_.Count; succeeded = @($_.Group | Where-Object status -eq 'Succeeded').Count; faceRejected = @($_.Group | Where-Object faceStatus -eq 'Rejected').Count } })
        manualReviewRequired = $true
        gatePassed = $succeeded.Count -eq $details.Count -and $rejected.Count -eq 0
    }
    notes = @('Reconstructed after the original matrix runner was interrupted after queueing; all selected tasks are terminal.', 'CPU face proxy is a filter only; visual/manual review remains required.', 'Scene reference files were recorded as metadata and were not injected into this baseline workflow.')
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath) | Out-Null
$report | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 6
Write-Host "REPORT=$reportPath"
if (-not $report.summary.gatePassed) { exit 2 }
