@echo off
setlocal
cd /d "%~dp0"
title Audio Form - close this window to stop
if not exist ".venv\Scripts\python.exe" (
  echo The project Python environment is missing.
  echo Please install the project dependencies first.
  pause
  exit /b 1
)
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%~dp0.tmp"
set "TMP=%~dp0.tmp"
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m voice_animation.web
if errorlevel 1 pause
endlocal
