@echo off
setlocal
if not exist "%~dp0app\launcher\allocator-launcher.exe" (
  echo A required file is missing. Extract the entire ZIP before running STOP.bat.
  if not "%AIP_NO_PAUSE%"=="1" pause
  exit /b 1
)
"%~dp0app\launcher\allocator-launcher.exe" stop
set "AIP_RESULT=%ERRORLEVEL%"
if not "%AIP_RESULT%"=="0" if not "%AIP_NO_PAUSE%"=="1" pause
exit /b %AIP_RESULT%
