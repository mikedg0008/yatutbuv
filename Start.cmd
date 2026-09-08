@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\travel_manager.py
) else (
  python scripts\travel_manager.py
)
if errorlevel 1 (
  echo.
  echo If Python or Shapely is missing, run setup.cmd once.
  pause
)
