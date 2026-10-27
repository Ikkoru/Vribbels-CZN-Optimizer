@echo off

REM The escape character, for this file's own red lines: the console
REM draws ANSI colour, and a .bat has no way to spell ESC but this.
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "RED=%ESC%[91m"
set "OFF=%ESC%[0m"

cd /d "%~dp0Vribbels" || (echo %RED%CANNOT FIND Vribbels NEXT TO THIS FILE%OFF% & pause & exit /b 1)

REM Steps 1 and 2 come from comparing your settings\ with the shipped
REM defaults: which files to delete, or nothing, in orange or green.
echo Don't forget to:
echo 0. Ensure the default settings are correct
python "./default_settings/normalize/compare_defaults.py"
echo 3. Be happy
echo.

REM Every step runs through this, which shows its warnings dark yellow
REM and its errors red and hands back the step's own exit code.
set "COLOUR=python build_tools\colour_output.py"

%COLOUR% python "./default_settings/normalize/normalize_defaults.py" || (echo %RED%NORMALIZE FAILED%OFF% & pause & exit /b 1)

REM The game facts every copy reads beside its own captures: yours are
REM folded into the shipped file here. Review its diff before committing.
%COLOUR% python "./default_settings/normalize/fold_shared_facts.py" || (echo %RED%SHARED FACTS FOLD FAILED%OFF% & pause & exit /b 1)

REM Every value each default has held, from git: what tells a player's
REM unchanged settings from changed ones where no sync recorded them.
REM Commit the file it writes with the release.
%COLOUR% python "./default_settings/normalize/defaults_history.py" || (echo %RED%DEFAULTS HISTORY FAILED%OFF% & pause & exit /b 1)

REM The game client's facts the build ships, brought level with this
REM machine's client: game_data/from_client.py, and the units a patch
REM added written into game_data's own tables. Review its diff before
REM committing. A client it cannot read leaves the last copy shipped,
REM which is said and does not stop the build.
%COLOUR% python "../docs/client_tables.py" --ship || (echo %RED%THE CLIENT'S FACTS WERE NOT SHIPPED: the build carries the last copy%OFF%)

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
  --add-data "default_settings\defaults_history.json;default_settings" ^
  --add-data "default_settings\preset_archetypes.json;default_settings" ^
  --add-data "default_settings\character_preset.json;default_settings" ^
  --add-data "default_settings\optimizer_settings.json;default_settings" ^
  --add-data "default_settings\shared_facts\shared_facts.json;default_settings\shared_facts" ^
  %TCLDATA% ^
  --hidden-import "PIL._tkinter_finder" ^
  czn_optimizer_gui.py

pause
