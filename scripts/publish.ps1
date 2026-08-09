$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Server = Join-Path $Root 'server'
$Web = Join-Path $Root 'web'
Write-Host 'Building Vue workspace...'
Push-Location $Web
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "Vue build failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
Write-Host 'Publishing .NET server...'
& dotnet publish (Join-Path $Server 'VideoStudio.Server.csproj') -c Release --no-restore -o (Join-Path $Server 'publish') --nologo
if ($LASTEXITCODE -ne 0) { throw " .NET publish failed with exit code $LASTEXITCODE" }
Write-Host "Published: $(Join-Path $Server 'publish')" -ForegroundColor Green
