@echo off

REM The escape character, for this file's own red lines: the console
REM draws ANSI colour, and a .bat has no way to spell ESC but this.
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "RED=%ESC%[91m"
set "OFF=%ESC%[0m"

echo Don't forget to:
echo 0. Ensure the default settings are correct.
echo 1. Delete default json files, then zRUN Vribbels
echo 2. Be happy
echo.

cd /d "%~dp0Vribbels" || (echo %RED%CANNOT FIND Vribbels NEXT TO THIS FILE%OFF% & pause & exit /b 1)

REM Every step runs through this, which shows its warnings dark yellow
REM and its errors red and hands back the step's own exit code.
set "COLOUR=python build_tools\colour_output.py"

%COLOUR% python "./default_settings/normalize/normalize_defaults.py" || (echo %RED%NORMALIZE FAILED%OFF% & pause & exit /b 1)

REM The game facts every copy reads beside its own captures: yours are
REM folded into the shipped file here. Review its diff before committing.
%COLOUR% python "./default_settings/normalize/fold_shared_facts.py" || (echo %RED%SHARED FACTS FOLD FAILED%OFF% & pause & exit /b 1)

REM Tcl/Tk 9 keeps its library inside the DLL, where PyInstaller cannot
REM find it -- and its runtime hook then raises on the built exe's first
REM line. This unpacks the library only when PyInstaller needs the help;
REM the directory it leaves behind is the switch below.
%COLOUR% python "./build_tcl/prepare_tcl_data.py" || (echo %RED%TCL DATA PREP FAILED%OFF% & pause & exit /b 1)
set "TCLDATA="
if exist "build_tcl\_tcl_data" set TCLDATA=--add-data "build_tcl\_tcl_data;_tcl_data" --add-data "build_tcl\_tk_data;_tk_data"

echo.
echo on

%COLOUR% pyinstaller --onefile --windowed ^
  --name "Vribbels_CZN_Optimizer_Ikkoru" ^
  --add-data "game_data;game_data" ^
  --add-data "images;images" ^
  --add-data "zstd_dictionary.bin;." ^
  --add-data "default_settings\presets.json;default_settings" ^
  --add-data "default_settings\character_preset.json;default_settings" ^
  --add-data "default_settings\optimizer_settings.json;default_settings" ^
  --add-data "default_settings\shared_facts\shared_facts.json;default_settings\shared_facts" ^
  %TCLDATA% ^
  --hidden-import "PIL._tkinter_finder" ^
  czn_optimizer_gui.py

pause
