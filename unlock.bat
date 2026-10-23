@echo off
rem Removes the firewall rules added by lockdown.bat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\lockdown.ps1" -Remove
