import logging
import time
import os
import requests
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import urljoin

from utils import save_updated_properties

logger = logging.getLogger(__name__)

class MugenEstateScraper:
    def __init__(self, credentials=None):
        self.credentials = credentials
        self.base_url = "https://mers.mugen-estate.co.jp"
        self.driver = None
        self.wait_time = 10
        # 絶対パスで指定
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.history_file = os.path.join(base_dir, "data", "mugen_estate", "property_history.json")
        self.property_history = self.load_property_history()

    def setup_driver(self):
        """Seleniumドライバーの設定"""
        try:
            options = webdriver.ChromeOptions()
            # options.add_argument('--headless')  # ヘッドレスモードを無効化
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1024,768')  # ウィンドウサイズを設定
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(self.wait_time)
            logger.debug("Seleniumドライバーの設定が完了しました")
        except Exception as e:
            logger.error(f"ドライバーの設定中にエラーが発生: {str(e)}")
            raise

    def login(self):
        """ログイン処理"""
        try:
            logger.info("ログイン処理を開始")
            self.driver.get(f"{self.base_url}/login")
            
            # CSRFトークンの取得
            csrf_token = self.driver.find_element(By.NAME, "_csrf").get_attribute("value")
            logger.debug(f"CSRFトークンを取得: {csrf_token}")
            
            # ログインフォームの入力
            email_input = self.driver.find_element(By.NAME, "loginId")
            password_input = self.driver.find_element(By.NAME, "password")
            
            email_input.send_keys(self.credentials["user_id"])
            password_input.send_keys(self.credentials["password"])
            
            # ログインボタンのクリック
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()
            
            # ログイン後のページ遷移を待機
            WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".navbar"))  # ログイン後のヘッダー要素
            )
            
            logger.info("ログインに成功しました")
            return True
            
        except TimeoutException:
            logger.error("ログイン処理がタイムアウトしました")
            raise
        except NoSuchElementException as e:
            logger.error(f"要素が見つかりません: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"ログイン中にエラーが発生: {str(e)}")
            raise

    def get_property_list(self):
        """物件一覧を取得（ページネーション対応）"""
        try:
            logger.info("物件一覧の取得を開始")
            properties = []
            current_page = 1
            
            # 既存の物件IDを取得（処理済みの物件ID）
            processed_property_ids = self.property_history["processed_properties"]
            active_property_ids = set(self.property_history["active_properties"].keys())
            logger.info(f"処理済み物件ID数: {len(processed_property_ids)}")
            logger.info(f"アクティブ物件ID数: {len(active_property_ids)}")
            
            while True:
                try:
                    # 物件一覧ページに移動
                    list_url = f"{self.base_url}/property/list?currentPage={current_page}"
                    logger.info(f"物件一覧ページに移動: {list_url}")
                    self.driver.get(list_url)
                    time.sleep(2)  # ページ読み込み待機
                    
                    # 物件要素を取得
                    logger.info("物件要素の取得を開始")
                    property_elements = WebDriverWait(self.driver, self.wait_time).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.col-12.my-1.border-top.border-primary.py-2"))
                    )
                    
                    # 物件が見つからない場合は終了
                    if not property_elements:
                        logger.info(f"ページ{current_page}に物件が見つかりません。処理を終了します。")
                        break
                    
                    logger.info(f"ページ{current_page}の処理を開始（{len(property_elements)}件）")
                    page_properties = []  # 現在のページの物件情報を保持
                    
                    # 現在のページの物件情報を取得
                    for i, element in enumerate(property_elements, 1):
                        try:
                            onclick_attr = element.get_attribute("onclick")
                            if onclick_attr:
                                property_id = onclick_attr.split('"')[1]
                                
                                # 処理済みの物件IDの場合はスキップ
                                if property_id in processed_property_ids:
                                    logger.info(f"物件{i}/{len(property_elements)}: ID={property_id}は既に処理済みのためスキップ")
                                    # アクティブ物件として更新
                                    if property_id not in active_property_ids:
                                        self.property_history["active_properties"][property_id] = {
                                            "property_name": element.find_element(By.CSS_SELECTOR, "div.col-12.my-1 > span").text.strip(),
                                            "last_seen": datetime.now().isoformat()
                                        }
                                        self.save_property_history()
                                    continue
                                
                                # 物件名を取得
                                property_name_elements = element.find_elements(By.CSS_SELECTOR, "div.col-12.my-1 > span")
                                property_name_parts = []
                                for name_element in property_name_elements:
                                    name_part = name_element.text.strip()
                                    if name_part:
                                        property_name_parts.append(name_part)
                                
                                property_name = "".join(property_name_parts)
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
                                
                                # 金額を取得
                                price_element = element.find_element(By.CSS_SELECTOR, "div.col-8.col-xl-6 span strong.text-danger")
                                price_text = price_element.text.strip()
                                logger.info(f"金額の生テキスト: {price_text}")
                                
                                # 金額の単位を変換
                                try:
                                    if "億" in price_text:
                                        # 億円と万円の組み合わせの場合
                                        if "億" in price_text and "万" in price_text:
                                            # 例: "4億2800万円" -> ["4", "2800"]
                                            parts = price_text.split("億")
                                            oku = float(parts[0])
                                            man = float(parts[1].replace("万円", ""))
                                            price = (oku * 100000000) + (man * 10000)
                                            logger.info(f"金額変換: {price_text} → {price:,}円 (億={oku}, 万={man})")
                                        else:
                                            # 億円のみの場合（例: "1億2500"）
                                            price_text = price_text.replace("億", "億円")
                                            price = float(price_text.replace("億円", "")) * 100000000
                                            logger.info(f"金額変換: {price_text} → {price:,}円")
                                    elif "万円" in price_text:
                                        price = float(price_text.replace("万円", "")) * 10000
                                        logger.info(f"金額変換: {price_text} → {price:,}円")
                                    else:
                                        price = float(price_text.replace("円", ""))
                                        logger.info(f"金額変換: {price_text} → {price:,}円")
                                    
                                    logger.info(f"物件{i}/{len(property_elements)}: ID={property_id}, 物件名={property_name}, 金額={price:,}円")
                                    page_properties.append({
                                        "property_id": property_id,
                                        "property_name": property_name,
                                        "price": int(price)
                                    })
                                    
                                    # 物件を処理済みとしてマークし、履歴を更新
                                    self.mark_property_as_processed(property_id)
                                    self.property_history["active_properties"][property_id] = {
                                        "property_name": property_name,
                                        "price": int(price),
                                        "last_seen": datetime.now().isoformat()
                                    }
                                    self.save_property_history()
                                    
                                except ValueError as e:
                                    logger.warning(f"物件{i}/{len(property_elements)}の金額変換中にエラー: {str(e)}, 金額テキスト={price_text}")
                                    continue
                        except Exception as e:
                            logger.warning(f"物件{i}/{len(property_elements)}の情報取得中にエラー: {str(e)}")
                            continue
                    
                    logger.info(f"ページ{current_page}で検出された新規物件数: {len(page_properties)}件")
                    
                    # 現在のページの物件を処理
                    for i, data in enumerate(page_properties, 1):
                        try:
                            property_id = data["property_id"]
                            logger.info(f"物件{i}/{len(page_properties)}: ID={property_id}の処理を開始")
                            
                            # 詳細ボタンを取得してクリック
                            logger.info(f"物件ID={property_id}の詳細ボタンを検索")
                            max_retries = 3
                            retry_count = 0
                            
                            while retry_count < max_retries:
                                try:
                                    property_element = WebDriverWait(self.driver, self.wait_time).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, f"div[onclick*='{property_id}']"))
                                    )
                                    
                                    # 要素が画面内に表示されるまでスクロール
                                    self.driver.execute_script("arguments[0].scrollIntoView(true);", property_element)
                                    time.sleep(1)  # スクロールアニメーション待機
                                    
                                    detail_button = property_element.find_element(By.CSS_SELECTOR, "button.btn.btn-sm.btn-primary")
                                    logger.info("詳細ボタンをクリック")
                                    detail_button.click()
                                    time.sleep(2)
                                    break
                                    
                                except Exception as e:
                                    retry_count += 1
                                    if retry_count >= max_retries:
                                        logger.error(f"物件ID={property_id}の詳細ボタンクリックに失敗（{max_retries}回リトライ）: {str(e)}")
                                        raise
                                    logger.warning(f"物件ID={property_id}の詳細ボタンクリックに失敗（リトライ{retry_count}/{max_retries}）: {str(e)}")
                                    time.sleep(2)  # リトライ前に待機
                                    # 物件一覧ページを再読み込み
                                    self.driver.get(list_url)
                                    time.sleep(2)
                            
                            # 詳細情報を取得
                            logger.info(f"物件ID={property_id}の詳細情報を取得")
                            detail_info = self.get_property_detail(property_id)
                            if detail_info:
                                # 一覧情報と詳細情報をマージ
                                detail_info.update({
                                    "property_name": data["property_name"],
                                    "price": data["price"]
                                })
                                properties.append(detail_info)
                                logger.info(f"物件ID={property_id}の詳細情報を取得完了")
                            else:
                                logger.warning(f"物件ID={property_id}の詳細情報の取得に失敗")
                            
                            # 物件一覧ページに戻る
                            self.driver.get(list_url)
                            time.sleep(2)
                            
                        except Exception as e:
                            logger.warning(f"物件{i}/{len(page_properties)}: ID={property_id}の処理中にエラー: {str(e)}")
                            # 物件一覧ページに戻る
                            self.driver.get(list_url)
                            time.sleep(2)
                            continue
                    
                    # 次のページへ
                    current_page += 1
                    logger.info(f"ページ{current_page - 1}の処理が完了しました")
                    
                except Exception as e:
                    logger.error(f"ページ{current_page}の処理中にエラー: {str(e)}")
                    break
            
            # 削除された物件を検出
            current_property_ids = {p["property_id"] for p in properties}
            deleted_property_ids = active_property_ids - current_property_ids
            
            if deleted_property_ids:
                logger.info(f"削除された物件を検出: {len(deleted_property_ids)}件")
                for property_id in deleted_property_ids:
                    deleted_property = self.property_history["active_properties"][property_id]
                    self.property_history["deleted_properties"][property_id] = {
                        **deleted_property,
                        "deleted_at": datetime.now().isoformat()
                    }
                    logger.info(f"物件が削除されました: ID={property_id}, 名称={deleted_property.get('property_name', '不明')}")
                
                # 削除された物件をactive_propertiesから削除
                for property_id in deleted_property_ids:
                    del self.property_history["active_properties"][property_id]
                
                # 履歴を保存
                self.save_property_history()
            
            logger.info(f"物件一覧の取得が完了しました。取得件数: {len(properties)}")
            return properties
            
        except Exception as e:
            logger.error(f"物件一覧の取得中にエラーが発生: {str(e)}")
            raise

    def get_coordinates_from_map(self):
        """JavaScriptから緯度/経度を取得"""
        try:
            # JavaScriptを実行して緯度/経度を取得
            coordinates_script = """
                let latitudeElement = document.evaluate(
                    "//script[contains(text(), 'let latitude')]",
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                ).singleNodeValue;
                
                if (latitudeElement) {
                    let scriptText = latitudeElement.textContent;
                    let latMatch = scriptText.match(/let latitude = ([\\d.]+);/);
                    let lngMatch = scriptText.match(/let longitude = ([\\d.]+);/);
                    return {
                        latitude: latMatch ? parseFloat(latMatch[1]) : null,
                        longitude: lngMatch ? parseFloat(lngMatch[1]) : null
                    };
                }
                return null;
            """
            
            result = self.driver.execute_script(coordinates_script)
            
            if result and result.get('latitude') and result.get('longitude'):
                coordinates = {
                    "latitude": result['latitude'],
                    "longitude": result['longitude']
                }
                logger.debug(f"緯度/経度を取得: {coordinates}")
                return coordinates
            else:
                logger.warning("緯度/経度の取得に失敗しました")
                return None
            
        except Exception as e:
            logger.warning(f"緯度/経度の取得中にエラーが発生: {str(e)}")
            return None

    def save_property_detail(self, property_id, detail_info):
        """物件詳細情報をJSONファイルとして保存"""
        try:
            # 保存先ディレクトリの作成
            save_dir = os.path.join("data", "mugen_estate")
            os.makedirs(save_dir, exist_ok=True)
            
            # JSONファイルのパス
            json_path = os.path.join(save_dir, f"{property_id}.json")
            
            # 物件詳細情報をJSONとして保存
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(detail_info, f, ensure_ascii=False, indent=2)
                
            # 更新物件情報を保存
            save_updated_properties(json_path)
            
            logger.info(f"物件詳細情報を保存しました: {json_path}")
            return True
            
        except Exception as e:
            logger.error(f"物件詳細情報の保存中にエラーが発生: {str(e)}")
            return False

    def get_property_detail(self, property_id):
        """物件詳細情報を取得"""
        try:
            logger.info(f"物件詳細情報の取得を開始: {property_id}")
            
            # 物件詳細ページのURLを構築
            detail_url = f"{self.base_url}/property/view?pjCode={property_id}"
            logger.info(f"物件詳細ページに移動: {detail_url}")
            self.driver.get(detail_url)
            
            # ページの読み込みを待機
            logger.info("ページの読み込みを待機")
            WebDriverWait(self.driver, self.wait_time * 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.container.mt-4.mb-4"))
            )
            time.sleep(5)  # 追加の待機時間
            
            # 詳細情報を取得
            detail_info = {
                "property_id": property_id
            }
            
            try:
                # 物件名と部屋番号を取得
                logger.info("物件名と部屋番号を取得")
                property_name_elements = self.driver.find_elements(By.CSS_SELECTOR, "h3.d-inline")
                property_name_parts = []
                for element in property_name_elements:
                    name_part = element.text.strip()
                    if name_part:
                        property_name_parts.append(name_part)
                
                property_name = "".join(property_name_parts)
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
            
            try:
                # 金額を取得
                logger.info("金額を取得")
                price_element = WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "strong.h4.text-danger"))
                )
                if price_element:
                    price_text = price_element.text.strip()
                    logger.info(f"金額の生テキスト: {price_text}")
                    # 金額の単位を変換
                    try:
                        if "億" in price_text:
                            # 億円と万円の組み合わせの場合
                            if "億" in price_text and "万" in price_text:
                                # 例: "4億2800万円" -> ["4", "2800"]
                                parts = price_text.split("億")
                                oku = float(parts[0])
                                man = float(parts[1].replace("万円", ""))
                                price = (oku * 100000000) + (man * 10000)
                                logger.info(f"金額変換: {price_text} → {price:,}円 (億={oku}, 万={man})")
                            else:
                                # 億円のみの場合（例: "1億2500"）
                                price_text = price_text.replace("億", "億円")
                                price = float(price_text.replace("億円", "")) * 100000000
                                logger.info(f"金額変換: {price_text} → {price:,}円")
                        elif "万円" in price_text:
                            price = float(price_text.replace("万円", "")) * 10000
                            logger.info(f"金額変換: {price_text} → {price:,}円")
                        else:
                            price = float(price_text.replace("円", ""))
                            logger.info(f"金額変換: {price_text} → {price:,}円")
                        
                        detail_info["price"] = int(price)
                        logger.info(f"金額を取得: {price_text} → {price:,}円")
                    except ValueError as e:
                        logger.warning(f"金額の変換に失敗: {price_text}, エラー: {str(e)}")
                        detail_info["price"] = 0  # 変換失敗時は0を設定
                
            except Exception as e:
                logger.warning(f"物件名、部屋番号、金額の取得に失敗: {str(e)}")
            
            try:
                # 詳細情報の行を取得
                logger.info("詳細情報の行を取得")
                detail_rows = WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.row.no-gutters > div.col-3.col-md-2, div.row.no-gutters > div.col-9.col-md-4, div.row.no-gutters > div.col-9.col-md-10"))
                )
                logger.info(f"詳細情報の行数: {len(detail_rows)}")
                
                current_key = None
                for i, element in enumerate(detail_rows, 1):
                    try:
                        if "tb-th" in element.get_attribute("class"):
                            current_key = element.text.strip()
                            logger.debug(f"キーを取得: {current_key}")
                        elif "tb-td" in element.get_attribute("class") and current_key:
                            # 地図ボタンを含む場合は、spanタグのテキストのみを取得
                            if "地図" in element.text:
                                value = element.find_element(By.CSS_SELECTOR, "span").text.strip()
                            else:
                                value = element.text.strip()
                            detail_info[current_key] = value
                            logger.debug(f"値を取得: {current_key}={value}")
                            current_key = None
                    except Exception as e:
                        logger.warning(f"詳細情報の要素{i}/{len(detail_rows)}取得中にエラー: {str(e)}")
                        continue
            except Exception as e:
                logger.warning(f"詳細情報の取得に失敗: {str(e)}")
            
            # 画像の取得と保存
            try:
                logger.info("画像の取得と保存を開始")
                images_info = self.save_property_images(property_id)
                if images_info:
                    detail_info["images"] = images_info
                    logger.info(f"画像の保存完了: {len(images_info)}件")
                else:
                    logger.warning("画像の保存に失敗")
            except Exception as e:
                logger.warning(f"画像の保存に失敗: {str(e)}")
            
            # 緯度/経度を取得
            try:
                logger.info("緯度/経度の取得を開始")
                coordinates = self.get_coordinates_from_map()
                if coordinates:
                    detail_info.update(coordinates)
                    logger.info(f"緯度/経度を取得: {coordinates}")
                else:
                    logger.warning("緯度/経度の取得に失敗")
            except Exception as e:
                logger.warning(f"緯度/経度の取得に失敗: {str(e)}")
            
            # 物件詳細情報をJSONファイルとして保存
            if self.save_property_detail(property_id, detail_info):
                logger.info(f"物件詳細情報の取得と保存が完了しました: {property_id}")
            else:
                logger.warning(f"物件詳細情報の保存に失敗しました: {property_id}")
            
            return detail_info
            
        except TimeoutException as e:
            logger.error(f"物件詳細ページの読み込みがタイムアウトしました: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"物件詳細ページの処理中にエラーが発生: {str(e)}")
            return None

    def save_property_images(self, property_id):
        """物件画像を保存"""
        try:
            # 保存先ディレクトリの作成
            save_dir = os.path.join("data", "mugen_estate", property_id)
            os.makedirs(save_dir, exist_ok=True)
            
            # 画像要素の取得
            images = self.driver.find_elements(By.CSS_SELECTOR, "div.thumbnail-thumb img")
            
            images_info = []
            for i, img in enumerate(images, 1):
                try:
                    src = img.get_attribute("src")
                    if not src:
                        continue
                    
                    # 相対パスを絶対パスに変換
                    if src.startswith("./"):
                        src = src.replace("./", "/")
                    full_url = urljoin(self.base_url, src)
                    
                    # ファイル名を取得
                    filename = os.path.basename(src)
                    save_path = os.path.join(save_dir, filename)
                    
                    # 画像をダウンロード
                    response = requests.get(full_url)
                    if response.status_code == 200:
                        with open(save_path, "wb") as f:
                            f.write(response.content)
                        
                        images_info.append({
                            "index": i,
                            "filename": filename,
                            "url": full_url,
                            "local_path": os.path.join(property_id, filename)
                        })
                        logger.debug(f"画像を保存しました: {filename}")
                    else:
                        logger.warning(f"画像のダウンロードに失敗: {full_url}")
                        
                except Exception as e:
                    logger.warning(f"画像の保存中にエラーが発生: {str(e)}")
                    continue
            
            return images_info
            
        except Exception as e:
            logger.error(f"画像の保存処理中にエラーが発生: {str(e)}")
            return None

    def load_property_history(self):
        """物件履歴を読み込み"""
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
        """物件履歴を保存"""
        try:
            # 保存先ディレクトリの作成（親ディレクトリも含めて作成）
            save_dir = os.path.dirname(self.history_file)
            logger.info(f"物件履歴の保存先ディレクトリを作成: {save_dir}")
            os.makedirs(save_dir, exist_ok=True)
            
            # processed_propertiesをリストに変換（JSON対応）
            history_data = {
                "last_updated": datetime.now().isoformat(),
                "active_properties": self.property_history["active_properties"],
                "deleted_properties": self.property_history["deleted_properties"],
                "processed_properties": list(self.property_history["processed_properties"]),
                "last_scraped": datetime.now().isoformat()
            }
            
            # 保存前の状態をログ出力
            logger.info(f"物件履歴の保存を開始: {self.history_file}")
            logger.info(f"アクティブ物件数: {len(history_data['active_properties'])}")
            logger.info(f"削除物件数: {len(history_data['deleted_properties'])}")
            logger.info(f"処理済み物件数: {len(history_data['processed_properties'])}")
            
            # JSONファイルに保存（インデント付きで見やすく保存）
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)
                f.flush()  # バッファをフラッシュして確実に書き込む
                os.fsync(f.fileno())  # ファイルシステムに確実に書き込む
            
            # 保存後の確認
            if os.path.exists(self.history_file):
                file_size = os.path.getsize(self.history_file)
                logger.info(f"物件履歴を保存しました。ファイルサイズ: {file_size:,} bytes")
            else:
                raise FileNotFoundError(f"ファイルの保存に失敗: {self.history_file}")
            
        except Exception as e:
            logger.error(f"物件履歴の保存中にエラーが発生: {str(e)}")
            logger.error(f"保存先パス: {self.history_file}")
            logger.error(f"エラーの詳細: {type(e).__name__}")
            import traceback
            logger.error(f"スタックトレース:\n{traceback.format_exc()}")
            raise  # エラーを再度発生させて、呼び出し元で処理できるようにする

    def update_property_history(self, current_properties):
        """物件履歴を更新"""
        try:
            logger.info(f"物件履歴の更新を開始: 更新対象物件数={len(current_properties)}")
            
            # 現在の物件IDリスト
            current_property_ids = {p["property_id"]: {
                "property_name": p.get("property_name", ""),
                "last_seen": datetime.now().isoformat(),
                "price": p.get("price", 0),
                "room_number": p.get("room_number", "")
            } for p in current_properties if "property_id" in p}
            
            logger.info(f"現在の物件数: {len(current_property_ids)}")
            logger.info(f"既存のアクティブ物件数: {len(self.property_history['active_properties'])}")
            
            # 既存の active_properties から削除された物件を検出
            deleted_count = 0
            for property_id in list(self.property_history["active_properties"].keys()):
                if property_id not in current_property_ids:
                    # 削除された物件を deleted_properties に移動
                    deleted_property = self.property_history["active_properties"][property_id]
                    self.property_history["deleted_properties"][property_id] = {
                        **deleted_property,
                        "deleted_at": datetime.now().isoformat()
                    }
                    deleted_count += 1
                    logger.info(f"物件が削除されました: ID={property_id}, 名称={deleted_property.get('property_name', '不明')}")
            
            # active_properties を更新
            self.property_history["active_properties"] = current_property_ids
            
            logger.info(f"物件履歴の更新完了: "
                       f"新規アクティブ物件数={len(current_property_ids)}, "
                       f"削除された物件数={deleted_count}, "
                       f"累計削除物件数={len(self.property_history['deleted_properties'])}")
            
            # 履歴を保存
            self.save_property_history()
            
        except Exception as e:
            logger.error(f"物件履歴の更新中にエラーが発生: {str(e)}")

    def is_property_processed(self, property_id):
        """物件が処理済みかどうかを確認"""
        return property_id in self.property_history["processed_properties"]

    def mark_property_as_processed(self, property_id):
        """物件を処理済みとしてマーク"""
        self.property_history["processed_properties"].add(property_id)
        logger.info(f"物件を処理済みとしてマーク: {property_id}")

    def scrape(self):
        """スクレイピングのメイン処理"""
        try:
            if not self.credentials:
                return {"status": "error", "message": "認証情報が設定されていません"}
            
            self.setup_driver()
            self.login()
            
            # 物件一覧を取得
            properties = self.get_property_list()
            
            # 物件履歴を更新
            self.update_property_history(properties)
            self.save_property_history()  # 明示的に保存
            
            # 各物件の詳細情報を取得（未処理の物件のみ）
            detailed_properties = []
            for property_info in properties:
                try:
                    property_id = property_info.get("property_id")
                    if property_id and not self.is_property_processed(property_id):
                        # 詳細情報を取得
                        detail_info = self.get_property_detail(property_id)
                        if detail_info:
                            # 一覧情報と詳細情報をマージ
                            property_info.update(detail_info)
                            detailed_properties.append(property_info)
                            # 処理済みとしてマーク
                            self.mark_property_as_processed(property_id)
                            # 履歴を保存
                            self.save_property_history()
                            logger.info(f"物件の詳細情報を取得完了: {property_id}")
                        else:
                            logger.warning(f"物件の詳細情報の取得に失敗: {property_id}")
                    else:
                        logger.info(f"物件はすでに処理済みです: {property_id}")
                        
                except Exception as e:
                    logger.warning(f"物件詳細情報の取得中にエラーが発生: {str(e)}")
                    continue
            
            # 最後に物件履歴を更新
            self.update_property_history(detailed_properties)
            self.save_property_history()  # 明示的に保存
            
            return {
                "status": "success",
                "message": "スクレイピングが完了しました",
                "data": {
                    "properties": detailed_properties,
                    "history": {
                        "active_count": len(self.property_history["active_properties"]),
                        "deleted_count": len(self.property_history["deleted_properties"]),
                        "processed_count": len(self.property_history["processed_properties"]),
                        "last_scraped": self.property_history["last_scraped"]
                    }
                }
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if self.driver:
                self.driver.quit()

    def __del__(self):
        """デストラクタ：ドライバーの終了処理"""
        if self.driver:
            self.driver.quit() 