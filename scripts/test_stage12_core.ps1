[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$serverDll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
if (-not (Test-Path -LiteralPath $serverDll -PathType Leaf)) { throw "Missing built server: $serverDll" }

& dotnet $serverDll --stage12-self-test
if ($LASTEXITCODE -ne 0) { throw "Stage12 core self-test failed with exit code $LASTEXITCODE" }

Write-Output 'Stage12 core self-test passed: canonical versions, legal/illegal transitions, purpose extension boundary, and half-file rejection.'
