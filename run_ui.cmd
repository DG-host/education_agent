@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Task ui
exit /b %ERRORLEVEL%
