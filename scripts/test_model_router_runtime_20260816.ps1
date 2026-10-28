[CmdletBinding()]
param(
    [int]$Port = 18084,
    [string]$ServerDll = 'C:\install\AI\VideoStudio\server\bin\Release\net8.0\VideoStudio.Server.dll',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\router_runtime_validation_20260816'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$baseUrl = "http://127.0.0.1:$Port"
$serverRoot = Split-Path -Parent (Split-Path -Parent $ServerDll)
$logRoot = Join-Path $OutputRoot 'sidecar'
New-Item -ItemType Directory -Force -Path $OutputRoot, $logRoot | Out-Null
$stdoutPath = Join-Path $logRoot 'stdout.log'
$stderrPath = Join-Path $logRoot 'stderr.log'
$reportPath = Join-Path $OutputRoot 'router-runtime-results.json'

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already listening; refusing to attach to an unknown process."
}
if (-not (Test-Path -LiteralPath $ServerDll)) { throw "Release server DLL missing: $ServerDll" }

$probeUsername = 'route-probe-20260816'
$probePassword = 'RouteProbe_20260816_' + ([Guid]::NewGuid().ToString('N').Substring(0, 16))
$salt = New-Object byte[] 16
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($salt)
$rng.Dispose()
$kdf = [Security.Cryptography.Rfc2898DeriveBytes]::new($probePassword, $salt, 210000, [Security.Cryptography.HashAlgorithmName]::SHA512)
$derived = $kdf.GetBytes(32)
$kdf.Dispose()
$toBase64Url = { param([byte[]]$bytes) [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_') }
$saltEncoded = & $toBase64Url $salt
$derivedEncoded = & $toBase64Url $derived
$probePasswordHash = 'pbkdf2-sha512$210000$' + $saltEncoded + '$' + $derivedEncoded
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = 'dotnet'
$psi.WorkingDirectory = $serverRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.Arguments = '"' + $ServerDll + '"'
$psi.Environment['AI_VIDEO_STUDIO_PREFER_ENV'] = '1'
$psi.Environment['AI_VIDEO_STUDIO_LISTEN_URL'] = $baseUrl
$psi.Environment['AI_VIDEO_STUDIO_ADMIN_USERNAME'] = $probeUsername
$psi.Environment['AI_VIDEO_STUDIO_ADMIN_PASSWORD'] = $probePassword
$psi.Environment['AI_VIDEO_STUDIO_ADMIN_PASSWORD_HASH'] = $probePasswordHash
$psi.Environment['AI_VIDEO_STUDIO_WORKER_ENABLED'] = '0'
$sidecar = $null
$stdoutTask = $null
$stderrTask = $null
$results = [System.Collections.Generic.List[object]]::new()

function Read-JsonResponse($response) {
    $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $parsed = $null
    try { $parsed = $body | ConvertFrom-Json } catch { $parsed = [ordered]@{ raw = $body.Substring(0, [Math]::Min(500, $body.Length)) } }
    return [pscustomobject]@{ statusCode = [int]$response.StatusCode; body = $parsed }
}

function Send-Json($client, [string]$method, [string]$path, $payload, [string]$csrfToken) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($method), "$baseUrl$path")
    $json = $payload | ConvertTo-Json -Depth 30 -Compress
    $request.Content = [System.Net.Http.StringContent]::new($json, [Text.Encoding]::UTF8, 'application/json')
    if (-not [string]::IsNullOrWhiteSpace($csrfToken)) { $request.Headers.TryAddWithoutValidation('X-CSRF-Token', $csrfToken) | Out-Null }
    $response = $client.SendAsync($request).GetAwaiter().GetResult()
    return Read-JsonResponse $response
}

try {
    $sidecar = [System.Diagnostics.Process]::Start($psi)
    $stdoutTask = $sidecar.StandardOutput.ReadToEndAsync()
    $stderrTask = $sidecar.StandardError.ReadToEndAsync()
    $health = $null
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 500
        try { $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 5 } catch { $health = $null }
    } while ($null -eq $health -and (Get-Date) -lt $deadline -and -not $sidecar.HasExited)
    if ($null -eq $health) { throw 'Router sidecar did not become healthy within 60 seconds.' }

    $cookies = [System.Net.CookieContainer]::new()
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.CookieContainer = $cookies
    $handler.UseCookies = $true
    $client = [System.Net.Http.HttpClient]::new($handler)
    try {
        $login = Send-Json $client 'POST' '/api/auth/login' ([ordered]@{username=$probeUsername;password=$probePassword}) ''
        if ($login.statusCode -ne 200 -or $null -eq $login.body.csrfToken) {
            throw "Sidecar login failed with HTTP $($login.statusCode)."
        }
        $csrfToken = [string]$login.body.csrfToken
        $cases = @(
            [ordered]@{caseId='simple-reference';payload=[ordered]@{action='blink and breathe';referenceCount=1;referenceRequired=$true};expect=[ordered]@{needSplit=$false;workflow='12_ltx_face_stable_v3'}},
            [ordered]@{caseId='complex-split';payload=[ordered]@{action='turn then sit';referenceCount=1;referenceRequired=$true};expect=[ordered]@{needSplit=$true;workflow='split-shot-gated'}},
            [ordered]@{caseId='driving-target-blocked';payload=[ordered]@{action='driving posture';referenceCount=0;referenceRequired=$false};expect=[ordered]@{needSplit=$true;workflow='wan2.2-animate'}}
        )
        foreach($case in $cases) {
            $response = Send-Json $client 'POST' '/api/motion/route' $case.payload $csrfToken
            $body = $response.body
            $workflow = if($null -ne $body){[string]$body.workflowVersion}else{''}
            $needSplit = if($null -ne $body){[bool]$body.needSplit}else{$false}
            $blockingReason = if($null -ne $body){[string]$body.blockingReason}else{''}
            $passed = $response.statusCode -eq 200 -and $workflow -eq $case.expect.workflow -and $needSplit -eq $case.expect.needSplit
            $results.Add([ordered]@{caseId=$case.caseId;request=$case.payload;httpStatus=$response.statusCode;workflowVersion=$workflow;needSplit=$needSplit;complexity=if($null -ne $body){$body.complexity}else{$null};detectedActions=if($null -ne $body){$body.detectedActions}else{@()};suggestedSubShots=if($null -ne $body){$body.suggestedSubShots}else{@()};blockingReason=$blockingReason;passed=$passed;response=$body})
        }
        $analyze = Send-Json $client 'POST' '/api/motion/analyze' ([ordered]@{action='walk to the desk, sit, then pick up a cup'}) $csrfToken
        $results.Add([ordered]@{caseId='complexity-analyze';request=[ordered]@{action='walk to the desk, sit, then pick up a cup'};httpStatus=$analyze.statusCode;passed=($analyze.statusCode -eq 200 -and [bool]$analyze.body.needSplit -and @($analyze.body.suggestedSubShots).Count -ge 2);response=$analyze.body})
    } finally { $client.Dispose(); $handler.Dispose() }

    $summary = [ordered]@{healthDatabaseOnline=[bool]$health.database.online;healthComfyOnline=[bool]$health.comfy.online;healthFfmpegAvailable=[bool]$health.ffmpeg.available;loginHttpStatus=$login.statusCode;totalCases=$results.Count;passedCases=@($results|Where-Object passed).Count;failedCases=@($results|Where-Object { -not $_.passed }).Count;runtimeSource='Release sidecar on 127.0.0.1:'+$Port;secretsRecorded=$false}
    [ordered]@{schemaVersion='2026-08-16.model-router-runtime-validation.v1';generatedAt=(Get-Date).ToString('o');baseUrl=$baseUrl;serverDll=$ServerDll;health=$health;results=@($results);summary=$summary} | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output "REPORT=$reportPath"
    if($summary.failedCases -gt 0){ exit 2 }
}
finally {
    if($sidecar -and -not $sidecar.HasExited){ $sidecar.Kill(); $sidecar.WaitForExit(10000) | Out-Null }
    if($stdoutTask){ $stdoutTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $stdoutPath -Encoding UTF8 }
    if($stderrTask){ $stderrTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $stderrPath -Encoding UTF8 }
}
