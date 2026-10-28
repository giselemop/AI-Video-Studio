param([switch]$EnableWorker)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$config = Get-Content -LiteralPath (Join-Path $projectRoot 'config/appsettings.json') -Raw | ConvertFrom-Json
$comfyRoot = [IO.Path]::GetFullPath($config.ComfyUI.Root)
$python = Join-Path $comfyRoot 'venv/Scripts/python.exe'
$server = Join-Path $projectRoot 'server/publish/VideoStudio.Server.exe'
$logRoot = Join-Path $projectRoot 'logs'
[IO.Directory]::CreateDirectory($logRoot) | Out-Null
if (-not (Test-Path -LiteralPath $python)) { throw 'The existing ComfyUI runtime is missing.' }
if (-not (Get-NetTCPConnection -State Listen -LocalPort 8188 -ErrorAction SilentlyContinue)) {
    $comfyArgs = @('main.py', '--listen', '127.0.0.1', '--port', '8188', '--use-pytorch-cross-attention', '--lowvram', '--disable-dynamic-vram', '--reserve-vram', '1.5', '--disable-pinned-memory', '--extra-model-paths-config', (Join-Path $comfyRoot 'extra_model_paths.yaml'))
    $comfy = Start-Process -FilePath $python -ArgumentList $comfyArgs -WorkingDirectory $comfyRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'minimax_comfy.stdout.log') -RedirectStandardError (Join-Path $logRoot 'minimax_comfy.stderr.log') -PassThru
    Write-Host ('Started local H3 ComfyUI, PID ' + $comfy.Id)
} else { Write-Host 'Existing ComfyUI listener preserved. H3 needs BF16/default model dtype and low-VRAM offloading; the original LTX launcher is unchanged.' }
if (-not (Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path -LiteralPath $server)) { throw 'Publish the current source with scripts/publish.ps1 before starting VideoStudio.' }
    $latestSource = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'server') -Filter '*.cs' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($latestSource.LastWriteTimeUtc -gt (Get-Item -LiteralPath $server).LastWriteTimeUtc) { throw 'Published server is older than source. Run scripts/publish.ps1 first.' }
    $env:AI_VIDEO_STUDIO_PREFER_ENV = '1'
    $env:AI_VIDEO_STUDIO_WORKER_ENABLED = if ($EnableWorker) { '1' } else { '0' }
    $studio = Start-Process -FilePath $server -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'minimax_studio.stdout.log') -RedirectStandardError (Join-Path $logRoot 'minimax_studio.stderr.log') -PassThru
    Set-Content -LiteralPath (Join-Path $logRoot 'studio.pid') -Value $studio.Id -Encoding ascii
    Write-Host ('Started VideoStudio, PID ' + $studio.Id + ', worker=' + [bool]$EnableWorker)
} else { Write-Host 'Existing VideoStudio listener preserved. This command does not change its Worker setting.' }
Write-Host 'Open http://127.0.0.1:18080/#minimax. Access follows the configured local-only/password mode.'
