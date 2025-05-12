import os
import json
from typing import Any, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import traceback
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import time

from utils import save_updated_properties

class     IntellicsScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.data_dir = "data/bukkaku_flie"
        os.makedirs(self.data_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)

        self.credentials = credentials
        self.property_history_path = os.path.join(self.data_dir, "property_history.json")
        self.property_history = self.load_property_history()
        
    def load_property_history(self) -> Dict[str, Any]:
        if os.path.exists(self.property_history_path):
            with open(self.property_history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 必要なキーが存在しない場合は初期化
                if "processed" not in data:
                    data["processed"] = []
                if "deleted" not in data:
                    data["deleted"] = []
                if "updated" not in data:
                    data["updated"] = []
                if "property_info" not in data:
                    data["property_info"] = {}
                return data
        return {
            "processed": [],  # 処理済み物件IDのリスト（変更なし）
            "deleted": [],    # 削除済み物件IDのリスト
            "updated": [],    # 更新された物件IDのリスト（新規または変更あり）
            "property_info": {}  # 物件IDごとの変更年月日と更新年月日
        }
    
    def update_property_history(self):
        with open(self.property_history_path, "w", encoding="utf-8") as f:
            json.dump(self.property_history, f, ensure_ascii=False, indent=4)
        
    def scrape(self) -> Dict[str, Any]:
        self.logger.info("ログインを開始します")
        
        # 物件履歴を読み込む
        self.property_history = self.load_property_history()
        processed_ids = set(self.property_history["processed"])
        deleted_ids = set(self.property_history["deleted"])
        updated_ids = set(self.property_history["updated"])
        property_info = self.property_history["property_info"]
        
        email = self.credentials["user_id"]
        password = self.credentials["password"]
        
        # Seleniumドライバーの設定
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--window-size=1024,768')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            driver.get("https://bukkaku.flie.jp/agent/sign_in")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "agent_email"))
            )
            driver.find_element(By.ID, "agent_email").send_keys(email)
            driver.find_element(By.ID, "agent_password").send_keys(password)
            driver.find_element(By.NAME, "commit").click()
            self.logger.info("ログインに成功しました")
            
            # 売主一覧ページのURLを記憶
            seller_list_url = driver.current_url
            
            # 売主の名前をすべて取得し、配列に保存
            seller_names = []
            seller_elements = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, "//div[@class='MuiButtonBase-root MuiListItemButton-root MuiListItemButton-gutters MuiListItemButton-root MuiListItemButton-gutters css-h9e5s1']"))
            )
            for seller in seller_elements:
                seller_names.append(seller.text.replace(" ", "_"))
            
            # 各売主を順番に処理
            for seller_name in seller_names:
                try:
                    # 売主一覧ページに戻る
                    driver.get(seller_list_url)
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_all_elements_located((By.XPATH, "//div[@class='MuiButtonBase-root MuiListItemButton-root MuiListItemButton-gutters MuiListItemButton-root MuiListItemButton-gutters css-h9e5s1']"))
                    )
                    
                    # 売主をクリック
                    seller = driver.find_element(By.XPATH, f"//div[text()='{seller_name.replace('_', ' ')}']")
                    self.logger.info(f"売主をクリックします: {seller_name}")
                    driver.execute_script("arguments[0].scrollIntoView();", seller)
                    seller.click()
                    
                    # 物件情報を取得
                    current_property_ids = []
                    while True:
                        try:
                            # 物件情報を含むdivを取得
                            property_elements = WebDriverWait(driver, 20).until(
                                EC.presence_of_all_elements_located((By.XPATH, "//div[@class='MuiGrid-root MuiGrid-container css-1d3bbye']"))
                            )
                            
                            for element in property_elements:
                                try:
                                    # 物件IDを取得
                                    property_id = element.get_attribute("data-property-id")
                                    current_property_ids.append(property_id)
                                    
                                    # 物件履歴のチェック
                                    if property_id:
                                        # 物件が処理済みリストに存在する場合
                                        if property_id in processed_ids:
                                            self.logger.info(f"物件 {property_id} は既に処理済みで、変更もありません。スキップします。")
                                            continue
                                        else:
                                            # 物件が処理済みリストに存在しない場合（新規物件）
                                            updated_ids.add(property_id)  # 新規物件は更新リストに追加
                                            property_info[property_id] = {
                                                "変更年月日": element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-div css-5zhqi1']").text,
                                                "更新年月日": element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-div css-1uk1gs8']/span").text
                                            }
                                            self.property_history["updated"] = list(updated_ids)
                                            self.property_history["property_info"] = property_info
                                            self.update_property_history()
                                            self.logger.info(f"物件 {property_id} を新規物件として追加しました。")

                                        # 物件が削除済みリストに存在する場合
                                        if property_id in deleted_ids:
                                            self.logger.info(f"物件 {property_id} は削除済みとして扱われていましたが、再登録されています。")
                                            deleted_ids.remove(property_id)
                                            updated_ids.add(property_id)  # 再登録物件は更新リストに追加
                                            property_info[property_id] = {
                                                "変更年月日": element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-div css-5zhqi1']").text,
                                                "更新年月日": element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-div css-1uk1gs8']/span").text
                                            }
                                            self.property_history["deleted"] = list(deleted_ids)
                                            self.property_history["updated"] = list(updated_ids)
                                            self.property_history["property_info"] = property_info
                                            self.update_property_history()
                                    
                                    # 物件名と部屋番号
                                    name_room = element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-h5 css-1cgz97i']").text
                                    # 金額
                                    price = element.find_element(By.XPATH, ".//h6[@class='MuiTypography-root MuiTypography-h6 css-2sihsm']").text
                                    # 住所
                                    address = element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-div css-5zhqi1']").text
                                    # 販売会社
                                    company = element.find_element(By.XPATH, ".//div[@class='MuiTypography-root MuiTypography-div css-1uk1gs8']/span").text
                                    
                                    property_data = {
                                        "物件名・部屋番号": name_room,
                                        "金額": price,
                                        "住所": address,
                                        "販売会社": company
                                    }
                                    
                                    # JSONファイルに保存
                                    file_name = f"{name_room.replace(' ', '_').replace('/', '_')}.json"
                                    with open(os.path.join(self.data_dir, file_name), "w", encoding="utf-8") as f:
                                        json.dump(property_data, f, ensure_ascii=False, indent=4)
                                        
                                    # 更新物件情報を保存
                                    save_updated_properties(os.path.join(self.data_dir, file_name))
                                    
                                except Exception as e:
                                    self.logger.error(f"物件情報の取得中にエラーが発生しました: {str(e)}")
                                    self.logger.debug(traceback.format_exc())
                            
                            # 次のページがあるか確認し、あればクリック
                            try:
                                next_button = driver.find_element(By.XPATH, "//button[@aria-label='Go to next page']")
                                driver.execute_script("arguments[0].scrollIntoView();", next_button)
                                next_button.click()
                                WebDriverWait(driver, 20).until(EC.staleness_of(property_elements[0]))
                            except Exception:
                                self.logger.info("次のページはありません。売主一覧に戻ります。")
                                break
                        
                        except Exception as e:
                            self.logger.error(f"物件情報の取得中にエラーが発生しました: {str(e)}")
                            self.logger.debug(traceback.format_exc())
                            break
                    
                    # 処理済みリストに存在する物件IDが今回のスクレイピング結果に存在しない場合
                    current_processed_ids = set(self.property_history["processed"])
                    for old_id in current_processed_ids:
                        if old_id not in current_property_ids:
                            self.logger.info(f"物件 {old_id} は今回のスクレイピング結果に存在しません。削除済みとして扱います。")
                            deleted_ids.add(old_id)
                            processed_ids.remove(old_id)
                            if old_id in property_info:
                                del property_info[old_id]
                            self.property_history["processed"] = list(processed_ids)
                            self.property_history["deleted"] = list(deleted_ids)
                            self.property_history["property_info"] = property_info
                            self.update_property_history()
                
                except StaleElementReferenceException as e:
                    self.logger.error(f"売主の処理中にエラーが発生しました: {str(e)}")
                    self.logger.debug(traceback.format_exc())
                    continue  # 次の売主に進む
                
                except Exception as e:
                    self.logger.error(f"売主の処理中にエラーが発生しました: {str(e)}")
                    self.logger.debug(traceback.format_exc())
            
            return {
                "status": "success",
                "message": "すべての売主の物件情報を取得し、保存しました"
            }
        except Exception as e:
            self.logger.error(f"エラーが発生しました: {str(e)}")
            self.logger.debug(traceback.format_exc())
            return {
                "status": "error",
                "message": str(e)
            }
        finally:
            driver.quit()

# 使用例
if __name__ == "__main__":
    credentials = {"user_id": "komatsu@mark-one.co.jp", "password": "mk460102"}
    scraper = IntellicsScraper(credentials)
    scraper.scrape()
