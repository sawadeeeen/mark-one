@echo off
echo デバッグモードで起動します...
set PYTHONPATH=.
set DEBUG_MODE=1
python -m pdb src/scraper_gui.py
pause 