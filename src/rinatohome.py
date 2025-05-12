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
import re
from datetime import datetime
from utils import save_updated_properties, get_updated_property_paths

logger = logging.getLogger(__name__)

class RinatohomeScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        """
        リナートのスクレイパーを初期化します。

        Args:
            credentials (Optional[Dict[str, str]]): ログイン認証情報
                - user_id: ユーザーID
                - password: パスワード
        """
        self.credentials = credentials
        self.base_url = "https://rinatohome.co.jp/partner/"
        self.detail_base_url = "https://ub16.mediate.ielove.jp/mediate/newsale/detail/id/"
        self.driver = None
        self.data_dir = "data/rinatohome"
        self.processed_ids_file = os.path.join(self.data_dir, "processed_ids.json")
        # データ保存用ディレクトリの作成
        os.makedirs(self.data_dir, exist_ok=True)
        # 物件履歴ファイルのパスを設定
        self.history_file = os.path.join(self.data_dir, "property_history.json")
        # 物件履歴を読み込み
        self.property_history = self.load_property_history()
        logger.debug("リナートスクレイパーを初期化しました")

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
        リナートにログインします。

        Returns:
            bool: ログイン成功時True、失敗時False
        """
        if not self.credentials:
            logger.error("認証情報が設定されていません")
            return False

        try:
            # パートナーページにアクセス
            self.driver.get(self.base_url)
            logger.info("パートナーページにアクセスしました")

            # 専用サイトへのリンクをクリック
            try:
                # まずリンクのテキストで検索
                link = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '専用サイトはこちら')]"))
                )
            except TimeoutException:
                # リンクのテキストで見つからない場合は、class属性で検索
                link = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.button"))
                )
            
            # リンクのURLを取得してログ出力
            link_url = link.get_attribute('href')
            logger.info(f"専用サイトのURL: {link_url}")
            
            # リンクをクリック
            link.click()
            logger.info("専用サイトへのリンクをクリックしました")

            # 新しいウィンドウが開くのを待機
            time.sleep(2)  # 新しいウィンドウが開くのを待つ
            self.driver.switch_to.window(self.driver.window_handles[-1])  # 最新のウィンドウに切り替え
            logger.info("専用サイトのウィンドウに切り替えました")

            # 元のタブを閉じる
            self.driver.switch_to.window(self.driver.window_handles[0])
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])  # 新しいタブに戻る
            logger.info("元のタブを閉じました")

            # ログインフォームが表示されるのを待機
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='_4407f7df050aca29f5b0c2592fb48e60']"))
            )

            # ユーザーIDとパスワードを入力
            user_id_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='_4407f7df050aca29f5b0c2592fb48e60']")
            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='_81fa5c7af7ae14682b577f42624eb1c0']")

            user_id_input.send_keys(self.credentials["user_id"])
            password_input.send_keys(self.credentials["password"])
            logger.info("認証情報を入力しました")

            # ログインボタンをクリック
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "button.bt_login")
            submit_button.click()
            logger.info("ログインボタンをクリックしました")

            # ログイン成功の確認（l-result__primaryクラスの有無で判定）
            try:
                # ログインフォームが消えることを確認
                WebDriverWait(self.driver, 10).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='_4407f7df050aca29f5b0c2592fb48e60']"))
                )
                logger.info("ログインフォームが消えました")

                # l-result__primaryクラスの要素が表示されることを確認
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".l-result__primary"))
                )
                logger.info("物件一覧ページが表示されました")

                # 現在のURLを確認
                current_url = self.driver.current_url
                logger.info(f"現在のURL: {current_url}")
                
                if "mediate/newsale" in current_url:
                    logger.info("ログインに成功しました")
                    return True
                else:
                    logger.warning(f"予期しないURLに遷移しました: {current_url}")
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

    def get_property_ids(self) -> list:
        """
        物件一覧から物件IDを取得します。

        Returns:
            list: 物件IDのリスト
        """
        try:
            # 物件一覧ページにアクセス
            list_url = "https://ub16.mediate.ielove.jp/mediate/newsale/"
            logger.info(f"物件一覧ページにアクセス開始: {list_url}")
            self.driver.get(list_url)
            logger.info("物件一覧ページにアクセスしました")

            # 物件一覧の読み込みを待機
            logger.debug("物件一覧の読み込みを待機中...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".l-result__primary"))
            )
            logger.debug("物件一覧の読み込みが完了しました")

            # result-list__itemsの数を確認
            items_containers = self.driver.find_elements(By.CSS_SELECTOR, ".result-list__items")
            logger.info(f"result-list__itemsの数: {len(items_containers)}")
            for i, container in enumerate(items_containers, 1):
                logger.info(f"result-list__items {i}: {container.get_attribute('outerHTML')[:200]}...")  # 最初の200文字だけ表示

            # 物件IDを取得
            logger.debug("物件リンクの検索を開始")
            # 物件一覧のコンテナを取得
            items_container = self.driver.find_element(By.CSS_SELECTOR, ".result-list__items")
            logger.debug("物件一覧のコンテナを取得しました")

            # 各物件要素を取得
            property_elements = items_container.find_elements(By.CSS_SELECTOR, ".result-list__item")
            logger.debug(f"物件要素を {len(property_elements)} 件見つけました")
            
            property_ids = []
            for i, element in enumerate(property_elements, 1):
                try:
                    # 各物件要素からリンクを取得
                    link = element.find_element(By.CSS_SELECTOR, "a[href*='/mediate/newsale/detail/id/']")
                    href = link.get_attribute('href')
                    if href:
                        # URLから物件IDを抽出
                        property_id = href.split('/id/')[-1].rstrip('/')
                        property_ids.append(property_id)
                        logger.debug(f"物件 {i}/{len(property_elements)}: ID={property_id}, URL={href}")
                    else:
                        logger.warning(f"物件 {i}/{len(property_elements)}: href属性が見つかりません")
                except NoSuchElementException:
                    logger.warning(f"物件 {i}/{len(property_elements)}: リンクが見つかりません")
                except Exception as e:
                    logger.warning(f"物件 {i}/{len(property_elements)}: 処理中にエラーが発生: {str(e)}")

            logger.info(f"合計{len(property_ids)}件の物件IDを取得しました")
            return property_ids

        except Exception as e:
            logger.error(f"物件IDの取得中にエラーが発生: {str(e)}")
            return []

    def get_property_urls(self) -> list:
        """
        物件一覧から物件URLを取得します。
        重複するURLは除外されます。

        Returns:
            list: 物件URLのリスト
        """
        try:
            # 物件一覧ページにアクセス
            list_url = "https://ub16.mediate.ielove.jp/mediate/newsale/"
            logger.info(f"物件一覧ページにアクセス開始: {list_url}")
            self.driver.get(list_url)
            logger.info("物件一覧ページにアクセスしました")

            # 物件一覧の読み込みを待機
            logger.debug("物件一覧の読み込みを待機中...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".l-result__primary"))
            )
            logger.debug("物件一覧の読み込みが完了しました")

            # 物件URLを取得（重複を除外）
            property_urls = set()  # setを使用して重複を除外
            links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/mediate/newsale/detail/id/']")
            
            for link in links:
                href = link.get_attribute('href')
                if href:
                    property_urls.add(href)  # setに追加（重複は自動的に除外）
                    logger.debug(f"物件URLを取得: {href}")

            # setをlistに変換
            property_urls = list(property_urls)
            logger.info(f"合計{len(property_urls)}件のユニークな物件URLを取得しました")
            return property_urls

        except Exception as e:
            logger.error(f"物件URLの取得中にエラーが発生: {str(e)}")
            return []

    def save_property_data(self, property_id: str, data: Dict[str, Any]) -> bool:
        """
        物件データをJSONファイルとして保存します。

        Args:
            property_id (str): 物件ID
            data (Dict[str, Any]): 保存するデータ

        Returns:
            bool: 保存成功時True、失敗時False
        """
        try:
            # 削除された物件の場合は別ディレクトリに保存
            if data.get("status") == "deleted":
                deleted_dir = os.path.join(self.data_dir, "deleted")
                os.makedirs(deleted_dir, exist_ok=True)
                file_path = os.path.join(deleted_dir, f"{property_id}.json")
            else:
                file_path = os.path.join(self.data_dir, f"{property_id}.json")

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"物件データを保存しました: {file_path}")
            
            # 更新物件情報を保存
            save_updated_properties(file_path)
            return True
        except Exception as e:
            logger.error(f"物件データの保存中にエラーが発生: {str(e)}")
            return False

    def download_image(self, property_id: str, image_url: str, image_type: str) -> Optional[str]:
        """
        画像をダウンロードして保存します。

        Args:
            property_id (str): 物件ID
            image_url (str): 画像のURL
            image_type (str): 画像の種類（間取り、外観など）

        Returns:
            Optional[str]: 保存したファイル名。失敗時はNone
        """
        try:
            # 物件IDのディレクトリを作成
            property_dir = os.path.join(self.data_dir, property_id)
            os.makedirs(property_dir, exist_ok=True)

            # URLからファイル名を取得
            file_name = os.path.basename(image_url)
            if not file_name:
                logger.error("画像URLからファイル名を取得できませんでした")
                return None

            file_path = os.path.join(property_dir, file_name)

            # 画像をダウンロード
            response = requests.get(image_url, stream=True)
            response.raise_for_status()

            # 画像を保存
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.debug(f"画像を保存しました: {file_path}")
            return file_name

        except Exception as e:
            logger.error(f"画像のダウンロード中にエラーが発生: {str(e)}")
            return None

    def scrape_property_details(self, property_id: str) -> Dict[str, Any]:
        """
        物件詳細ページから情報を取得します。

        Args:
            property_id (str): 物件ID

        Returns:
            Dict[str, Any]: 物件情報
        """
        try:
            # ログインページにリダイレクトされているかチェック
            if "login" in self.driver.current_url:
                logger.info("ログインページにリダイレクトされました。再ログインを試みます。")
                if not self.login():
                    raise Exception("再ログインに失敗しました")
                # 物件詳細ページに再度アクセス
                detail_url = f"{self.detail_base_url}{property_id}"
                self.driver.get(detail_url)
                time.sleep(3)  # ページの読み込みを待つ

            # 物件が存在するか確認
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.info__ttl"))
                )
            except TimeoutException:
                logger.warning(f"物件ID {property_id} は削除されています")
                deleted_data = {
                    "property_id": property_id,
                    "status": "deleted",
                    "message": "物件が削除されています",
                    "check_date": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                # 削除された物件用のディレクトリに保存
                deleted_dir = os.path.join(self.data_dir, "deleted")
                os.makedirs(deleted_dir, exist_ok=True)
                deleted_file = os.path.join(deleted_dir, f"{property_id}.json")
                with open(deleted_file, 'w', encoding='utf-8') as f:
                    json.dump(deleted_data, f, ensure_ascii=False, indent=2)
                logger.info(f"削除された物件情報を保存しました: {deleted_file}")
                return deleted_data

            # 物件名を取得
            try:
                property_name_element = self.driver.find_element(By.CSS_SELECTOR, "h1.info__ttl")
                property_name = property_name_element.text.strip()
                room_number = ""
                if "　" in property_name:  # 全角スペースで分割
                    name_parts = property_name.split("　")
                    property_name = name_parts[0]
                    room_number = name_parts[1]
                elif " " in property_name:  # 半角スペースで分割
                    name_parts = property_name.split(" ")
                    property_name = name_parts[0]
                    if len(name_parts) > 1:
                        room_number = name_parts[1]
                elif "&nbsp;" in property_name:  # HTMLの特殊文字で分割
                    name_parts = property_name.split("&nbsp;")
                    property_name = name_parts[0]
                    if len(name_parts) > 1:
                        room_number = name_parts[1]
                logger.debug(f"物件名: {property_name}, 部屋番号: {room_number}")
            except NoSuchElementException:
                logger.warning(f"物件名が見つかりません: {property_id}")
                property_name = ""
                room_number = ""

            # 最終更新日を取得
            update_date = self.driver.find_element(By.CSS_SELECTOR, "p.info__update").text
            logger.debug(f"最終更新日: {update_date}")

            # 物件詳細テーブルから情報を取得
            info_tables = self.driver.find_elements(By.CSS_SELECTOR, "table.ui-table")
            if not info_tables:
                raise Exception("物件詳細テーブルが見つかりません")
            
            # 各テーブルから情報を取得
            property_info = {}
            for info_table in info_tables:
                try:
                    # テーブルのヘッダーを取得
                    headers = info_table.find_elements(By.CSS_SELECTOR, "th")
                    for header in headers:
                        try:
                            header_text = header.text.strip()
                            if not header_text:
                                continue
                                
                            # ヘッダーに対応する値を取得
                            value = header.find_element(By.XPATH, "./following-sibling::td").text.strip()
                            property_info[header_text] = value
                            logger.debug(f"{header_text}: {value}")
                        except NoSuchElementException:
                            continue
                except Exception as e:
                    logger.warning(f"テーブルからの情報取得中にエラーが発生: {str(e)}")
                    continue

            # 「設備・条件」タブをクリックして情報を取得
            try:
                # タブをクリック
                equipment_tab = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.tab__items[aria-controls='tab2']"))
                )
                # タブが表示されるまで待機
                time.sleep(1)
                # JavaScriptを使用してクリック
                self.driver.execute_script("arguments[0].click();", equipment_tab)
                time.sleep(3)  # タブの切り替えを待つ

                # 設備条件の情報を取得
                equipment_tables = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table.ui-table"))
                )
                for table in equipment_tables:
                    try:
                        rows = table.find_elements(By.CSS_SELECTOR, "tr")
                        for row in rows:
                            try:
                                header = row.find_element(By.CSS_SELECTOR, "th")
                                value = row.find_element(By.CSS_SELECTOR, "td")
                                
                                header_text = header.text.strip()
                                value_text = value.text.strip()
                                
                                if header_text and value_text:
                                    property_info[header_text] = value_text
                                    logger.debug(f"設備条件 - {header_text}: {value_text}")
                            except NoSuchElementException:
                                continue
                    except Exception as e:
                        logger.warning(f"設備条件テーブルからの情報取得中にエラーが発生: {str(e)}")
                        continue

                # 「物件詳細」タブに戻る
                basic_tab = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.tab__items[aria-controls='tab1']"))
                )
                # タブが表示されるまで待機
                time.sleep(1)
                # JavaScriptを使用してクリック
                self.driver.execute_script("arguments[0].click();", basic_tab)
                time.sleep(3)  # タブの切り替えを待つ

            except Exception as e:
                logger.error(f"設備条件タブの処理中にエラーが発生: {str(e)}")
                # エラーが発生した場合でも物件詳細タブに戻ることを試みる
                try:
                    # ページをリロードして物件詳細タブに戻る
                    self.driver.refresh()
                    time.sleep(3)
                except Exception as recovery_error:
                    logger.error(f"物件詳細タブへの復帰中にエラーが発生: {str(recovery_error)}")

            # 「取扱会社」タブをクリックして情報を取得
            try:
                # タブをクリック
                company_tab = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.tab__items[aria-controls='tab4']"))
                )
                # タブが表示されるまで待機
                time.sleep(1)
                # JavaScriptを使用してクリック
                self.driver.execute_script("arguments[0].click();", company_tab)
                time.sleep(3)  # タブの切り替えを待つ

                # 取扱会社の情報を取得
                company_tables = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table.ui-table"))
                )
                for table in company_tables:
                    try:
                        rows = table.find_elements(By.CSS_SELECTOR, "tr")
                        for row in rows:
                            try:
                                # 行内のすべてのthとtd要素を取得
                                headers = row.find_elements(By.CSS_SELECTOR, "th")
                                values = row.find_elements(By.CSS_SELECTOR, "td")
                                
                                # 1行に複数のヘッダーと値がある場合の処理
                                for i, header in enumerate(headers):
                                    header_text = header.text.strip()
                                    if not header_text:
                                        continue

                                    # colspan属性がある場合は次の行を処理
                                    if i < len(values):
                                        value = values[i]
                                        value_text = value.text.strip()
                                        if value_text == "-":
                                            value_text = ""
                                        
                                        property_info[header_text] = value_text
                                        logger.debug(f"取扱会社 - {header_text}: {value_text}")
                            except NoSuchElementException:
                                continue
                    except Exception as e:
                        logger.warning(f"取扱会社テーブルからの情報取得中にエラーが発生: {str(e)}")
                        continue

                # 「物件詳細」タブに戻る
                basic_tab = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.tab__items[aria-controls='tab1']"))
                )
                # タブが表示されるまで待機
                time.sleep(1)
                # JavaScriptを使用してクリック
                self.driver.execute_script("arguments[0].click();", basic_tab)
                time.sleep(3)  # タブの切り替えを待つ

            except Exception as e:
                logger.error(f"取扱会社タブの処理中にエラーが発生: {str(e)}")
                # エラーが発生した場合でも物件詳細タブに戻ることを試みる
                try:
                    # ページをリロードして物件詳細タブに戻る
                    self.driver.refresh()
                    time.sleep(3)
                except Exception as recovery_error:
                    logger.error(f"物件詳細タブへの復帰中にエラーが発生: {str(recovery_error)}")

            # 取得した情報を変数に代入
            basic_facilities = property_info.get('基本設備・条件', '')
            kitchen_bathroom = property_info.get('キッチン/バス・トイレ', '')
            interior_furniture = property_info.get('内装/家具・家電/通信', '')
            equipment_structure = property_info.get('設備/構造/リフォーム', '')
            parking_garden = property_info.get('駐車場・駐輪場/庭', '')
            security_conditions = property_info.get('セキュリティ/サービス/条件', '')
            location_land = property_info.get('立地条件/土地', '')
            property_type = property_info.get('物件種目', '')
            building_structure = property_info.get('建物構造', '')
            layout = property_info.get('間取り', '')
            roof_balcony_area = property_info.get('ルーフバルコニー面積', '')
            maintenance_fee = property_info.get('管理費', '')
            key_money = property_info.get('権利金', '')
            land_rights = property_info.get('土地権利', '')
            current_status = property_info.get('現況', '')
            management_type = property_info.get('管理形態', '')
            management_union = property_info.get('管理組合', '')
            parking = property_info.get('駐車場', '')
            other_fees = property_info.get('その他費用', '')
            other_transport = property_info.get('その他交通', '')
            message_to_agent = property_info.get('客付会社様へのメッセージ', '')
            sales_point = property_info.get('セールスポイント', '')
            notes = property_info.get('備考', '')
            built_date = property_info.get('築年月', '')
            floor = property_info.get('所在階', '')
            floor_area = property_info.get('専有面積', '')
            terrace_area = property_info.get('テラス面積', '')
            repair_fund = property_info.get('修繕積立金', '')
            deposit = property_info.get('保証金', '')
            land_area_type = property_info.get('用途地域', '')
            delivery_date = property_info.get('引渡時期', '')
            management_company = property_info.get('管理会社', '')
            bicycle_parking = property_info.get('駐輪場', '')
            address = property_info.get('所在地', '')
            direction = property_info.get('向き', '')
            balcony_area = property_info.get('バルコニー面積', '')
            private_garden_area = property_info.get('専用庭面積', '')
            repair_fund_foundation = property_info.get('修繕積立基金', '')
            road_condition = property_info.get('接道状況', '')
            city_planning = property_info.get('都市計画', '')
            building_confirmation_number = property_info.get('建築確認番号', '')
            manager = property_info.get('管理人', '')
            renovation = property_info.get('リフォーム', '')
            company_name = property_info.get('取扱会社', '')
            phone_number = property_info.get('電話番号', '')
            license_number = property_info.get('免許番号', '')
            company_address = property_info.get('住所', '')
            commission_rate = property_info.get('仲介手数料/分配率', '')
            transaction_type = property_info.get('取引態様', '')
            fax_number = property_info.get('FAX番号', '')

            # 緯度経度を取得
            try:
                # JavaScriptの変数定義を探す
                page_source = self.driver.page_source
                lat_match = re.search(r"map\.showMapFromLatLng\('([^']+)'", page_source)
                lng_match = re.search(r"map\.showMapFromLatLng\('[^']+',\s*'([^']+)'", page_source)
                
                latitude = lat_match.group(1) if lat_match else None
                longitude = lng_match.group(1) if lng_match else None
                
                logger.debug(f"緯度: {latitude}, 経度: {longitude}")
            except Exception as e:
                logger.error(f"緯度経度の取得中にエラーが発生: {str(e)}")
                latitude = None
                longitude = None

            # 画像を取得
            images = []
            image_elements = self.driver.find_elements(By.CSS_SELECTOR, "li.gallery__thum-items img")
            
            for img in image_elements:
                try:
                    # 画像のURLを取得
                    img_url = img.get_attribute('src')
                    if not img_url:
                        continue

                    # 画像の種類を取得（data-note属性から）
                    parent_link = img.find_element(By.XPATH, "./..")
                    image_type = parent_link.get_attribute('data-note').strip()
                    if not image_type:
                        image_type = "その他"
                    
                    # 余分な空白やHTMLタグを削除
                    image_type = image_type.replace('<span>', '').replace('</span>', '').strip()
                    image_type = ' '.join(image_type.split())  # 連続する空白を1つに

                    # 画像をダウンロード
                    file_name = self.download_image(property_id, img_url, image_type)
                    if file_name:
                        images.append({
                            "type": image_type,
                            "file_name": file_name
                        })
                        logger.debug(f"画像情報を取得: 種類={image_type}, ファイル名={file_name}")

                except Exception as e:
                    logger.error(f"画像の取得中にエラーが発生: {str(e)}")
                    continue

            # その他交通を配列形式に変換
            other_transport_array = []
            print(f"other_transport: {other_transport}")
            if other_transport:
                # 全角スペースを半角スペースに変換し、連続するスペースを1つに置換
                other_transport = other_transport.replace('　', ' ')
                other_transport = re.sub(r'\s+', ' ', other_transport).strip()
                
                # 「分 」で分割して各交通情報を取得
                transport_items = other_transport.split('分 ')
                
                for item in transport_items:
                    item = item.strip()
                    if not item:  # 空の項目をスキップ
                        continue
                        
                    # 各交通情報から路線名、駅名、徒歩時間を抽出
                    match = re.match(r'(.+?)「(.+?)」駅\s*徒歩(\d+)', item.strip())
                    if match:
                        route_name = match.group(1).strip()
                        station_name = match.group(2).strip()
                        walking_time = match.group(3).strip()
                        
                        other_transport_array.append({
                            "路線名": route_name,
                            "駅": station_name,
                            "徒歩時間": walking_time
                        })
                        logger.debug(f"交通情報を取得: 路線={route_name}, 駅={station_name}, 徒歩時間={walking_time}分")

            return {
                "物件ID": property_id,
                "物件名": property_name,
                "部屋番号": room_number,
                "更新日": update_date,
                "物件種別": property_type,
                "建物構造": building_structure,
                "間取り": layout,
                "ルーフバルコニー面積": roof_balcony_area,
                "管理費": maintenance_fee,
                "権利金": key_money,
                "土地権利": land_rights,
                "現況": current_status,
                "管理形態": management_type,
                "管理組合": management_union,
                "駐車場": parking,
                "その他費用": other_fees,
                "その他交通": other_transport_array,
                "客付会社様へのメッセージ": message_to_agent,
                "セールスポイント": sales_point,
                "備考": notes,
                "築年月": built_date,
                "所在階": floor,
                "専有面積": floor_area,
                "テラス面積": terrace_area,
                "修繕積立金": repair_fund,
                "保証金": deposit,
                "用途地域": land_area_type,
                "引渡時期": delivery_date,
                "管理会社": management_company,
                "駐輪場": bicycle_parking,
                "所在地": address,
                "向き": direction,
                "バルコニー面積": balcony_area,
                "専用庭面積": private_garden_area,
                "修繕積立基金": repair_fund_foundation,
                "接道状況": road_condition,
                "都市計画": city_planning,
                "建築確認番号": building_confirmation_number,
                "管理人": manager,
                "リフォーム": renovation,
                "取扱会社": company_name,
                "電話番号": phone_number,
                "免許番号": license_number,
                "住所": company_address,
                "仲介手数料/分配率": commission_rate,
                "取引態様": transaction_type,
                "FAX番号": fax_number,
                "基本設備・条件": basic_facilities,
                "キッチン/バス・トイレ": kitchen_bathroom,
                "内装/家具・家電/通信": interior_furniture,
                "設備/構造/リフォーム": equipment_structure,
                "駐車場・駐輪場/庭": parking_garden,
                "セキュリティ/サービス/条件": security_conditions,
                "立地条件/土地": location_land,
                "緯度": latitude,
                "経度": longitude,
                "画像": images,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"物件詳細の取得中にエラーが発生: {str(e)}")
            return {
                "property_id": property_id,
                "status": "error",
                "message": str(e)
            }

    def load_processed_ids(self) -> set:
        """
        処理済みの物件IDを読み込みます。

        Returns:
            set: 処理済みの物件IDのセット
        """
        try:
            if os.path.exists(self.processed_ids_file):
                with open(self.processed_ids_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            return set()
        except Exception as e:
            logger.error(f"処理済み物件IDの読み込み中にエラーが発生: {str(e)}")
            return set()

    def save_processed_ids(self, processed_ids: set) -> bool:
        """
        処理済みの物件IDを保存します。

        Args:
            processed_ids (set): 処理済みの物件IDのセット

        Returns:
            bool: 保存成功時True、失敗時False
        """
        try:
            with open(self.processed_ids_file, 'w', encoding='utf-8') as f:
                json.dump(list(processed_ids), f, ensure_ascii=False, indent=2)
            logger.info(f"処理済み物件IDを保存しました: {len(processed_ids)}件")
            return True
        except Exception as e:
            logger.error(f"処理済み物件IDの保存中にエラーが発生: {str(e)}")
            return False

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

    def scrape(self, property_id: str = None) -> Dict[str, Any]:
        """
        リナートから情報をスクレイピングします。

        Args:
            property_id (str, optional): 特定の物件IDを指定する場合に使用します。

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

            # 物件一覧ページにアクセス
            list_url = "https://ub16.mediate.ielove.jp/mediate/newsale/index/num/10/page/0/"
            logger.info(f"物件一覧ページにアクセス開始: {list_url}")
            self.driver.get(list_url)
            logger.info("物件一覧ページにアクセスしました")

            # 物件一覧の読み込みを待機
            logger.debug("物件一覧の読み込みを待機中...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".l-result__primary"))
            )
            logger.debug("物件一覧の読み込みが完了しました")

            results = []
            page = 0  # 0ページ目から開始
            all_property_ids = set()  # 現在の物件IDを保持するセット

            while True:
                # 物件リンクを取得
                property_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/mediate/newsale/detail/id/']")
                if not property_links:
                    logger.info(f"ページ {page} に物件がありません。処理を終了します。")
                    break

                logger.info(f"ページ {page} の物件リンクを {len(property_links)} 件見つけました")
                total = len(property_links)

                for i in range(total):
                    try:
                        # 毎回最新の物件リンクを取得
                        property_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/mediate/newsale/detail/id/']")
                        if i >= len(property_links):
                            logger.warning(f"物件リンクが見つかりません: インデックス {i}")
                            continue

                        link = property_links[i]
                        # リンクが有効になるまで待機
                        WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='/mediate/newsale/detail/id/']"))
                        )

                        # URLから物件IDを抽出
                        href = link.get_attribute('href')
                        if not href:
                            continue
                        property_id = href.split('/id/')[-1].rstrip('/')
                        all_property_ids.add(property_id)  # 現在の物件IDリストに追加
                        
                        # 物件名を取得
                        try:
                            property_name_element = link.find_element(By.CSS_SELECTOR, "a.estateName")
                            property_name = property_name_element.text.strip()
                            room_number = ""
                            if "　" in property_name:  # 全角スペースで分割
                                name_parts = property_name.split("　")
                                property_name = name_parts[0]
                                room_number = name_parts[1]
                            elif " " in property_name:  # 半角スペースで分割
                                name_parts = property_name.split(" ")
                                property_name = name_parts[0]
                                if len(name_parts) > 1:
                                    room_number = name_parts[1]
                            elif "&nbsp;" in property_name:  # HTMLの特殊文字で分割
                                name_parts = property_name.split("&nbsp;")
                                property_name = name_parts[0]
                                if len(name_parts) > 1:
                                    room_number = name_parts[1]
                            logger.debug(f"物件名: {property_name}, 部屋番号: {room_number}")
                        except NoSuchElementException:
                            logger.warning(f"物件名が見つかりません: {property_id}")
                            property_name = ""
                            room_number = ""
                        
                        # 処理済みの物件IDの場合はスキップ
                        if self.is_property_processed(property_id):
                            logger.info(f"物件 {i+1}/{total} は既に処理済みです (ID: {property_id})")
                            # アクティブ物件として更新
                            self.property_history["active_properties"][property_id] = {
                                "property_name": property_name,
                                "last_seen": datetime.now().isoformat()
                            }
                            self.save_property_history()
                            continue
                            
                        logger.info(f"物件 {i+1}/{total} の処理を開始 (ID: {property_id})")
                        
                        # 物件詳細ページにリンクをクリックして遷移
                        logger.debug(f"物件詳細ページへのリンクをクリック: {href}")
                        try:
                            # 要素が視認可能になるようにスクロール
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", link)
                            time.sleep(1)  # スクロールの完了を待つ
                            
                            # 通常のクリックを試みる
                            try:
                                link.click()
                            except Exception as click_error:
                                logger.warning(f"通常のクリックに失敗: {str(click_error)}")
                                # JavaScriptを使用してクリックを試みる
                                self.driver.execute_script("arguments[0].click();", link)
                                
                            logger.debug("物件詳細ページに遷移しました")
                        except Exception as e:
                            logger.error(f"リンクのクリックに失敗: {str(e)}")
                            # 最後の手段として、URLを直接開く
                            logger.debug("URLを直接開きます")
                            self.driver.get(href)
                            time.sleep(3)  # ページの読み込みを待つ

                        # 新しいタブが開かれた場合の処理
                        if len(self.driver.window_handles) > 1:
                            logger.debug("新しいタブが開かれました")
                            # 最新のタブに切り替え
                            self.driver.switch_to.window(self.driver.window_handles[-1])
                            logger.debug("新しいタブに切り替えました")

                        # ページの読み込みを待機
                        logger.debug("ページの読み込みを待機中...")
                        time.sleep(3)  # ページの読み込みを待つ
                        logger.debug("ページの読み込みが完了しました")

                        # 物件詳細情報を取得
                        result = self.scrape_property_details(property_id)
                        
                        # 物件データをJSONファイルとして保存
                        if self.save_property_data(property_id, result):
                            results.append(result)
                            # 物件を処理済みとしてマーク
                            self.mark_property_as_processed(property_id, result)
                            logger.info(f"物件 {i+1}/{total} のスクレイピングが完了しました (ID: {property_id})")
                        else:
                            raise Exception("物件データの保存に失敗しました")

                        # 新しいタブを閉じて物件一覧ページのタブに戻る
                        if len(self.driver.window_handles) > 1:
                            logger.debug("新しいタブを閉じます")
                            self.driver.close()
                            # 物件一覧ページのタブに戻る（最初のタブ）
                            self.driver.switch_to.window(self.driver.window_handles[0])
                            logger.debug("物件一覧ページのタブに戻りました")
                        else:
                            # 同じタブの場合は物件一覧ページに直接アクセス
                            logger.debug("物件一覧ページに戻ります")
                            self.driver.get(list_url)
                            time.sleep(2)  # ページの読み込みを待つ

                    except Exception as e:
                        logger.error(f"物件 {i+1}/{total} のスクレイピング中にエラーが発生 (ID: {property_id}): {str(e)}")
                        results.append({
                            "property_id": property_id,
                            "status": "error",
                            "message": str(e)
                        })
                        # エラーが発生した場合も物件一覧ページに戻る
                        try:
                            if len(self.driver.window_handles) > 1:
                                self.driver.close()
                                self.driver.switch_to.window(self.driver.window_handles[0])
                            else:
                                self.driver.get(list_url)
                            time.sleep(2)
                        except Exception as e:
                            logger.error(f"物件一覧ページへの戻り中にエラーが発生: {str(e)}")

                # 次のページに移動
                page += 1
                next_page_url = f"https://ub16.mediate.ielove.jp/mediate/newsale/index/num/10/page/{page}/"
                logger.info(f"次のページに移動します: {next_page_url}")
                self.driver.get(next_page_url)
                time.sleep(2)  # ページの読み込みを待つ

            # 削除された物件を検出
            active_property_ids = set(self.property_history["active_properties"].keys())
            deleted_property_ids = active_property_ids - all_property_ids
            
            # 削除された物件を処理
            for property_id in deleted_property_ids:
                self.mark_property_as_deleted(property_id)

            logger.info("全ての物件の処理が完了しました")
            return {
                "status": "success",
                "data": {
                    "properties": results,
                    "history": {
                        "active_count": len(self.property_history["active_properties"]),
                        "deleted_count": len(self.property_history["deleted_properties"]),
                        "processed_count": len(self.property_history["processed_properties"])
                    }
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

if __name__ == "__main__":
    # デバッグ用のコード
    logging.basicConfig(level=logging.DEBUG)
    
    # テスト用の認証情報
    test_credentials = {
        "user_id": "test_user",
        "password": "test_password"
    }
    
    # スクレイパーのテスト実行
    scraper = RinatohomeScraper(test_credentials)
    result = scraper.scrape("763557")  # テスト用の物件ID
    print(result) 