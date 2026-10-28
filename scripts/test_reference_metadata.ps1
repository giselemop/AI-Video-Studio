[CmdletBinding()]
param(
    [string]$ServerDll = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ServerDll)) {
    $ServerDll = Join-Path (Split-Path -Parent $PSScriptRoot) 'server\bin\Debug\net8.0\VideoStudio.Server.dll'
}
$ServerDll = [IO.Path]::GetFullPath($ServerDll)
if (-not (Test-Path -LiteralPath $ServerDll -PathType Leaf)) { throw "Missing built server: $ServerDll" }

& dotnet.exe $ServerDll --reference-metadata-self-test
if ($LASTEXITCODE -ne 0) { throw "Reference metadata regression failed with exit code $LASTEXITCODE" }
