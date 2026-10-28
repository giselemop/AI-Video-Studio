[CmdletBinding()]
param(
    [string]$QualityReport = 'C:\install\AI\Data\QA\identity_pipeline_20260816\character-qa-results.json',
    [string]$HarnessProject = 'C:\install\AI\VideoStudio\tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\reference_selector_v2_benchmark_20260816'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$quality = Get-Content -LiteralPath $QualityReport -Raw -Encoding UTF8 | ConvertFrom-Json
$references = @($quality.goldenPack.references)
$cases = @(
    [pscustomobject]@{code='R01';requested='Front';shot='CloseUp';expected='Front';fallback=$false;action='blink'},
    [pscustomobject]@{code='R02';requested='FrontLeft30';shot='CloseUp';expected='Front';fallback=$true;action='look left'},
    [pscustomobject]@{code='R03';requested='FrontRight30';shot='CloseUp';expected='Front';fallback=$true;action='look right'},
    [pscustomobject]@{code='R04';requested='Left45';shot='Medium';expected='Front';fallback=$true;action='turn left'},
    [pscustomobject]@{code='R05';requested='Right45';shot='Medium';expected='Front';fallback=$true;action='turn right'},
    [pscustomobject]@{code='R06';requested='HalfBody';shot='Medium';expected='Front';fallback=$true;action='raise hand'},
    [pscustomobject]@{code='R07';requested='FullBody';shot='Long';expected='Front';fallback=$true;action='stand'},
    [pscustomobject]@{code='R08';requested='LeftProfile';shot='Medium';expected='Front';fallback=$true;action='look left'},
    [pscustomobject]@{code='R09';requested='RightProfile';shot='Medium';expected='Front';fallback=$true;action='look right'}
)
$expanded = foreach($item in $cases){ foreach($seed in 1..3){ [ordered]@{caseId="$($item.code)-S$seed";seed=$seed;requestedView=$item.requested;shotSize=$item.shot;action=$item.action;expectedView=$item.expected;expectedFallback=$item.fallback} } }
$inputPath = Join-Path $OutputRoot 'selector-benchmark-input.json'
$outputPath = Join-Path $OutputRoot 'selector-v2-results.json'
[ordered]@{schemaVersion='2026-08-16.reference-selector-v2-input.v1';references=$references;cases=@($expanded)} |
    ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $inputPath -Encoding UTF8
& dotnet run --project $HarnessProject --no-build -- --selector-input $inputPath --selector-output $outputPath
if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }
Write-Output "REPORT=$outputPath"
