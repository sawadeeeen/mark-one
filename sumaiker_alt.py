# sumaiker_alt.py として新規作成
import tkinter as tk
import os
import subprocess
import sys
import json

class SimpleScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("すまいける - シンプル版")
        self.root.geometry("800x600")
        self.root.configure(bg="white")
        
        # 設定ファイルを読み込む
        self.settings = self.load_settings()
        
        # サイト選択用の変数
        self.site_vars = {}
        
        self.create_widgets()
    
    def load_settings(self):
        try:
            with open("scraper_settings.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    
    def save_settings(self):
        settings = {}
        for site_name, var in self.site_vars.items():
            settings[site_name] = {"enabled": var.get()}
            
            # 認証情報を取得（サイトごとに必要に応じて）
            if site_name in self.entries:
                user_id = self.entries[site_name]["user_id"].get()
                password = self.entries[site_name]["password"].get()
                settings[site_name]["user_id"] = user_id
                settings[site_name]["password"] = password
        
        # いえらぶ認証情報
        settings["ielove"] = {
            "user_id": self.ielove_user_id.get(),
            "password": self.ielove_password.get()
        }
        
        try:
            with open("scraper_settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            print("設定を保存しました")
        except Exception as e:
            print(f"設定の保存中にエラーが発生: {str(e)}")
    
    def create_widgets(self):
        # タイトル
        title = tk.Label(self.root, text="すまいける - 不動産情報スクレイピングツール", font=("Helvetica", 16), bg="white", fg="black")
        title.pack(pady=20)
        
        # メインフレーム
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # サイト一覧（左側）
        sites_frame = tk.Frame(main_frame, bg="white", bd=1, relief=tk.SOLID)
        sites_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        sites_label = tk.Label(sites_frame, text="スクレイピング対象サイト", font=("Helvetica", 12), bg="white", fg="black")
        sites_label.pack(pady=10)
        
        # サイトリスト
        sites = [
            "株式会社リナート",
            "株式会社JPM",
            "株式会社ムゲンエステート",
            "株式会社エフステージ",
            "株式会社未来都市開発",
            "株式会社シンプレックス・リアルティ",
            "株式会社アークフェニックス",
            "株式会社インテリックス",
            "イタンジBB",
            "レインズ"
        ]
        
        self.entries = {}  # サイトごとの入力フィールドを保存
        
        for site in sites:
            site_frame = tk.Frame(sites_frame, bg="white", pady=5)
            site_frame.pack(fill=tk.X)
            
            var = tk.BooleanVar()
            self.site_vars[site] = var
            
            # 設定からチェック状態を読み込む
            if site in self.settings and "enabled" in self.settings[site]:
                var.set(self.settings[site]["enabled"])
            
            cb = tk.Checkbutton(site_frame, text=site, variable=var, bg="white", fg="black")
            cb.pack(side=tk.LEFT)
            
            # 認証情報入力欄
            login_frame = tk.Frame(site_frame, bg="white")
            login_frame.pack(side=tk.RIGHT)
            
            tk.Label(login_frame, text="ID:", bg="white", fg="black").pack(side=tk.LEFT)
            user_id = tk.Entry(login_frame, width=15)
            user_id.pack(side=tk.LEFT, padx=5)
            
            tk.Label(login_frame, text="パスワード:", bg="white", fg="black").pack(side=tk.LEFT)
            password = tk.Entry(login_frame, width=15, show="*")
            password.pack(side=tk.LEFT)
            
            # 設定から認証情報を読み込む
            if site in self.settings:
                if "user_id" in self.settings[site]:
                    user_id.insert(0, self.settings[site]["user_id"])
                if "password" in self.settings[site]:
                    password.insert(0, self.settings[site]["password"])
            
            self.entries[site] = {"user_id": user_id, "password": password}
        
        # いえらぶ認証情報
        ielove_frame = tk.LabelFrame(main_frame, text="いえらぶ認証情報", bg="white", fg="black", bd=1, relief=tk.SOLID)
        ielove_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10)
        
        tk.Label(ielove_frame, text="ユーザーID:", bg="white", fg="black").pack(anchor=tk.W, pady=5)
        self.ielove_user_id = tk.Entry(ielove_frame, width=20)
        self.ielove_user_id.pack(fill=tk.X, padx=5)
        
        tk.Label(ielove_frame, text="パスワード:", bg="white", fg="black").pack(anchor=tk.W, pady=5)
        self.ielove_password = tk.Entry(ielove_frame, width=20, show="*")
        self.ielove_password.pack(fill=tk.X, padx=5)
        
        # 設定からいえらぶ認証情報を読み込む
        if "ielove" in self.settings:
            if "user_id" in self.settings["ielove"]:
                self.ielove_user_id.insert(0, self.settings["ielove"]["user_id"])
            if "password" in self.settings["ielove"]:
                self.ielove_password.insert(0, self.settings["ielove"]["password"])
        
        # ボタンフレーム
        button_frame = tk.Frame(self.root, bg="white")
        button_frame.pack(pady=20)
        
        # スクレイピング開始ボタン
        start_button = tk.Button(button_frame, text="スクレイピング開始", command=self.start_scraping, bg="lightgray", fg="black", font=("Helvetica", 12), padx=10, pady=5)
        start_button.pack(side=tk.LEFT, padx=10)
        
        # CSV出力ボタン
        csv_button = tk.Button(button_frame, text="CSV出力", command=self.export_to_csv, bg="lightgray", fg="black", font=("Helvetica", 12), padx=10, pady=5)
        csv_button.pack(side=tk.LEFT, padx=10)
        
        # HTML出力ボタン
        html_button = tk.Button(button_frame, text="HTML出力", command=self.export_to_html, bg="lightgray", fg="black", font=("Helvetica", 12), padx=10, pady=5)
        html_button.pack(side=tk.LEFT, padx=10)
        
        # いえらぶ出力ボタン
        ierabu_button = tk.Button(button_frame, text="いえらぶ出力", command=self.export_to_ierabu, bg="lightgray", fg="black", font=("Helvetica", 12), padx=10, pady=5)
        ierabu_button.pack(side=tk.LEFT, padx=10)
        
        # 設定を保存ボタン
        save_button = tk.Button(self.root, text="設定を保存", command=self.save_settings, bg="lightgray", fg="black", font=("Helvetica", 12), padx=10, pady=5)
        save_button.pack(pady=10)
    
    def start_scraping(self):
        self.save_settings()
        selected_sites = [site for site, var in self.site_vars.items() if var.get()]
        
        if not selected_sites:
            tk.messagebox.showwarning("警告", "スクレイピングするサイトが選択されていません")
            return
        
        tk.messagebox.showinfo("情報", f"選択されたサイト: {', '.join(selected_sites)}\n\nスクレイピングを開始します")
        
        # オリジナルのスクレイパースクリプトを実行
        env = os.environ.copy()
        env["TK_THEME"] = "light"
        env["TCLLIBPATH"] = "/opt/homebrew/lib"
        env["TK_SILENCE_DEPRECATION"] = "1"
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "src", "scraper_gui.py")
        
        # コマンドラインからスクレイピングを実行
        subprocess.call([sys.executable, "-c", 
            f"import sys; sys.path.append('{script_dir}'); "
            f"from src.merge_json import main; main()"])
        
        tk.messagebox.showinfo("完了", "スクレイピングが完了しました")
    
    def export_to_csv(self):
        tk.messagebox.showinfo("CSV出力", "CSVファイルを出力します")
        # CSVエクスポート機能を実装
    
    def export_to_html(self):
        tk.messagebox.showinfo("HTML出力", "HTMLファイルを出力します")
        # HTMLエクスポート機能を実装
    
    def export_to_ierabu(self):
        tk.messagebox.showinfo("いえらぶ出力", "いえらぶ形式で出力します")
        # いえらぶエクスポート機能を実装

# アプリケーションを実行
if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleScraperGUI(root)
    root.mainloop()
