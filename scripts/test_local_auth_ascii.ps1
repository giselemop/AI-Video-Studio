[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [Parameter(Mandatory)] [string]$Username,
    [Parameter(Mandatory)] [string]$Password
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
Add-Type -AssemblyName System.Net.Http

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
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [hashtable]$Headers = @{}
    )

    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path")
    try {
        foreach ($entry in $Headers.GetEnumerator()) { [void]$request.Headers.TryAddWithoutValidation($entry.Key, [string]$entry.Value) }
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 16 -Compress
            $request.Content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, 'application/json')
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = if ([string]::IsNullOrWhiteSpace($raw)) { $null } else { $raw | ConvertFrom-Json }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Body = $parsed }
    }
    finally {
        $request.Dispose()
    }
}

try {
    $status = Invoke-Api 'GET' '/api/auth/status'
    Assert-True ($status.StatusCode -eq 200 -and $status.Body.configured) 'Test service did not load the temporary administrator configuration.'
    Assert-True (-not $status.Body.authenticated) 'A new client must not receive an authenticated session.'

    $anonymous = Invoke-Api 'GET' '/api/projects'
    Assert-True ($anonymous.StatusCode -eq 401) "Anonymous project read must return 401; got $($anonymous.StatusCode)."

    $wrongPassword = Invoke-Api 'POST' '/api/auth/login' @{ username = $Username; password = "$Password-wrong" }
    Assert-True ($wrongPassword.StatusCode -eq 401) "Wrong password must return 401; got $($wrongPassword.StatusCode)."

    $login = Invoke-Api 'POST' '/api/auth/login' @{ username = $Username; password = $Password }
    Assert-True ($login.StatusCode -eq 200 -and $login.Body.csrfToken) "Correct login must return a session and CSRF token; got $($login.StatusCode)."
    Assert-True (($cookieJar.GetCookies([Uri]$BaseUrl) | Where-Object Name -eq 'ai_video_studio_session').Count -eq 1) 'Login did not set the session cookie.'
    Assert-True (($cookieJar.GetCookies([Uri]$BaseUrl) | Where-Object Name -eq 'ai_video_studio_csrf').Count -eq 1) 'Login did not set the CSRF cookie.'

    $projects = Invoke-Api 'GET' '/api/projects'
    Assert-True ($projects.StatusCode -eq 200) "Authenticated project read must return 200; got $($projects.StatusCode)."

    $probeBody = @{ taskType = 'Image'; resourceClass = 'GPU'; parameters = @{ positive = 'local auth regression' } }
    $missingCsrf = Invoke-Api 'POST' '/api/tasks/preflight' $probeBody
    Assert-True ($missingCsrf.StatusCode -eq 403) "Unsafe request without CSRF must return 403; got $($missingCsrf.StatusCode)."

    $badOrigin = Invoke-Api 'POST' '/api/tasks/preflight' $probeBody @{ 'Origin' = 'http://not-local.example'; 'X-CSRF-Token' = $login.Body.csrfToken }
    Assert-True ($badOrigin.StatusCode -eq 403) "Non-local origin must return 403; got $($badOrigin.StatusCode)."

    $preflight = Invoke-Api 'POST' '/api/tasks/preflight' $probeBody @{ 'X-CSRF-Token' = $login.Body.csrfToken }
    Assert-True ($preflight.StatusCode -eq 200) "Valid CSRF preflight must return 200; got $($preflight.StatusCode)."

    $audit = Invoke-Api 'GET' '/api/auth/audit?limit=50'
    Assert-True ($audit.StatusCode -eq 200) "Authenticated audit read must return 200; got $($audit.StatusCode)."
    Assert-True (@($audit.Body | Where-Object { $_.action -eq 'auth.login' -and $_.outcome -eq 'Succeeded' -and $_.actor -eq $Username }).Count -ge 1) 'The audit trail lacks this successful login.'

    $logout = Invoke-Api 'POST' '/api/auth/logout' $null @{ 'X-CSRF-Token' = $login.Body.csrfToken }
    Assert-True ($logout.StatusCode -eq 200) "Logout must return 200; got $($logout.StatusCode)."
    $afterLogout = Invoke-Api 'GET' '/api/projects'
    Assert-True ($afterLogout.StatusCode -eq 401) "Project read after logout must return 401; got $($afterLogout.StatusCode)."

    Write-Output 'Local auth regression passed: anonymous access, invalid credentials, CSRF, origin validation, audit records, and logout invalidation all behaved as expected.'
}
finally {
    $client.Dispose()
    $handler.Dispose()
}
