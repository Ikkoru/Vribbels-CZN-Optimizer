@echo off
cd /d "%~dp0"
rem The spacing audit in the app's empty states, one after the other:
rem `empty` (your settings, copied, and nothing captured), then `fresh`
rem (a first launch: the shipped defaults, nothing captured). Each runs
rem in a scratch copy under _tmp\audit_states\, rebuilt every time, so
rem the live settings are only read -- see Vribbels\audit_states.py.
rem Close the app once its audit has printed, and the next state starts.
rem Marks a working copy rather than a released build: the capture's
rem wire catalogue runs only when this is set. A built exe never is.
set VRIBBELS_DEV=1
choice /c MVF /n /m "Misses only, Verbose, or Freeze each state's baseline? [M/V/F] "
set MODE=--spacing-audit
if errorlevel 2 set MODE=--spacing-audit-verbose
if errorlevel 3 set MODE=--spacing-audit-freeze
for %%S in (empty fresh) do (
    echo.
    echo === %%S ===
    python Vribbels\czn_optimizer_gui.py %MODE% --audit-state=%%S
)

pause
