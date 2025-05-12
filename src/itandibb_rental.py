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


class ItandiBBRentalScraper:
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.data_dir = "data/itandibb_rental"
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

            search_rows_all = WebDriverWait(driver, 30).until(
                EC.presence_of_all_elements_located((By.XPATH, "//tr[contains(@class, 'MuiTableRow-root')]"))
            )
            self.logger.info(f"{len(search_rows_all)} 件の検索条件（含むタイトル）を検出。")

            for idx in range(1, len(search_rows_all)):
                try:
                    search_rows = driver.find_elements(By.XPATH, "//tr[contains(@class, 'MuiTableRow-root')]")
                    if idx >= len(search_rows):
                        self.logger.warning(f"[検索条件 {idx}] は存在しません。スキップ。")
                        continue

                    row = search_rows[idx]
                    self.logger.info(f"[検索条件 {idx}] クリック: {row.text}")
                    driver.execute_script("arguments[0].click();", row)
                    time.sleep(2)

                    while True:
                        try:
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//a[starts-with(@href, '/rent_rooms/')]"))
                            )
                            links = driver.find_elements(By.XPATH, "//a[starts-with(@href, '/rent_rooms/')]")
                        except TimeoutException:
                            self.logger.info(f"[検索条件 {idx}] 物件が存在しません。スキップ。")
                            break

                        for link in links:
                            try:
                                href = link.get_attribute("href")
                                match = re.search(r"/rent_rooms/(\d+)", href)
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

                                api_url = f"https://api.itandibb.com/api/internal/v4/rent_rooms/{property_id}"
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
                                self.logger.info(f"[検索条件 {idx}] 最終ページです。終了。")
                                break
                            else:
                                self.logger.info(f"[検索条件 {idx}] 次ページへ進みます。")
                                next_btn.click()
                                time.sleep(3)
                        except NoSuchElementException:
                            self.logger.info(f"[検索条件 {idx}] 次へボタンが見つかりません。終了。")
                            break

                    self.logger.info(f"[検索条件 {idx}] 完了。トップページに戻ります。")
                    driver.get("https://itandibb.com/top")
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//tr[contains(@class, 'MuiTableRow-root')]"))
                    )

                except Exception as e:
                    self.logger.warning(f"[検索条件 {idx}] の処理中にエラー: {e}")
                    self.logger.debug(traceback.format_exc())
                    driver.save_screenshot(f"search_error_{idx}.png")
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


if __name__ == "__main__":
    credentials = {"user_id": "info@mark-one.co.jp", "password": "mk460102"}
    scraper = ItandiBBRentalScraper(credentials)
    result = scraper.scrape()
    logging.getLogger("itandibb").info(f"スクレイピング結果: {result}")
