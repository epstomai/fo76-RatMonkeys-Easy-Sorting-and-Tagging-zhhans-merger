@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-fo76-strings-merge.ps1" %*
if errorlevel 1 (
  echo.
  echo Merge failed. Press any key to close.
  pause >nul
  exit /b 1
)
echo.
echo Merge finished. Press any key to close.
pause >nul
