@echo off
rem Run on a machine WITH internet. Fills the offline\ folder so setup.bat works with no internet.
rem Add -Models to also copy the installed Ollama models (large).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\pack_offline.ps1" %*
pause
