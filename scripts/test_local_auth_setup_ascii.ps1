[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080'
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
$httpClientAssembly = [System.IO.Path]::Combine([System.Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory(), 'System.Net.Http.dll')
Add-Type -Path $httpClientAssembly
$root = Split-Path -Parent $PSScriptRoot
$publishDirectory = Join-Path $root 'server\publish'
$serverPath = Join-Path $publishDirectory 'VideoStudio.Server.exe'
if (-not (Test-Path -LiteralPath $serverPath)) { throw "Published service not found: $serverPath" }
if (Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18080 is already in use. Stop the local VideoStudio service before isolated setup regression.' }

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Read-LocalEnvironment {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }
    foreach ($raw in [System.IO.File]::ReadAllLines($Path, [System.Text.UTF8Encoding]::new($false))) {
        $line = $raw.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith('#')) { continue }
        $separator = $line.IndexOf('=')
        if ($separator -le 0) { continue }
        $values[$line.Substring(0, $separator).Trim()] = $line.Substring($separator + 1).Trim().Trim('"').Trim("'")
    }
    return $values
}

function New-Client {
    $jar = [System.Net.CookieContainer]::new()
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.CookieContainer = $jar
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(30)
    return [pscustomobject]@{ Jar = $jar; Handler = $handler; Client = $client }
}

function Invoke-Api {
    param(
        [object]$Api,
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
        $response = $Api.Client.SendAsync($request).GetAwaiter().GetResult()
        $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = if ([string]::IsNullOrWhiteSpace($raw)) { $null } else { $raw | ConvertFrom-Json }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Body = $parsed }
    }
    finally { $request.Dispose() }
}

function Start-IsolatedServer {
    param([string]$TemporaryRoot, [hashtable]$SourceEnvironment)
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $serverPath
    $startInfo.WorkingDirectory = $publishDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables['VIDEO_STUDIO_ROOT'] = $TemporaryRoot
    foreach ($key in @('AI_VIDEO_STUDIO_DB_HOST', 'AI_VIDEO_STUDIO_DB_PORT', 'AI_VIDEO_STUDIO_DB_NAME', 'AI_VIDEO_STUDIO_DB_USER', 'AI_VIDEO_STUDIO_DB_PASSWORD')) {
        if ($SourceEnvironment.ContainsKey($key)) { $startInfo.EnvironmentVariables[$key] = $SourceEnvironment[$key] }
    }
    return [System.Diagnostics.Process]::Start($startInfo)
}

function Wait-ForService {
    param([bool]$Configured)
    $deadline = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $deadline) {
        try {
            $status = Invoke-RestMethod -Uri "$BaseUrl/api/auth/status" -TimeoutSec 3
            if ([bool]$status.configured -eq $Configured) { return $status }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    throw 'Isolated setup regression service did not reach the expected state within 40 seconds.'
}

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('video-studio-auth-setup-' + [guid]::NewGuid().ToString('N'))
$sourceEnvironment = Read-LocalEnvironment (Join-Path $root 'config\local.env')
$server = $null
$api = $null
$username = 'setup-regression'
$password = 'T' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')

try {
    [System.IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
    $server = Start-IsolatedServer -TemporaryRoot $temporaryRoot -SourceEnvironment $sourceEnvironment
    $status = Wait-ForService $false
    Assert-True (-not $status.configured -and $status.setupAllowed) 'A fresh isolated root must expose local setup and no configured admin.'

    $api = New-Client
    $beforeSetup = Invoke-Api $api 'GET' '/api/projects'
    Assert-True ($beforeSetup.StatusCode -eq 503) "Protected API before setup must return 503; got $($beforeSetup.StatusCode)."

    $invalidSetup = Invoke-Api $api 'POST' '/api/auth/setup' @{ username = $username; password = 'short' }
    Assert-True ($invalidSetup.StatusCode -eq 400) "Short setup password must return 400; got $($invalidSetup.StatusCode)."

    $setup = Invoke-Api $api 'POST' '/api/auth/setup' @{ username = $username; password = $password }
    Assert-True ($setup.StatusCode -eq 200 -and $setup.Body.csrfToken) "Valid setup must create an authenticated session; got $($setup.StatusCode)."
    $envPath = Join-Path $temporaryRoot 'config\local.env'
    $saved = [System.IO.File]::ReadAllText($envPath, [System.Text.UTF8Encoding]::new($false))
    Assert-True ($saved -match 'AI_VIDEO_STUDIO_ADMIN_USERNAME=setup-regression') 'Setup did not persist the administrator name.'
    Assert-True ($saved -match 'AI_VIDEO_STUDIO_ADMIN_PASSWORD_HASH=pbkdf2-sha512\$') 'Setup did not persist a PBKDF2 password hash.'
    Assert-True (-not $saved.Contains($password)) 'The setup password was persisted in plaintext.'
    Assert-True (-not ($saved -match '(?m)^AI_VIDEO_STUDIO_ADMIN_PASSWORD=')) 'A plaintext administrator password entry was persisted.'

    $projects = Invoke-Api $api 'GET' '/api/projects'
    Assert-True ($projects.StatusCode -eq 200) "Authenticated session created during setup must access protected API; got $($projects.StatusCode)."
    $secondSetup = Invoke-Api $api 'POST' '/api/auth/setup' @{ username = $username; password = $password }
    Assert-True ($secondSetup.StatusCode -eq 409) "Setup must be one-time after configuration; got $($secondSetup.StatusCode)."

    $server.Kill()
    $server.WaitForExit(10000) | Out-Null
    $server = Start-IsolatedServer -TemporaryRoot $temporaryRoot -SourceEnvironment $sourceEnvironment
    $persistedStatus = Wait-ForService $true
    Assert-True (-not $persistedStatus.authenticated) 'A restarted browser client must not inherit an authenticated session.'

    $restartClient = New-Client
    try {
        $login = Invoke-Api $restartClient 'POST' '/api/auth/login' @{ username = $username; password = $password }
        Assert-True ($login.StatusCode -eq 200 -and $login.Body.csrfToken) "Persisted PBKDF2 account must be able to log in after restart; got $($login.StatusCode)."
    }
    finally {
        $restartClient.Client.Dispose()
        $restartClient.Handler.Dispose()
    }

    Write-Output 'Local setup regression passed: first-run setup, PBKDF2 persistence, duplicate setup rejection, and restart login all behaved as expected.'
}
finally {
    if ($api) {
        $api.Client.Dispose()
        $api.Handler.Dispose()
    }
    if ($server -and -not $server.HasExited) {
        $server.Kill()
        $server.WaitForExit(10000) | Out-Null
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
