#!/usr/bin/env python3
import os
import sys
import logging
import json

# ロギングの設定
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("reins_debug")

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 認証情報を読み込む
try:
    with open("scraper_settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    reins_settings = settings.get("レインズ", {})
    if not reins_settings or not reins_settings.get("enabled"):
        logger.error("レインズが有効になっていません")
        sys.exit(1)
    
    credentials = {
        "user_id": reins_settings.get("user_id", ""),
        "password": reins_settings.get("password", "")
    }
    
    if not credentials["user_id"] or not credentials["password"]:
        logger.error("認証情報が設定されていません")
        sys.exit(1)
    
    logger.info(f"認証情報: user_id={credentials['user_id']}, パスワード={'*' * len(credentials['password'])}")
    
    # データディレクトリを作成
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/reins_sales", exist_ok=True)
    os.makedirs("data/reins_rental", exist_ok=True)
    
    # 一時的な utils.py ファイルを作成（必要な場合）
    utils_content = """
def save_updated_properties(file_path):
    import os
    import json
    
    try:
        # updated.jsonのパスを設定
        updated_file = os.path.join("data", "updated.json")
        
        # 既存のデータを読み込む
        existing_data = []
        if os.path.exists(updated_file):
            with open(updated_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = []
        
        # 重複を避けながら新しい物件を追加
        if file_path not in existing_data:
            existing_data.append(file_path)
    
        # データを保存
        os.makedirs(os.path.dirname(updated_file), exist_ok=True)
        with open(updated_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
       
    except Exception as e:
        print(f"更新物件情報の保存中にエラーが発生: {str(e)}")
        raise
    """
    
    # utils.pyがない場合は一時的に作成
    if not os.path.exists("src/utils.py"):
        with open("src/utils.py", "w", encoding="utf-8") as f:
            f.write(utils_content)
        logger.info("一時的なutils.pyファイルを作成しました")
    
    # REINSスクレイパーを実行
    logger.info("レインズスクレイパーを実行します...")
    
    # スクレイパーをインポート
    from src.reins import ReinsScraper
    
    # スクレイパーを実行
    scraper = ReinsScraper(credentials)
    result = scraper.scrape()
    
    logger.info(f"スクレイピング結果: {result}")
    
    # 結果を確認
    sales_files = os.listdir("data/reins_sales") if os.path.exists("data/reins_sales") else []
    rental_files = os.listdir("data/reins_rental") if os.path.exists("data/reins_rental") else []
    
    logger.info(f"販売物件ファイル数: {len(sales_files)}")
    logger.info(f"賃貸物件ファイル数: {len(rental_files)}")
    
    # マージ処理を実行
    logger.info("マージ処理を実行します...")
    from src.merge_json import main
    main()
    
    # マージ結果を確認
    if os.path.exists("data/merged.json"):
        with open("data/merged.json", "r", encoding="utf-8") as f:
            merged_data = json.load(f)
        logger.info(f"マージ成功: {len(merged_data)}件のデータ")
    else:
        logger.error("マージファイルが作成されませんでした")
    
except Exception as e:
    import traceback
    logger.error(f"エラーが発生しました: {str(e)}")
    logger.error(traceback.format_exc())
