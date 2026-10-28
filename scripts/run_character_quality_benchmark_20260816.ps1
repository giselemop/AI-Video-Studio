[CmdletBinding()]
param(
    [string]$ManifestPath = 'C:\install\AI\Data\QA\identity_pipeline_20260816\identity-manifest.json',
    [string]$OutputPath = 'C:\install\AI\Data\QA\identity_pipeline_20260816\character-qa-results.json'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Missing identity manifest: $ManifestPath" }
$project = 'C:\install\AI\VideoStudio\tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj'
dotnet run --project $project --no-restore -- --input $ManifestPath --output $OutputPath
if (-not (Test-Path -LiteralPath $OutputPath)) { throw "Character QA did not write $OutputPath" }
$report = Get-Content -LiteralPath $OutputPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Output ("Character QA: {0} candidates, {1} auto-accepted, Golden Pack={2}, LoRA={3}" -f @($report.candidates).Count, @($report.candidates | Where-Object accepted).Count, $report.goldenPack.validation.status, $report.loraStatus)
if ($report.loraStatus -ne 'BLOCKED_DATASET_QUALITY' -and $report.goldenPack.validation.status -notin @('Passed', 'Conditional-manual-review-required')) { exit 2 }
