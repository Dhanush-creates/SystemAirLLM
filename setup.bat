@echo off
rem One-time setup on a new machine. Safe to run again.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
pause
