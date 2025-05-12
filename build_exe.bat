@echo off
pip install -r requirements.txt
python create_icon.py
pyinstaller --noconsole --onefile --icon=app.ico src/scraper_gui.py
copy scraper_settings.json dist\ 2>nul
echo EXEファイルの作成が完了しました。distフォルダ内のscraper_gui.exeを使用してください。
pause 