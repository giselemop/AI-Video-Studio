[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [string]$Username = $env:AI_VIDEO_STUDIO_TEST_USERNAME,
    [string]$Password = $env:AI_VIDEO_STUDIO_TEST_PASSWORD
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($Password)) { throw '需要通过 -Username/-Password 或 AI_VIDEO_STUDIO_TEST_USERNAME/AI_VIDEO_STUDIO_TEST_PASSWORD 提供本机管理员测试凭据。' }

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$cookieJar = [System.Net.CookieContainer]::new()
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.CookieContainer = $cookieJar
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)

function Invoke-Api {
    param([string]$Method, [string]$Path, [object]$Body = $null, [bool]$UseCsrf = $false)
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path")
    try {
        if ($UseCsrf -and $script:csrfToken) { [void]$request.Headers.TryAddWithoutValidation('X-CSRF-Token', $script:csrfToken) }
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 16 -Compress
            $request.Content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, 'application/json')
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = if ([string]::IsNullOrWhiteSpace($raw)) { $null } else { $raw | ConvertFrom-Json }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Body = $parsed }
    } finally { $request.Dispose() }
}

function Invoke-GetJson { param([string]$Path) $response = Invoke-Api 'GET' $Path; if ($response.StatusCode -ne 200) { throw "GET $Path failed with HTTP $($response.StatusCode): $($response.Body.error)" }; return $response.Body }
function Invoke-PostJson { param([string]$Path, [object]$Body) Invoke-Api 'POST' $Path $Body $true }

try {
    $login = Invoke-Api 'POST' '/api/auth/login' @{ username = $Username; password = $Password }
    Assert-True ($login.StatusCode -eq 200 -and $login.Body.csrfToken) "本机管理员登录失败：HTTP $($login.StatusCode)。"
    $script:csrfToken = $login.Body.csrfToken

$workflows = @(Invoke-GetJson '/api/workflows' | ForEach-Object { $_ })
$controlNet = $workflows | Where-Object { $_.name -match 'controlnet|openpose' -or $_.path -match 'controlnet|openpose' } | Select-Object -First 1
$imageWorkflow = $workflows | Where-Object { $_.workflowType -match 'Image|TextToImage' } | Select-Object -First 1
Assert-True ($null -ne $controlNet) 'No registered ControlNet workflow was found for the preflight regression.'
Assert-True ($null -ne $imageWorkflow) 'No registered image workflow was found for the preflight regression.'

$controlTask = @{
    taskType = 'Keyframe'
    workflowId = $controlNet.id
    resourceClass = 'GPU'
    parameters = @{ positive = 'preflight regression'; seed = 1001 }
}
$preview = Invoke-PostJson '/api/tasks/preflight' $controlTask
Assert-True ($preview.StatusCode -eq 200) "Task preflight should return HTTP 200, got $($preview.StatusCode)."
Assert-True (-not $preview.Body.passed) 'ControlNet task without a pose input was incorrectly marked ready.'

$blockedControl = Invoke-PostJson '/api/tasks' $controlTask
Assert-True ($blockedControl.StatusCode -eq 422) "ControlNet task should be rejected before queueing, got HTTP $($blockedControl.StatusCode)."

$loraTask = @{
    taskType = 'Image'
    workflowId = $imageWorkflow.id
    resourceClass = 'GPU'
    parameters = @{
        positive = 'preflight regression'
        loraNames = @('missing-preflight-regression.safetensors')
    }
}
$blockedLora = Invoke-PostJson '/api/tasks' $loraTask
Assert-True ($blockedLora.StatusCode -eq 422) "Missing LoRA task should be rejected before queueing, got HTTP $($blockedLora.StatusCode)."

$invalidEntity = Invoke-PostJson '/api/tasks' @{
    projectId = 999999999
    taskType = 'Image'
    workflowId = $imageWorkflow.id
    resourceClass = 'GPU'
    parameters = @{ positive = 'preflight regression' }
}
Assert-True ($invalidEntity.StatusCode -eq 422) "Task with a missing project should be rejected before queueing, got HTTP $($invalidEntity.StatusCode)."

$projects = @(Invoke-GetJson '/api/projects' | ForEach-Object { $_ })
$duplicateProbe = $null
foreach ($project in $projects) {
    $episodes = @(Invoke-GetJson "/api/projects/$($project.id)/episodes" | ForEach-Object { $_ })
    foreach ($episode in $episodes) {
        $shot = @(Invoke-GetJson "/api/episodes/$($episode.id)/shots" | ForEach-Object { $_ } | Select-Object -First 1)
        if ($shot.Count -gt 0) {
            $duplicateProbe = [pscustomobject]@{ Project = $project; Episode = $episode; Shot = $shot[0] }
            break
        }
    }
    if ($null -ne $duplicateProbe) { break }
}
Assert-True ($null -ne $duplicateProbe) 'No existing shot was found for duplicate-number regression.'

$validImage = Invoke-PostJson '/api/tasks/preflight' @{
    projectId = $duplicateProbe.Project.id
    episodeId = $duplicateProbe.Episode.id
    shotId = $duplicateProbe.Shot.id
    taskType = 'Image'
    resourceClass = 'GPU'
    parameters = @{ positive = 'preflight regression'; seed = 1002 }
}
Assert-True ($validImage.StatusCode -eq 200 -and $validImage.Body.passed) 'A normal keyframe image task without a video workflow should pass preflight.'

$failedGeneric = @(Invoke-GetJson '/api/tasks?limit=500' | ForEach-Object { $_ } |
    Where-Object { $_.status -eq 'Failed' -and $_.taskType -match '^(Image|Keyframe|ImageToVideo|Video)$' } |
    Select-Object -First 1)
Assert-True ($failedGeneric.Count -eq 1) 'No failed generic task fixture was found for retry/rerun preflight regression.'
$failedTaskId = $failedGeneric[0].id
$blockedRetry = Invoke-PostJson "/api/tasks/$failedTaskId/retry" @{}
Assert-True ($blockedRetry.StatusCode -eq 422) "Invalid historical retry should be rejected before requeueing, got HTTP $($blockedRetry.StatusCode)."
$blockedRerun = Invoke-PostJson "/api/tasks/$failedTaskId/rerun" @{}
Assert-True ($blockedRerun.StatusCode -eq 422) "Invalid historical rerun should be rejected before task creation, got HTTP $($blockedRerun.StatusCode)."

$duplicateShot = Invoke-PostJson '/api/shots' @{
    projectId = $duplicateProbe.Project.id
    episodeId = $duplicateProbe.Episode.id
    shotNumber = $duplicateProbe.Shot.shotNumber
    title = 'duplicate-number-preflight-regression'
}
Assert-True ($duplicateShot.StatusCode -eq 409) "Duplicate shot number should return HTTP 409, got $($duplicateShot.StatusCode)."

$invalidVoice = Invoke-PostJson '/api/audio/tts' @{
    text = 'audio preflight regression'
    voiceId = 'missing-preflight-voice'
    speed = 1
    pitch = 0
}
Assert-True ($invalidVoice.StatusCode -eq 422) "Unknown TTS voice should be rejected before queueing, got HTTP $($invalidVoice.StatusCode)."

$validVoice = Invoke-PostJson '/api/audio/preflight' @{
    text = 'audio preflight regression'
    voiceId = ''
}
Assert-True ($validVoice.StatusCode -eq 200 -and $validVoice.Body.passed) 'The default Chinese TTS preflight did not produce a decodable audio sample.'

Write-Output 'Task submission preflight regression passed: invalid submission, retry and rerun paths were rejected before queueing, duplicate shot numbers return 409, and default Chinese TTS preflight passed.'
}
finally {
    try { if ($script:csrfToken) { Invoke-Api 'POST' '/api/auth/logout' $null $true | Out-Null } } catch { }
    $client.Dispose()
    $handler.Dispose()
}
