#!/usr/bin/env python3
import os
import sys
import logging
import json
import traceback

# ロギングの設定
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("reins_debug")

# プロジェクトのパスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# データディレクトリを作成
os.makedirs("data", exist_ok=True)
os.makedirs("data/reins_sales", exist_ok=True)
os.makedirs("data/reins_rental", exist_ok=True)

# 設定ファイルから認証情報を読み込み
try:
    with open("scraper_settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    credentials = {
        "user_id": settings["レインズ"]["user_id"],
        "password": settings["レインズ"]["password"]
    }
    logger.info(f"認証情報を読み込みました: {credentials['user_id']}")
except Exception as e:
    logger.error(f"設定ファイルの読み込みエラー: {e}")
    sys.exit(1)

# ChromeDriverのパスを手動で設定
home_dir = os.path.expanduser("~")
chromedriver_path = os.path.join(home_dir, ".chromedriver", "chromedriver")

if not os.path.exists(chromedriver_path):
    logger.error(f"ChromeDriverが見つかりません: {chromedriver_path}")
    logger.info("ChromeDriverを手動でインストールする必要があります")
    sys.exit(1)

logger.info(f"ChromeDriverのパス: {chromedriver_path}")

# レインズのスクレイピング処理を実行
try:
    # Seleniumのインポート
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    
    # Chromeオプションの設定
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1024,768")
    options.add_argument("--disable-gpu")
    
    # Service設定
    service = Service(executable_path=chromedriver_path)
    
    # utils.pyの関数定義（インポートエラー回避用）
    def save_updated_properties(file_path):
        try:
            updated_file = os.path.join("data", "updated.json")
            existing_data = []
            if os.path.exists(updated_file):
                with open(updated_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            if not isinstance(existing_data, list):
                existing_data = []
            if file_path not in existing_data:
                existing_data.append(file_path)
            os.makedirs(os.path.dirname(updated_file), exist_ok=True)
            with open(updated_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            logger.info(f"更新物件情報を保存しました: {file_path}")
        except Exception as e:
            logger.error(f"更新物件情報の保存エラー: {e}")
    
    # モンキーパッチ: ChromeDriverManagerを使わない
    from src import reins
    
    # save_updated_propertiesを差し替え
    reins.save_updated_properties = save_updated_properties
    
    # 元の関数をオーバーライド
    def simple_scrape():
        logger.info("ChromeDriverを直接指定してスクレイピングを開始")
        
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=options)
            
            # ログインページにアクセス
            driver.get("https://system.reins.jp/login/main/KG/GKG001200")
            logger.info("ログインページにアクセスしました")
            
            # ログインフォームに入力
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
            ).send_keys(credentials["user_id"])
            
            driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(credentials["password"])
            logger.info("ログイン情報を入力しました")
            
            # チェックボックスをクリック
            checkbox = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'][id^='__BVID__20']"))
            )
            driver.execute_script("arguments[0].click();", checkbox)
            
            # ログインボタンをクリック
            login_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary"))
            )
            driver.execute_script("arguments[0].click();", login_button)
            logger.info("ログインボタンをクリックしました")
            
            # 物件検索ページに移動
            driver.get("https://system.reins.jp/main/KG/GKG003100")
            logger.info("物件検索ページに移動しました")
            
            # 物件検索ボタンを確認
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn-primary"))
            )
            logger.info("物件検索ボタンを確認しました")
            
            # 物件を処理
            # ... (これ以降の処理はとりあえず省略。テスト的にログインまでできればOK)
            
            return {"status": "success", "message": "ログインに成功しました"}
            
        except Exception as e:
            logger.error(f"スクレイピング中にエラー: {e}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
        finally:
            if driver:
                driver.quit()
                logger.info("ブラウザを終了しました")
    
    # 簡易的なスクレイピングを実行
    result = simple_scrape()
    logger.info(f"スクレイピング結果: {result}")
    
    # マージ処理は今回はスキップ
    
except Exception as e:
    logger.error(f"実行中にエラー: {e}")
    logger.error(traceback.format_exc())
