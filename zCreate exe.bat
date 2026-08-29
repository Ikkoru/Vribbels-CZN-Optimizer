@echo off

echo Don't forget to:
echo 0. Ensure the default settings are correct.
echo 1. Delet default json files, then zRUN Vribbels
echo 2. Be happy
echo.

cd ".\Vribbels"

python "./default_settings/normalize/normalize_defaults.py" || (echo NORMALIZE FAILED & pause & exit /b 1)
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
  --hidden-import "PIL._tkinter_finder" ^
  czn_optimizer_gui.py

pause