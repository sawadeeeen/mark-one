import os
import json
import traceback
import time
import re
from typing import Any, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, InvalidSessionIdException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import logging

from utils import save_updated_properties


class ItandiBBSalesScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.data_dir = "data/itandibb_sales"
        os.makedirs(self.data_dir, exist_ok=True)
        self.logger = logging.getLogger("itandibb")
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(handler)

        self.credentials = credentials
        self.property_history_file = os.path.join(self.data_dir, "property_history.json")
        self.property_history = self.load_property_history()

    def load_property_history(self) -> Dict[str, Any]:
        if os.path.exists(self.property_history_file):
            with open(self.property_history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"processed": [], "deleted": []}

    def update_property_history(self):
        with open(self.property_history_file, "w", encoding="utf-8") as f:
            json.dump(self.property_history, f, ensure_ascii=False, indent=4)

    def scrape(self) -> Dict[str, Any]:
        self.logger.info("ログインを開始します")

        email = self.credentials["user_id"]
        password = self.credentials["password"]

        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1024,768")
        options.add_argument("--disable-gpu")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            driver.get("https://itandibb.com/top")
            original_window = driver.current_window_handle

            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "email")))
            driver.find_element(By.ID, "email").send_keys(email)
            driver.find_element(By.ID, "password").send_keys(password)
            driver.find_element(By.NAME, "commit").click()
            self.logger.info("ログインに成功しました")

            time.sleep(5)
            self.logger.info(f"ログイン後URL: {driver.current_url}")

            # 2. 「売買物件」クリック
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[.//span[text()='売買物件']]"))
            ).click()
            time.sleep(1)

            # 3. 「居住用部屋」クリック
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/sale_rooms/list')]"))
            ).click()
            time.sleep(2)

            # 4. 「選択」ボタン
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//div[text()='選択']]"))
            ).click()
            print("✅ 『選択』クリック")
            time.sleep(1)

            # 5. 「関東」
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//label[.//span[text()='関東']]"))
            ).click()
            print("✅ 『関東』クリック")
            time.sleep(1)

            # 地域ごとにクリックして「全域」チェック
            for prefecture in ["埼玉県", "千葉県", "東京都", "神奈川県"]:
                # 6. 都道府県クリック
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, f"//label[.//span[text()='{prefecture}']]"))
                ).click()
                print(f"✅ 『{prefecture}』クリック")
                time.sleep(1)

                # 7. 「全域」チェック
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//label[.//span[text()='全域']]"))
                ).click()
                print(f"✅ 『全域（{prefecture}）』チェックON")
                time.sleep(1)

            # 8. 「確定」ボタン
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//div[text()=' 確定 ']]"))
            ).click()
            print("✅ 『確定』クリック")
            time.sleep(2)

            # 9. 「検索」ボタン
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), '検索')]]"))
            ).click()
            print("✅ 『検索』クリック")
            time.sleep(3)


















            while True:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//a[starts-with(@href, '/sale_rooms/')]"))
                    )
                    links = driver.find_elements(By.XPATH, "//a[starts-with(@href, '/sale_rooms/')]")
                except TimeoutException:
                    self.logger.info(f"物件が存在しません。スキップ。")
                    break

                for link in links:
                    try:
                        href = link.get_attribute("href")
                        match = re.search(r"/sale_rooms/(\d+)", href)
                        if not match:
                            continue
                        property_id = match.group(1)

                        if property_id in self.property_history["processed"]:
                            self.logger.info(f"[{property_id}] は既に処理済み。スキップ。")
                            continue

                        self.logger.info(f"[{property_id}] 詳細リンクをクリック")
                        driver.execute_script("arguments[0].click();", link.find_element(By.TAG_NAME, "button"))

                        WebDriverWait(driver, 10).until(EC.number_of_windows_to_be(2))
                        for handle in driver.window_handles:
                            if handle != original_window:
                                driver.switch_to.window(handle)
                                break

                        api_url = f"https://api.itandibb.com/api/internal/v4/sale_rooms/{property_id}"
                        driver.get(api_url)

                        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
                        pre = driver.find_element(By.TAG_NAME, "pre")

                        if "429 Too Many Requests" in driver.page_source or "アクセスが多いため" in driver.page_source:
                            self.logger.error("ページにアクセス制限の警告が表示されています。処理を中断します。")
                            return {"status": "error", "message": "429 Too Many Requests"}

                        data = json.loads(pre.text)
                        if data.get("message") == "too many requests":
                            self.logger.error("APIレスポンスに 'too many requests' が含まれています。処理を中断します。")
                            return {"status": "error", "message": "too many requests – API制限"}

                        file_name = f"{property_id}.json"
                        with open(os.path.join(self.data_dir, file_name), "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=4)

                        # 更新物件情報を保存
                        save_updated_properties(os.path.join(self.data_dir, file_name))

                        self.logger.info(f"[{property_id}] 保存完了: {file_name}")
                        self.property_history["processed"].append(property_id)
                        self.update_property_history()

                        driver.close()
                        driver.switch_to.window(original_window)
                        time.sleep(1)

                    except Exception as e:
                        self.logger.warning(f"[{property_id}] 物件処理中エラー: {e}")
                        self.logger.debug(traceback.format_exc())
                        continue

                try:
                    next_btn = driver.find_element(
                        By.XPATH,
                        "//button[contains(@class, 'MuiFlatPageButton-rootEnd') and contains(., '次へ')]"
                    )
                    if "Mui-disabled" in next_btn.get_attribute("class") or next_btn.get_attribute("disabled"):
                        self.logger.info(f"最終ページです。終了。")
                        break
                    else:
                        self.logger.info(f"次ページへ進みます。")
                        next_btn.click()
                        time.sleep(3)
                except NoSuchElementException:
                    self.logger.info(f"次へボタンが見つかりません。終了。")
                    break



                except Exception as e:
                    self.logger.warning(f"の処理中にエラー: {e}")
                    self.logger.debug(traceback.format_exc())
                    continue

            return {"status": "success", "message": "すべての検索条件のスクレイピングが完了しました"}

        except InvalidSessionIdException:
            self.logger.error("セッションが無効です。")
            return {"status": "error", "message": "Invalid session"}
        except Exception as e:
            self.logger.error(f"スクレイピング中にエラー: {e}")
            self.logger.debug(traceback.format_exc())
            driver.save_screenshot("fatal_error.png")
            return {"status": "error", "message": str(e)}
        finally:
            driver.quit()

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
            self.logger.info("物件詳細情報の取得を開始")
            
            # ページ読み込み完了を待機
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            
            # 物件種別を判定
            property_type = None
            try:
                property_type_element = driver.find_element(By.CSS_SELECTOR, "div.property-type")
                property_type_text = property_type_element.text.strip()
                if "賃貸" in property_type_text:
                    property_type = "賃貸"
                elif "売買" in property_type_text:
                    property_type = "売買"
                self.logger.info(f"物件種別: {property_type}")
            except Exception as e:
                self.logger.warning(f"物件種別の取得に失敗: {str(e)}")
            
            # テーブルから情報を取得
            table = driver.find_element(By.CSS_SELECTOR, "table")
            rows = table.find_elements(By.CSS_SELECTOR, "tr")
            
            # 交通と所在地（1行目）
            transport_address = rows[1].find_elements(By.CSS_SELECTOR, "td")[0]
            transport_text = transport_address.find_elements(By.CSS_SELECTOR, "p")[0].text
            address = transport_address.find_elements(By.CSS_SELECTOR, "p")[1].text
            self.logger.info(f"交通: {transport_text}")
            self.logger.info(f"所在地: {address}")
            
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
            self.logger.info(f"間取り: {layout}")
            self.logger.info(f"面積: {area}㎡")
            
            # 物件種別と建築年月（1行目）
            type_year = rows[1].find_elements(By.CSS_SELECTOR, "td")[2]
            property_type_detail = type_year.find_elements(By.CSS_SELECTOR, "p")[0].text
            built_date = type_year.find_elements(By.CSS_SELECTOR, "p")[1].text
            self.logger.info(f"物件種別詳細: {property_type_detail}")
            self.logger.info(f"建築年月: {built_date}")
            
            # 価格（1行目）
            price_element = rows[1].find_elements(By.CSS_SELECTOR, "td.price")[0]
            price_text = price_element.find_element(By.CSS_SELECTOR, "span").text
            self.logger.info(f"価格: {price_text}万円")

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
                    
                    self.logger.info(f"物件名全体: {full_name}")
                else:
                    self.logger.error("2番目のh1タグが見つかりません")
                    full_name = ""
            except Exception as e:
                self.logger.error(f"物件名の取得に失敗: {str(e)}")
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
            
            self.logger.info(f"建物名: {building_name}")
            self.logger.info(f"部屋番号: {room_number}")

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
                self.logger.info(f"オススメ情報: {len(recommend_info)}件")
            except Exception as e:
                self.logger.warning(f"オススメ情報の取得に失敗: {str(e)}")
            
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
                        self.logger.warning(f"画像情報の取得に失敗: {str(e)}")
                        continue
                
                self.logger.info(f"画像情報: {len(images)}件")
                
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
                                self.logger.info(f"画像を保存しました: {image_path}")
                                
                                # 保存したパスを画像情報に追加
                                image["saved_path"] = os.path.join(property_id, filename)
                            else:
                                self.logger.warning(f"画像のダウンロードに失敗: {response.status_code}")
                        except Exception as e:
                            self.logger.warning(f"画像の保存に失敗: {str(e)}")
                            continue
                
            except Exception as e:
                self.logger.warning(f"画像リストの取得に失敗: {str(e)}")

            # 売買物件特有の情報を取得
            sale_info = {}
            if property_type == "売買":
                try:
                    # 土地面積
                    land_area = rows[2].find_elements(By.CSS_SELECTOR, "td")[1].text.replace("㎡", "")
                    sale_info["土地面積"] = float(land_area) if land_area else None
                    
                    # 建蔽率・容積率
                    coverage_ratio = rows[2].find_elements(By.CSS_SELECTOR, "td")[2].text
                    sale_info["建蔽率"] = coverage_ratio
                    
                    # 用途地域
                    zoning = rows[3].find_elements(By.CSS_SELECTOR, "td")[0].text
                    sale_info["用途地域"] = zoning
                    
                    # 設備
                    equipment = rows[3].find_elements(By.CSS_SELECTOR, "td")[1].text
                    sale_info["設備"] = equipment
                    
                    # 取引態様
                    transaction_type = rows[3].find_elements(By.CSS_SELECTOR, "td")[2].text
                    sale_info["取引態様"] = transaction_type
                    
                    self.logger.info(f"売買物件特有情報: {sale_info}")
                except Exception as e:
                    self.logger.warning(f"売買物件特有情報の取得に失敗: {str(e)}")
            
            # 基本情報を構築
            property_data = {
                "物件種別": property_type,  # 物件タイプ（賃貸/売買）
                "物件種別詳細": property_type_detail,  # 物件タイプの詳細
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
            
            # 売買物件の場合は追加情報をマージ
            if property_type == "売買":
                property_data.update(sale_info)
            
            return property_data
            
        except Exception as e:
            self.logger.error(f"物件詳細情報の取得中にエラー: {str(e)}")
            return {}


if __name__ == "__main__":
    credentials = {"user_id": "info@mark-one.co.jp", "password": "mk460102"}
    scraper = ItandiBBSalesScraper(credentials)
    result = scraper.scrape()
    logging.getLogger("itandibb").info(f"スクレイピング結果: {result}")
