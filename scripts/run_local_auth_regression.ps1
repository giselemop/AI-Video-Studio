[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [switch]$IncludeBrowser,
    [switch]$IncludeLegacyRegression
)

$ErrorActionPreference = 'Stop'

function Get-Utf8ScriptBlock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    # Windows PowerShell 5.1 may interpret UTF-8 scripts without a BOM through
    # the active ANSI code page. Load the existing Chinese-language checks
    # explicitly as UTF-8 so this documented regression command is stable.
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $source = [System.IO.File]::ReadAllText($Path, $utf8)
    return [scriptblock]::Create($source)
}

$root = Split-Path -Parent $PSScriptRoot
$publishDirectory = Join-Path $root 'server\publish'
$serverPath = Join-Path $publishDirectory 'VideoStudio.Server.exe'
if (-not (Test-Path -LiteralPath $serverPath)) { throw "Published service not found: $serverPath" }
if (Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18080 is already in use. Stop the local VideoStudio service before isolated auth regression.' }

$testUsername = 'auth-regression'
$testPassword = 'T' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $serverPath
$startInfo.WorkingDirectory = $publishDirectory
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_ADMIN_USERNAME'] = $testUsername
$startInfo.EnvironmentVariables['AI_VIDEO_STUDIO_ADMIN_PASSWORD'] = $testPassword
$server = [System.Diagnostics.Process]::Start($startInfo)

try {
    $deadline = (Get-Date).AddSeconds(40)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $status = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/api/auth/status" -TimeoutSec 3
            if ($status.configured) { $ready = $true; break }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Auth regression service did not become ready within 40 seconds.' }

    & (Join-Path $PSScriptRoot 'test_local_auth_ascii.ps1') -BaseUrl $BaseUrl -Username $testUsername -Password $testPassword

    if ($IncludeBrowser) {
        $env:AI_VIDEO_STUDIO_TEST_USERNAME = $testUsername
        $env:AI_VIDEO_STUDIO_TEST_PASSWORD = $testPassword
        Push-Location (Join-Path $root 'web')
        try { npm run test:e2e }
        finally { Pop-Location }
    }
    if ($IncludeLegacyRegression) {
        $env:AI_VIDEO_STUDIO_TEST_USERNAME = $testUsername
        $env:AI_VIDEO_STUDIO_TEST_PASSWORD = $testPassword
        & (Get-Utf8ScriptBlock -Path (Join-Path $PSScriptRoot 'test_text_integrity.ps1')) -BaseUrl $BaseUrl -Username $testUsername -Password $testPassword
        & (Get-Utf8ScriptBlock -Path (Join-Path $PSScriptRoot 'test_task_submission_preflight.ps1')) -BaseUrl $BaseUrl -Username $testUsername -Password $testPassword
    }
}
finally {
    if ($server -and -not $server.HasExited) {
        $server.Kill()
        $server.WaitForExit(10000) | Out-Null
    }
}
