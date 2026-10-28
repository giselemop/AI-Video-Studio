[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Read-Source {
    param([string]$RelativePath)
    $path = Join-Path $repoRoot $RelativePath
    Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "Missing source file: $RelativePath"
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8
}

$program = Read-Source 'server/Program.cs'
$auth = Read-Source 'server/LocalAuthService.cs'
$database = Read-Source 'server/Database.cs'
$paths = Read-Source 'server/AssetPathPolicy.cs'
$preflight = Read-Source 'server/TaskSubmissionPreflightService.cs'
$queue = Read-Source 'server/GenerationQueue.cs'
$backup = Read-Source 'scripts/backup.ps1'
$qaEndpoints = Read-Source 'server/QaEndpoints.cs'

Assert-True ($program.Contains('UseUrls(') -and $program.Contains('http://127.0.0.1:18080') -and -not $program.Contains('http://0.0.0.0:18080') -and -not $program.Contains('http://+:18080') -and $program.Contains('WithOrigins(')) 'API listener and CORS must stay explicit and local-only by default.'
Assert-True ($program.Contains('AuthenticateAsync(context, requiresCsrf') -and $program.Contains('AuditRequestAsync')) 'API writes must pass through authentication, CSRF, and audit middleware.'
Assert-True ($auth.Contains('SameSite = SameSiteMode.Strict') -and $auth.Contains('HttpOnly = true') -and $auth.Contains('X-CSRF-Token')) 'Session cookies and CSRF token handling must be hardened.'
Assert-True ($database.Contains('if (!_settings.AutoApplySchema)') -and $database.Contains('no schema-creation or migration statements will be executed')) 'Startup schema mutation must remain explicit opt-in.'
Assert-True ($database.Contains('NormalizeLoopbackHttpUrl') -and $program.Contains('AllowAutoRedirect = false')) 'ComfyUI configuration and HTTP client must stay loopback-only and redirect-free.'
Assert-True ($paths.Contains('TryResolveExistingWorkflow') -and $preflight.Contains('TryResolveExistingWorkflow') -and $queue.Contains('TryResolveExistingWorkflow')) 'Workflow files must resolve under the controlled Workflows root before loading.'
Assert-True ($backup.Contains("'SHOW DATABASES;'") -and $backup.Contains('mysqldump produced no usable output') -and $backup.Contains('Get-FileHash') -and $backup.Contains('backup-manifest.txt')) 'Backups must avoid interpolated database-name SQL and record a non-empty dump hash.'
Assert-True ($qaEndpoints.Contains('OverrideHardFailure') -and $qaEndpoints.Contains('!input.OverrideHardFailure || string.IsNullOrWhiteSpace(input.Note)') -and $qaEndpoints.Contains('episode.Text("qaStatus")') -and $qaEndpoints.Contains('shotForReview?.Text("qaStatus")')) 'Manual override of automatic shot and Episode QA rejection must be explicit and documented.'

Write-Output 'P0 security static regression passed: loopback/CORS, auth-CSRF-audit, schema opt-in, and backup integrity guards are present.'
