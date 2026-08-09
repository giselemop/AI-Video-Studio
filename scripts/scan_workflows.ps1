$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Server = Join-Path $Root 'server\publish\VideoStudio.Server.dll'
if (-not (Test-Path $Server)) { & (Join-Path $PSScriptRoot 'publish.ps1') }
$response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/api/workflows/scan'
$response | ConvertTo-Json -Depth 5
