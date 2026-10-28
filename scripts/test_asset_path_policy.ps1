[CmdletBinding()]
param(
    [string]$DataRoot = 'C:\install\AI\Data',
    [string]$ModelsRoot = 'C:\install\AI\Models'
)

$ErrorActionPreference = 'Stop'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Test-UnsafePathSyntax {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $true }
    if ($Value.StartsWith('\\') -or $Value.StartsWith('\\?\') -or $Value.StartsWith('\\.\') -or $Value.IndexOf([char]0) -ge 0) { return $true }
    $colon = $Value.IndexOf(':')
    if ($colon -lt 0) { return $false }
    return -not ($colon -eq 1 -and [char]::IsLetter($Value[0]) -and $Value.Length -gt 2 -and ($Value[2] -eq '\' -or $Value[2] -eq '/'))
}

function Resolve-PolicyPath {
    param([string]$StoredPath, [string]$Root)
    if (Test-UnsafePathSyntax $StoredPath) { return $null }
    try {
        $candidate = if ([IO.Path]::IsPathRooted($StoredPath)) { $StoredPath } else { [IO.Path]::Combine($Root, $StoredPath) }
        $full = [IO.Path]::GetFullPath($candidate).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
        $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
        if (-not $full.StartsWith($rootFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { return $null }
        if (-not [IO.File]::Exists($full)) { return $null }
        $item = Get-Item -LiteralPath $full -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $null }
        $current = $item.Directory
        while ($null -ne $current) {
            if (($current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $null }
            $current = $current.Parent
        }
        return $full
    } catch { return $null }
}

$policySource = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\server\AssetPathPolicy.cs') -Raw -Encoding UTF8
Assert-True ($policySource -match 'TryResolveExisting') 'AssetPathPolicy must expose the single existing-file resolver.'
Assert-True ($policySource -match 'TryResolveExistingWorkflow') 'Workflow files must have a controlled-root resolver too.'
Assert-True ($policySource -match 'HasReparsePointInPath') 'AssetPathPolicy must reject reparse points.'
Assert-True ($policySource -match 'imageProbe') 'Image uploads must be decoded and dimension-checked, not header-only.'
Assert-True ($policySource -match 'assetPath') 'The media contract must use assetPath rather than an unrestricted path query.'

$dataFull = [IO.Path]::GetFullPath($DataRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$modelsFull = [IO.Path]::GetFullPath($ModelsRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
Assert-True ([IO.Directory]::Exists($dataFull)) "Data root does not exist: $dataFull"
Assert-True ([IO.Directory]::Exists($modelsFull)) "Models root does not exist: $modelsFull"

$files = @(Get-ChildItem -LiteralPath $dataFull -File -Recurse -Force)
Assert-True ($files.Count -gt 0) 'No Data files were found for the positive boundary check.'
foreach ($file in $files) {
    Assert-True ($file.FullName.StartsWith($dataFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) "Data file escaped the root: $($file.FullName)"
    Assert-True (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Data file is a reparse point: $($file.FullName)"
}

$relativePositive = $files[0].FullName.Substring($dataFull.Length + 1)
$positive = Resolve-PolicyPath -StoredPath $relativePositive -Root $dataFull
Assert-True ($null -ne $positive) 'A real Data file was rejected by the read-only policy model.'

$negative = @(
    '..\config\appsettings.json',
    '..\Data2\asset.mp4',
    'C:\install\AI\Data2\asset.mp4',
    '\\server\share\asset.mp4',
    '\\?\C:\install\AI\Data\asset.mp4',
    'C:relative.mp4',
    'Images\frame.png:secret'
)
foreach ($candidate in $negative) {
    Assert-True ($null -eq (Resolve-PolicyPath -StoredPath $candidate -Root $dataFull)) "Unsafe candidate was accepted: $candidate"
}

Write-Output ("AssetPathPolicy read-only boundary regression passed: {0} Data files checked; {1} malicious candidates rejected." -f $files.Count, $negative.Count)
