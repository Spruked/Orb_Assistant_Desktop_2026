@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_desktop_orb.ps1"
set "exit_code=%ERRORLEVEL%"
if not "%exit_code%"=="0" (
  echo.
  echo Orb launch failed with exit code %exit_code%.
  pause
)
exit /b %exit_code%
