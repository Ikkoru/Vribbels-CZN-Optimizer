@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Chaos runs table and spreadsheet

REM Makes my_chaos_runs.tsv and my_chaos_runs.xlsx on the Desktop from
REM the Chaos runs a capture recorded: docs\chaos_runs.py, then
REM docs\chaos_runs_xlsx.py. Written for someone who has never used a
REM command line: it checks for Python and openpyxl, says what to do
REM where either is missing, and asks for the data folder by drag and
REM drop. ASCII only, CRLF: cmd misreads anything else.

REM The report's own messages carry characters a Japanese or other
REM non-UTF-8 console cannot print.
set "PYTHONIOENCODING=utf-8"

echo.
echo  Chaos runs table and spreadsheet
echo  ================================
echo.

REM ---------------------------------------------------------- Python
REM 3.12 or newer. `py` first: the python.org installer always adds it,
REM and `python` can be the Microsoft Store's stand-in, which fails
REM this test as a missing Python should.
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1 && set "PY=python"
if not defined PY goto :no_python
echo  [ok] Python found.

REM -------------------------------------------------------- openpyxl
%PY% -c "import openpyxl" >nul 2>&1 && goto :have_openpyxl
echo.
echo  The spreadsheet needs one add-on for Python: openpyxl.
choice /c YN /m " Install it now"
if errorlevel 2 goto :no_openpyxl
REM No --user: pip picks the user folder itself where Python's own is
REM not writable, and --user fails outright inside a virtual env.
%PY% -m pip install openpyxl
%PY% -c "import openpyxl" >nul 2>&1 || goto :no_openpyxl
:have_openpyxl
echo  [ok] openpyxl found.

REM ---------------------------------------------------- data folder
echo.
echo  Where does your program keep its captures?
echo   - If you use the .exe: drag the folder that holds
echo     Vribbels_CZN_Optimizer_Ikkoru.exe into this window, then press Enter.
echo   - If you run zRUN.bat from this folder: just press Enter.
echo.
set "DATA="
set /p "DATA= Folder: "
if defined DATA set "DATA=%DATA:"=%"
if not defined DATA set "DATA=%~dp0Vribbels"
REM The folder holding the exe, or its snapshots folder: either works.
if exist "%DATA%\snapshots\" set "DATA=%DATA%\snapshots"
if not exist "%DATA%\" goto :no_folder

REM ------------------------------------------------------- where to
REM The real Desktop, which OneDrive can move away from %USERPROFILE%.
REM CHAOS_RUNS_OUT, where set, is used instead: a test's folder.
set "DESK=%CHAOS_RUNS_OUT%"
if not defined DESK for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESK=%%d"
if not defined DESK set "DESK=%USERPROFILE%\Desktop"
set "TABLE=%DESK%\my_chaos_runs.tsv"

REM ------------------------------------------------------------ make
echo.
echo  Reading your Chaos runs. The first time reads every capture log,
echo  which can take several minutes.
echo.
%PY% docs\chaos_runs.py --data "%DATA%" --out "%TABLE%"
if errorlevel 1 goto :failed
if not exist "%TABLE%" goto :no_runs
echo.
%PY% docs\chaos_runs_xlsx.py "%TABLE%"
if errorlevel 1 goto :no_runs

echo.
echo  Done. On your Desktop:
echo   my_chaos_runs.tsv   the table (share this one to combine with others)
echo   my_chaos_runs.xlsx  the spreadsheet
echo  Run this again after more Chaos runs: it adds the new ones.
explorer /select,"%DESK%\my_chaos_runs.xlsx"
goto :end

REM ---------------------------------------------------------- errors
:no_python
echo.
echo  Python 3.12 or newer was not found. To install it:
echo   1. Open https://www.python.org/downloads/ and click the big
echo      yellow "Download Python" button.
echo   2. Run the installer. On its first screen, TICK the box
echo      "Add python.exe to PATH", then click "Install Now".
echo   3. Close this window and double-click this file again.
echo.
choice /c YN /m " Open the download page now"
if errorlevel 2 goto :end
start "" "https://www.python.org/downloads/"
goto :end

:no_openpyxl
echo.
echo  openpyxl is not installed, so no spreadsheet can be made.
echo  Run this file again and answer Y to install it.
goto :end

:no_folder
echo.
echo  That folder was not found:
echo   %DATA%
echo  Run this file again and drag the folder in.
goto :end

:no_runs
echo.
echo  No Chaos runs were found in:
echo   %DATA%
echo  Play a Chaos run with capture on, then run this file again.
goto :end

:failed
echo.
echo  Something went wrong while reading the runs; the message above
echo  says what. Share it, with a screenshot, if you ask for help.
goto :end

:end
echo.
pause
