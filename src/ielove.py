import json
import os
import logging
import time
from typing import Dict, Any, List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # ログレベルをDEBUGに設定

# コンソールハンドラの設定
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class IeloveDataFormatter:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.data_dir = "data"
        self.merged_file = "merged.json"
        
        # 別名マッピング
        self.key_mappings = {
            "ファイルパス": ["ファイルパス"],
            "その他交通": ["その他交通", "バス停", "バス停 徒歩"],
            "その他費用": ["その他費用", "その他費用月額"],
            "テラス面積": ["テラス面積", "バルコニー(テラス)面積", "物件情報.バルコニー面積"],
            "バルコニー方向": ["バルコニー方向", "向き"],
            "バルコニー面積": ["バルコニー面積", "物件情報.バルコニー面積"],
            "引渡時期": ["引渡時期", "引渡日", "入居可能時期"],
            "価格": ["価格", "金額", "販売価格", "賃料", "物件情報.価格", "物件情報.販売価格"],
            "画像": ["画像", "物件情報.画像"],
            "階建": ["階建", "階数", "構造・所在階", "物件情報.階建 / 所在階"],
            "管理会社": ["管理会社", "管理会社名", "分譲会社名"],
            "管理形態": ["管理形態", "物件情報.管理形態"],
            "管理人": ["管理人", "管理人状況"],
            "管理組合": ["管理組合", "管理組合有無"],
            "管理費": ["管理費", "管理費月額", "共益費", "物件情報.管理費"],
            "間取り": ["間取り", "部屋数・間取り", "物件情報.間取り"],
            "契約期間": ["契約期間"],
            "建築年月": ["建築年月", "築年月", "築年", "築年数", "物件情報.築年月"],
            "建物": ["建物"],
            "建物構造": ["建物構造", "構造", "物件情報.構造"],
            "建物名": ["建物名", "建物名・号室", "物件名", "物件名・部屋番号", "物件情報.物件名", "物件情報.物件名_詳細"],
            "現況": ["現況"],
            "交通": ["交通", "物件情報.交通"],
            "向き": ["向き", "バルコニー方向"],
            "更新料": ["更新料"],
            "構造・所在階": ["構造・所在階", "階建", "階数", "物件情報.階建 / 所在階"],
            "最寄り駅": ["最寄り駅", "交通", "物件情報.交通"],
            "最寄り駅 徒歩": ["最寄り駅 徒歩"],
            "施工会社名": ["施工会社名"],
            "事務所使用": ["事務所使用"],
            "修繕積立金": ["修繕積立金", "修繕積立金月額", "物件情報.修繕積立金"],
            "住所": ["住所", "所在地", "所在地名１", "所在地名２", "所在地名３", "物件情報.所在地"],
            "所在階": ["所在階", "構造・所在階", "物件情報.階建 / 所在階"],
            "設備": ["設備", "設備/構造/リフォーム", "設備・条件・住宅性能等"],
            "専有面積": ["専有面積", "面積", "物件情報.専有面積"],
            "専用庭面積": ["専用庭面積"],
            "総戸数": ["総戸数", "総戸(室)数"],
            "地下階層": ["地下階層", "地上階層"],
            "築年月": ["築年月", "築年", "築年数", "建築年月", "物件情報.築年月"],
            "駐車場": ["駐車場", "駐車場（月額）", "駐車場月額", "駐車場・駐輪場/庭", "駐車場在否"],
            "駐輪場": ["駐輪場"],
            "賃料": ["賃料", "価格", "金額", "販売価格"],
            "都道府県名": ["都道府県名"],
            "内装": ["内装"],
            "入居可能時期": ["入居可能時期", "引渡時期", "引渡日"],
            "販売価格": ["販売価格", "価格", "金額", "賃料", "物件情報.価格", "物件情報.販売価格"],
            "備考": ["備考", "物件情報.備考"],
            "敷金": ["敷金"],
            "部屋数・間取り": ["部屋数・間取り", "間取り", "物件情報.間取り"],
            "部屋番号": ["部屋番号"],
            "物件名": ["物件名", "物件名・部屋番号", "建物名", "建物名・号室", "物件情報.物件名", "物件情報.物件名_詳細"],
            "分譲会社名": ["分譲会社名", "管理会社", "管理会社名"],
            "面積": ["面積", "専有面積", "物件情報.専有面積"],
            "容積率": ["容積率"],
            "用途地域": ["用途地域", "用途地域1", "用途地域2"],
            "礼金": ["礼金"]
        }

    def get_value_from_aliases(self, data: Dict[str, Any], key: str) -> Any:
        """
        キーとその別名から値を取得します。
        
        Args:
            data (Dict[str, Any]): データ
            key (str): キー
            
        Returns:
            Any: 取得した値（キーが存在しない場合は空文字列）
        """
        # 直接キーが存在する場合
        if key in data and data[key] is not None:
            return data[key]
            
        # キーがメインキーとして登録されている場合
        if key in self.key_mappings:
            for alias in self.key_mappings[key]:
                if alias in data and data[alias] is not None:
                    return data[alias]
                    
        # キーが別名として登録されている場合
        for main_key, aliases in self.key_mappings.items():
            if key in aliases and main_key in data and data[main_key] is not None:
                return data[main_key]
                
        return ""

    def format_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        データを整形します。
        
        Args:
            data (Dict[str, Any]): 整形前のデータ
            
        Returns:
            Dict[str, Any]: 整形後のデータ
        """
        formatted_data = {}
        for key in self.key_mappings.keys():
            formatted_data[key] = self.get_value_from_aliases(data, key)
        return formatted_data

    def process_merged_file(self) -> List[Dict[str, Any]]:
        """
        merged.jsonファイルを処理します。
        
        Returns:
            List[Dict[str, Any]]: 処理済みのデータリスト
        """
        try:
            with open(os.path.join(self.data_dir, self.merged_file), "r", encoding="utf-8") as f:
                data = json.load(f)
                
            formatted_data = []
            for item in data:
                formatted_data.append(self.format_data(item))
                
            return formatted_data
            
        except Exception as e:
            self.logger.error(f"ファイルの処理中にエラーが発生しました: {str(e)}")
            return []

    def save_formatted_data(self, data: List[Dict[str, Any]], output_file: str = "ielove.json"):
        """
        整形済みデータを保存します。
        
        Args:
            data (List[Dict[str, Any]]): 保存するデータ
            output_file (str): 出力ファイル名
        """
        try:
            with open(os.path.join(self.data_dir, output_file), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"ファイルの保存中にエラーが発生しました: {str(e)}")

class IeloveScraper:
    def __init__(self, user_id, password):
        self.user_id = user_id
        self.password = password
        self.base_url = "https://cloud.ielove.jp"
        self.login_url = f"{self.base_url}/introduction/index/login/changePc/1"
        
        # Chromeオプションの設定
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1024,768')
        chrome_options.add_argument('--disable-gpu')
        
        # エラー回避のための追加オプション
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-dev-tools')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--no-default-browser-check')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # プロファイルディレクトリの設定
        profile_dir = os.path.join(os.getcwd(), 'chrome_profile')
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir)
        chrome_options.add_argument(f'--user-data-dir={profile_dir}')
        
        try:
            # WebDriverの初期化
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.wait = WebDriverWait(self.driver, 10)
        except Exception as e:
            logger.error(f"Chromeの起動に失敗しました: {str(e)}")
            raise

    def login(self):
        """いえらぶにログインする"""
        try:
            # ログインページにアクセス
            logger.debug("ログインページにアクセスします")
            self.driver.get(self.login_url)
            
            # ページの読み込みを待機
            self.driver.implicitly_wait(10)
            
            # ログインフォームの要素を待機
            logger.debug("ログインフォームの要素を待機します")
            try:
                # ユーザーIDフィールドを待機
                user_id_field = self.wait.until(
                    EC.presence_of_element_located((By.ID, "_4407f7df050aca29f5b0c2592fb48e60"))
                )
                # パスワードフィールドを待機
                password_field = self.wait.until(
                    EC.presence_of_element_located((By.ID, "_81fa5c7af7ae14682b577f42624eb1c0"))
                )
                
                # ログイン情報を入力
                logger.debug("ログイン情報を入力します")
                user_id_field.clear()
                user_id_field.send_keys(self.user_id)
                password_field.clear()
                password_field.send_keys(self.password)
                
                # 自動ログインを有効にする
                try:
                    auto_login_checkbox = self.wait.until(
                        EC.element_to_be_clickable((By.ID, "autoLogin"))
                    )
                    auto_login_checkbox.click()
                    logger.debug("自動ログインを有効にしました")
                except Exception as e:
                    logger.debug(f"自動ログインの設定中にエラーが発生しました（無視します）: {str(e)}")
                
                # ログインボタンを待機してクリック
                logger.debug("ログインボタンをクリックします")
                login_button = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "loginButton"))
                )
                login_button.click()
                
                # ログイン後のダイアログを処理
                try:
                    logger.debug("ログイン後のダイアログを処理します")
                    # 閉じるボタンを待機してクリック
                    close_button = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".dialog_close.fa.fa-remove"))
                    )
                    close_button.click()
                    logger.debug("ダイアログを閉じました")
                except Exception as e:
                    logger.debug(f"ダイアログの処理中にエラーが発生しました（無視します）: {str(e)}")
                
                time.sleep(5)  # ログイン処理の完了を待機
                
                # ログイン成功の確認
                logger.debug("ログイン成功を確認します")
                try:
                    # ログイン後のページ遷移を待機
                    self.wait.until(
                        lambda driver: "ログアウト" in driver.page_source or "マイページ" in driver.page_source
                    )
                    logger.info("いえらぶへのログインに成功しました")
                    return True
                except Exception as e:
                    logger.error(f"ログイン成功の確認中にエラーが発生しました: {str(e)}")
                    # エラー時のページソースをログに出力
                    logger.debug(f"現在のページソース: {self.driver.page_source[:1000]}")
                    return False
                    
            except Exception as e:
                logger.error(f"ログインフォームの操作中にエラーが発生しました: {str(e)}")
                # エラー時のスクリーンショットを保存
                self.driver.save_screenshot("login_error.png")
                # エラー時のページソースをログに出力
                logger.debug(f"現在のページソース: {self.driver.page_source[:1000]}")
                return False

        except Exception as e:
            logger.error(f"いえらぶへのログイン中にエラーが発生しました: {str(e)}")
            return False

    def logout(self):
        """いえらぶからログアウトする"""
        try:
            logout_url = f"{self.base_url}/introduction/index/logout"
            self.driver.get(logout_url)
            logger.info("いえらぶからログアウトしました")
        except Exception as e:
            logger.error(f"いえらぶからのログアウト中にエラーが発生しました: {str(e)}")
        finally:
            self.driver.quit()

    def __del__(self):
        """デストラクタ"""
        try:
            self.driver.quit()
        except:
            pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    formatter = IeloveDataFormatter()
    formatted_data = formatter.process_merged_file()
    formatter.save_formatted_data(formatted_data)
    print(f"処理完了: {len(formatted_data)}件のデータを処理しました") 