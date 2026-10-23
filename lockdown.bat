@echo off
rem Blocks all outbound network traffic from the model server and the workbench (Windows Firewall).
rem Asks for administrator rights. Undo with unlock.bat.
rem   lockdown.bat             apply the rules
rem   lockdown.bat -SelfTest   apply, test, and remove again; result in logs\lockdown_selftest.txt
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\lockdown.ps1" %*
