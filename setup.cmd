@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  set "TRAVEL_PYTHON=python"
) else (
  set "TRAVEL_PYTHON=py -3"
)
%TRAVEL_PYTHON% -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10 or newer is required'"
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" (
  %TRAVEL_PYTHON% -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import tkinter; import shapely"
if errorlevel 1 goto failed
echo.
echo Ready. Double-click Start.cmd to open your travel log.
pause
exit /b 0
:failed
echo.
echo Setup failed. The error is above. Python 3.10+ with Tcl/Tk is required.
echo Your existing travel data and Git settings were not changed.
pause
exit /b 1
