#!/usr/bin/env python3
import os
import sys
import logging
import json

# ロギングの設定
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("reins_debug")

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
    
    # REINSスクレイパーを実行
    logger.info("レインズスクレイパーを実行します...")
    
    # Pythonのパスを追加
    sys.path.append(".")
    
    # スクレイパーをインポート
    from src.reins import ReinsScraper
    
    # スクレイパーを実行
    scraper = ReinsScraper(credentials)
    result = scraper.scrape()
    
    logger.info(f"スクレイピング結果: {result}")
    
    # 結果を確認
    sales_files = os.listdir("data/reins_sales")
    rental_files = os.listdir("data/reins_rental")
    
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

