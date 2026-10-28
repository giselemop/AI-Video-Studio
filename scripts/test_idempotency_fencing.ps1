[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$database = Get-Content -LiteralPath (Join-Path $repoRoot 'server\Database.cs') -Raw -Encoding UTF8
$production = Get-Content -LiteralPath (Join-Path $repoRoot 'server\ProductionEndpoints.cs') -Raw -Encoding UTF8

Assert-True ($database.Contains('input_fingerprint') -and $database.Contains('ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)')) 'Generation task creation must persist a fingerprint and reuse the unique idempotent row.'
Assert-True ($database.Contains('IdempotencyConflictException') -and $database.Contains('CreateProductionRunAsync')) 'Production run creation must reject a reused key with a different batch identity.'
Assert-True ($production.Contains('Idempotency-Key') -and $production.Contains('ProductionRunByIdempotencyKeyAsync') -and $production.Contains('Results.Conflict')) 'The production endpoint must return a conflict instead of silently reusing a different run.'

Write-Output 'Idempotency static regression passed: task fingerprints and production-run identity conflicts are enforced.'
