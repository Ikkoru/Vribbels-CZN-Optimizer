@echo off
cd /d "%~dp0"
rem Marks a working copy rather than a released build: the capture's
rem wire catalogue runs only when this is set. A built exe never is.
set VRIBBELS_DEV=1
rem The app is rendered, never shown, and exits when its table is out:
rem first at 100%, then at 200% without touching the saved UI scale.
python Vribbels\czn_optimizer_gui.py --spacing-audit
python Vribbels\czn_optimizer_gui.py --spacing-audit --audit-scale=200%%

pause