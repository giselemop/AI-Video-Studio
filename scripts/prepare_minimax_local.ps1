param([switch]$VerifyOnly, [ValidateRange(1,16)][int]$Workers = 8)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$config = Get-Content -LiteralPath (Join-Path $projectRoot 'config/appsettings.json') -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath (Join-Path $projectRoot 'config/minimax-local-assets.json') -Raw | ConvertFrom-Json
$comfyRoot = [IO.Path]::GetFullPath($config.ComfyUI.Root)
$modelRoot = [IO.Path]::GetFullPath($config.Paths.Models)
$workflowRoot = [IO.Path]::GetFullPath($config.Paths.Workflows)
$python = Join-Path $comfyRoot 'venv/Scripts/python.exe'
$loaderRoot = Join-Path $comfyRoot 'custom_nodes/ComfyUI-GGUF-H3'
if (-not (Test-Path -LiteralPath $python)) { throw 'Existing ComfyUI Python runtime is missing; no environment will be reinstalled.' }
if (-not (Test-Path -LiteralPath $loaderRoot)) {
    if ($VerifyOnly) { throw 'MiniMax H3 GGUF loader is missing.' }
    & git clone --no-checkout $manifest.loader.repository $loaderRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not clone the H3 loader.' }
    & git -C $loaderRoot fetch --depth 1 origin $manifest.loader.revision
    if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the pinned H3 loader revision.' }
    & git -C $loaderRoot checkout --detach $manifest.loader.revision
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the pinned H3 loader revision.' }
}
$actualRevision = (& git -C $loaderRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $manifest.loader.revision) { throw 'Existing H3 loader revision differs; preserved without reset or overwrite.' }
& $python -c "import importlib.metadata as m; print('gguf=' + m.version('gguf'))"
if ($LASTEXITCODE -ne 0) {
    if ($VerifyOnly) { throw 'GGUF Python package is missing.' }
    & $python -m pip install gguf==0.19.0
    if ($LASTEXITCODE -ne 0) { throw 'GGUF dependency installation failed.' }
}
$source = Join-Path $projectRoot 'tools/minimax/minimax_h3_local_i2v_api.json'
$target = Join-Path $workflowRoot 'minimax_h3_local_i2v_api.json'
if (-not (Test-Path -LiteralPath $target)) {
    if ($VerifyOnly) { throw 'MiniMax local workflow is missing.' }
    [IO.Directory]::CreateDirectory($workflowRoot) | Out-Null
    [IO.File]::Copy($source, $target, $false)
}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) {
    throw 'Existing MiniMax workflow differs from the pinned source; preserved.'
}
$downloadArgs = @((Join-Path $projectRoot 'tools/minimax/download_assets.py'), '--models', $modelRoot, '--workers', $Workers)
if ($VerifyOnly) { $downloadArgs += '--verify-only' }
Write-Host 'MiniMax local H3: pinned data assets, no API key. This does not approve generated content.'
& $python @downloadArgs
if ($LASTEXITCODE -ne 0) { throw 'MiniMax model preparation is incomplete. Keep partial files and run the same command to resume.' }
Write-Host 'Model hashes and the local workflow are ready. Open VideoStudio to register and test the route.'
