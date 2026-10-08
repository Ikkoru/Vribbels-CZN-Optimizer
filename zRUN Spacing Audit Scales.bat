@echo off
cd /d "%~dp0"
rem The spacing audit at the scales between 100% and 200%: 125%, 150%
rem and 175%, each against a baseline of its own. The app is rendered,
rem never shown, and exits when its table is out; the saved UI scale is
rem neither read nor touched.
rem Marks a working copy rather than a released build: the capture's
rem wire catalogue runs only when this is set. A built exe never is.
set VRIBBELS_DEV=1
choice /c MVF /n /m "Misses only, Verbose, or Freeze each scale's baseline? [M/V/F] "
set MODE=--spacing-audit
if errorlevel 2 set MODE=--spacing-audit-verbose
if errorlevel 3 set MODE=--spacing-audit-freeze
for %%P in (125 150 175) do (
    python Vribbels\czn_optimizer_gui.py %MODE% --audit-scale=%%P%%
)

pause
