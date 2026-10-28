[CmdletBinding()]
param([switch]$RunE2E, [switch]$KeepRunning, [switch]$SkipGpuDependentPreflight)

$ErrorActionPreference = 'Stop'
$null = Add-Type -AssemblyName System.Net.Http
$baseUrl = 'http://127.0.0.1:18080'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw "Missing built server: $dll" }
if (Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18080 is already in use.' }

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Get-Utf8ScriptBlock {
    param([Parameter(Mandatory)][string]$Path)
    return [scriptblock]::Create([IO.File]::ReadAllText($Path, [Text.UTF8Encoding]::new($false)))
}

$username = 'stage3b-auth-regression'
$password = 'T' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$outFile = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-security-' + [Guid]::NewGuid().ToString('N') + '.stdout.log')
$errFile = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-security-' + [Guid]::NewGuid().ToString('N') + '.stderr.log')
$server = $null
$client = $null
$handler = $null
$csrfToken = $null
$passed = $false

function Invoke-Api {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [object]$Body = $null,
        [hashtable]$Headers = @{},
        [switch]$SkipCsrf
    )
    $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::new($Method), "$baseUrl$Path")
    try {
        foreach ($entry in $Headers.GetEnumerator()) { [void]$request.Headers.TryAddWithoutValidation($entry.Key, [string]$entry.Value) }
        if (-not $SkipCsrf -and $Method -notin @('GET', 'HEAD', 'OPTIONS') -and $script:csrfToken) { [void]$request.Headers.TryAddWithoutValidation('X-CSRF-Token', $script:csrfToken) }
        if ($null -ne $Body) {
            $request.Content = [Net.Http.StringContent]::new(($Body | ConvertTo-Json -Depth 20 -Compress), [Text.Encoding]::UTF8, 'application/json')
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = if ([string]::IsNullOrWhiteSpace($raw)) { $null } else { try { $raw | ConvertFrom-Json } catch { $raw } }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Body = $parsed; Headers = $response.Headers; ContentHeaders = $response.Content.Headers }
    }
    finally { $request.Dispose() }
}

try {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'dotnet.exe'
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = '"' + $dll + '"'
    $startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_PREFER_ENV'] = '1'
    $startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_ADMIN_USERNAME'] = $username
    $startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_ADMIN_PASSWORD'] = $password
    $startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA'] = '0'
    $startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_WORKER_ENABLED'] = '0'
    $startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_ALLOW_DATABASE_CREATE'] = '0'
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $server = [Diagnostics.Process]::Start($startInfo)

    $health = $null
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        try { $health = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/health" -TimeoutSec 3; if ($health.StatusCode -eq 200) { break } } catch { }
        $server.Refresh()
        if ($server.HasExited) { throw 'API exited before security regression became ready.' }
    }
    Assert-True ($null -ne $health -and $health.StatusCode -eq 200) 'API health did not return HTTP 200.'
    $healthJson = $health.Content | ConvertFrom-Json
    Assert-True $healthJson.database.online 'API health reports database offline.'
    Assert-True $healthJson.ffmpeg.available 'API health reports FFmpeg unavailable.'
    $listeners = @(Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction Stop)
    Assert-True ($listeners.Count -eq 1 -and $listeners[0].LocalAddress -eq '127.0.0.1') 'API is not listening only on 127.0.0.1:18080.'

    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.CookieContainer = [Net.CookieContainer]::new()
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(30)

    $authScript = Get-Utf8ScriptBlock (Join-Path $PSScriptRoot 'test_local_auth_ascii.ps1')
    & $authScript -BaseUrl $baseUrl -Username $username -Password $password
    if (-not $SkipGpuDependentPreflight) {
        $preflightScript = Get-Utf8ScriptBlock (Join-Path $PSScriptRoot 'test_task_submission_preflight.ps1')
        & $preflightScript -BaseUrl $baseUrl -Username $username -Password $password
    }

    $login = Invoke-Api 'POST' '/api/auth/login' @{ username = $username; password = $password } -SkipCsrf
    Assert-True ($login.StatusCode -eq 200 -and $login.Body.csrfToken) 'Security harness login failed.'
    $script:csrfToken = $login.Body.csrfToken

    $schema = Invoke-Api 'GET' '/api/production/schema'
    Assert-True ($schema.StatusCode -eq 200 -and $schema.Body.ready) 'Formal 008 schema endpoint is not ready.'
    $system = Invoke-Api 'GET' '/api/system/settings'
    Assert-True ($system.StatusCode -eq 200 -and $system.Body.database.user -eq 'ai_video_studio_app') 'Runtime settings expose an unexpected database user.'
    Assert-True ($system.Body.database.user -ne 'root') 'Runtime settings still use root as the application account.'

    if ($SkipGpuDependentPreflight) {
        $blockedPreflight = Invoke-Api 'POST' '/api/tasks/preflight' @{ taskType = 'Image'; resourceClass = 'GPU'; parameters = @{ positive = 'stage3b offline fail-closed probe' } }
        Assert-True ($blockedPreflight.StatusCode -eq 200 -and -not $blockedPreflight.Body.passed) 'GPU preflight unexpectedly passed while ComfyUI is offline.'
        $blockedSubmit = Invoke-Api 'POST' '/api/tasks' @{ projectId = 999999999; taskType = 'Image'; resourceClass = 'GPU'; parameters = @{ positive = 'stage3b invalid project probe' } }
        Assert-True ($blockedSubmit.StatusCode -eq 422) 'Invalid GPU submission was not rejected before queueing.'
        Write-Output 'PASS GPU task preflight fails closed while ComfyUI is offline; invalid submission rejected before queueing'
    }

    $cleanup = Invoke-Api 'GET' '/api/maintenance/cache-cleanup/preview'
    Assert-True ($cleanup.StatusCode -eq 200) 'Cache cleanup dry-run endpoint did not return 200.'
    Write-Output 'PASS cache-cleanup preview is read-only endpoint response'

    $corsAllowed = Invoke-Api 'OPTIONS' '/api/projects' $null @{ Origin = 'http://127.0.0.1:18081'; 'Access-Control-Request-Method' = 'GET' } -SkipCsrf
    Assert-True ($corsAllowed.Headers.Contains('Access-Control-Allow-Origin') -and $corsAllowed.Headers.GetValues('Access-Control-Allow-Origin') -contains 'http://127.0.0.1:18081') 'Allowed loopback CORS origin was not returned exactly.'
    $corsDenied = Invoke-Api 'OPTIONS' '/api/projects' $null @{ Origin = 'http://not-local.example'; 'Access-Control-Request-Method' = 'GET' } -SkipCsrf
    Assert-True (-not $corsDenied.Headers.Contains('Access-Control-Allow-Origin')) 'Unlisted CORS origin received an allow header.'
    Write-Output 'PASS exact CORS allowlist and unlisted-origin rejection'

    $pathCandidates = @('..\config\appsettings.json', '\\server\share\asset.mp4', '\\?\C:\install\AI\Data\asset.mp4', 'C:relative.mp4', 'Images\frame.png:secret')
    foreach ($candidate in $pathCandidates) {
        $encoded = [Uri]::EscapeDataString($candidate)
        $response = Invoke-Api 'GET' "/api/media?assetPath=$encoded"
        Assert-True ($response.StatusCode -eq 404) "Unsafe media path was not rejected: $candidate ($($response.StatusCode))"
    }
    Write-Output ("PASS runtime media path negatives rejected={0}" -f $pathCandidates.Count)

    $projects = @(Invoke-Api 'GET' '/api/projects').Body
    $assetByProject = @{}
    foreach ($project in $projects) {
        $assets = @(Invoke-Api 'GET' "/api/assets?projectId=$($project.id)").Body
        $asset = $assets | Where-Object { $_.id -gt 0 } | Select-Object -First 1
        if ($null -ne $asset) { $assetByProject[[string]$project.id] = $asset }
    }
    $pairs = @($assetByProject.GetEnumerator())
    if ($pairs.Count -ge 2) {
        $first = $pairs[0]; $second = $pairs[1]
        $cross = Invoke-Api 'GET' "/api/production/projects/$($first.Key)/assets/$($second.Value.id)"
        Assert-True ($cross.StatusCode -in @(400, 404)) 'Cross-project Asset ID was accepted.'
        $wrongPurpose = Invoke-Api 'GET' "/api/production/projects/$($first.Key)/assets/$($first.Value.id)?purpose=NotARealPurpose"
        Assert-True ($wrongPurpose.StatusCode -eq 400) 'Invalid Asset purpose was accepted.'
        Write-Output 'PASS cross-project Asset ID and invalid purpose rejected'
    }
    else {
        Write-Output 'NOT RUN cross-project Asset ID runtime pair: formal API returned fewer than two project asset groups'
    }

    $shot = $null
    foreach ($project in $projects) {
        $episodes = @(Invoke-Api 'GET' "/api/projects/$($project.id)/episodes").Body
        foreach ($episode in $episodes) {
            $shots = @(Invoke-Api 'GET' "/api/episodes/$($episode.id)/shots").Body
            if ($shots.Count -gt 0) { $shot = $shots[0]; break }
        }
        if ($null -ne $shot) { break }
    }
    Assert-True ($null -ne $shot) 'No existing shot available for terminal-state bypass regression.'
    $terminal = Invoke-Api 'PUT' "/api/shots/$($shot.id)" @{ shotNumber = $shot.shotNumber; title = $shot.title; status = 'Approved' }
    Assert-True ($terminal.StatusCode -eq 409) 'Ordinary shot update bypassed the formal terminal-state guard.'
    Write-Output 'PASS ordinary shot API cannot set formal terminal status'

    $badEndpoint = Invoke-Api 'PUT' '/api/system/settings/llm' @{ provider = 'OpenAICompatible'; baseUrl = 'https://example.invalid'; model = 'stage3b-no-egress'; temperature = 0.2; maxTokens = 3000 }
    Assert-True ($badEndpoint.StatusCode -eq 400) 'Non-allowlisted LLM host was accepted.'
    $httpPublic = Invoke-Api 'PUT' '/api/system/settings/llm' @{ provider = 'OpenAICompatible'; baseUrl = 'http://api.openai.com'; model = 'stage3b-no-egress'; temperature = 0.2; maxTokens = 3000 }
    Assert-True ($httpPublic.StatusCode -eq 400) 'Non-HTTPS public LLM endpoint was accepted.'
    $oversized = Invoke-Api 'POST' '/api/llm/preview' @{ systemPrompt = ('x' * (128 * 1024 + 1)); userPrompt = 'no-egress'; maxTokens = 256 }
    Assert-True ($oversized.StatusCode -eq 400) 'Oversized LLM prompt was not rejected before egress.'
    Write-Output 'PASS LLM non-allowlist, non-HTTPS and prompt-size negatives; no third-party request sent'

    $audit = Invoke-Api 'GET' '/api/auth/audit?limit=100'
    $auditText = $audit.Body | ConvertTo-Json -Depth 20 -Compress
    Assert-True (-not $auditText.Contains($password)) 'Auth audit response leaked the temporary password.'
    Assert-True (-not $auditText.Contains('stage3b-no-egress')) 'Audit response leaked rejected LLM configuration content.'
    Write-Output 'PASS audit response contains no temporary password or rejected LLM secret'

    if ($RunE2E) {
        $env:AI_VIDEO_STUDIO_TEST_USERNAME = $username
        $env:AI_VIDEO_STUDIO_TEST_PASSWORD = $password
        Push-Location (Join-Path $repoRoot 'web')
        try {
            & npm.cmd run test:episode-output
            if ($LASTEXITCODE -ne 0) { throw "frontend episode-output E2E exited with code $LASTEXITCODE" }
        }
        finally { Pop-Location }
        Write-Output 'PASS frontend episode-output Playwright E2E against real API'
    }

    $passed = $true
    if ($KeepRunning) { $server = $null }
}
finally {
    Remove-Item Env:AI_VIDEO_STUDIO_TEST_USERNAME,Env:AI_VIDEO_STUDIO_TEST_PASSWORD -ErrorAction SilentlyContinue
    if ($null -ne $client) { $client.Dispose() }
    if ($null -ne $handler) { $handler.Dispose() }
    if ($null -ne $server) {
        try { $server.Refresh() } catch { }
        try { if (-not $server.HasExited) { $server.Kill(); $server.WaitForExit(10000) | Out-Null } } catch { }
    }
    if (-not $passed -and (Test-Path -LiteralPath $errFile)) {
        Write-Output 'API stderr tail:'
        Get-Content -LiteralPath $errFile -Tail 30
    }
}
