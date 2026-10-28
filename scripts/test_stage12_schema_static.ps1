[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$migration = Get-Content -LiteralPath (Join-Path $repoRoot 'database\migrations\008_stage12_production_core.sql') -Raw -Encoding UTF8
$migrator = Get-Content -LiteralPath (Join-Path $repoRoot 'server\Stage12SchemaMigrator.cs') -Raw -Encoding UTF8
$coreRepository = Get-Content -LiteralPath (Join-Path $repoRoot 'server\ProductionCoreRepository.cs') -Raw -Encoding UTF8
$database = Get-Content -LiteralPath (Join-Path $repoRoot 'server\Database.cs') -Raw -Encoding UTF8

function Assert-True { param([bool]$Condition, [string]$Message); if (-not $Condition) { throw $Message } }

foreach ($table in @('production_profiles','entity_versions','shot_plans','task_attempts','asset_manifests','artifact_publish_intents','llm_egress_audit')) {
    Assert-True $migration.Contains("CREATE TABLE IF NOT EXISTS $table") "Missing append-only stage12 table: $table"
}
Assert-True ($migration.Contains('UNIQUE KEY uq_production_profiles') -and $migration.Contains('UNIQUE KEY uq_entity_versions') -and $migration.Contains('UNIQUE KEY uq_task_attempt')) 'Version, entity, and attempt uniqueness constraints are missing.'
Assert-True ($migration.Contains('status VARCHAR(32)') -and $migration.Contains('CHECK (status IN')) 'Migration must constrain lifecycle/status values.'
Assert-True ($migration.Contains('source_kind') -and $migration.Contains('immutable_path') -and $migration.Contains('sha256')) 'Manifest must record source, immutable path, and content hash.'
Assert-True ($migrator.Contains('008_stage12_production_core') -and $coreRepository.Contains('IsSchemaReadyAsync') -and $coreRepository.Contains('Stage12SchemaMigrator.Version')) 'Stage12 migration is not registered with a read-only readiness check.'
Assert-True ($database.Contains('AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA') -and $database.Contains('if (!_settings.AutoApplySchema)')) 'Schema mutation is not explicitly opt-in.'
Assert-True (-not $migration.Contains('DROP TABLE') -and -not $migration.Contains('DELETE FROM')) 'Stage12 migration contains a destructive table/data operation.'

Write-Output 'Stage12 schema static regression passed: append-only version/attempt/manifest/audit tables, uniqueness/status constraints, and opt-in-only mutation boundary are present; no database was opened.'
