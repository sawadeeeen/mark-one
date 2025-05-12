import os
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

def save_updated_properties(updated_property: str):
    """
    更新された物件情報を保存します。

    Args:
        updated_property (str): 更新された物件のJSONファイルパス
    """
    try:
        # updated.jsonのパスを設定
        updated_file = os.path.join("data", "updated.json")
        
        # 既存のデータを読み込む
        existing_data = []
        if os.path.exists(updated_file):
            with open(updated_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = []
        
        # 重複を避けながら新しい物件を追加
        if updated_property not in existing_data:
            existing_data.append(updated_property)
    
        # データを保存
        os.makedirs(os.path.dirname(updated_file), exist_ok=True)
        with open(updated_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
       
    except Exception as e:
        logger.error(f"更新物件情報の保存中にエラーが発生: {str(e)}")
        raise

def get_updated_property_paths(property_history: Dict[str, Any], data_dir: str) -> List[str]:
    """
    更新された物件のJSONファイルパスを取得します。

    Args:
        property_history (Dict[str, Any]): 物件履歴データ
        data_dir (str): データディレクトリのパス

    Returns:
        List[str]: 更新された物件のJSONファイルパスのリスト
    """
    updated_paths = []
    
    # 更新された物件と新規物件のIDを取得
    updated_ids = set(property_history.get("updated", []))
    
    # 各物件IDに対してJSONファイルのパスを生成
    for property_id in updated_ids:
        property_file = os.path.join(data_dir, f"{property_id}.json")
        if os.path.exists(property_file):
            updated_paths.append(os.path.abspath(property_file))
    
    return updated_paths 