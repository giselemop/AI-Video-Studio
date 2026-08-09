@echo off
setlocal
set "VIDEO_STUDIO_ROOT=%~dp0"
set "STUDIO_PID=%VIDEO_STUDIO_ROOT%logs\studio.pid"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%STUDIO_PID%'; if(Test-Path -LiteralPath $f){$id=[int](Get-Content -LiteralPath $f); $p=Get-Process -Id $id -ErrorAction SilentlyContinue; if($p -and $p.Path -like '*VideoStudio.Server.exe'){Stop-Process -Id $id -Force}; Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue}"
echo AI Video Studio stopped.
endlocal
