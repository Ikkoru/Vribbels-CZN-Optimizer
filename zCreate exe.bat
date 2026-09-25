@echo off

echo Don't forget to:
echo 0. Ensure the default settings are correct.
echo 1. Delete default json files, then zRUN Vribbels
echo 2. Be happy
echo.

cd /d "%~dp0Vribbels" || (echo CANNOT FIND Vribbels NEXT TO THIS FILE & pause & exit /b 1)

python "./default_settings/normalize/normalize_defaults.py" || (echo NORMALIZE FAILED & pause & exit /b 1)

REM The game facts every copy reads beside its own captures: yours are
REM folded into the shipped file here. Review its diff before committing.
python "./default_settings/normalize/fold_shared_facts.py" || (echo SHARED FACTS FOLD FAILED & pause & exit /b 1)

REM Tcl/Tk 9 keeps its library inside the DLL, where PyInstaller cannot
REM find it -- and its runtime hook then raises on the built exe's first
REM line. This unpacks the library only when PyInstaller needs the help;
REM the directory it leaves behind is the switch below.
python "./build_tcl/prepare_tcl_data.py" || (echo TCL DATA PREP FAILED & pause & exit /b 1)
set "TCLDATA="
if exist "build_tcl\_tcl_data" set TCLDATA=--add-data "build_tcl\_tcl_data;_tcl_data" --add-data "build_tcl\_tk_data;_tk_data"

echo.
echo on

pyinstaller --onefile --windowed ^
  --name "Vribbels_CZN_Optimizer_Ikkoru" ^
  --add-data "game_data;game_data" ^
  --add-data "images;images" ^
  --add-data "zstd_dictionary.bin;." ^
  --add-data "default_settings\presets.json;default_settings" ^
  --add-data "default_settings\character_preset.json;default_settings" ^
  --add-data "default_settings\optimizer_settings.json;default_settings" ^
  --add-data "default_settings\shared_facts.json;default_settings" ^
  %TCLDATA% ^
  --hidden-import "PIL._tkinter_finder" ^
  czn_optimizer_gui.py

pause
