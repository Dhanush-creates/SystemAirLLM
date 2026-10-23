@echo off
rem Makes dist\sovereign-workbench.zip: a clean copy of the project for another machine.
rem Add -WithOffline to include the offline\ folder.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package.ps1" %*
pause
