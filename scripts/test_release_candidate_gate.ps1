[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$migration = Get-Content -LiteralPath (Join-Path $repoRoot 'database\migrations\009_release_candidate_packages.sql') -Raw -Encoding UTF8
$eligibility = Get-Content -LiteralPath (Join-Path $repoRoot 'server\ReleaseEligibility.cs') -Raw -Encoding UTF8
$repository = Get-Content -LiteralPath (Join-Path $repoRoot 'server\ReleaseCandidateRepository.cs') -Raw -Encoding UTF8
$qa = Get-Content -LiteralPath (Join-Path $repoRoot 'server\QaEndpoints.cs') -Raw -Encoding UTF8
$queue = Get-Content -LiteralPath (Join-Path $repoRoot 'server\GenerationQueue.cs') -Raw -Encoding UTF8
$retryPolicy = Get-Content -LiteralPath (Join-Path $repoRoot 'server\QaRetryPolicy.cs') -Raw -Encoding UTF8
$contracts = Get-Content -LiteralPath (Join-Path $repoRoot 'server\WorkflowContracts.cs') -Raw -Encoding UTF8
$program = Get-Content -LiteralPath (Join-Path $repoRoot 'server\Program.cs') -Raw -Encoding UTF8

function Assert-True { param([bool]$Condition, [string]$Message); if (-not $Condition) { throw $Message } }

Assert-True ($migration.Contains('CREATE TABLE IF NOT EXISTS release_candidate_packages') -and $migration.Contains('UNIQUE KEY uq_release_candidate_episode_version')) 'Release candidate packages must be append-only per episode/version.'
Assert-True ($eligibility.Contains('TechnicalStatus') -and $eligibility.Contains('ContentStatus') -and $eligibility.Contains('LicenseEvidence') -and $eligibility.Contains('AiDisclosure') -and $eligibility.Contains('TrackedAssetAsync')) 'Eligibility must keep technical, content, license, AI disclosure, and stable asset evidence separate.'
Assert-True ($eligibility.Contains('blocking.Count == 0 ? "Ready" : "Blocked"') -and $eligibility.Contains('AiDisclosureRecorded') -and $eligibility.Contains('SourceSnapshotMatches') -and $eligibility.Contains('ValidateRuntimeTrace') -and $eligibility.Contains('稳定 assetId/manifestId/version')) 'Candidate readiness must require release evidence, a self-consistent source snapshot, stable asset bindings, and runtime trace validation.'
Assert-True ($repository.Contains('release_candidate_packages') -and $repository.Contains('MAX(version)') -and $repository.Contains('FindReadyBySourceHashAsync') -and $repository.Contains('ExpireReadyForDifferentSourceAsync') -and $repository.Contains('IdempotencyConflictException') -and $repository.Contains('1062')) 'Candidate versions must use idempotency, stale-source expiry, duplicate-ready suppression, and duplicate-key conflict retry.'
$database = Get-Content -LiteralPath (Join-Path $repoRoot 'server\Database.cs') -Raw -Encoding UTF8
$characterEndpoint = Get-Content -LiteralPath (Join-Path $repoRoot 'server\CharacterIdentityEndpoints.cs') -Raw -Encoding UTF8
Assert-True ($database.Contains('character_reference_reviews') -and $database.Contains('characterReferenceReviewRequired') -and $database.Contains('InTransactionAsync')) 'Character reference decisions must append history transactionally and invalidate related QA results when the approved asset or decision changes.'
Assert-True ($characterEndpoint.Contains('principal.Username') -and $characterEndpoint.Contains('TryResolveExisting(reference.Text("path")')) 'Character review must use the logged-in reviewer and reject uncontrolled reference assets.'
Assert-True ($qa.Contains('candidateId') -and $qa.Contains('ValidateCandidateForExportAsync') -and $qa.Contains('MarkExpiredAsync') -and -not $qa.Contains('readyCandidate')) 'Episode export must require an explicit candidateId and expire stale candidates instead of selecting any Ready row.'
Assert-True ($queue.Contains('ReleaseCandidatePolicy.VersionAndSnapshotMatch') -and $queue.Contains('postPublishCandidate') -and $queue.Contains('EnsureCandidateArtifactHashAsync')) 'Queue execution must re-check candidate version and artifact hashes at start and after publication.'
Assert-True ($retryPolicy.Contains('inherit-original-route') -and $retryPolicy.Contains('alternative-route-explicit-only')) 'QA retry policy must make route alternatives explicit.'
Assert-True ($queue.Contains('retrySourceSnapshot') -and $queue.Contains('RETRY_SOURCE_DRIFT') -and $queue.Contains('original.Long("id")') -and $queue.Contains('qa-retry:') -and $queue.Contains('TaskType = originalTaskType') -and $queue.Contains('original.Text("status") is "Pending" or "Running"')) 'QA retry must carry the original source snapshot, parent task binding, and idempotency key, then reject source drift.'
Assert-True ($queue.Contains('characterReferences') -and $queue.Contains('assetVersion = asset?.AssetVersion') -and $queue.Contains('RETRY_ACTION_TRACE_MISSING')) 'Generation traces must retain character review versions, formal asset versions, and the original action target.'
Assert-True ($contracts.Contains('ValidateCurrentModelFingerprints') -and $contracts.Contains('forceRefresh: true') -and $contracts.Contains('ModelFingerprintCache')) 'Model admission must force-refresh weight hashes at execution/release boundaries and cover the same-size/same-mtime replacement case.'
Assert-True ($database.Contains('ReleaseCandidateSchemaMigrator') -and $program.Contains('/api/workflow-contracts')) 'Runtime must register the release migration and expose workflow contract status.'

$harness = Join-Path $repoRoot 'tests\VideoStudio.QualityHarness\bin\Debug\net8.0\VideoStudio.QualityHarness.dll'
Assert-True (Test-Path -LiteralPath $harness -PathType Leaf) 'Build the quality harness before running the behavioral release-candidate regression.'
& dotnet.exe $harness --self-test
if ($LASTEXITCODE -ne 0) { throw "Release candidate behavioral regression failed with exit code $LASTEXITCODE" }

Write-Output 'Release candidate gate regression passed: explicit candidate binding, source/hash/version checks, stale-candidate expiry, retry/idempotency structure, and behavioral snapshot/retry invariants are present; no database was opened.'
