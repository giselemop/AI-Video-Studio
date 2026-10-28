[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [Parameter(Mandatory = $true)][long]$EpisodeId,
    [switch]$ExpectFormalReady
)

$ErrorActionPreference = 'Stop'
$output = Invoke-RestMethod -Uri "$BaseUrl/api/episodes/$EpisodeId/output" -Method Get
if ($null -eq $output.qualityGate) { throw "Episode output did not return qualityGate" }

if ($ExpectFormalReady) {
    if (-not $output.qualityGate.formalReady) { throw "Expected formalReady=true, but the gate is blocked: $($output.formalBlockedReason)" }
    if (-not $output.canRender) { throw "Expected canRender=true" }
    Write-Output "PASS formal gate: Episode $EpisodeId is ready for formal render"
    exit 0
}

if ($output.canRender) { throw "Expected this fixture to be blocked; pass -ExpectFormalReady for an approved episode" }
$body = @{ episodeId = $EpisodeId; includeSubtitles = $true } | ConvertTo-Json
try {
    Invoke-RestMethod -Uri "$BaseUrl/api/episode/render" -Method Post -ContentType 'application/json' -Body $body | Out-Null
    throw "Formal render unexpectedly accepted for blocked Episode $EpisodeId"
}
catch {
    $response = $_.Exception.Response
    if ($null -eq $response -or [int]$response.StatusCode -ne 422) { throw }
}
Write-Output "PASS formal gate: Episode $EpisodeId rejected with HTTP 422"
