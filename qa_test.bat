@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\qa_test.ps1" %*
exit /b %ERRORLEVEL%
