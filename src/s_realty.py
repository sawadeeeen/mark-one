import os
import json
import logging
from typing import Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from utils import save_updated_properties

# ロガーの設定
logger = logging.getLogger(__name__)

class SRealtyScraper:
    def __init__(self, credentials=None):
        """
        シンプレックス・リアルティのスクレイパーを初期化します。

        Args:
            credentials (Dict[str, str], optional): 認証情報
        """
        self.base_url = "https://www.s-realty.co.jp"
        self.search_url = f"{self.base_url}/buy/"
        self.data_dir = "data/s-realty"
        
        # データ保存用ディレクトリの作成
        os.makedirs(self.data_dir, exist_ok=True)
        logger.info(f"データ保存ディレクトリを作成しました: {self.data_dir}")

    def scrape(self) -> Dict[str, Any]:
        """
        物件情報をスクレイピングします。

        Returns:
            Dict[str, Any]: {
                "status": "success" | "error",
                "message": str,
                "物件一覧": List[Dict] (成功時のみ),
                "総件数": int (成功時のみ)
            }
        """
        driver = None
        try:
            logger.info("スクレイピングを開始します")
            
            # 物件履歴を読み込む
            history_path = os.path.join(self.data_dir, "property_history.json")
            if os.path.exists(history_path):
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            else:
                history = {
                    "処理済み": [],
                    "削除済み": []
                }
            logger.info(f"物件履歴を読み込みました: 処理済み {len(history['処理済み'])}件, 削除済み {len(history['削除済み'])}件")
            
            # Seleniumドライバーの設定
            options = Options()
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1024,768')
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # 物件一覧ページにアクセス
            driver.get(self.search_url)
            logger.info("物件一覧ページにアクセスしました")
            
            # ページが完全に読み込まれるまで待機
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul.buy-index__list"))
                )
                logger.info("ページの読み込みが完了しました")
            except Exception as e:
                logger.error(f"ページの読み込みでタイムアウト: {str(e)}")
                raise
            
            # 物件一覧を取得
            print("物件一覧を取得します")
            properties = []
            current_property_ids = []  # 現在の物件ID一覧
            property_elements = driver.find_elements(By.CSS_SELECTOR, "ul.buy-index__list li")
            logger.info(f"物件要素数: {len(property_elements)}件")
            
            if not property_elements:
                logger.warning("物件要素が見つかりませんでした")
                # ページのHTMLを出力してデバッグ
                logger.debug(f"ページのHTML: {driver.page_source}")
                return {
                    "status": "error",
                    "message": "物件要素が見つかりませんでした",
                    "物件一覧": [],
                    "総件数": 0
                }
            
            for element in property_elements:
                try:
                    # 物件リンクを取得
                    link = element.find_element(By.CSS_SELECTOR, "a")
                    property_url = link.get_attribute("href")
                    
                    # 物件IDを抽出
                    property_id = property_url.strip('/').split('/')[-1]
                    current_property_ids.append(property_id)
                    
                    # 処理済みの物件はスキップ
                    if property_id in history["処理済み"]:
                        logger.info(f"物件ID {property_id} は処理済みのためスキップします")
                        continue
                    
                    # 物件基本情報を取得
                    property_info = {
                        "物件名": element.find_element(By.CSS_SELECTOR, "h3.title-s--mt0").text,
                        "URL": property_url,
                        "価格": element.find_element(By.CSS_SELECTOR, "p.buy-index__price").text,
                        "所在地": element.find_element(By.CSS_SELECTOR, "dl.buy-index__summary dd:nth-of-type(1)").text,
                        "交通": element.find_element(By.CSS_SELECTOR, "dl.buy-index__summary dd:nth-of-type(2)").text,
                        "間取り": element.find_element(By.CSS_SELECTOR, "dl.buy-index__summary dd:nth-of-type(3)").text,
                        "専有面積": element.find_element(By.CSS_SELECTOR, "dl.buy-index__summary dd:nth-of-type(4)").text,
                        "築年月": element.find_element(By.CSS_SELECTOR, "dl.buy-index__summary dd:nth-of-type(5)").text,
                    }
                    
                    # NEWラベルの有無を確認
                    try:
                        new_label = element.find_element(By.CSS_SELECTOR, "span.buy-index__new")
                        property_info["新着"] = True
                    except:
                        property_info["新着"] = False
                    
                    # 物件詳細ページにアクセス
                    logger.info(f"物件詳細ページにアクセス: {property_url}")
                    driver.get(property_url)
                    
                    # ページ読み込み完了を待機
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h2.title-l"))
                    )
                    
                    # 物件詳細情報を取得
                    try:
                        logger.info(f"物件詳細情報の取得を開始: {property_url}")
                        
                        detail_property_name = driver.find_element(By.CSS_SELECTOR, "h2.title-l").text
                        property_info["物件名_詳細"] = detail_property_name
                        logger.info(f"物件詳細名を取得: {detail_property_name}")
                        
                        # 物件概要を取得
                        summary_elements = driver.find_elements(By.CSS_SELECTOR, "ul.buy-article__summary li")
                        for element in summary_elements:
                            try:
                                title = element.find_element(By.CSS_SELECTOR, "p.title-s--mt0").text
                                text = element.find_element(By.CSS_SELECTOR, "p.txt").text
                                property_info[title] = text
                            except Exception as e:
                                logger.warning(f"物件概要の要素取得でエラー: {str(e)}")
                        
                        # 備考を取得（配列として保存）
                        try:
                            remarks_text = driver.find_element(By.CSS_SELECTOR, "div.buy-article__box2 p.txt--mb40").text
                            remarks = [line.strip() for line in remarks_text.split('\n') if line.strip()]
                            property_info["備考"] = remarks
                            logger.info(f"備考を取得: {len(remarks)}件")
                        except Exception as e:
                            logger.warning(f"備考の取得でエラー: {str(e)}")
                            property_info["備考"] = []
                        
                        # 物件紹介を取得
                        try:
                            introduction = driver.find_element(By.CSS_SELECTOR, "div.buy-article__introduction p.txt").text
                            property_info["物件紹介"] = introduction
                            logger.info("物件紹介を取得")
                        except Exception as e:
                            logger.warning(f"物件紹介の取得でエラー: {str(e)}")
                            property_info["物件紹介"] = ""
                        
                        # 物件IDをURLから抽出
                        property_id = property_url.strip('/').split('/')[-1]
                        property_info["物件ID"] = property_id
                        logger.info(f"物件ID: {property_id}")
                        
                        # 画像情報を取得
                        logger.info("画像情報の取得を開始")
                        images = []
                        image_elements = driver.find_elements(By.CSS_SELECTOR, "ul.slick-dots li img")
                        logger.info(f"画像要素数: {len(image_elements)}件")
                        
                        if image_elements:
                            # 物件ごとのディレクトリを作成
                            property_dir = os.path.join(self.data_dir, property_id)
                            os.makedirs(property_dir, exist_ok=True)
                            logger.info(f"物件ディレクトリを作成: {property_dir}")
                            
                            import requests
                            from urllib.parse import urlparse
                            
                            for index, img in enumerate(image_elements, 1):
                                try:
                                    img_url = img.get_attribute("src")
                                    logger.info(f"画像{index}のURL: {img_url}")
                                    
                                    img_class = img.get_attribute("class") or ""
                                    
                                    # 画像の種類を判定
                                    image_type = "その他"
                                    if "bg-black-img" in img_class:
                                        image_type = "間取り図"
                                    logger.info(f"画像{index}の種類: {image_type}")
                                    
                                    # 画像URLからファイル名を取得
                                    filename = os.path.basename(urlparse(img_url).path)
                                    logger.info(f"画像{index}のファイル名: {filename}")
                                    
                                    # 画像をダウンロード
                                    logger.info(f"画像{index}のダウンロード開始")
                                    response = requests.get(img_url)
                                    if response.status_code == 200:
                                        image_path = os.path.join(property_dir, filename)
                                        with open(image_path, "wb") as f:
                                            f.write(response.content)
                                        logger.info(f"画像{index}を保存しました: {image_path}")
                                        
                                        # 画像情報を記録
                                        images.append({
                                            "インデックス": index,
                                            "URL": img_url,
                                            "ファイル名": filename,
                                            "保存パス": os.path.join(property_id, filename),
                                            "種類": image_type
                                        })
                                        logger.info(f"画像{index}の情報を記録")
                                    else:
                                        logger.warning(f"画像{index}のダウンロードに失敗: ステータスコード {response.status_code}")
                                except Exception as e:
                                    logger.warning(f"画像{index}の処理中にエラー: {str(e)}")
                                    continue
                            
                            property_info["画像"] = images
                            logger.info(f"物件の画像情報を保存: 合計{len(images)}件")
                        else:
                            logger.warning("画像要素が見つかりませんでした")

                        # 物件ごとのJSONファイルを保存
                        property_json = {
                            "ステータス": "成功",
                            "メッセージ": "物件情報を取得しました",
                            "物件情報": property_info
                        }
                        
                        # ファイル名に使用できない文字を置換
                        safe_property_name = property_info["物件名"].replace("/", "／").replace("\\", "＼").replace(":", "：")
                        json_filename = f"{safe_property_name}.json"
                        json_path = os.path.join(self.data_dir, json_filename)
                        
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(property_json, f, ensure_ascii=False, indent=2)
                            
                        # 更新物件情報を保存
                        save_updated_properties(json_path)

                        logger.info(f"物件情報をJSONに保存しました: {json_path}")
                        
                        # 物件履歴を更新
                        if property_id not in history["処理済み"]:
                            history["処理済み"].append(property_id)
                            # 物件履歴をJSON保存
                            with open(history_path, "w", encoding="utf-8") as f:
                                json.dump(history, f, ensure_ascii=False, indent=2)
                            logger.info(f"物件ID {property_id} を処理済みリストに追加しました")
                        
                    except Exception as e:
                        logger.error(f"物件詳細情報の取得中にエラー: {str(e)}")
                        logger.error(f"エラー詳細: {type(e).__name__}")
                        import traceback
                        logger.error(f"スタックトレース: {traceback.format_exc()}")
                    
                    # 一覧ページに戻る
                    driver.back()
                    
                    # 一覧ページの読み込み完了を待機
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.buy-index"))
                    )
                    
                    properties.append(property_info)
                    logger.info(f"物件情報を取得: {property_info['物件名']}")
                    
                except Exception as e:
                    logger.warning(f"物件情報の取得に失敗: {str(e)}")
                    continue
            
            # 削除済み物件を特定
            deleted_ids = [pid for pid in history["処理済み"] if pid not in current_property_ids]
            for deleted_id in deleted_ids:
                if deleted_id not in history["削除済み"]:
                    history["削除済み"].append(deleted_id)
                    history["処理済み"].remove(deleted_id)
                    logger.info(f"物件ID {deleted_id} を削除済みリストに移動しました")
            
            # 最終的な物件履歴を保存
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logger.info("物件履歴を更新しました")
            
            logger.info(f"{len(properties)}件の物件情報を取得しました")
            
            # 結果をJSONに保存
            result = {
                "status": "success",
                "message": f"物件 {len(properties)}件を取得しました",
                "物件一覧": properties,
                "総件数": len(properties)
            }
            
            json_path = os.path.join(self.data_dir, "property_list.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"結果をJSONに保存しました: {json_path}")
            
            return result
        
        except Exception as e:
            logger.error(f"スクレイピング中にエラーが発生: {str(e)}")
            return {
                "status": "error",
                "message": f"エラーが発生しました: {str(e)}"
            }
        finally:
            if driver:
                driver.quit()
                logger.info("ブラウザを終了しました")
