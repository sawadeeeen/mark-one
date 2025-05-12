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
from datetime import datetime
from pathlib import Path
import requests
from urllib.parse import urlparse

from utils import save_updated_properties

logger = logging.getLogger(__name__)

class FstageScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        """
        Fstageのスクレイパーを初期化します。

        Args:
            credentials (Optional[Dict[str, str]]): ログイン認証情報
                - user_id: ログインID（携帯番号）
                - password: パスワード
        """
        self.base_url = "https://naiken.fstage.co.jp"
        self.login_url = f"{self.base_url}/login"
        self.all_area_url = f"{self.base_url}/bukkens/result?areas%5B%5D=all"
        self.driver = None
        self.data_dir = "data/fstage"
        # データ保存用ディレクトリの作成
        os.makedirs(self.data_dir, exist_ok=True)
        # 物件履歴ファイルのパスを設定
        self.history_file = os.path.join(self.data_dir, "property_history.json")
        # 物件履歴を初期化
        self.property_history = self._load_property_history()
        
        # 認証情報を設定
        self.credentials = self._format_credentials(credentials) if credentials else {}
        logger.debug("Fstageスクレイパーを初期化しました")

    def _format_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """
        認証情報を内部形式に変換します。

        Args:
            credentials (Dict[str, str]): 外部から受け取った認証情報

        Returns:
            Dict[str, str]: 内部形式の認証情報
        """
        return {
            "keitai": credentials.get("user_id", ""),
            "password": credentials.get("password", "")
        }

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
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(10)  # 暗黙的な待機を設定

    def login(self) -> bool:
        """
        Fstageにログインします。

        Returns:
            bool: ログイン成功時True、失敗時False
        """
        if not self.credentials or not self.credentials.get("keitai") or not self.credentials.get("password"):
            logger.error("認証情報が不正です")
            return False

        try:
            # ログインページにアクセス
            self.driver.get(self.login_url)
            logger.info("ログインページにアクセスしました")

            # CSRFトークンを取得
            csrf_token = self.driver.find_element(By.CSS_SELECTOR, "input[name='_token']").get_attribute('value')
            logger.debug(f"CSRFトークンを取得: {csrf_token}")

            # 携帯番号とパスワードを入力
            keitai_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='keitai']")
            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='password']")

            keitai_input.send_keys(self.credentials["keitai"])
            password_input.send_keys(self.credentials["password"])
            logger.info("認証情報を入力しました")

            # ログインボタンをクリック
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "button.btn-blue31")
            submit_button.click()
            logger.info("ログインボタンをクリックしました")

            # ログイン成功の確認（URLの変更で判定）
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda driver: driver.current_url != self.login_url
                )
                logger.info("ログインに成功しました")
                return True
            except TimeoutException:
                logger.error("ログイン後のリダイレクトがタイムアウトしました")
                return False

        except Exception as e:
            logger.error(f"ログイン中にエラーが発生: {str(e)}")
            return False

    def navigate_to_all_area(self) -> bool:
        """
        すべてのエリアページに移動します。

        Returns:
            bool: 移動成功時True、失敗時False
        """
        try:
            # すべてのエリアリンクを探して直接クリック
            try:
                all_area_link = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.property-index__list-item[href*='areas%5B%5D=all']"))
                )
                all_area_link.click()
                logger.info("「すべてのエリア」リンクをクリックしました")
            except TimeoutException:
                # リンクが見つからない場合は直接URLにアクセス
                logger.warning("「すべてのエリア」リンクが見つかりません。直接URLにアクセスします")
                self.driver.get(self.all_area_url)
                logger.info("「すべてのエリア」ページに直接アクセスしました")

            # ページ遷移の完了を待機
            WebDriverWait(self.driver, 10).until(
                lambda driver: "bukkens/result" in driver.current_url
            )
            logger.info("物件一覧ページへの遷移が完了しました")
            return True

        except Exception as e:
            logger.error(f"「すべてのエリア」ページへの移動中にエラーが発生: {str(e)}")
            return False

    def find_and_click_property(self, property_id: str) -> bool:
        """
        指定された物件IDの物件を見つけてクリックします。

        Args:
            property_id (str): 物件ID

        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            # 物件リンクを探す
            property_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f"a[href*='/bukkens/{property_id}']"))
            )
            
            # リンクが表示されるまでスクロール
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", property_link)
            time.sleep(1)  # スクロールの完了を待つ

            # リンクがクリック可能になるまで待機
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f"a[href*='/bukkens/{property_id}']"))
            )

            # リンクをクリック
            property_link.click()
            logger.info(f"物件ID {property_id} のリンクをクリックしました")

            # 物件詳細ページへの遷移を確認
            WebDriverWait(self.driver, 10).until(
                lambda driver: f"/bukkens/{property_id}" in driver.current_url
            )
            logger.info("物件詳細ページへの遷移が完了しました")
            return True

        except Exception as e:
            logger.error(f"物件ID {property_id} のリンクのクリック中にエラーが発生: {str(e)}")
            return False

    def _split_property_name(self, full_name: str) -> Dict[str, str]:
        """
        物件名から建物名と部屋番号を分割します。

        Args:
            full_name (str): 完全な物件名

        Returns:
            Dict[str, str]: 分割された建物名と部屋番号
        """
        import re
        
        # 末尾の部屋番号を検索（○○○号室のパターン）
        room_match = re.search(r'\s*\d+号室\s*$', full_name)
        
        if room_match:
            # マッチした部分を取得し、前後の空白を削除
            room_number = room_match.group().strip()
            # 建物名は物件名から部屋番号を除いた部分
            building_name = full_name[:room_match.start()].strip()
            logger.info(f"物件名を分割: 建物名={building_name}, 部屋番号={room_number}")
        else:
            # 部屋番号が見つからない場合
            building_name = full_name.strip()
            room_number = ""
            logger.info(f"部屋番号なしの物件: 建物名={building_name}")

        return {
            "building_name": building_name,
            "room_number": room_number
        }

    def _parse_transportation(self, transport_text: str) -> list:
        """
        交通情報を解析して構造化データに変換します。

        Args:
            transport_text (str): 交通情報のテキスト

        Returns:
            list: 交通情報の配列
        """
        try:
            # 各行を分割
            transport_lines = [line.strip() for line in transport_text.split('\n') if line.strip()]
            transport_data = []

            for line in transport_lines:
                # ◆を削除
                line = line.replace('◆', '').strip()
                
                # 路線名・駅名と徒歩時間を分割
                parts = line.split('徒歩')
                if len(parts) == 2:
                    station_info = parts[0].strip()
                    walking_time = parts[1].replace('分', '').strip()
                    
                    # 路線名と駅名を分割
                    station_parts = station_info.split('「')
                    if len(station_parts) == 2:
                        line_name = station_parts[0].strip()
                        station_name = station_parts[1].replace('」', '').strip()
                        
                        transport_data.append({
                            "路線名": line_name,
                            "駅名": station_name,
                            "徒歩時間": int(walking_time)
                        })

            logger.info(f"交通情報を解析: {transport_data}")
            return transport_data
        except Exception as e:
            logger.error(f"交通情報の解析中にエラーが発生: {str(e)}")
            return []

    def _download_and_save_images(self, property_number: str) -> list:
        """
        物件画像をダウンロードして保存します。

        Args:
            property_number (str): 物件番号

        Returns:
            list: 保存した画像情報のリスト
        """
        try:
            # 画像保存用のディレクトリを作成
            image_dir = os.path.join(self.data_dir, property_number)
            os.makedirs(image_dir, exist_ok=True)
            
            # 画像要素を取得
            image_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.property-detail__slider-thumb-item-img img")
            saved_images = []
            
            for index, img in enumerate(image_elements, 1):
                try:
                    # 画像URLを取得
                    image_url = img.get_attribute('src')
                    if not image_url:
                        continue
                    
                    # ファイル名を生成（URLの最後の部分を使用）
                    original_filename = os.path.basename(urlparse(image_url).path)
                    file_extension = os.path.splitext(original_filename)[1]
                    filename = f"{index:03d}{file_extension}"
                    filepath = os.path.join(image_dir, filename)
                    
                    # 画像をダウンロード
                    response = requests.get(image_url, stream=True)
                    if response.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(1024):
                                f.write(chunk)
                        
                        # 保存した画像の情報を記録
                        saved_images.append({
                            "filename": filename,
                            "original_url": image_url
                        })
                        logger.info(f"画像を保存しました: {filepath}")
                    else:
                        logger.warning(f"画像のダウンロードに失敗: {image_url}")
                
                except Exception as e:
                    logger.warning(f"画像の保存中にエラー: {str(e)}")
                    continue
            
            return saved_images
            
        except Exception as e:
            logger.error(f"画像の保存中にエラーが発生: {str(e)}")
            return []

    def get_property_details(self) -> Dict[str, Any]:
        """
        物件詳細ページから物件情報を取得します。

        Returns:
            Dict[str, Any]: 物件情報
        
        Raises:
            Exception: 物件が契約予定の場合
        """
        try:
            # 契約予定かどうかをチェック
            reserve_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.reserve-complete__title")
            if reserve_elements and "契約予定" in reserve_elements[0].text:
                logger.info("この物件は契約予定です")
                raise Exception("この物件は契約予定です")

            # 物件名を取得
            full_property_name = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.property-detail__title"))
            ).text
            logger.info(f"物件名を取得: {full_property_name}")

            # 物件名を建物名と部屋番号に分割
            name_parts = self._split_property_name(full_property_name)

            # 物件番号を取得（「物件番号：」の部分を除去）
            property_number = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.property-detail__no"))
            ).text.replace("物件番号：", "")
            logger.info(f"物件番号を取得: {property_number}")

            # 販売価格を取得
            price_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.property-detail__price-main"))
            )
            price = price_element.find_element(By.CSS_SELECTOR, "span").text
            price_unit = price_element.find_element(By.CSS_SELECTOR, "small").text
            full_price = f"{price}{price_unit}"
            logger.info(f"販売価格を取得: {full_price}")

            # 修繕積立金と管理費を取得
            maintenance_fee = ""
            management_fee = ""
            fee_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.property-detail__price-sub-wrap > div")
            for element in fee_elements:
                label = element.find_element(By.CSS_SELECTOR, "span").text
                value = element.find_element(By.CSS_SELECTOR, "b").text
                if "修繕積立金" in label:
                    maintenance_fee = value
                    logger.info(f"修繕積立金を取得: {maintenance_fee}")
                elif "管理費" in label:
                    management_fee = value
                    logger.info(f"管理費を取得: {management_fee}")

            # 物件詳細情報を取得
            info_items = {}
            detail_elements = self.driver.find_elements(By.CSS_SELECTOR, "dl.property-detail__info-items > div")
            for element in detail_elements:
                try:
                    label = element.find_element(By.CSS_SELECTOR, "dt").text
                    value = element.find_element(By.CSS_SELECTOR, "dd").text.strip()
                    
                    # 専有面積と間取りの場合、分割して保存
                    if "専有面積" in label and "間取り" in label:
                        area, layout = value.split("|")
                        info_items["専有面積"] = area.strip()
                        info_items["間取り"] = layout.strip()
                    # 階建 / 階数の場合、分割して保存
                    elif "階建 / 階数" in label:
                        info_items["階建"] = value
                    # その他の情報はそのまま保存
                    else:
                        # ラベルから不要な文字を削除
                        clean_label = label.split("|")[0].strip()
                        info_items[clean_label] = value
                    
                    logger.info(f"{label}: {value}")
                except Exception as e:
                    logger.warning(f"詳細情報の取得中にエラー: {str(e)}")
                    continue

            # 交通情報を解析
            if "交通" in info_items:
                info_items["交通"] = self._parse_transportation(info_items["交通"])

            # 画像情報を取得して保存
            images = self._download_and_save_images(property_number)
            
            # 基本情報と詳細情報を結合（画像情報を追加）
            property_info = {
                "property_name": full_property_name,
                "building_name": name_parts["building_name"],
                "room_number": name_parts["room_number"],
                "property_number": property_number,
                "price": full_price,
                "maintenance_fee": maintenance_fee,
                "management_fee": management_fee,
                "images": images,  # 画像情報を追加
                **{k: v for k, v in info_items.items()}
            }

            return property_info

        except Exception as e:
            logger.error(f"物件情報の取得中にエラーが発生: {str(e)}")
            return {
                "property_name": "",
                "building_name": "",
                "room_number": "",
                "property_number": "",
                "price": "",
                "maintenance_fee": "",
                "management_fee": "",
                "専有面積": "",
                "間取り": "",
                "築年月": "",
                "所在地": "",
                "交通": [],
                "階建": "",
                "エレベータ": "",
                "images": []
            }

    def save_property_data(self, property_data: Dict[str, Any]) -> bool:
        """
        物件情報をJSONファイルとして保存します。

        Args:
            property_data (Dict[str, Any]): 保存する物件情報

        Returns:
            bool: 保存成功時True、失敗時False
        """
        try:
            if not property_data.get("property_number"):
                logger.error("物件番号が取得できていないため、保存をスキップします")
                return False

            # 保存するデータを作成（画像情報を追加）
            save_data = {
                "物件名": property_data.get("property_name", ""),
                "建物名": property_data.get("building_name", ""),
                "部屋番号": property_data.get("room_number", ""),
                "物件番号": property_data.get("property_number", ""),
                "販売価格": property_data.get("price", ""),
                "修繕積立金": property_data.get("maintenance_fee", ""),
                "管理費": property_data.get("management_fee", ""),
                "専有面積": property_data.get("専有面積", ""),
                "間取り": property_data.get("間取り", ""),
                "築年月": property_data.get("築年月", ""),
                "所在地": property_data.get("所在地", ""),
                "交通": property_data.get("交通", []),
                "階建": property_data.get("階建", ""),
                "エレベータ": property_data.get("エレベータ", ""),
                "画像": property_data.get("images", []),
                "スクレイピング日時": datetime.now().isoformat()
            }

            # ファイル名を設定
            filename = os.path.join(self.data_dir, f"{property_data['property_number']}.json")

            # JSONファイルとして保存
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)

            # 更新物件情報を保存
            save_updated_properties(filename)

            logger.info(f"物件情報を保存しました: {filename}")
            return True

        except Exception as e:
            logger.error(f"物件情報の保存中にエラーが発生: {str(e)}")
            return False

    def return_to_list(self) -> bool:
        """
        物件一覧画面に戻ります。

        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            # ブラウザの戻るボタンを実行
            self.driver.execute_script("window.history.back();")
            
            # 物件一覧ページに戻ったことを確認
            WebDriverWait(self.driver, 10).until(
                lambda driver: "bukkens/result" in driver.current_url
            )
            logger.info("物件一覧ページに戻りました")
            return True

        except Exception as e:
            logger.error(f"物件一覧ページへの戻り中にエラーが発生: {str(e)}")
            return False

    def get_all_property_ids_in_page(self) -> list:
        """
        現在のページの全物件IDを取得します。

        Returns:
            list: 物件IDのリスト
        """
        try:
            # 物件リンクを全て取得
            property_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/bukkens/']")
            property_ids = []
            
            for link in property_links:
                try:
                    href = link.get_attribute('href')
                    # /bukkens/{id} の形式からIDを抽出
                    if '/bukkens/' in href:
                        property_id = href.split('/bukkens/')[-1]
                        if property_id.isdigit():
                            property_ids.append(property_id)
                except Exception as e:
                    logger.warning(f"物件リンクの解析中にエラー: {str(e)}")
                    continue
            
            logger.info(f"現在のページから{len(property_ids)}件の物件IDを取得しました")
            return property_ids
        except Exception as e:
            logger.error(f"物件ID取得中にエラーが発生: {str(e)}")
            return []

    def navigate_to_next_page(self) -> bool:
        """
        次のページに移動します。
        ページネーションのリンクから次のページの存在を判断し、存在する場合は移動します。

        Returns:
            bool: 次のページが存在しTrue、存在しない場合False
        """
        try:
            # 現在のページ番号を取得
            current_url = self.driver.current_url
            current_page = 1
            if "page=" in current_url:
                current_page = int(current_url.split("page=")[1].split("&")[0])
            
            logger.info(f"現在のページ: {current_page}")
            
            # ページネーションのリンクを取得
            pagination_links = self.driver.find_elements(By.CSS_SELECTOR, "div.common-pagination__inner a[href*='page=']")
            next_page_url = None
            
            # 次のページ番号のURLを探す
            for link in pagination_links:
                href = link.get_attribute("href")
                if "page=" in href:
                    page_num = int(href.split("page=")[1].split("&")[0])
                    if page_num == current_page + 1:
                        next_page_url = href
                        break
            
            if not next_page_url:
                logger.info("次のページは存在しません")
                return False

            logger.info(f"次のページのURL: {next_page_url}")
            
            # 次のページに移動
            self.driver.get(next_page_url)
            time.sleep(2)  # ページ読み込みを待機
            
            # ページ遷移の完了を待機
            expected_page = current_page + 1
            WebDriverWait(self.driver, 10).until(
                lambda driver: (
                    "bukkens/result" in driver.current_url and
                    f"page={expected_page}" in driver.current_url and
                    len(driver.find_elements(By.CSS_SELECTOR, "a[href*='/bukkens/']")) > 0
                )
            )
            
            logger.info(f"ページ {expected_page} に移動しました")
            return True

        except Exception as e:
            logger.error(f"次ページへの移動中にエラーが発生: {str(e)}")
            return False

    def _load_property_history(self) -> Dict[str, str]:
        """
        物件履歴を読み込みます。

        Returns:
            Dict[str, str]: 物件履歴（キー：物件ID、値：ステータス）
        """
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"物件履歴の読み込み中にエラーが発生: {str(e)}")
            return {}

    def _save_property_history(self) -> bool:
        """
        物件履歴を保存します。

        Returns:
            bool: 保存成功時True、失敗時False
        """
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.property_history, f, ensure_ascii=False, indent=2)
            logger.info("物件履歴を保存しました")
            return True
        except Exception as e:
            logger.error(f"物件履歴の保存中にエラーが発生: {str(e)}")
            return False

    def _update_property_history(self, property_id: str, status: str = "active") -> None:
        """
        物件履歴を更新します。

        Args:
            property_id (str): 物件ID
            status (str): ステータス（"active" または "deleted"）
        """
        self.property_history[property_id] = status
        self._save_property_history()

    def scrape_all_properties(self) -> Dict[str, Any]:
        """
        全ページの物件情報をスクレイピングします。

        Returns:
            Dict[str, Any]: スクレイピング結果
        """
        try:
            # ドライバーの設定
            self.setup_driver()

            # ログイン
            if not self.login():
                raise Exception("ログインに失敗しました")

            # すべてのエリアページに移動
            if not self.navigate_to_all_area():
                raise Exception("物件一覧ページへの移動に失敗しました")

            total_scraped = 0
            page_number = 1
            found_property_ids = set()  # スクレイピングで見つかった物件IDを記録
            
            while True:
                logger.info(f"ページ {page_number} のスクレイピングを開始します")
                
                # 現在のページの全物件IDを取得
                property_ids = self.get_all_property_ids_in_page()
                
                # 各物件の詳細を取得
                for property_id in property_ids:
                    try:
                        # 物件IDを見つかったリストに追加
                        found_property_ids.add(property_id)
                        
                        # 既にスクレイピング済みの物件はスキップ
                        if property_id in self.property_history and self.property_history[property_id] == "active":
                            logger.info(f"物件ID {property_id} は既にスクレイピング済みのためスキップします")
                            continue
                        
                        if self.find_and_click_property(property_id):
                            try:
                                property_details = self.get_property_details()
                                if self.save_property_data(property_details):
                                    total_scraped += 1
                                    # 物件履歴を更新
                                    self._update_property_history(property_id, "active")
                            except Exception as e:
                                if "契約予定です" in str(e):
                                    logger.info(f"物件ID {property_id} は契約予定のため、削除済みとしてマーク")
                                    self._update_property_history(property_id, "deleted")
                                else:
                                    logger.error(f"物件ID {property_id} のスクレイピング中にエラー: {str(e)}")
                            
                            # 一覧ページに戻る
                            if not self.return_to_list():
                                logger.warning("物件一覧ページへの戻りに失敗しました")
                                continue
                    except Exception as e:
                        logger.error(f"物件ID {property_id} のスクレイピング中にエラー: {str(e)}")
                        continue

                logger.info(f"ページ {page_number} のスクレイピングが完了しました")
                
                # 次のページが存在する場合は移動
                if not self.navigate_to_next_page():
                    logger.info("全ページのスクレイピングが完了しました")
                    break
                
                page_number += 1

            # 見つからなかった物件を削除済みとしてマーク
            for property_id in self.property_history:
                if property_id not in found_property_ids:
                    self._update_property_history(property_id, "deleted")

            return {
                "status": "success",
                "message": "全ページのスクレイピングが完了しました",
                "total_scraped": total_scraped
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
                self.driver.quit()

    def scrape(self, property_id: Optional[str] = None) -> Dict[str, Any]:
        """
        物件情報をスクレイピングします。

        Args:
            property_id (Optional[str]): 特定の物件IDを指定する場合に使用します。

        Returns:
            Dict[str, Any]: スクレイピング結果
        """
        try:
            # ドライバーの設定
            self.setup_driver()

            # ログイン
            if not self.login():
                raise Exception("ログインに失敗しました")

            # すべてのエリアページに移動
            if not self.navigate_to_all_area():
                raise Exception("物件一覧ページへの移動に失敗しました")

            # 特定の物件IDが指定されている場合、その物件をクリック
            if property_id:
                # 既にスクレイピング済みの物件はスキップ
                if property_id in self.property_history and self.property_history[property_id] == "active":
                    logger.info(f"物件ID {property_id} は既にスクレイピング済みのためスキップします")
                    return {
                        "status": "skipped",
                        "message": "既にスクレイピング済みの物件です",
                        "data": None
                    }

                if not self.find_and_click_property(property_id):
                    raise Exception(f"物件ID {property_id} の物件が見つかりませんでした")
                
                # 物件詳細情報を取得
                property_details = self.get_property_details()
                
                # 物件情報をJSONファイルとして保存
                if not self.save_property_data(property_details):
                    logger.warning("物件情報の保存に失敗しました")
                else:
                    # 物件履歴を更新
                    self._update_property_history(property_id, "active")

                # 物件一覧ページに戻る
                if not self.return_to_list():
                    logger.warning("物件一覧ページへの戻りに失敗しました")

                return {
                    "status": "success",
                    "message": "スクレイピングが完了しました",
                    "data": property_details
                }

            # 物件IDが指定されていない場合は全物件をスクレイピング
            return self.scrape_all_properties()

        except Exception as e:
            logger.error(f"スクレイピング中にエラーが発生: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
        finally:
            # ブラウザを閉じる
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    # デバッグ用のコード
    logging.basicConfig(level=logging.DEBUG)
    
    # テスト用の認証情報
    test_credentials = {
        "user_id": "09012345678",
        "password": "test_password"
    }
    
    # スクレイパーのインスタンス化
    scraper = FstageScraper(test_credentials)
    
    # 特定の物件IDのスクレイピングをテスト
    result = scraper.scrape(property_id="4946")
    print(f"単一物件のスクレイピング結果: {result}")
    
    # 全物件のスクレイピングをテスト
    result = scraper.scrape()
    print(f"全物件のスクレイピング結果: {result}") 