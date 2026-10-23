@echo off
rem Starts the workbench and opens it in the browser. Run setup.bat once first.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The workbench is not set up on this machine yet.
  echo Double-click setup.bat first, then start.bat again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m workbench.launch
pause
