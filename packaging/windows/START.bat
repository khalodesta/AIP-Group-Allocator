@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0app\launcher\start.ps1"
if errorlevel 1 pause
endlocal
