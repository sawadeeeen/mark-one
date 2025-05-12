import logging
from typing import Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import os
import requests
import urllib.parse
import re
from datetime import datetime

from utils import save_updated_properties

logger = logging.getLogger(__name__)

class JPMScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        """
        JPMのスクレイパーを初期化します。

        Args:
            credentials (Optional[Dict[str, str]]): ログイン認証情報
                - user_id: ユーザーID
                - password: パスワード
        """
        self.credentials = credentials
        self.base_url = "https://www.jpm-co.jp/login/"
        self.driver = None
        self.data_dir = "data/jpm"
        # データ保存用ディレクトリの作成
        os.makedirs(self.data_dir, exist_ok=True)
        # 物件履歴ファイルのパスを設定
        self.history_file = os.path.join(self.data_dir, "property_history.json")
        # 物件履歴を読み込み
        self.property_history = self.load_property_history()
        logger.debug("JPMスクレイパーを初期化しました")

    def load_property_history(self) -> Dict[str, Any]:
        """
        物件履歴を読み込みます。

        Returns:
            Dict[str, Any]: 物件履歴データ
        """
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # processed_propertiesをsetに変換
                    data["processed_properties"] = set(data.get("processed_properties", []))
                    return data
            return {
                "last_updated": "",
                "active_properties": {},  # 現在も掲載されている物件
                "deleted_properties": {},  # 削除された物件
                "processed_properties": set(),  # 処理済みの物件ID
                "last_scraped": ""  # 最後にスクレイピングした日時
            }
        except Exception as e:
            logger.error(f"物件履歴の読み込み中にエラーが発生: {str(e)}")
            return {
                "last_updated": "",
                "active_properties": {},
                "deleted_properties": {},
                "processed_properties": set(),
                "last_scraped": ""
            }

    def save_property_history(self):
        """
        物件履歴を保存します。
        """
        try:
            # processed_propertiesをリストに変換（JSON対応）
            history_data = {
                "last_updated": datetime.now().isoformat(),
                "active_properties": self.property_history["active_properties"],
                "deleted_properties": self.property_history["deleted_properties"],
                "processed_properties": list(self.property_history["processed_properties"]),
                "last_scraped": datetime.now().isoformat()
            }
            
            # JSONファイルに保存
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)
                f.flush()  # バッファをフラッシュ
                os.fsync(f.fileno())  # ファイルシステムに確実に書き込む
            
            logger.info(f"物件履歴を保存しました: アクティブ={len(self.property_history['active_properties'])}, 削除済み={len(self.property_history['deleted_properties'])}, 処理済み={len(self.property_history['processed_properties'])}")
            
        except Exception as e:
            logger.error(f"物件履歴の保存中にエラーが発生: {str(e)}")
            raise

    def is_property_processed(self, property_id: str) -> bool:
        """
        物件が処理済みかどうかを確認します。

        Args:
            property_id (str): 物件ID

        Returns:
            bool: 処理済みの場合True
        """
        return property_id in self.property_history["processed_properties"]

    def mark_property_as_processed(self, property_id: str, property_info: Dict[str, Any]):
        """
        物件を処理済みとしてマークし、履歴を更新します。

        Args:
            property_id (str): 物件ID
            property_info (Dict[str, Any]): 物件情報
        """
        self.property_history["processed_properties"].add(property_id)
        self.property_history["active_properties"][property_id] = {
            "property_name": property_info.get("物件名", ""),
            "last_seen": datetime.now().isoformat()
        }
        self.save_property_history()
        logger.info(f"物件を処理済みとしてマーク: {property_id}")

    def mark_property_as_deleted(self, property_id: str):
        """
        物件を削除済みとしてマークし、履歴を更新します。

        Args:
            property_id (str): 物件ID
        """
        if property_id in self.property_history["active_properties"]:
            property_info = self.property_history["active_properties"][property_id]
            self.property_history["deleted_properties"][property_id] = {
                **property_info,
                "deleted_at": datetime.now().isoformat()
            }
            del self.property_history["active_properties"][property_id]
            self.save_property_history()
            logger.info(f"物件を削除済みとしてマーク: {property_id}")

    def setup_driver(self):
        """Seleniumドライバーを設定します"""
        chrome_options = Options()
        # ヘッドレスモードを無効化
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        # ウィンドウサイズを設定（全画面表示を無効化）
        chrome_options.add_argument('--window-size=1024,768')
        chrome_options.add_argument('--disable-gpu')  # GPUアクセラレーションを無効化
        # 文字化け対策
        chrome_options.add_argument('--lang=ja_JP')
        chrome_options.add_argument('--disable-features=TranslateUI')
        chrome_options.add_argument('--accept-lang=ja')
        chrome_options.add_experimental_option('prefs', {
            'intl.accept_languages': 'ja,ja_JP',
            'profile.default_content_settings.popups': 0,
            'download.prompt_for_download': False,
        })
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(10)  # 暗黙的な待機を設定

    def login(self) -> bool:
        """
        JPMにログインします。

        Returns:
            bool: ログイン成功時True、失敗時False
        """
        if not self.credentials:
            logger.error("認証情報が設定されていません")
            return False

        try:
            # ログインページにアクセス
            self.driver.get(self.base_url)
            logger.info("ログインページにアクセスしました")

            # ログインフォームが表示されるのを待機
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "jpm_chukai_id"))
            )

            # ユーザーIDとパスワードの入力フィールドを取得
            user_id_input = self.driver.find_element(By.NAME, "jpm_chukai_id")
            password_input = self.driver.find_element(By.NAME, "jpm_chukai_pw")

            if self.credentials:
                user_id_input.send_keys(self.credentials["user_id"])
                password_input.send_keys(self.credentials["password"])
                logger.info("認証情報を入力しました")
            else:
                # 入力フィールドを無効化
                self.driver.execute_script("arguments[0].disabled = true;", user_id_input)
                self.driver.execute_script("arguments[0].disabled = true;", password_input)
                logger.info("認証情報が設定されていないため、入力フィールドを無効化しました")

            # ログインフォームを送信
            try:
                submit_button = self.driver.find_element(By.CSS_SELECTOR, "p.loginbtn input[type='submit']")
                submit_button.click()
            except:  # noqa: E722
                # エラーを無視して処理を継続
                pass
            
            logger.info("ログインフォームを送信しました")

            # ログイン成功の確認
            try:
                # ログイン後のページ遷移を待機
                WebDriverWait(self.driver, 10).until(
                    lambda driver: "chukai.html" in driver.current_url
                )
                
                # 現在のURLを確認
                current_url = self.driver.current_url
                logger.info(f"現在のURL: {current_url}")
                logger.info("ログインに成功しました")
                
                # 物件一覧のリンクをクリック
                try:
                    # リンクが表示されるまで待機
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/chukai/bukken/list/all/']"))
                    )
                    
                    # リンクをクリック
                    bukken_list_link = self.driver.find_element(By.CSS_SELECTOR, "a[href='/chukai/bukken/list/all/']")
                    bukken_list_link.click()
                    logger.info("物件一覧のページに移動しました")
                    
                    # ページの読み込みを待機
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                    )
                    
                    return True
                except Exception as e:
                    logger.error(f"物件一覧ページへの移動中にエラーが発生: {str(e)}")
                    return False

            except TimeoutException as e:
                logger.error(f"ログイン成功の確認がタイムアウトしました: {str(e)}")
                return False

        except TimeoutException as e:
            logger.error(f"ログイン処理がタイムアウトしました: {str(e)}")
            return False
        except NoSuchElementException as e:
            logger.error(f"ログインに必要な要素が見つかりませんでした: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"ログイン中にエラーが発生: {str(e)}")
            return False

    def download_image(self, url: str, save_path: str) -> bool:
        """
        画像をダウンロードして保存します。

        Args:
            url (str): 画像のURL
            save_path (str): 保存先のパス

        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"画像のダウンロード中にエラーが発生: {str(e)}")
            return False

    def scrape(self) -> Dict[str, Any]:
        """
        JPMから情報をスクレイピングします。

        Returns:
            Dict[str, Any]: スクレイピングした情報
        """
        try:
            logger.info("スクレイピング処理を開始")

            # ドライバーの設定
            logger.debug("Seleniumドライバーの設定を開始")
            self.setup_driver()
            logger.debug("Seleniumドライバーの設定が完了しました")

            # ログインが必要な場合はログインを実行
            if self.credentials:
                logger.info("ログイン処理を開始")
                if not self.login():
                    raise Exception("ログインに失敗しました")
                logger.info("ログイン処理が完了しました")
            else:
                logger.info("認証情報が設定されていないため、ログインをスキップします")

            # 全ての物件情報を格納するリスト
            all_properties = []
            total_count = 0
            page = 1

            while True:
                # 物件一覧ページにアクセス
                if page > 1:
                    page_url = f"https://www.jpm-co.jp/chukai/bukken/list/all/?page={page}"
                    logger.info(f"{page}ページ目にアクセス: {page_url}")
                    self.driver.get(page_url)
                    time.sleep(2)  # ページ読み込み待機

                try:
                    # 物件一覧の行を取得
                    property_rows = self.driver.find_elements(By.CSS_SELECTOR, "table.s_ttl.v-m tbody tr")
                    
                    # 物件がない場合は終了
                    if not property_rows:
                        logger.info(f"ページ{page}に物件が見つかりませんでした。スクレイピングを終了します。")
                        break
                    
                    property_count = len(property_rows)
                    total_count += property_count
                    logger.info(f"ページ{page}の物件数: {property_count}件")

                    # 物件情報を格納するリスト
                    properties = []

                    # 各物件の詳細ページにアクセス
                    for row in property_rows:
                        try:
                            # 物件名のリンクを取得
                            link = row.find_element(By.CSS_SELECTOR, "td div.t-l a")
                            property_url = link.get_attribute("href")
                            property_name = link.text.strip()
                            
                            # 物件情報を初期化
                            property_info = {
                                "物件名": property_name,
                                "URL": property_url
                            }
                            
                            # 管理番号を取得
                            try:
                                management_number = row.find_element(By.CSS_SELECTOR, "td[title='管理番号']").text.strip()
                                property_info["管理番号"] = management_number  # 管理番号を追加
                                
                                # 処理済みの物件IDの場合はスキップ
                                if self.is_property_processed(management_number):
                                    logger.info(f"管理番号 {management_number} の物件は既に処理済みのためスキップします")
                                    # アクティブ物件として更新
                                    self.property_history["active_properties"][management_number] = {
                                        "property_name": property_name,
                                        "last_seen": datetime.now().isoformat()
                                    }
                                    self.save_property_history()
                                    continue
                                
                                logger.info(f"物件「{property_name}」(管理番号: {management_number})のページにアクセス: {property_url}")
                            except Exception as e:
                                logger.error(f"管理番号の取得に失敗: {str(e)}")
                                continue
                            
                            # 新しいタブで開く
                            self.driver.execute_script("window.open(arguments[0], '_blank');", property_url)
                            
                            # 新しいタブに切り替え
                            self.driver.switch_to.window(self.driver.window_handles[-1])
                            
                            # ページの読み込みを待機
                            try:
                                # まずページ全体の読み込みを待機
                                WebDriverWait(self.driver, 10).until(
                                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                                )
                                
                                # 明示的な待機を追加
                                time.sleep(3)
                                
                                # テーブルの存在を確認
                                table_present = False
                                try:
                                    table = WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
                                    )
                                    table_present = True
                                except TimeoutException:
                                    pass

                                if not table_present:
                                    # テーブルが見つからない場合は削除された物件として記録
                                    deleted_info = {
                                        "管理番号": management_number,
                                        "status": "deleted",
                                        "url": property_url,
                                        "last_check_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "message": "物件情報が見つかりません（削除された可能性があります）"
                                    }
                                    # 削除された物件の情報を保存
                                    deleted_dir = os.path.join(self.data_dir, "deleted")
                                    os.makedirs(deleted_dir, exist_ok=True)
                                    file_path = os.path.join(deleted_dir, f"{management_number}.json")
                                    try:
                                        with open(file_path, "w", encoding="utf-8") as f:
                                            json.dump(deleted_info, f, ensure_ascii=False, indent=2)
                                        logger.warning(f"削除された物件として記録しました: {file_path}")
                                    except Exception as e:
                                        logger.error(f"削除物件情報の保存中にエラーが発生: {str(e)}")
                                    
                                    # タブを閉じて物件一覧に戻る
                                    self.driver.close()
                                    self.driver.switch_to.window(self.driver.window_handles[0])
                                    continue
                                
                            except Exception as e:
                                logger.error(f"ページの読み込み中にエラーが発生: {str(e)}")
                                # エラーが発生した場合、タブを閉じて物件一覧に戻る
                                if len(self.driver.window_handles) > 1:
                                    self.driver.close()
                                    self.driver.switch_to.window(self.driver.window_handles[0])
                                continue
                            
                            # 物件情報を取得
                            # property_info = {}  # この行を削除
                            
                            # 緯度/経度を取得
                            try:
                                # ページのソースを取得
                                page_source = self.driver.page_source
                                # 緯度/経度を含む行を探す
                                latlng_match = re.search(r'var\s+latlng\s*=\s*new\s+google\.maps\.LatLng\(([\d.]+),\s*([\d.]+)\)', page_source)
                                if latlng_match:
                                    lat = float(latlng_match.group(1))
                                    lng = float(latlng_match.group(2))
                                    property_info["緯度"] = lat
                                    property_info["経度"] = lng
                                    logger.info(f"緯度/経度を取得: {lat}, {lng}")
                            except Exception as e:
                                logger.error(f"緯度/経度の取得中にエラーが発生: {str(e)}")
                                property_info["緯度"] = None
                                property_info["経度"] = None
                            
                            # ポイント情報を取得
                            try:
                                point_div = self.driver.find_element(By.CSS_SELECTOR, "div.point")
                                points = []
                                for p in point_div.find_elements(By.CSS_SELECTOR, "p"):
                                    point_text = p.text.strip()
                                    if point_text:
                                        points.append(point_text)
                                if points:
                                    property_info["ポイント"] = points
                                    logger.info(f"ポイント情報を取得: {points}")
                            except NoSuchElementException:
                                logger.info("ポイント情報はありません")
                                property_info["ポイント"] = []
                            except Exception as e:
                                logger.error(f"ポイント情報の取得中にエラーが発生: {str(e)}")
                                property_info["ポイント"] = []
                            
                            # テーブルから情報を取得
                            try:
                                # すべてのテーブルを取得
                                tables = self.driver.find_elements(By.CSS_SELECTOR, "table")
                                logger.info(f"{len(tables)}個のテーブルを検出しました")
                                
                                for table_index, table in enumerate(tables, 1):
                                    logger.info(f"テーブル{table_index}の処理を開始")
                                    
                                    # デバッグ用：テーブルのHTML構造を出力
                                    table_html = table.get_attribute('outerHTML')
                                    logger.debug(f"テーブル{table_index}のHTML構造: {table_html}")
                                    
                                    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
                                    logger.info(f"テーブル{table_index}から{len(rows)}行の情報を取得します")
                                    
                                    # 各行から情報を取得
                                    for row in rows:
                                        try:
                                            cells = row.find_elements(By.CSS_SELECTOR, "th, td")
                                            logger.debug(f"行のセル数: {len(cells)}")
                                            
                                            for i in range(0, len(cells), 2):
                                                if i + 1 < len(cells):
                                                    key = cells[i].text.strip()
                                                    value = cells[i + 1].text.strip()
                                                    logger.info(f"取得した項目: {key} = {value}")
                                                    
                                                    # キーを英語に変換
                                                    key_mapping = {
                                                        "管理番号": "管理番号",
                                                        "価格": "価格",
                                                        "専有面積": "専有面積",
                                                        "築年月": "築年月",
                                                        "構造・所在階": "構造・所在階",
                                                        "管理会社名": "管理会社名",
                                                        "管理費": "管理費",
                                                        "現況": "現況",
                                                        "駐車場": "駐車場",
                                                        "建物名・号室": "建物名・号室",
                                                        "部屋数・間取り": "部屋数・間取り",
                                                        "土地権利": "土地権利",
                                                        "総戸数": "total_units",
                                                        "管理形態": "管理形態",
                                                        "修繕積立金": "修繕積立金",
                                                        "引渡日": "引渡日",
                                                        "バルコニー面積": "バルコニー面積",
                                                        "駐車場（月額）": "駐車場（月額）",
                                                        "所在地": "所在地",
                                                        "アクセス": "アクセス",
                                                        "面積/間取り": "面積/間取り",
                                                        "補足": "補足"
                                                    }
                                                    
                                                    if key in key_mapping:
                                                        mapped_key = key_mapping[key]
                                                        logger.debug(f"キーのマッピング: {key} -> {mapped_key}")
                                                        
                                                        if key == "アクセス":
                                                            # アクセス情報の処理（既存のコード）
                                                            access_html = cells[i + 1].get_attribute('innerHTML')
                                                            logger.info(f"アクセス情報のHTML: {access_html}")
                                                            
                                                            access_lines = access_html.split('<br>')
                                                            logger.info(f"アクセス情報の分割結果: {access_lines}")
                                                            
                                                            access_info = []
                                                            for line in access_lines:
                                                                line = re.sub(r'<[^>]+>', '', line).strip()
                                                                line = line.replace('\n', '').replace('\r', '')
                                                                logger.info(f"アクセス情報の行: {line}")
                                                                
                                                                if line:
                                                                    route_match = re.match(r'【路線(\d+)】(.+?)駅?\s*徒歩(\d+)分', line)
                                                                    if route_match:
                                                                        route_info = {
                                                                            "番号": int(route_match.group(1)),
                                                                            "駅名": route_match.group(2).strip(),
                                                                            "徒歩": int(route_match.group(3))
                                                                        }
                                                                        access_info.append(route_info)
                                                                        logger.info(f"解析したアクセス情報: {route_info}")
                                                                    else:
                                                                        logger.warning(f"アクセス情報のパターンが一致しません: {line}")
                                                                        access_info.append({"raw_text": line})
                                                            
                                                            if access_info:
                                                                property_info[mapped_key] = access_info
                                                                logger.info(f"最終的なアクセス情報: {access_info}")
                                                        elif key == "面積/間取り":
                                                            area_layout = value.split('/')
                                                            if len(area_layout) == 2:
                                                                property_info["面積"] = area_layout[0].strip()
                                                                property_info["間取り"] = area_layout[1].strip()
                                                        elif key == "補足":
                                                            notes = value.split('\n')
                                                            notes_info = [note.strip() for note in notes if note.strip()]
                                                            property_info[mapped_key] = notes_info
                                                            logger.info(f"補足情報を取得: {notes_info}")
                                                        else:
                                                            property_info[mapped_key] = value
                                                            logger.info(f"保存した項目: {mapped_key} = {value}")
                                                    else:
                                                        logger.warning(f"マッピングされていない項目: {key}")
                                        except Exception as e:
                                            logger.error(f"行の処理中にエラーが発生: {str(e)}")
                                            continue
                                    
                                    logger.info(f"テーブル{table_index}の処理が完了")
                                
                            except Exception as e:
                                logger.error(f"テーブルの処理中にエラーが発生: {str(e)}")
                                logger.error(f"ページのHTML: {self.driver.page_source}")
                            
                            # 画像情報を取得
                            try:
                                image_list = self.driver.find_element(By.CSS_SELECTOR, "ul#paging")
                                image_items = image_list.find_elements(By.CSS_SELECTOR, "li")
                                
                                # 画像保存用のディレクトリを作成
                                images_dir = os.path.join(self.data_dir, management_number)
                                os.makedirs(images_dir, exist_ok=True)
                                
                                # 画像情報を格納するリスト
                                images = []
                                
                                for i, item in enumerate(image_items, 1):
                                    try:
                                        img = item.find_element(By.CSS_SELECTOR, "img")
                                        img_url = img.get_attribute("src")
                                        img_alt = img.get_attribute("alt")
                                        
                                        # URLから元のファイル名を取得してデコード
                                        encoded_filename = os.path.basename(img_url)
                                        original_filename = urllib.parse.unquote(encoded_filename)
                                        save_path = os.path.join(images_dir, original_filename)
                                        
                                        # 画像をダウンロード
                                        if self.download_image(img_url, save_path):
                                            image_info = {
                                                "番号": i,
                                                "ファイル名": original_filename,
                                                "alt": img_alt,
                                                "url": img_url
                                            }
                                            images.append(image_info)
                                            logger.info(f"画像をダウンロードしました: {original_filename}")
                                    except Exception as e:
                                        logger.error(f"画像情報の取得中にエラーが発生: {str(e)}")
                                
                                # 画像情報を物件情報に追加
                                property_info["images"] = images
                                
                            except Exception as e:
                                logger.error(f"画像リストの取得中にエラーが発生: {str(e)}")
                                property_info["images"] = []

                            logger.info(f"物件情報を取得: {property_info}")
                            properties.append(property_info)
                            
                            # 物件を処理済みとしてマーク
                            self.mark_property_as_processed(management_number, property_info)
                            
                            # 管理番号.jsonとして保存
                            if "管理番号" in property_info:
                                management_number = property_info["管理番号"]
                                file_path = os.path.join(self.data_dir, f"{management_number}.json")
                                try:
                                    with open(file_path, "w", encoding="utf-8") as f:
                                        json.dump(property_info, f, ensure_ascii=False, indent=2)
                                    
                                    # 更新物件情報を保存
                                    save_updated_properties(file_path)

                                    logger.info(f"物件情報を保存しました: {file_path}")
                                except Exception as e:
                                    logger.error(f"物件情報の保存中にエラーが発生: {str(e)}")
                            
                            # タブを閉じて物件一覧に戻る
                            self.driver.close()
                            self.driver.switch_to.window(self.driver.window_handles[0])
                            
                            # 次の物件に進む前に少し待機
                            time.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"物件詳細ページへのアクセス中にエラーが発生: {str(e)}")
                            # エラーが発生した場合、メインウィンドウに戻る
                            if len(self.driver.window_handles) > 1:
                                self.driver.close()
                                self.driver.switch_to.window(self.driver.window_handles[0])
                            continue

                    # 全ての物件情報を格納するリストに追加
                    all_properties.extend(properties)
                    
                    # 次のページへ
                    page += 1

                except Exception as e:
                    logger.error(f"ページ{page}の処理中にエラーが発生: {str(e)}")
                    break

            # 削除された物件を検出
            current_property_ids = {p["管理番号"] for p in all_properties if "管理番号" in p}
            active_property_ids = set(self.property_history["active_properties"].keys())
            deleted_property_ids = active_property_ids - current_property_ids
            
            # 削除された物件を処理
            for property_id in deleted_property_ids:
                self.mark_property_as_deleted(property_id)
            
            return {
                "status": "success",
                "message": "全ページの物件情報の取得に成功しました",
                "total_pages": page - 1,
                "total_property_count": total_count,
                "properties": all_properties,
                "history": {
                    "active_count": len(self.property_history["active_properties"]),
                    "deleted_count": len(self.property_history["deleted_properties"]),
                    "processed_count": len(self.property_history["processed_properties"])
                }
            }

        except Exception as e:
            logger.error(f"スクレイピング中にエラーが発生: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
        finally:
            # ブラウザを閉じる
            if self.driver:
                logger.debug("ブラウザを閉じます")
                self.driver.quit()
                logger.debug("ブラウザを閉じました") 