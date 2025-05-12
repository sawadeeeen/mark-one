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

from utils import save_updated_properties

class ArchScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.data_dir = "data/arch"
        os.makedirs(self.data_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)

        self.credentials = credentials
        self.history_file = os.path.join(self.data_dir, "property_history.json")
        self.processed_ids = set()
        self.deleted_ids = set()
        
        # property_history.jsonを読み込む
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r', encoding='utf-8') as f:
                self.history_data = json.load(f)
        else:
            self.history_data = {"processed": [], "deleted": []}

    def update_history(self, property_id: str, is_deleted: bool = False):
        if is_deleted:
            self.deleted_ids.add(property_id)
        else:
            self.processed_ids.add(property_id)
        
        # JSONファイルを更新
        self.history_data["processed"] = list(self.processed_ids)
        self.history_data["deleted"] = list(self.deleted_ids)
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history_data, f, ensure_ascii=False, indent=4)

    def scrape(self) -> Dict[str, Any]:
        self.logger.info("ログインを開始します")
        
        email = self.credentials["user_id"]
        password = self.credentials["password"]
        
        # Seleniumドライバーの設定
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--window-size=1024,768')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            driver.get("https://www.arch.gr.jp/")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "login_mail"))
            )
            driver.find_element(By.NAME, "login_mail").send_keys(email)
            driver.find_element(By.NAME, "login_pass").send_keys(password)
            driver.find_element(By.NAME, "submit").click()
            self.logger.info("ログインに成功しました")
            
            # 物件一覧ページを開く
            driver.get("https://www.arch.gr.jp/itiran.html")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            self.logger.info("物件一覧ページを表示しました")
            
            # 物件一覧から詳細ページに移動
            visited_links = set()
            property_links = driver.find_elements(By.XPATH, "//tr[@class='def']//a")
            for link in property_links:
                href = link.get_attribute("href")
                if href:
                    property_id = href.split("/")[-2]
                    
                    # 既に処理済みの物件IDはスキップ
                    if property_id in self.history_data["processed"]:
                        self.logger.info(f"物件ID {property_id} は既に処理済みです。スキップします。")
                        continue
                    
                    visited_links.add(href)
                    driver.get(href)
                    self.logger.info(f"詳細ページに移動しました: {href}")
                    
                    # 準備中の物件をスキップ
                    try:
                        preparation_message = driver.find_element(By.XPATH, "//div[@class='itiran']").text
                        if "この物件は，ただいま準備中です。" in preparation_message:
                            self.logger.info(f"物件ID {property_id} は準備中のためスキップします。")
                            continue
                    except Exception:
                        pass  # 準備中メッセージがない場合は通常の処理を続行
                    
                    # 詳細ページから情報を取得
                    try:
                        # 要素が表示されるまで待機
                        property_name_element = WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, "//td[text()='物件名']/following-sibling::td"))
                        )
                        property_name = property_name_element.text.strip()
                    except Exception as e:
                        self.logger.error(f"物件名の取得に失敗しました: {str(e)}")
                    price = driver.find_element(By.XPATH, "//td[text()='価格']/following-sibling::td").text.strip()
                    transport = driver.find_element(By.XPATH, "//td[text()='交通']/following-sibling::td").text.strip()
                    location = driver.find_element(By.XPATH, "//td[text()='所在地']/following-sibling::td").text.strip()
                    latitude = driver.find_element(By.XPATH, "//iframe").get_attribute("src").split("geo_lat=")[1].split("&")[0]
                    longitude = driver.find_element(By.XPATH, "//iframe").get_attribute("src").split("geo_lng=")[1].split("&")[0]
                    
                    # 追加情報を取得
                    building = driver.find_element(By.XPATH, "//td[text()='建物']/following-sibling::td").text.strip()
                    land = driver.find_element(By.XPATH, "//td[text()='土地']/following-sibling::td").text.strip()
                    area = driver.find_element(By.XPATH, "//td[text()='面積']/following-sibling::td").text.strip()
                    year_built = driver.find_element(By.XPATH, "//td[text()='築年']/following-sibling::td").text.strip()
                    construction = driver.find_element(By.XPATH, "//td[text()='施工']/following-sibling::td").text.strip()
                    management_fee = driver.find_element(By.XPATH, "//td[text()='管理費']/following-sibling::td").text.strip()
                    management_type = driver.find_element(By.XPATH, "//td[text()='管理形態']/following-sibling::td").text.strip()
                    management_company = driver.find_element(By.XPATH, "//td[text()='管理会社']/following-sibling::td").text.strip()
                    total_units = driver.find_element(By.XPATH, "//td[text()='総戸数']/following-sibling::td").text.strip()
                    layout = driver.find_element(By.XPATH, "//td[text()='間取り']/following-sibling::td").text.strip()
                    delivery_date = driver.find_element(By.XPATH, "//td[text()='引渡日']/following-sibling::td").text.strip()
                    interior = driver.find_element(By.XPATH, "//td[text()='内装']/following-sibling::td").text.strip()
                    flat35 = driver.find_element(By.XPATH, "//td[text()='フラット３５']/following-sibling::td").text.strip()
                    office_use = driver.find_element(By.XPATH, "//td[text()='事務所使用']/following-sibling::td").text.strip()
                    pets = driver.find_element(By.XPATH, "//td[text()='ペット']/following-sibling::td").text.strip()
                    parking = driver.find_element(By.XPATH, "//td[text()='駐車場']/following-sibling::td").text.strip()
                    remarks = driver.find_element(By.XPATH, "//td[text()='備考']/following-sibling::td").text.strip()
                    
                    # JSONに保存
                    property_data = {
                        "物件名": property_name,
                        "価格": price,
                        "交通": transport,
                        "所在地": location,
                        "緯度": latitude,
                        "経度": longitude,
                        "建物": building,
                        "土地": land,
                        "面積": area,
                        "築年": year_built,
                        "施工": construction,
                        "管理費": management_fee,
                        "管理形態": management_type,
                        "管理会社": management_company,
                        "総戸数": total_units,
                        "間取り": layout,
                        "引渡日": delivery_date,
                        "内装": interior,
                        "フラット３５": flat35,
                        "事務所使用": office_use,
                        "ペット": pets,
                        "駐車場": parking,
                        "備考": remarks
                    }
                    
                    json_path = os.path.join(self.data_dir, f"{property_id}.json")
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(property_data, f, ensure_ascii=False, indent=4)
                    
                    self.logger.info(f"情報を保存しました: {json_path}")
                    
                    # 物件IDを処理済みとして更新
                    self.update_history(property_id)
                    
                    # 更新物件情報を保存
                    save_updated_properties(json_path)
                    
                    # 一覧ページに戻る
                    driver.execute_script("window.history.back()")
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    self.logger.info("一覧ページに戻りました")
            
            # 削除済みIDを更新
            for old_id in self.history_data["processed"]:
                if old_id not in self.processed_ids:
                    self.update_history(old_id, is_deleted=True)
            
            return {
                "status": "success",
                "message": "物件情報の取得に成功しました"
            }
        except Exception as e:
            self.logger.error(f"エラーが発生しました: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
        finally:
            driver.quit()

# 使用例
if __name__ == "__main__":
    credentials = {"user_id": "your_email@example.com", "password": "your_password"}
    scraper = ArchScraper(credentials)
    scraper.scrape()
