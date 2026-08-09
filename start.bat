@echo off
setlocal
set "VIDEO_STUDIO_ROOT=%~dp0"
set "SERVER_EXE=%VIDEO_STUDIO_ROOT%server\publish\VideoStudio.Server.exe"
set "COMFY_PY=%~dp0..\ComfyUI\venv\Scripts\python.exe"
set "COMFY_ROOT=%~dp0..\ComfyUI"
set "COMFY_LOG=%VIDEO_STUDIO_ROOT%logs\comfyui.log"
set "COMFY_ERR=%VIDEO_STUDIO_ROOT%logs\comfyui_error.log"
set "STUDIO_PID=%VIDEO_STUDIO_ROOT%logs\studio.pid"
if not exist "%VIDEO_STUDIO_ROOT%logs" mkdir "%VIDEO_STUDIO_ROOT%logs"
for %%D in ("%VIDEO_STUDIO_ROOT%" "%VIDEO_STUDIO_ROOT%..\Data" "%VIDEO_STUDIO_ROOT%..\Models" "%VIDEO_STUDIO_ROOT%..\Workflows" "%VIDEO_STUDIO_ROOT%..\ComfyUI") do if not exist "%%~fD" echo WARNING: AI directory missing: %%~fD
if not exist "%VIDEO_STUDIO_ROOT%..\..\FFmpeg\bin\ffmpeg.exe" echo WARNING: FFmpeg is missing.
where powershell.exe >nul 2>&1
if errorlevel 1 echo WARNING: Windows PowerShell is missing; local TTS will be unavailable.
if not exist "%SERVER_EXE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%VIDEO_STUDIO_ROOT%scripts\publish.ps1"
  if errorlevel 1 exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 8188 -ErrorAction SilentlyContinue; if(-not $c){exit 1}" >nul 2>&1
if errorlevel 1 (
  if exist "%COMFY_PY%" start "ComfyUI" /b "%COMFY_PY%" "%COMFY_ROOT%\main.py" --listen 127.0.0.1 --port 8188 --preview-method auto 1>"%COMFY_LOG%" 2>"%COMFY_ERR%"
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction SilentlyContinue; if($c){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 echo WARNING: MySQL is not listening on 3306. Database actions will remain unavailable.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue; if($c){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
  start "AI Video Studio" /b "%SERVER_EXE%" 1>"%VIDEO_STUDIO_ROOT%logs\studio_console.log" 2>&1
  timeout /t 1 /nobreak >nul
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue; if($c){$c.OwningProcess | Set-Content -LiteralPath '%STUDIO_PID%' -Encoding ascii}"
)
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:18080"
echo AI Video Studio: http://127.0.0.1:18080
endlocal
