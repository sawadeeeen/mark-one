#!/usr/bin/env python3
import os
import sys
import logging
import json

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scraper_runner")

# コマンドライン引数をチェック
if len(sys.argv) < 2:
    print("使用方法: python3 run_specific_scraper.py [スクレイパー名]")
    print("例: python3 run_specific_scraper.py mirai_toshi")
    print("\n利用可能なスクレイパー:")
    print("- mirai_toshi (株式会社未来都市開発)")
    print("- jpm (株式会社JPM)")
    print("- mugen_estate (株式会社ムゲンエステート)")
    print("- s_realty (株式会社シンプレックス・リアルティ)")
    print("- fstage (株式会社エフステージ)")
    print("- bukkaku_file (株式会社インテリックス)")
    print("- arch (株式会社アークフェニックス)")
    print("- rinatohome (株式会社リナート)")
    sys.exit(1)

scraper_name = sys.argv[1]

# データディレクトリを確認
data_dir = "data"
os.makedirs(data_dir, exist_ok=True)

# 設定を読み込む
settings = {}
try:
    with open("scraper_settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
except Exception as e:
    logger.error(f"設定ファイルの読み込みに失敗: {e}")
    settings = {}

# スクレイパーマッピング
scraper_mapping = {
    "mirai_toshi": {
        "class": "MiraiToshiScraper",
        "module": "src.mirai_toshi",
        "name": "株式会社未来都市開発",
        "needs_auth": False
    },
    "jpm": {
        "class": "JPMScraper",
        "module": "src.jpm",
        "name": "株式会社JPM",
        "needs_auth": True
    },
    "mugen_estate": {
        "class": "MugenEstateScraper",
        "module": "src.mugen_estate",
        "name": "株式会社ムゲンエステート",
        "needs_auth": True
    },
    "s_realty": {
        "class": "SRealtyScraper",
        "module": "src.s_realty",
        "name": "株式会社シンプレックス・リアルティ",
        "needs_auth": True
    },
    "fstage": {
        "class": "FstageScraper",
        "module": "src.fstage",
        "name": "株式会社エフステージ",
        "needs_auth": True
    },
    "bukkaku_file": {
        "class": "IntellicsScraper",
        "module": "src.bukkaku_file",
        "name": "株式会社インテリックス",
        "needs_auth": True
    },
    "arch": {
        "class": "ArchScraper",
        "module": "src.arch",
        "name": "株式会社アークフェニックス",
        "needs_auth": True
    },
    "rinatohome": {
        "class": "RinatohomeScraper",
        "module": "src.rinatohome",
        "name": "株式会社リナート",
        "needs_auth": True
    }
}

# スクレイパーが存在するか確認
if scraper_name not in scraper_mapping:
    logger.error(f"スクレイパー '{scraper_name}' は存在しません")
    sys.exit(1)

scraper_info = scraper_mapping[scraper_name]
logger.info(f"{scraper_info['name']}のスクレイピングを開始します")

# 認証情報の準備
credentials = None
if scraper_info["needs_auth"]:
    site_name = scraper_info["name"]
    if site_name in settings and settings[site_name]["enabled"]:
        credentials = {
            "user_id": settings[site_name]["user_id"],
            "password": settings[site_name]["password"]
        }
        if not credentials["user_id"] or not credentials["password"]:
            logger.warning(f"{site_name}の認証情報が設定されていません")
            if input(f"{site_name}の認証情報なしで続行しますか？ (y/n): ").lower() != 'y':
                sys.exit(1)
    else:
        logger.warning(f"{site_name}が有効になっていないか、設定に存在しません")
        if input(f"{site_name}の認証情報なしで続行しますか？ (y/n): ").lower() != 'y':
            sys.exit(1)

# スクレイパーを実行
try:
    # モジュールの動的インポート
    module = __import__(scraper_info["module"], fromlist=[scraper_info["class"]])
    scraper_class = getattr(module, scraper_info["class"])
    
    # utils.pyを確認
    utils_path = "src/utils.py"
    if not os.path.exists(utils_path):
        logger.warning("utils.pyが見つかりません。一時的なファイルを作成します")
        with open(utils_path, "w", encoding="utf-8") as f:
            f.write("""
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

def get_updated_property_paths(property_history, data_dir):
    updated_paths = []
    updated_ids = set(property_history.get("updated", []))
    for property_id in updated_ids:
        property_file = os.path.join(data_dir, f"{property_id}.json")
        if os.path.exists(property_file):
            updated_paths.append(os.path.abspath(property_file))
    return updated_paths
""")
    
    # スクレイパーのインスタンス化と実行
    scraper = scraper_class(credentials)
    result = scraper.scrape()
    
    logger.info(f"スクレイピング結果: {result}")
    
    # マージ処理を実行
    logger.info("マージ処理を実行します")
    from src.merge_json import main
    main()
    
    # 結果を表示
    merged_file = os.path.join(data_dir, "merged.json")
    if os.path.exists(merged_file):
        with open(merged_file, "r", encoding="utf-8") as f:
            merged_data = json.load(f)
        logger.info(f"マージ成功: {len(merged_data)}件のデータ")
    else:
        logger.warning("マージファイルが作成されませんでした")
    
except Exception as e:
    import traceback
    logger.error(f"スクレイパーの実行中にエラーが発生: {e}")
    logger.error(traceback.format_exc())
