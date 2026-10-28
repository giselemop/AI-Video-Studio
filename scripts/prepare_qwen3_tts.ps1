$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$qwenConfig = Get-Content -LiteralPath (Join-Path $studioRoot 'config/qwen3-tts.json') -Raw | ConvertFrom-Json
$qwenPython = $qwenConfig.python
$qwenEnvironment = Split-Path -Parent (Split-Path -Parent $qwenPython)
$existingCudaPython = 'C:\install\AI\ComfyUI\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $qwenPython)) {
    & $existingCudaPython -m venv $qwenEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'Qwen virtual environment creation failed' }
}
# Read the CUDA runtime through an environment-local .pth. Never install into ComfyUI.
$qwenSite = Join-Path $qwenEnvironment 'Lib/site-packages'
Set-Content -LiteralPath (Join-Path $qwenSite 'existing_cuda_runtime.pth') -Value 'C:\install\AI\ComfyUI\venv\Lib\site-packages' -Encoding ascii
& $qwenPython -m pip install --disable-pip-version-check -r (Join-Path $studioRoot 'tools/qwen3_tts/requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Qwen dependencies installation failed' }
& $qwenPython -c 'import torch,transformers,qwen_tts; print("Qwen imports OK",torch.__version__,transformers.__version__,torch.cuda.is_available())'
if ($LASTEXITCODE -ne 0) { throw 'Qwen import check failed' }
& $qwenPython (Join-Path $studioRoot 'tools/qwen3_tts/prepare_model.py')
if ($LASTEXITCODE -ne 0) { throw 'Pinned Qwen model preparation failed' }
