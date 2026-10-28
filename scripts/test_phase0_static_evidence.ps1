[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Check {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][bool]$Passed,
        [Parameter(Mandatory)][string]$Evidence
    )

    if ($Passed) {
        Write-Output ("[PASS] {0}: {1}" -f $Name, $Evidence)
    } else {
        Write-Output ("[FAIL] {0}: {1}" -f $Name, $Evidence)
        $failures.Add($Name)
    }
}

function Read-RepoFile {
    param([Parameter(Mandatory)][string]$RelativePath)

    $path = Join-Path $repoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-Check -Name "missing file: $RelativePath" -Passed $false -Evidence 'file does not exist'
        return ''
    }

    return Get-Content -LiteralPath $path -Raw -Encoding UTF8
}

$program = Read-RepoFile 'server/Program.cs'
$database = Read-RepoFile 'server/Database.cs'
$queue = Read-RepoFile 'server/GenerationQueue.cs'
$leases = Read-RepoFile 'server/TaskLeaseRepository.cs'
$gpuGate = Read-RepoFile 'server/GpuGlobalGate.cs'
$paths = Read-RepoFile 'server/AssetPathPolicy.cs'
$envExample = Read-RepoFile 'config/local.env.example'

Add-Check 'api listener boundary' `
    ($program.Contains('UseUrls(') -and
     $program.Contains('http://127.0.0.1:18080') -and
     -not $program.Contains('http://0.0.0.0:18080') -and
     -not $program.Contains('http://+:18080')) `
    'UseUrls is loopback-only; no public listener marker was found'

Add-Check 'asset policy registration' `
    ($program.Contains('AddSingleton') -and $program.Contains('AssetPathPolicy') -and $program.Contains('TryResolveExisting')) `
    'AssetPathPolicy is registered and the media path uses controlled resolution'

Add-Check 'task idempotency' `
    ($database.Contains('idempotency_key') -and $database.Contains('ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)')) `
    'task creation includes an idempotency key and duplicate-key reuse'

Add-Check 'task lease claim' `
    ($database.Contains('ClaimTaskAsync') -and
     $database.Contains('lease_expires_at') -and
     $database.Contains("status='Pending'") -and
     $database.Contains("status='Running'")) `
    'database code includes conditional Pending-to-Running claim and lease updates'

Add-Check 'schema mutation opt-in' `
    ($database.Contains('AutoApplySchema') -and
     $database.Contains('AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA') -and
     $database.Contains('if (!_settings.AutoApplySchema)') -and
     $envExample.Contains('AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA=0')) `
    'database creation and migrations are guarded by an explicit opt-in flag defaulting to 0'

Add-Check 'queue recovery and single GPU policy' `
    ($queue.Contains('_leases.RecoverExpiredAsync') -and
     $queue.Contains('_leases.ClaimAsync') -and
     $queue.Contains('gpuConcurrency = 1') -and
     $queue.Contains('SingleReader = true') -and
     $queue.Contains('_gpuGate.AcquireAsync') -and
     $leases.Contains('lease_token=@token') -and
     $gpuGate.Contains('FileShare.None')) `
    'queue startup recovers expired leases, reports one GPU slot, and uses a cross-process file gate'

Add-Check 'asset path safety baseline' `
    ($paths -ne '' -and
     $paths.Contains('TryResolveExisting') -and
     $paths.Contains('DataRoot') -and
     $paths.Contains('ReparsePoint') -and
     $paths.Contains('current.Exists')) `
    'asset policy resolves under Data and checks existing reparse-point ancestors'

foreach ($migration in @(
    '002_production_pipeline.sql',
    '003_video_qa.sql',
    '004_reliability_references_audio.sql',
    '005_quality_optimization.sql',
    '006_repair_garbled_text.sql',
    '007_local_auth_audit.sql',
    '008_stage12_production_core.sql',
    '009_release_candidate_packages.sql'
)) {
    $migrationPath = Join-Path $repoRoot (Join-Path 'database/migrations' $migration)
    Add-Check "migration file exists: $migration" (Test-Path -LiteralPath $migrationPath -PathType Leaf) 'presence only; migration is not executed'
}

if ($failures.Count -gt 0) {
    throw ("phase0 static evidence failed: " + ($failures -join ', '))
}

Write-Output 'phase0 static evidence complete; no service, database, or file writes were performed'
