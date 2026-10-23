@echo off
rem Full system check: every function, including a call to each model. Takes a few minutes.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The workbench is not set up on this machine yet. Double-click setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "from workbench import modelserver; print(modelserver.ensure())"
".venv\Scripts\python.exe" tests\test_core.py
".venv\Scripts\python.exe" tests\test_api.py
".venv\Scripts\python.exe" -m workbench.doctor --full
pause
