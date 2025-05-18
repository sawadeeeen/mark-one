#!/usr/bin/env python3
import os
import sys
import json
import subprocess

def load_settings():
    """設定ファイルを読み込む"""
    try:
        with open("scraper_settings.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("警告: 設定ファイルが見つからないか、無効です。")
        return {}

def get_enabled_sites(settings):
    """有効になっているサイトを取得"""
    enabled_sites = []
    for site, config in settings.items():
        if site != "ielove" and config.get("enabled", False):
            enabled_sites.append(site)
    return enabled_sites

def run_scraper():
    """スクレイピングを実行"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # データディレクトリ作成
    os.makedirs("data", exist_ok=True)
    
    print("merge_jsonモジュールを実行中...")
    try:
        subprocess.call([sys.executable, "-c", 
            f"import sys; sys.path.append('{script_dir}'); "
            f"from src.merge_json import main; main()"])
        print("スクレイピングが完了しました")
    except Exception as e:
        print(f"エラー: スクレイピング実行中に問題が発生しました - {e}")

def export_to_csv():
    """CSVファイルにエクスポート"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("CSVファイルを出力します...")
    
    try:
        result = subprocess.call([sys.executable, "-c", 
            f"import sys; sys.path.append('{script_dir}'); "
            f"import os, json, csv; "
            f"data_dir = 'data'; "
            f"merged_json_path = os.path.join(data_dir, 'merged.json'); "
            f"if not os.path.exists(merged_json_path): "
            f"    print('エラー: merged.jsonファイルが見つかりません'); "
            f"    sys.exit(1); "
            f"with open(merged_json_path, 'r', encoding='utf-8') as f: "
            f"    data = json.load(f); "
            f"if not data: "
            f"    print('警告: データが空です'); "
            f"    sys.exit(1); "
            f"csv_path = os.path.join(data_dir, 'output.csv'); "
            f"with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f: "
            f"    fieldnames = list(data[0].keys()); "
            f"    writer = csv.DictWriter(f, fieldnames=fieldnames); "
            f"    writer.writeheader(); "
            f"    for row in data: writer.writerow(row); "
            f"print(f'CSVファイルを出力しました: {csv_path}'); "
        ])
        
        if result != 0:
            print("CSV出力中にエラーが発生しました")
    except Exception as e:
        print(f"エラー: CSV出力中に問題が発生しました - {e}")

def export_to_html():
    """HTMLファイルにエクスポート"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("HTMLファイルを出力します...")
    
    try:
        result = subprocess.call([sys.executable, "-c", 
            f"import sys; sys.path.append('{script_dir}'); "
            f"import os, json, webbrowser; "
            f"data_dir = 'data'; "
            f"merged_json_path = os.path.join(data_dir, 'merged.json'); "
            f"if not os.path.exists(merged_json_path): "
            f"    print('エラー: merged.jsonファイルが見つかりません'); "
            f"    sys.exit(1); "
            f"with open(merged_json_path, 'r', encoding='utf-8') as f: "
            f"    data = json.load(f); "
            f"if not data: "
            f"    print('警告: データが空です'); "
            f"    sys.exit(1); "
            f"html_path = os.path.join(data_dir, 'output.html'); "
            f"html = '''<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"UTF-8\">"
            f"<title>物件一覧</title><style>table{{border-collapse:collapse;width:100%}}"
            f"th,td{{border:1px solid #ddd;padding:8px;}}tr:nth-child(even){{background-color:#f2f2f2}}"
            f"th{{padding-top:12px;padding-bottom:12px;text-align:left;background-color:#4CAF50;color:white;}}"
            f"</style></head><body><h1>物件一覧</h1><table>'''; "
            
            f"# ヘッダー行を作成"
            f"html += '<tr>'; "
            f"for key in data[0].keys(): "
            f"    html += f'<th>{{key}}</th>'; "
            f"html += '</tr>'; "
            
            f"# データ行を作成"
            f"for item in data: "
            f"    html += '<tr>'; "
            f"    for key, value in item.items(): "
            f"        if isinstance(value, list) and key in ['画像', 'images']: "
            f"            cell = '<td>'; "
            f"            for img in value: "
            f"                if isinstance(img, dict): "
            f"                    img_path = img.get('saved_path') or img.get('file_name') or img.get('url'); "
            f"                    if img_path: "
            f"                        cell += f'<img src=\"{{img_path}}\" width=\"100\">'; "
            f"            cell += '</td>'; "
            f"        else: "
            f"            cell = f'<td>{{value if value is not None else \"\"}}</td>'; "
            f"        html += cell; "
            f"    html += '</tr>'; "
            
            f"html += '</table></body></html>'; "
            
            f"with open(html_path, 'w', encoding='utf-8') as f: "
            f"    f.write(html); "
            
            f"print(f'HTMLファイルを出力しました: {html_path}'); "
            f"webbrowser.open(f'file://{os.path.abspath(html_path)}'); "
        ])
        
        if result != 0:
            print("HTML出力中にエラーが発生しました")
    except Exception as e:
        print(f"エラー: HTML出力中に問題が発生しました - {e}")

def export_to_ierabu(ielove_settings):
    """いえらぶ出力する"""
    user_id = ielove_settings.get("user_id", "")
    password = ielove_settings.get("password", "")
    
    if not user_id or not password:
        print("エラー: いえらぶの認証情報が設定されていません")
        return
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("いえらぶ形式で出力します...")
    
    try:
        result = subprocess.call([sys.executable, "-c", 
            f"import sys; sys.path.append('{script_dir}'); "
            f"from src.ielove import IeloveDataFormatter; "
            f"formatter = IeloveDataFormatter(); "
            f"formatted_data = formatter.process_merged_file(); "
            f"formatter.save_formatted_data(formatted_data); "
            f"print(f'いえらぶ形式で出力しました: {{len(formatted_data)}}件のデータを処理しました'); "
        ])
        
        if result != 0:
            print("いえらぶ出力中にエラーが発生しました")
    except Exception as e:
        print(f"エラー: いえらぶ出力中に問題が発生しました - {e}")

def show_help():
    """ヘルプを表示"""
    print("""
使い方: python simple_scraper.py [オプション]

オプション:
  scrape       - スクレイピングを実行
  csv          - CSVにエクスポート
  html         - HTMLにエクスポート
  ierabu       - いえらぶ形式でエクスポート
  help         - このヘルプを表示

例:
  python simple_scraper.py scrape    # スクレイピングを実行
  python simple_scraper.py csv       # CSVにエクスポート
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("オプションが指定されていません。ヘルプを表示します。")
        show_help()
        sys.exit(1)
    
    action = sys.argv[1].lower()
    settings = load_settings()
    
    if action == "scrape":
        enabled_sites = get_enabled_sites(settings)
        if not enabled_sites:
            print("警告: スクレイピング対象のサイトが選択されていません")
            print("scraper_settings.json ファイルを確認して、少なくとも1つのサイトを有効にしてください")
            sys.exit(1)
        
        print(f"スクレイピング対象サイト: {', '.join(enabled_sites)}")
        run_scraper()
    
    elif action == "csv":
        export_to_csv()
    
    elif action == "html":
        export_to_html()
    
    elif action == "ierabu":
        if "ielove" not in settings:
            print("エラー: いえらぶの設定が見つかりません")
            sys.exit(1)
        
        export_to_ierabu(settings["ielove"])
    
    elif action == "help":
        show_help()
    
    else:
        print(f"エラー: 不明なオプション '{action}'")
        show_help()
        sys.exit(1)
