import os
import json
import traceback
import time
import logging
import re
from typing import Any, Dict, Optional, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, InvalidSessionIdException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import requests
from bs4 import BeautifulSoup
import sys

from src.utils import save_updated_properties

class ReinsScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.data_dir = "data/reins"
        os.makedirs(self.data_dir, exist_ok=True)
        self.logger = logging.getLogger("reins")
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        if not self.logger.handlers:
            self.logger.addHandler(handler)

        self.credentials = credentials
        self.property_history_file = os.path.join(self.data_dir, "property_history.json")
        self.property_history = self.load_property_history()

    def load_property_history(self) -> Dict[str, Any]:
        if os.path.exists(self.property_history_file):
            with open(self.property_history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "processed": [],  # 処理済み物件IDのリスト
            "deleted": [],    # 削除済み物件IDのリスト
            "updated": [],    # 更新された物件IDのリスト
            "property_info": {}  # 物件IDごとの変更年月日と更新年月日
        }
        
    def get_label_sets(self, search_type: str) -> Dict[str, List[str]]:
        """売買・賃貸ごとのラベルセットを返す"""
        common_labels = {
            "company": [
                "商号", "代表電話番号", "問合せ先電話番号",
                "物件問合せ担当者", "物件担当者電話番号",
                "Ｅメールアドレス", "自社管理欄"
            ],
            "location": [
                "都道府県名", "所在地名１", "所在地名２",
                "所在地名３", "建物名", "部屋番号",
                "その他所在地表示"
            ],
            "layout": ["間取タイプ", "間取部屋数"],
            "building": [
                "築年月", "建物構造", "地上階層", "地下階層",
                "所在階", "バルコニー方向", "総戸数", "棟総戸数"
            ],
            "parking": [
                "駐車場在否", "駐車場月額",
                "駐車場月額(最低値)", "駐車場月額(最高値)"
            ],
            "legal": ["用途地域", "最適用途", "国土法届出"],
            "equipment": [
                "設備・条件・住宅性能等", "設備(フリースペース)",
                "条件(フリースペース)", "省エネルギー性能",
                "目安光熱費"
            ]
        }

        if search_type == "売買":
            specific_labels = {
                "basic": [
                    "物件番号", "登録年月日", "変更年月日", "更新年月日",
                    "物件種目", "広告転載区分", "取引態様", "媒介契約年月日",
                    "取引状況", "取引状況の補足"
                ],
                "price": ["価格", "うち価格消費税", "変更前価格", "㎡単価", "坪単価"],
                "area": [
                    "面積計測方式", "専有面積", "不動産ＩＤ（建物）",
                    "バルコニー(テラス)面積", "土地共有持分面積", "土地共有持分"
                ],
                "management": [
                    "管理組合有無", "管理費", "うち管理費消費税",
                    "管理形態", "管理会社名", "管理人状況",
                    "修繕積立金", "施主", "施工会社名",
                    "分譲会社名", "その他一時金なし",
                    "その他一時金名称１", "金額１",
                    "その他一時金名称２", "金額２",
                    "その他月額費名称", "その他月額費金額"
                ],
                "current": ["現況", "引渡時期", "引渡年月"],
                "right": ["土地権利", "借地料", "借地期限"],
                "reward": ["報酬形態", "手数料割合率", "手数料"]
            }
        else:
            specific_labels = {
                "basic": [
                    "物件番号", "登録年月日", "変更年月日", "更新年月日",
                    "物件種目", "広告転載区分", "建物賃貸借区分", "契約期間"
                ],
                "price": ["賃料", "敷金", "礼金", "保証金", "共益費", "㎡単価", "坪単価"],
                "area": ["使用部分面積", "バルコニー(テラス)面積"],
                "management": ["管理費", "管理形態", "更新料"],
                "current": ["現況", "入居可能時期"],
                "right": [],
                "reward": ["報酬形態", "手数料割合率", "手数料"]
            }

        return {**common_labels, **specific_labels}


    def collect_labels(self, driver, label_sets: Dict[str, List[str]], detail_data: Dict[str, Any]):
        """定義されたラベルセットを使って値を抽出"""
        for section, labels in label_sets.items():
            for label in labels:
                value = self.get_element_text(driver, label)
                if value:
                    detail_data[label] = value
                    
    def update_property_history(self):
        with open(self.property_history_file, "w", encoding="utf-8") as f:
            json.dump(self.property_history, f, ensure_ascii=False, indent=4)

    def sanitize_filename(self, filename: str) -> str:
        # 無効な文字を置換
        invalid_chars = r'[<>:"/\\|?*\n\r\t]'
        sanitized = re.sub(invalid_chars, '_', filename)
        # 連続するアンダースコアを1つに
        sanitized = re.sub(r'_+', '_', sanitized)
        # 先頭と末尾のアンダースコアを削除
        sanitized = sanitized.strip('_')
        return sanitized

    def get_element_text(self, driver, label: str) -> str:
        try:
            # ラベル要素が見つかるまで待機
            # print(label+"を探しています")
            # まず、ラベルを含む要素を探す
            label_xpath = f"//span[contains(@class, 'p-label-title') and contains(text(), '{label}')]"
            label_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, label_xpath))
            )
            
            # 親要素を探す（colクラスを持つ・・要素）
            # print(label+"の親要素を探しています")
            parent = label_element.find_element(By.XPATH, "ancestor::div[contains(@class, 'col')]")
            
            # 値要素を探す（rowクラスを持つ要素内のcolクラスを持つ要素）
            # print(label+"の値要素を探しています")
            try:
                value_element = parent.find_element(By.XPATH, ".//div[contains(@class, 'row')]//div[contains(@class, 'col')]")
                text = value_element.text.strip()
            except NoSuchElementException:
                # 値要素が見つからない場合は空文字を返す
                text = "-"
            
            print(f"{label}: {text}")
            return text
        except Exception as e:
            self.logger.debug(f"ラベル '{label}' の値取得失敗: {e}")
            return "-"

    def get_transport_info(self, driver, section_index: int) -> Dict[str, str]:
        transport_info = {}
        try:
            # 全角数字に変換
            full_width_number = str(section_index).translate(str.maketrans('0123456789', '０１２３４５６７８９'))
            section = driver.find_element(By.XPATH, f"//h3[contains(text(),'交通{full_width_number}')]")
            container = section.find_element(By.XPATH, "following-sibling::div[1]")
            labels = container.find_elements(By.CSS_SELECTOR, "span.p-label-title")
            for label in labels:
                try:
                    value = self.get_element_text(driver, label.text.strip())
                    if value:
                        transport_info[label.text.strip()] = value
                except Exception:
                    continue
        except Exception as e:
            self.logger.warning(f"交通{full_width_number}の取得失敗: {e}")
        return transport_info

    def get_room_info(self, driver, room_index: int) -> Dict[str, str]:
        room_info = {}
        try:
            # 全角数字に変換
            full_width_number = str(room_index).translate(str.maketrans('0123456789', '０１２３４５６７８９'))
            labels = [
                f"室{full_width_number}:所在階",
                f"室{full_width_number}:室タイプ",
                f"室{full_width_number}:室広さ"
            ]
            for label in labels:
                value = self.get_element_text(driver, label)
                if value:
                    room_info[label] = value
        except Exception as e:
            self.logger.warning(f"室{full_width_number}情報の取得失敗: {e}")
        return room_info

    def get_renovation_info(self, driver, index: int) -> Dict[str, str]:
        renovation_info = {}
        try:
            # 全角数字に変換
            full_width_number = str(index).translate(str.maketrans('0123456789', '０１２３４５６７８９'))
            labels = [
                f"増改築年月{full_width_number}",
                f"増改築履歴{full_width_number}"
            ]
            for label in labels:
                value = self.get_element_text(driver, label)
                if value:
                    renovation_info[label] = value
        except Exception as e:
            self.logger.warning(f"増改築情報{full_width_number}の取得失敗: {e}")
        return renovation_info

    def get_surrounding_info(self, driver, index: int) -> Dict[str, str]:
        surrounding_info = {}
        try:
            # 全角数字に変換
            full_width_number = str(index).translate(str.maketrans('0123456789', '０１２３４５６７８９'))
            labels = [
                f"周辺環境{full_width_number}(フリー)",
                f"距離{full_width_number}",
                f"時間{full_width_number}"
            ]
            for label in labels:
                value = self.get_element_text(driver, label)
                if value:
                    surrounding_info[label] = value
        except Exception as e:
            self.logger.warning(f"周辺環境{full_width_number}の取得失敗: {e}")
        return surrounding_info

    def download_images(self, property_number: str, html_content: str, driver):
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            image_dir = os.path.join(self.data_dir, property_number)
            os.makedirs(image_dir, exist_ok=True)
            
            images = []
            # 画像要素の取得
            image_elements = soup.find_all('div', {'class': 'mx-auto'})
            
            # セッションを作成
            session = requests.Session()
            
            # クッキーを取得
            cookies = driver.get_cookies()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            # ヘッダーを設定
            headers = {
                'User-Agent': driver.execute_script("return navigator.userAgent"),
                'Referer': driver.current_url,
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
                'Connection': 'keep-alive',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache'
            }
            session.headers.update(headers)
            
            for i, element in enumerate(image_elements, 1):
                try:
                    # style属性から背景画像URLを取得
                    style = element.get('style', '')
                    if 'background: url(' in style:
                        # URLを抽出
                        url = style.split('url(')[1].split(')')[0].strip('"')
                        if url.startswith('/'):
                            url = f"https://system.reins.jp{url}"
                        
                        # ファイル名を生成
                        filename = f"{property_number}_{i:02d}.jpg"
                        filepath = os.path.join(image_dir, filename)
                        
                        # 画像をダウンロード
                        response = session.get(url, stream=True, timeout=30)
                        if response.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            self.logger.info(f"画像を保存しました: {filepath}")
                            images.append({
                                "filename": filename,
                                "url": url,
                                "path": filepath
                            })
                        else:
                            self.logger.warning(f"画像のダウンロードに失敗しました: {url} (ステータスコード: {response.status_code})")
                except Exception as e:
                    self.logger.warning(f"画像 {i} の処理中にエラーが発生しました: {e}")
                    continue
            
            return images
        except Exception as e:
            self.logger.error(f"画像のダウンロード処理でエラーが発生しました: {e}")
            return []

    def scrape(self) -> Dict[str, Any]:
        self.logger.info("レインズのスクレイピングを開始します")

        user_id = self.credentials["user_id"]
        password = self.credentials["password"]

        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1024,768")
        options.add_argument("--disable-gpu")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            driver.get("https://system.reins.jp/login/main/KG/GKG001200")
            self.logger.info("ログインページにアクセスしました")

            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
            ).send_keys(user_id)

            driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(password)
            self.logger.info("ログイン情報を入力しました")
            time.sleep(2)

            checkbox = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'][id^='__BVID__20']"))
            )
            driver.execute_script("arguments[0].click();", checkbox)
            time.sleep(1)

            login_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary"))
            )
            driver.execute_script("arguments[0].click();", login_button)
            time.sleep(5)

            # 売買物件検索と賃貸物件検索の両方を処理
            search_types = [
                ("売買 物件検索", "売買"),
                ("賃貸 物件検索", "賃貸")
            ]

            for search_text, search_type in search_types:
                # ✅ 物件種別ごとに保存パスと履歴ファイルを切り替え
                self.data_dir = "data/reins_sales" if search_type == "売買" else "data/reins_rental"
                os.makedirs(self.data_dir, exist_ok=True)
                self.property_history_file = os.path.join(
                    self.data_dir,
                    "property_history_sales.json" if search_type == "売買" else "property_history_rental.json"
                )
                self.property_history = self.load_property_history()

                processed_ids = set(self.property_history["processed"])
                deleted_ids = set(self.property_history["deleted"])
                updated_ids = set(self.property_history["updated"])
                property_info = self.property_history["property_info"]

                self.logger.info(f"{search_type}物件検索を開始します")
                driver.get("https://system.reins.jp/main/KG/GKG003100")
                time.sleep(3)
      
                search_button = WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, f"//button[contains(@class, 'btn-primary') and contains(text(),'{search_text}')]"))
                )
                driver.execute_script("arguments[0].click();", search_button)
                time.sleep(3)

                search_condition_button = WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'検索条件を表示')]"))
                )
                driver.execute_script("arguments[0].click();", search_condition_button)
                time.sleep(3)

                select_box = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "select.p-selectbox-input[id^='__BVID__']"))
                )
                self.logger.info(f"{search_type}物件の検索条件のセレクトボックスを取得しました")

                options = select_box.find_elements(By.TAG_NAME, "option")
                valid_conditions = []
                for option in options:
                    text = option.text.strip()
                    if text and not re.match(r'^\d+:$', text):
                        valid_conditions.append({
                            "value": option.get_attribute("value"),
                            "text": text
                        })
                        self.logger.info(f"有効な検索条件: {text}")

                is_first_condition = True
                # 各検索条件に対して処理を実行
                for condition in valid_conditions:
                    
                    if is_first_condition:
                        is_first_condition = False
                    else:
                        search_condition_button = WebDriverWait(driver, 30).until(
                            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'検索条件を表示')]"))
                        )
                        driver.execute_script("arguments[0].click();", search_condition_button)
                        time.sleep(3)

                        select_box = WebDriverWait(driver, 30).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "select.p-selectbox-input[id^='__BVID__']"))
                        )
                        self.logger.info(f"{search_type}物件の検索条件のセレクトボックスを取得しました")

                    self.logger.info(f"{search_type}物件 - 検索条件 '{condition['text']}' の処理を開始します")
                    
                    # 検索条件を選択
                    select_box.click()
                    time.sleep(1)
                    option = driver.find_element(By.CSS_SELECTOR, f"option[value='{condition['value']}']")
                    option.click()
                    self.logger.info(f"{search_type}物件 - 検索条件を選択しました: {condition['text']}")
                    time.sleep(2)

                    # 読込ボタンをクリック
                    driver.find_element(By.XPATH, "//button[contains(text(),'読込')]").click()
                    time.sleep(2)

                    # OKボタンをクリック
                    ok_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary"))
                    )
                    driver.execute_script("arguments[0].click();", ok_button)
                    time.sleep(2)

                    # "検索結果が0件" の表示を検出
                    try:
                        no_results_element = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.p-note-danger"))
                        )
                        if "検索結果が0件です" in no_results_element.text:
                            self.logger.info(f"{search_type}物件 - 検索条件 '{condition['text']}' の検索結果が0件 →　検索条件一覧に戻ります　2")
                            driver.get("https://system.reins.jp/main/BK/GBK001210")
                            time.sleep(3)
                            continue
                    except TimeoutException:
                        self.logger.info(f"{search_type}物件 - 検索条件 '{condition['text']}' の検索結果あり → 通常処理を継続")

                    # 詳細ボタンをクリック
                    try:
                        detail_buttons = driver.find_elements(By.XPATH, "//button[contains(text(),'詳細')]")
                        driver.execute_script("arguments[0].click();", detail_buttons[0])
                    except Exception as e:
                        self.logger.warning(f"{search_type}物件 - 詳細ボタンのクリックに失敗しました: {e}")
                        continue

                    # 詳細情報の取得処理
                    while True:
                        if "429 Too Many Requests" in driver.page_source:
                            self.logger.warning("429エラー。中断します。")
                            return {"status": "error", "message": "429 Too Many Requests"}

                        time.sleep(3)

                        detail_data = {}
                        property_number = ""

                        # ラベルセットを取得（売買/賃貸で自動分岐）
                        label_sets = self.get_label_sets(search_type)

                        # ラベル値をまとめて収集
                        self.collect_labels(driver, label_sets, detail_data)

                        # 物件番号を抽出
                        property_number = detail_data.get("物件番号", "")

                        # 物件履歴のチェック
                        if property_number:
                            # 物件が処理済みリストに存在する場合
                            if property_number in processed_ids:
                                # 変更年月日と更新年月日を取得
                                change_date = detail_data.get("変更年月日", "")
                                update_date = detail_data.get("更新年月日", "")
                                
                                # 保存されている情報と比較
                                saved_info = property_info.get(property_number, {})
                                saved_change_date = saved_info.get("変更年月日", "")
                                saved_update_date = saved_info.get("更新年月日", "")
                                
                                # 日付が異なる場合は更新リストに追加
                                if (change_date != saved_change_date or 
                                    update_date != saved_update_date):
                                    updated_ids.add(property_number)
                                    processed_ids.remove(property_number)  # 処理済みリストから削除
                                    property_info[property_number] = {
                                        "変更年月日": change_date,
                                        "更新年月日": update_date
                                    }
                                    self.property_history["updated"] = list(updated_ids)
                                    self.property_history["processed"] = list(processed_ids)
                                    self.property_history["property_info"] = property_info
                                    self.update_property_history()
                                    self.logger.info(f"{search_type}物件 - 物件 {property_number} の情報が更新されました")
                                else:
                                    self.logger.info(f"{search_type}物件 - 物件 {property_number} は既に処理済みで、変更もありません。スキップします。")
                            else:
                                # 物件が処理済みリストに存在しない場合（新規物件）
                                updated_ids.add(property_number)  # 新規物件は更新リストに追加
                                property_info[property_number] = {
                                    "変更年月日": detail_data.get("変更年月日", ""),
                                    "更新年月日": detail_data.get("更新年月日", "")
                                }
                                self.property_history["updated"] = list(updated_ids)
                                self.property_history["property_info"] = property_info
                                self.update_property_history()
                                self.logger.info(f"{search_type}物件 - 物件 {property_number} を新規物件として追加しました。")

                            # 物件が削除済みリストに存在する場合
                            if property_number in deleted_ids:
                                self.logger.info(f"{search_type}物件 - 物件 {property_number} は削除済みとして扱われていましたが、再登録されています。")
                                deleted_ids.remove(property_number)
                                updated_ids.add(property_number)  # 再登録物件は更新リストに追加
                                property_info[property_number] = {
                                    "変更年月日": detail_data.get("変更年月日", ""),
                                    "更新年月日": detail_data.get("更新年月日", "")
                                }
                                self.property_history["deleted"] = list(deleted_ids)
                                self.property_history["updated"] = list(updated_ids)
                                self.property_history["property_info"] = property_info
                                self.update_property_history()

                        # 画像のダウンロード
                        if property_number:
                            images = self.download_images(property_number, driver.page_source, driver)
                            if images:
                                detail_data["画像"] = images

                        # データの保存
                        if property_number:
                            safe_filename = self.sanitize_filename(f"{property_number}")
                            file_path = os.path.join(self.data_dir, f"{safe_filename}.json")
                            with open(file_path, "w", encoding="utf-8") as f:
                                json.dump(detail_data, f, ensure_ascii=False, indent=4)
                                
                            # 更新物件情報を保存
                            save_updated_properties(file_path)

                            self.logger.info(f"{search_type}物件 - 保存完了: {file_path}")
                        else:
                            self.logger.warning(f"{search_type}物件 - 物件番号が取得できませんでした")

                        # 次の物件ボタンをクリック
                        try:
                            next_button = driver.find_element(By.XPATH, "//button[contains(@class, 'btn p-button btn-outline btn-block px-0') and contains(text(), '次の物件')]")
                            next_button.click()
                            time.sleep(3)
                        except NoSuchElementException:
                            self.logger.info(f"{search_type}物件 - 次のページなし → 物件一覧へ戻ります")
                            time.sleep(5)
                            back_button = driver.find_element(By.CSS_SELECTOR, "div.p-frame-navbar-left button.p-frame-backer")
                            back_button.click()
                            time.sleep(3)
                            
                            try:
                                next_page_button = driver.find_element(By.XPATH, "//button[@aria-label='Go to next page']")
                                next_page_button.click()
                                self.logger.info(f"{search_type}物件 - 物件 {property_number} の次のページへ移動しました")
                                time.sleep(3)
                                
                                detail_buttons = driver.find_elements(By.XPATH, "//button[contains(text(),'詳細')]")
                                driver.execute_script("arguments[0].click();", detail_buttons[0]) 
                                time.sleep(3)
                                continue
                            except NoSuchElementException:
                                self.logger.info(f"{search_type}物件 - 物件 {property_number} の次のページなし → 検索条件一覧に戻ります　1")
                                driver.get("https://system.reins.jp/main/BK/GBK001210")
                                time.sleep(3)
                                break

            # 処理済みリストに存在する物件IDが今回のスクレイピング結果に存在しない場合
            current_processed_ids = set(self.property_history["processed"])
            for old_id in current_processed_ids:
                if old_id not in processed_ids:
                    self.logger.info(f"{search_type}物件 - 物件 {old_id} は今回のスクレイピング結果に存在しません。削除済みとして扱います。")
                    deleted_ids.add(old_id)
                    processed_ids.remove(old_id)
                    if old_id in property_info:
                        del property_info[old_id]
                    self.property_history["processed"] = list(processed_ids)
                    self.property_history["deleted"] = list(deleted_ids)
                    self.property_history["property_info"] = property_info
                    self.update_property_history()

            return {"status": "success", "message": "すべての検索条件の処理が完了しました"}

        except Exception as e:
            self.logger.error(f"エラー発生: {e}")
            self.logger.debug(traceback.format_exc())
            try:
                driver.save_screenshot("fatal_error.png")
            except:
                pass
            return {"status": "error", "message": str(e)}

        finally:
            driver.quit()


if __name__ == "__main__":
    credentials = {"user_id": "139608150624", "password": "mark-1"}
    scraper = ReinsScraper(credentials)
    result = scraper.scrape()
    logging.getLogger("reins").info(f"結果: {result}")
