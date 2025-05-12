from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import json
import os
from typing import Dict, Any
import re
import logging

from utils import save_updated_properties

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# コンソールハンドラの設定
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class MiraiToshiScraper:
    def __init__(self, credentials=None):
        """
        未来都市開発のスクレイパーを初期化します。

        Args:
            credentials (Dict[str, str], optional): 認証情報（未来都市開発は不要）
        """
        self.base_url = "https://mirai-toshi.co.jp"
        self.search_url = f"{self.base_url}/estate/data.php?c=search"
        self.data_dir = "data/mirai-toshi"
        os.makedirs(self.data_dir, exist_ok=True)
        logger.info("未来都市開発スクレイパーを初期化しました")

    def get_property_details(self, driver, property_id: str) -> Dict[str, Any]:
        """
        物件詳細ページから情報を取得します。

        Args:
            driver: WebDriverインスタンス
            property_id (str): 物件ID

        Returns:
            Dict[str, Any]: 物件詳細情報
        """
        try:
            logger.info("物件詳細情報の取得を開始")
            
            # ページ読み込み完了を待機
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            
            # テーブルから情報を取得
            table = driver.find_element(By.CSS_SELECTOR, "table")
            rows = table.find_elements(By.CSS_SELECTOR, "tr")
            
            # 交通と所在地（1行目）
            transport_address = rows[1].find_elements(By.CSS_SELECTOR, "td")[0]
            transport_text = transport_address.find_elements(By.CSS_SELECTOR, "p")[0].text
            address = transport_address.find_elements(By.CSS_SELECTOR, "p")[1].text
            logger.info(f"交通: {transport_text}")
            logger.info(f"所在地: {address}")
            
            # 交通情報を分解（路線名・駅名・徒歩時間）
            transport_parts = []
            for transport in transport_text.split("、"):
                match = re.match(r"(.+?)(駅|　).*?徒歩：?(\d+)分", transport)
                if match:
                    transport_parts.append({
                        "路線名": match.group(1).strip(),
                        "駅名": match.group(2).strip(),
                        "徒歩時間": int(match.group(3))
                    })
            
            # 間取りと面積（1行目）
            layout_area = rows[1].find_elements(By.CSS_SELECTOR, "td")[1]
            layout = layout_area.find_elements(By.CSS_SELECTOR, "p")[0].text
            area = layout_area.find_elements(By.CSS_SELECTOR, "p")[1].text.replace("㎡", "")
            logger.info(f"間取り: {layout}")
            logger.info(f"面積: {area}㎡")
            
            # 物件種別と建築年月（1行目）
            type_year = rows[1].find_elements(By.CSS_SELECTOR, "td")[2]
            property_type = type_year.find_elements(By.CSS_SELECTOR, "p")[0].text
            built_date = type_year.find_elements(By.CSS_SELECTOR, "p")[1].text
            logger.info(f"物件種別: {property_type}")
            logger.info(f"建築年月: {built_date}")
            
            # 価格（1行目）
            price_element = rows[1].find_elements(By.CSS_SELECTOR, "td.price")[0]
            price_text = price_element.find_element(By.CSS_SELECTOR, "span").text
            logger.info(f"価格: {price_text}万円")

            # 物件名を取得
            try:
                # 2番目のh1タグから物件名を取得
                h1_elements = driver.find_elements(By.CSS_SELECTOR, "h1")
                if len(h1_elements) >= 2:
                    h1_element = h1_elements[1]  # 2番目のh1タグ
                    full_name = h1_element.text.strip()
                    
                    # div.item-typeの内容を除去して物件名を取得
                    property_type_div = h1_element.find_element(By.CSS_SELECTOR, "div.item-type")
                    property_type_text = property_type_div.text.strip()
                    full_name = full_name.replace(property_type_text, "").strip()
                    
                    logger.info(f"物件名全体: {full_name}")
                else:
                    logger.error("2番目のh1タグが見つかりません")
                    full_name = ""
            except Exception as e:
                logger.error(f"物件名の取得に失敗: {str(e)}")
                # 失敗した場合は空文字を使用
                full_name = ""

            # 部屋番号を抽出
            room_number = None
            building_name = full_name
            
            # 部屋番号のパターンを検索
            room_patterns = [
                r'\d+号室$',  # 末尾が数字+号室
                r'[A-Za-z]?\d+$',  # 末尾がアルファベット(省略可)+数字
                r'#\d+$',  # 末尾が#数字
                r'[\-0-9]+階$'  # 末尾が数字+階
            ]
            
            for pattern in room_patterns:
                match = re.search(pattern, full_name)
                if match:
                    room_number = match.group()
                    building_name = full_name[:match.start()].strip()
                    break
            
            logger.info(f"建物名: {building_name}")
            logger.info(f"部屋番号: {room_number}")

            # オススメ情報を取得
            recommend_info = []
            try:
                content_div = driver.find_element(By.CSS_SELECTOR, "div.content")
                content_text = content_div.get_attribute('innerHTML')
                
                # <br>タグで分割して各項目を取得
                for item in content_text.split("<br>"):
                    # HTMLタグを除去し、空白を削除
                    clean_item = re.sub(r'<[^>]+>', '', item).strip()
                    # 空でない項目のみ追加
                    if clean_item and not clean_item.startswith("物件紹介文・おすすめ情報"):
                        # ◆を除去
                        clean_item = clean_item.replace("◆", "").strip()
                        recommend_info.append(clean_item)
                logger.info(f"オススメ情報: {len(recommend_info)}件")
            except Exception as e:
                logger.warning(f"オススメ情報の取得に失敗: {str(e)}")
            
            # 画像情報を取得
            images = []
            try:
                image_list = driver.find_element(By.CSS_SELECTOR, "ul.info-img")
                image_items = image_list.find_elements(By.CSS_SELECTOR, "li")
                
                for index, item in enumerate(image_items):
                    try:
                        link = item.find_element(By.CSS_SELECTOR, "a")
                        img = item.find_element(By.CSS_SELECTOR, "img")
                        href = link.get_attribute("href")
                        alt = img.get_attribute("alt") or ""
                        caption = item.text.replace(alt, "").strip()
                        
                        # noimage画像は除外
                        if "noimage" in href:
                            continue
                            
                        # 相対パスを絶対パスに変換
                        if href.startswith("./"):
                            href = href.replace("./", f"{self.base_url}/estate/")
                            
                        images.append({
                            "index": index,
                            "url": href,
                            "alt": alt,
                            "caption": caption
                        })
                    except Exception as e:
                        logger.warning(f"画像情報の取得に失敗: {str(e)}")
                        continue
                
                logger.info(f"画像情報: {len(images)}件")
                
                # 画像をダウンロードして保存
                if images:
                    # 物件IDごとのディレクトリを作成
                    property_image_dir = os.path.join(self.data_dir, property_id)
                    os.makedirs(property_image_dir, exist_ok=True)
                    
                    import requests
                    from urllib.parse import urlparse
                    
                    for image in images:
                        try:
                            # 画像URLからファイル名を取得
                            url_path = urlparse(image["url"]).path
                            filename = os.path.basename(url_path)
                            
                            # 画像をダウンロード
                            response = requests.get(image["url"])
                            if response.status_code == 200:
                                image_path = os.path.join(property_image_dir, filename)
                                with open(image_path, "wb") as f:
                                    f.write(response.content)
                                logger.info(f"画像を保存しました: {image_path}")
                                
                                # 保存したパスを画像情報に追加
                                image["saved_path"] = os.path.join(property_id, filename)
                            else:
                                logger.warning(f"画像のダウンロードに失敗: {response.status_code}")
                        except Exception as e:
                            logger.warning(f"画像の保存に失敗: {str(e)}")
                            continue
                
            except Exception as e:
                logger.warning(f"画像リストの取得に失敗: {str(e)}")
            
            return {
                "物件種別": property_type,  # 物件タイプ（売マンション等）
                "建物名": building_name.strip(),  # 建物名
                "部屋番号": room_number.strip() if room_number else None,  # 部屋番号（ない場合はNone）
                "交通": transport_parts,  # 交通情報（路線名・駅名・徒歩時間）
                "所在地": address,  # 所在地
                "間取り": layout,  # 間取り
                "面積": float(area),  # 面積（㎡）
                "建築年月": built_date,  # 建築年月
                "価格": int(price_text.replace(",", "")),  # 価格（万円）
                "オススメ情報": recommend_info,  # オススメ情報（配列）
                "画像": images  # 画像情報（配列）
            }
        except Exception as e:
            logger.error(f"物件詳細情報の取得中にエラー: {str(e)}")
            return {}

    def find_and_click_property(self, driver, property_id: str) -> bool:
        """
        指定された物件IDの詳細リンクをクリックします。

        Args:
            driver: WebDriverインスタンス
            property_id (str): 物件ID

        Returns:
            bool: クリック成功時True、失敗時False
        """
        try:
            logger.info(f"物件ID: {property_id} の詳細リンクを探しています")
            # 詳細リンクを探す（data.php?c=info&item=の形式に修正）
            detail_link = driver.find_element(By.CSS_SELECTOR, f"p.detail a[href*='info'][href*='item={property_id}']")
            href = detail_link.get_attribute('href')
            logger.info(f"詳細リンクのURL: {href}")
            logger.info(f"物件ID: {property_id} の詳細リンクを見つけました")
            detail_link.click()
            logger.info(f"物件ID: {property_id} の詳細ページに移動しました")
            return True
        except Exception as e:
            logger.error(f"物件ID: {property_id} の詳細リンクのクリックに失敗: {str(e)}")
            return False

    def scrape(self) -> Dict[str, Any]:
        """
        物件情報をスクレイピングします。

        Returns:
            Dict[str, Any]: {
                "ステータス": "成功" | "エラー",
                "メッセージ": str,
                "物件一覧": List[Dict] (成功時のみ),
                "総件数": int (成功時のみ)
            }
        """
        driver = None
        try:
            logger.info("スクレイピングを開始します")
            
            # property_history.jsonを読み込む
            history_path = os.path.join(self.data_dir, "property_history.json")
            try:
                if os.path.exists(history_path):
                    with open(history_path, "r", encoding="utf-8") as f:
                        history = json.load(f)
                        existing_ids = set(history.get("物件一覧", {}).keys())
                        logger.info(f"履歴から{len(existing_ids)}件の物件IDを読み込みました")
                else:
                    history = {"物件一覧": {}}
                    existing_ids = set()
                    # 新規作成時は即座に保存
                    with open(history_path, "w", encoding="utf-8") as f:
                        json.dump(history, f, ensure_ascii=False, indent=2)
                    logger.info("新しい履歴ファイルを作成しました")
            except json.JSONDecodeError as e:
                logger.error(f"履歴ファイルの読み込みに失敗: {str(e)}")
                # 破損している場合は新規作成
                history = {"物件一覧": {}}
                existing_ids = set()
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                logger.info("破損した履歴ファイルを新規作成しました")

            # Seleniumドライバーの設定
            options = Options()
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1024,768')
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            logger.info("ブラウザを起動しました")

            # 物件リンクを取得する関数
            def get_property_links():
                all_links = driver.find_elements(By.CSS_SELECTOR, "a")
                logger.info(f"ページ内のリンク総数: {len(all_links)}件")
                
                detail_links = driver.find_elements(By.CSS_SELECTOR, "p.detail a")
                logger.info(f"詳細を見るリンク数: {len(detail_links)}件")
                
                info_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='c=info']")
                logger.info(f"info含むリンク数: {len(info_links)}件")
                
                property_links = driver.find_elements(By.CSS_SELECTOR, "p.detail a[href*='c=info']")
                logger.info(f"物件リンク数: {len(property_links)}件")
                
                return property_links

            # 次のページが存在するかチェックする関数
            def has_next_page():
                try:
                    # 現在のページ番号を取得
                    current_page_element = driver.find_element(By.CSS_SELECTOR, "div.page_navi li span")
                    current_page = int(current_page_element.text)
                    logger.info(f"現在のページ: {current_page}")
                    
                    # 次へのリンク（>）を探す
                    next_links = driver.find_elements(By.CSS_SELECTOR, "div.page_navi li a")
                    for link in next_links:
                        if link.text == ">":
                            next_url = link.get_attribute("href")
                            logger.info(f"次のページのURL: {next_url}")
                            return next_url
                    
                    logger.info("次のページは存在しません")
                    return None
                        
                except Exception as e:
                    logger.warning(f"次のページの確認中にエラー: {str(e)}")
                    return None

            properties = []
            current_ids = set()  # 現在のスクレイピングで見つかった物件ID
            
            # 全ページをループ
            current_url = self.search_url
            while True:
                # 物件一覧ページにアクセス
                driver.get(current_url)
                logger.info(f"ページにアクセスしました: {current_url}")
                
                # ページが完全に読み込まれるまで待機
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "p.detail a"))
                )
                
                # 物件リンクを取得
                property_links = get_property_links()
                
                # 物件IDと対応するhrefを保存
                property_info = []
                for link in property_links:
                    href = link.get_attribute('href')
                    if 'item=' in href:
                        property_id = href.split('item=')[-1]
                        property_info.append({
                            'id': property_id,
                            'href': href
                        })
                        current_ids.add(property_id)
                
                # 保存した情報を使って処理
                for info in property_info:
                    property_id = info['id']
                    href = info['href']
                    
                    # 既存の物件IDの場合はスキップ
                    if property_id in existing_ids:
                        logger.info(f"物件ID: {property_id} は既に処理済みのためスキップします")
                        # 処理済みの物件情報を取得し、ステータスを確認
                        existing_property = history["物件一覧"][property_id]
                        if "ステータス" not in existing_property:
                            existing_property["ステータス"] = "有効"
                        properties.append(existing_property)
                        continue
                    
                    logger.info(f"物件ID: {property_id} の処理を開始")
                    
                    # 直接URLにアクセス
                    driver.get(href)
                    logger.info(f"物件ID: {property_id} の詳細ページにアクセスしました")
                    
                    # 詳細情報を取得
                    details = self.get_property_details(driver, property_id)
                    details["物件ID"] = property_id
                    details["ステータス"] = "有効"  # ステータスを追加
                    properties.append(details)
                    
                    # 個別の物件JSONファイルを保存
                    property_json_path = os.path.join(self.data_dir, f"{property_id}.json")
                    with open(property_json_path, "w", encoding="utf-8") as f:
                        json.dump(details, f, ensure_ascii=False, indent=2)
                    logger.info(f"物件ID: {property_id} の情報を個別JSONファイルに保存しました: {property_json_path}")
                    
                    # 履歴に追加して保存（エラーハンドリング付き）
                    try:
                        if not isinstance(history["物件一覧"], dict):
                            history["物件一覧"] = {}
                        history["物件一覧"][property_id] = details
                        with open(history_path, "w", encoding="utf-8") as f:
                            json.dump(history, f, ensure_ascii=False, indent=2)
                            
                        # 更新物件情報を保存
                        save_updated_properties(property_json_path)

                        logger.info(f"物件ID: {property_id} の情報を履歴に保存しました")
                    except Exception as e:
                        logger.error(f"履歴の保存に失敗: {str(e)}")
                    
                    # 一覧ページに戻る
                    driver.back()
                    logger.info("一覧ページに戻りました")
                    
                    # ページが完全に読み込まれるまで待機
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "p.detail a"))
                    )
                
                # 次のページのURLを取得
                next_page_url = has_next_page()
                if next_page_url:
                    current_url = next_page_url
                    logger.info(f"次のページに移動します: {current_url}")
                else:
                    logger.info("全てのページの処理が完了しました")
                    break
            
            # 削除された物件を特定
            deleted_ids = existing_ids - current_ids
            if deleted_ids:
                try:
                    logger.info(f"{len(deleted_ids)}件の物件が削除されました: {deleted_ids}")
                    for deleted_id in deleted_ids:
                        if deleted_id in history["物件一覧"]:
                            if "ステータス" not in history["物件一覧"][deleted_id]:
                                history["物件一覧"][deleted_id] = {
                                    **history["物件一覧"][deleted_id],
                                    "ステータス": "削除済み"
                                }
                            else:
                                history["物件一覧"][deleted_id]["ステータス"] = "削除済み"
                    
                    with open(history_path, "w", encoding="utf-8") as f:
                        json.dump(history, f, ensure_ascii=False, indent=2)
                    logger.info("削除済み物件の情報を更新しました")
                except Exception as e:
                    logger.error(f"削除済み物件の更新に失敗: {str(e)}")
            
            # 結果をJSONに保存
            result = {
                "status": "success",
                "メッセージ": f"物件 {len(properties)}件を取得しました",
                "物件一覧": properties,
                "総件数": len(properties)
            }
            
            json_path = os.path.join(self.data_dir, "property_list.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"結果をJSONに保存しました: {json_path}")
            
            return result

        except Exception as e:
            logger.error(f"スクレイピング中にエラーが発生: {str(e)}")
            return {
                "ステータス": "エラー",
                "メッセージ": f"エラーが発生しました: {str(e)}"
            }
        finally:
            if driver:
                driver.quit()
                logger.info("ブラウザを終了しました")

if __name__ == "__main__":
    # 単体テスト用のコード
    scraper = MiraiToshiScraper()
    result = scraper.scrape()
    print(json.dumps(result, ensure_ascii=False, indent=2))
