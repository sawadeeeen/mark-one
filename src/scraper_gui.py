import tkinter as tk
from tkinter import ttk, messagebox
import json
import base64
from cryptography.fernet import Fernet
import os
import logging
import sys
import threading
from arch import ArchScraper
from bukkaku_file import IntellicsScraper
from fstage import FstageScraper
from itandibb import ItandiBBScraper
from itandibb_sales import ItandiBBSalesScraper
import merge_json
from rinatohome import RinatohomeScraper
from jpm import JPMScraper
from mugen_estate import MugenEstateScraper
from mirai_toshi import MiraiToshiScraper
from s_realty import SRealtyScraper
from reins import ReinsScraper


# デバッグモードの設定
DEBUG_MODE = os.environ.get('DEBUG_MODE', '0') == '1'

# ロガーの設定
logger = logging.getLogger(__name__)
if DEBUG_MODE:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('debug.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
else:
    logging.basicConfig(level=logging.INFO)

# スクレイパーのマッピング
SCRAPERS = {
    "株式会社リナート": RinatohomeScraper,
    "株式会社JPM": JPMScraper,
    "株式会社ムゲンエステート": MugenEstateScraper,
    "株式会社エフステージ": FstageScraper,
    "株式会社未来都市開発": MiraiToshiScraper,
    "株式会社シンプレックス・リアルティ": SRealtyScraper,
    "株式会社アークフェニックス": ArchScraper,
    "株式会社インテリックス": IntellicsScraper,
    "イタンジBB": ItandiBBScraper,
    "レインズ": ReinsScraper,
    # 他のスクレイパーをここに追加
}

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Webスクレイピングツール")
        
        # 画面サイズを取得して半分のサイズを計算
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.window_width = screen_width // 2
        self.window_height = screen_height // 2
        
        # 画面中央に配置
        x = (screen_width - self.window_width) // 2
        y = (screen_height - self.window_height) // 2
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")
        
        logger.debug("GUIアプリケーションを初期化中...")
        
        # 暗号化キーの設定
        self.key_file = "scraper_key.key"
        self.key = self.load_or_generate_key()
        self.cipher_suite = Fernet(self.key)
        
        # サイトのリスト（実際のURLに置き換えてください）
        self.sites = [
            {"name": "株式会社リナート", "login_required": True},
            {"name": "株式会社JPM", "login_required": True},
            {"name": "株式会社ムゲンエステート", "login_required": True},
            {"name": "株式会社エフステージ", "login_required": True},
            {"name": "株式会社未来都市開発", "login_required": False},
            {"name": "株式会社シンプレックス・リアルティ", "login_required": True},
            {"name": "株式会社アークフェニックス", "login_required": True},
            {"name": "株式会社インテリックス", "login_required": True},
            {"name": "イタンジBB", "login_required": True},
            {"name": "レインズ", "login_required": True},
        ]
        
        self.site_vars = {}
        self.credentials = {}
        self.input_frames = {}  # 入力エリアのフレームを保持
        
        self.create_widgets()
        self.load_settings()
        
        if DEBUG_MODE:
            self.create_debug_widgets()
            logger.debug("デバッグモードが有効です")

    def create_debug_widgets(self):
        """デバッグ用のウィジェットを作成"""
        debug_frame = ttk.LabelFrame(self.root, text="デバッグ情報", padding=10)
        debug_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # デバッグ情報表示用のテキストエリア
        self.debug_text = tk.Text(debug_frame, height=5)
        self.debug_text.pack(fill=tk.X)
        
        # デバッグ用のボタン
        ttk.Button(debug_frame, text="状態確認", 
                  command=self.show_debug_info).pack(pady=5)

    def show_debug_info(self):
        """現在の状態をデバッグ表示"""
        if not DEBUG_MODE:
            return
            
        debug_info = []
        debug_info.append("=== デバッグ情報 ===")
        debug_info.append("選択されているサイト:")
        for site, var in self.site_vars.items():
            if var.get():
                debug_info.append(f"- {site}")
        
        debug_info.append("\n設定ファイルの状態:")
        try:
            open("scraper_settings.json", "r", encoding="utf-8")
            debug_info.append("設定ファイル: 存在します")
        except FileNotFoundError:
            debug_info.append("設定ファイル: 存在しません")
        
        self.debug_text.delete(1.0, tk.END)
        self.debug_text.insert(tk.END, "\n".join(debug_info))
        logger.debug("\n".join(debug_info))

    def create_widgets(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root)
        main_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # いえらぶ認証情報フレーム
        ielove_frame = ttk.LabelFrame(self.root, text="いえらぶ認証情報", padding=10)
        ielove_frame.place(x=20, y=360, width=300, height=150)

        # ユーザーID入力
        ttk.Label(ielove_frame, text="ユーザーID:").pack(anchor=tk.W)
        self.ielove_user_id = ttk.Entry(ielove_frame)
        self.ielove_user_id.pack(fill=tk.X)
        self.ielove_user_id.bind('<FocusOut>', lambda e: self.save_settings())

        # パスワード入力
        ttk.Label(ielove_frame, text="パスワード:").pack(anchor=tk.W)
        self.ielove_password = ttk.Entry(ielove_frame, show="*")
        self.ielove_password.pack(fill=tk.X)
        self.ielove_password.bind('<FocusOut>', lambda e: self.save_settings())
        
        # スクロールバー付きキャンバス
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # キャンバスの幅をメインフレームに合わせる
        main_frame.pack_propagate(False)
        main_frame.configure(width=self.window_width-20, height=self.window_height-200)  # ボタンやマージン分を考慮

        # キャンバスウィンドウの幅を設定
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # キャンバスの幅をメインフレームに合わせる
        canvas.pack(side="left", fill="both", expand=True, padx=5)
        scrollbar.pack(side="right", fill="y")

        # 1行あたりの最大列数を計算（画面幅から余白を引いて、適度な幅で割る）
        columns_per_row = 5  # 1行あたり5つのサイトを表示

        # サイトごとの設定を作成
        for i, site in enumerate(self.sites):
            row = i // columns_per_row    # 行番号
            col = i % columns_per_row     # 列番号
            
            frame = ttk.LabelFrame(scrollable_frame, text=site["name"], padding=10)
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            # スクレイピングするかどうかのチェックボックス
            var = tk.BooleanVar()
            self.site_vars[site["name"]] = var
            
            # 入力エリアを格納するフレーム
            input_frame = ttk.Frame(frame)
            self.input_frames[site["name"]] = input_frame  # フレームを保持
            
            # スクレイピングするかどうかのチェックボックス
            check = ttk.Checkbutton(frame, text="スクレイピングする", 
                                  variable=var,
                                  command=lambda f=input_frame, v=var, s=site: self.toggle_input_area_and_save(f, v, s))
            check.pack(anchor=tk.W)
            
            # ログイン情報入力エリア
            if site["login_required"]:
                login_frame = ttk.Frame(input_frame)
                
                # ユーザーID入力
                ttk.Label(login_frame, text="ユーザーID:").pack(anchor=tk.W)
                user_id = ttk.Entry(login_frame)
                user_id.pack(fill=tk.X)
                user_id.bind('<FocusOut>', lambda e: self.save_settings())
                
                # パスワード入力
                ttk.Label(login_frame, text="パスワード:").pack(anchor=tk.W)
                password = ttk.Entry(login_frame, show="*")
                password.pack(fill=tk.X)
                password.bind('<FocusOut>', lambda e: self.save_settings())
                
                self.credentials[site["name"]] = {"user_id": user_id, "password": password}
                
                # 初期状態では非表示
                login_frame.pack_forget()

        # 列の幅を均等に設定
        for i in range(columns_per_row):
            scrollable_frame.grid_columnconfigure(i, weight=1, uniform="column")

        # ボタンフレーム
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)

        # スタイルの設定
        style = ttk.Style()
        style.configure('Large.TButton', font=('Helvetica', 12))

        # スクレイピング開始ボタン
        start_button = ttk.Button(button_frame, text="スクレイピング開始", 
                                command=self.start_scraping,
                                style='Large.TButton',
                                padding=10)
        start_button.pack(side=tk.LEFT, padx=5)

        # CSV出力ボタン
        csv_button = ttk.Button(button_frame, text="CSV出力", 
                              command=self.export_to_csv,
                              style='Large.TButton',
                              padding=10)
        csv_button.pack(side=tk.LEFT, padx=5)

        # HTML出力ボタン
        html_button = ttk.Button(button_frame, text="HTML出力", 
                               command=self.export_to_html,
                               style='Large.TButton',
                               padding=10)
        html_button.pack(side=tk.LEFT, padx=5)

        # いえらぶ出力ボタン
        ierabu_button = ttk.Button(button_frame, text="いえらぶ出力", 
                                 command=self.export_to_ierabu,
                                 style='Large.TButton',
                                 padding=10)
        ierabu_button.pack(side=tk.LEFT, padx=5)

    def load_or_generate_key(self):
        """暗号化キーを読み込むか、新しく生成する"""
        try:
            with open(self.key_file, "rb") as f:
                return f.read()
        except FileNotFoundError:
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            return key

    def save_settings(self):
        """設定を保存する（エラーメッセージなし）"""
        logger.debug("設定の保存を開始")
        settings = {}
        for site in self.sites:
            site_name = site["name"]
            settings[site_name] = {
                "enabled": self.site_vars[site_name].get()
            }
            # ログインが必要なサイトの認証情報を保存（スクレイピング設定に関わらず保存）
            if site["login_required"] and site_name in self.credentials:
                settings[site_name].update({
                    "user_id": self.credentials[site_name]["user_id"].get(),
                    "password": base64.b64encode(
                        self.cipher_suite.encrypt(
                            self.credentials[site_name]["password"].get().encode()
                        )
                    ).decode()
                })
        
        # いえらぶ認証情報を保存
        settings["ielove"] = {
            "user_id": self.ielove_user_id.get(),
            "password": base64.b64encode(
                self.cipher_suite.encrypt(
                    self.ielove_password.get().encode()
                )
            ).decode()
        }
        
        try:
            with open("scraper_settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            logger.debug("設定の保存が完了しました")
        except Exception as e:
            logger.error(f"設定の保存中にエラーが発生: {str(e)}")

    def load_settings(self):
        logger.debug("設定の読み込みを開始")
        try:
            with open("scraper_settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
                
            for site in self.sites:
                site_name = site["name"]
                if site_name in settings:
                    self.site_vars[site_name].set(settings[site_name]["enabled"])
                    if site["login_required"]:
                        self.credentials[site_name]["user_id"].insert(0, settings[site_name]["user_id"])
                        
                        try:
                            # パスワードの復号化
                            encrypted = base64.b64decode(settings[site_name]["password"])
                            decrypted = self.cipher_suite.decrypt(encrypted)
                            self.credentials[site_name]["password"].insert(0, decrypted.decode())
                        except Exception as e:
                            logger.error(f"パスワードの復号化中にエラーが発生: {str(e)}")
                            self.credentials[site_name]["password"].insert(0, "")
                    
                    # チェックボックスの状態に応じて入力エリアを表示
                    self.toggle_input_area_and_save(self.input_frames[site_name], self.site_vars[site_name], site)
            
            # いえらぶ認証情報を読み込み
            if "ielove" in settings:
                self.ielove_user_id.insert(0, settings["ielove"]["user_id"])
                try:
                    encrypted = base64.b64decode(settings["ielove"]["password"])
                    decrypted = self.cipher_suite.decrypt(encrypted)
                    self.ielove_password.insert(0, decrypted.decode())
                except Exception as e:
                    logger.error(f"いえらぶパスワードの復号化中にエラーが発生: {str(e)}")
                    self.ielove_password.insert(0, "")
                    
            logger.debug("設定の読み込みが完了しました")
        except FileNotFoundError:
            logger.debug("設定ファイルが見つかりません")
            pass
        except Exception as e:
            logger.error(f"設定の読み込み中にエラーが発生: {str(e)}")
            messagebox.showerror("エラー", f"設定の読み込み中にエラーが発生しました: {str(e)}")

    def get_selected_scrapers(self):
        """選択されたスクレイパーを取得します"""
        selected_scrapers = []
        for site in self.sites:
            if self.site_vars[site["name"]].get():
                selected_scrapers.append(site["name"])
        return selected_scrapers

    def start_scraping(self):
        """スクレイピングを開始します"""
        try:
            # # dataディレクトリの作成（絶対パスを使用）
            # current_dir = os.path.dirname(os.path.abspath(__file__))
            # data_dir = os.path.join(os.path.dirname(current_dir), "data")
            
            # if not os.path.exists(data_dir):
            #     os.makedirs(data_dir)
            #     logger.info(f"dataディレクトリを作成しました: {data_dir}")

            # # 更新物件情報をクリア
            # updated_file = os.path.join(data_dir, "updated.json")
            
            # if os.path.exists(updated_file):
            #     os.remove(updated_file)
            #     logger.info("更新物件情報をクリアしました")
            # else:
            #     logger.info("更新物件情報が存在しません")   

            # # 選択されたスクレイパーを取得
            # selected_scrapers = self.get_selected_scrapers()
            # if not selected_scrapers:
            #     messagebox.showwarning("警告", "スクレイパーを選択してください")
            #     return

            # # スクレイピング対象のサイトを取得
            # selected_sites = [site for site in self.sites if self.site_vars[site["name"]].get()]
            
            # if not selected_sites:
            #     logger.warning("スクレイピング対象のサイトが選択されていません")
            #     messagebox.showwarning("警告", "スクレイピングするサイトが選択されていません")
            #     return
            
            # # 各サイトのスクレイピングを実行
            # for site in selected_sites:
            #     site_name = site["name"]
            #     logger.info(f"スクレイピング開始: {site_name}")
                
            #     # スクレイパークラスが存在する場合のみ実行
            #     if site_name in SCRAPERS:
            #         try:
            #             # 認証情報の準備
            #             credentials = None
            #             if site["login_required"]:
            #                 credentials = {
            #                 "user_id": self.credentials[site_name]["user_id"].get(),
            #                 "password": self.credentials[site_name]["password"].get()
            #                 }
                        
            #             # スクレイパーのインスタンスを作成して実行
            #             scraper = SCRAPERS[site_name](credentials)
            #             scraper.scrape()
                        
            #         except Exception as e:
            #             logger.error(f"{site_name}のスクレイピング中にエラーが発生: {str(e)}")
            #             messagebox.showerror("エラー", f"{site_name}のスクレイピング中にエラーが発生しました: {str(e)}")
            #             continue
            #     else:
            #         logger.warning(f"スクレイパーが見つかりません: {site_name}")
            #         messagebox.showwarning("警告", f"スクレイパーが見つかりません: {site_name}")
            
            # logger.info("すべてのスクレイピングが完了しました")
            # messagebox.showinfo("完了", "スクレイピングが完了しました")
            
            # マージ処理
            merge_json.main()
            
        except Exception as e:
            logger.error(f"スクレイピング中にエラーが発生: {str(e)}")
            messagebox.showerror("エラー", f"スクレイピング中にエラーが発生しました: {str(e)}")

    def toggle_input_area(self, frame, var):
        """入力エリアの表示/非表示を切り替える"""
        if var.get():
            frame.pack(fill=tk.X, pady=5)
        else:
            frame.pack_forget()

    def toggle_input_area_and_save(self, frame, var, site):
        """入力エリアの表示/非表示を切り替えて設定を保存"""
        if var.get():
            frame.pack(fill=tk.X, pady=5)
            if site["login_required"]:
                for widget in frame.winfo_children():
                    if isinstance(widget, ttk.Frame):
                        widget.pack(fill=tk.X, pady=5)
        else:
            frame.pack_forget()
        self.save_settings()

    def export_to_csv(self):
        """merged.jsonをCSVファイルに変換して出力します"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(os.path.dirname(current_dir), "data")
            merged_json_path = os.path.join(data_dir, "merged.json")
            
            if not os.path.exists(merged_json_path):
                messagebox.showerror("エラー", "merged.jsonファイルが見つかりません")
                return
            
            # JSONファイルを読み込む
            with open(merged_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not data:
                messagebox.showwarning("警告", "データが空です")
                return
            
            # CSVファイルのパスを設定
            csv_path = os.path.join(data_dir, "output.csv")
            
            # CSVファイルに書き出し
            import csv
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                # ヘッダーを取得（最初のデータのキーを使用）
                fieldnames = list(data[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                # ヘッダーを書き込み
                writer.writeheader()
                
                # データを書き込み
                for row in data:
                    writer.writerow(row)
            
            messagebox.showinfo("完了", f"CSVファイルを出力しました: {csv_path}")
            logger.info(f"CSVファイルを出力しました: {csv_path}")
            
        except Exception as e:
            logger.error(f"CSV出力中にエラーが発生: {str(e)}")
            messagebox.showerror("エラー", f"CSV出力中にエラーが発生しました: {str(e)}")

    def export_to_html(self):
        """merged.jsonをHTMLファイルに変換して出力します"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(os.path.dirname(current_dir), "data")
            merged_json_path = os.path.join(data_dir, "merged.json")
            
            if not os.path.exists(merged_json_path):
                messagebox.showerror("エラー", "merged.jsonファイルが見つかりません")
                return
            
            # JSONファイルを読み込む
            with open(merged_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not data:
                messagebox.showwarning("警告", "データが空です")
                return
            
            # HTMLファイルのパスを設定
            html_path = os.path.join(data_dir, "output.html")
            
            # HTMLテンプレートを作成
            html_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>物件一覧</title>
</head>
<body style="font-family:Arial,sans-serif;margin:20px">
    <h1>物件一覧</h1>
    <div style="position:relative;max-height:calc(100vh - 150px);overflow:auto;margin-top:20px">
        <table style="border-collapse:collapse;width:100%">
            <thead style="position:sticky;top:0;z-index:1;background-color:#f2f2f2">
                <tr>
                    {headers}
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
</body>
</html>"""
            
            # ヘッダーを生成
            headers = data[0].keys()
            header_html = "".join(f'<th style="border:1px solid #ddd;padding:8px;text-align:left;background-color:#f2f2f2">{header}</th>' for header in headers)
            
            # 行データを生成
            rows_html = ""
            for i, row in enumerate(data):
                bg_color = "#f9f9f9" if i % 2 == 0 else "#ffffff"
                row_html = f'<tr style="background-color:{bg_color}">'
                for key, value in row.items():
                    # 画像データの場合は<img>タグを生成
                    if isinstance(value, list) and key in ["画像", "images"]:
                        cell_content = ""
                        for img in value:
                            if isinstance(img, dict):
                                img_path = img.get("saved_path") or img.get("file_name") or img.get("url")
                                if img_path:
                                    cell_content += f'<img src="{img_path}" alt="物件画像" style="max-width:200px;margin:5px">'
                        row_html += f'<td style="border:1px solid #ddd;padding:8px;text-align:left">{cell_content}</td>'
                    else:
                        # Noneを空文字列に変換
                        display_value = "" if value is None else value
                        row_html += f'<td style="border:1px solid #ddd;padding:8px;text-align:left">{display_value}</td>'
                row_html += "</tr>"
                rows_html += row_html
            
            # HTMLを生成して保存
            html_content = html_template.format(headers=header_html, rows=rows_html)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            # デフォルトのWebブラウザでHTMLファイルを開く
            import webbrowser
            webbrowser.open(f'file://{os.path.abspath(html_path)}')
            
            messagebox.showinfo("完了", f"HTMLファイルを出力し、ブラウザで開きました: {html_path}")
            logger.info(f"HTMLファイルを出力し、ブラウザで開きました: {html_path}")
            
        except Exception as e:
            logger.error(f"HTML出力中にエラーが発生: {str(e)}")
            messagebox.showerror("エラー", f"HTML出力中にエラーが発生しました: {str(e)}")

    def export_to_ierabu(self):
        """いえらぶ形式で出力します"""
        try:
            # いえらぶの認証情報を取得
            user_id = self.ielove_user_id.get()
            password = self.ielove_password.get()

            if not user_id or not password:
                messagebox.showerror("エラー", "いえらぶの認証情報を入力してください")
                return

            # いえらぶスクレイパーのインスタンスを作成
            from ielove import IeloveScraper
            scraper = IeloveScraper(user_id, password)

            # ログイン
            if not scraper.login():
                messagebox.showerror("エラー", "いえらぶへのログインに失敗しました")
                return

            try:
                # データの処理と出力
                from ielove import IeloveDataFormatter
                formatter = IeloveDataFormatter()
                formatted_data = formatter.process_merged_file()
                formatter.save_formatted_data(formatted_data)

                messagebox.showinfo("完了", "いえらぶ形式で出力しました")
                logger.info("いえらぶ形式で出力しました")

            finally:
                # ログアウト
                scraper.logout()

        except Exception as e:
            logger.error(f"いえらぶ出力中にエラーが発生: {str(e)}")
            messagebox.showerror("エラー", f"いえらぶ出力中にエラーが発生しました: {str(e)}")

if __name__ == "__main__":
    if DEBUG_MODE:
        print("デバッグモードで起動しています")
        print("ログファイル: debug.log")
        
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop() 