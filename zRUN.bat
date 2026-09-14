@echo off
cd /d "%~dp0"
rem Marks a working copy rather than a released build: the capture's
rem wire catalogue runs only when this is set. A built exe never is.
set VRIBBELS_DEV=1
python Vribbels\czn_optimizer_gui.py