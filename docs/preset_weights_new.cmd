@echo off
rem A new combatant's default Gear Score preset: docs\preset_weights.md,
rem "A new combatant's preset".
cd /d "%~dp0.."
set "NAME="
set "LIKE="
set /p NAME=Combatant's name, as the Optimizer tab shows it:
if "%NAME%"=="" goto :end
set /p LIKE=Preset to take Ego/HP tie-breakers from (Enter for the default):
if "%LIKE%"=="" (
    python docs\preset_weights.py --new "%NAME%"
) else (
    python docs\preset_weights.py --new "%NAME%" --like "%LIKE%"
)
:end
pause
