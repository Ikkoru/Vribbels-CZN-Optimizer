@echo off
cd /d "%~dp0"
python checks/run_all.py %*

pause
