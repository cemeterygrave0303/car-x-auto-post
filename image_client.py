"""
画像アップロードモジュール
imgbb（無料画像ホスティング）を使用して画像をアップロードし、公開URLを返す。
サービスアカウントのDrive容量制限を回避するため imgbb を採用。
"""
import base64
import os
from typing import Optional

import requests

from logger import get_logger

logger = get_logger(__name__)


def _get_api_key() -> str:
    """imgbb APIキーを環境変数またはStreamlit Secretsから取得する"""
    # Streamlit Secrets から取得を試みる
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "IMGBB_API_KEY" in st.secrets:
            return str(st.secrets["IMGBB_API_KEY"])
    except Exception:
        pass
    # 環境変数から取得
    key = os.getenv("IMGBB_API_KEY", "")
    return key


def upload_image(
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str] = None,  # imgbb では不要だが互換性のため残す
    folder_id: Optional[str] = None,  # 同上
) -> Optional[str]:
    """
    画像バイト列を imgbb にアップロードし、公開URLを返す。

    Args:
        file_bytes : ファイルのバイトデータ
        filename   : 保存するファイル名
        mime_type  : 使用しない（互換性のため残す）
        folder_id  : 使用しない（互換性のため残す）

    Returns:
        公開URL (str) または None（失敗時）
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("IMGBB_API_KEY が設定されていません。Streamlit Secrets に追加してください。")
        raise ValueError(
            "IMGBB_API_KEY が未設定です。\n"
            "1. imgbb.com で無料登録\n"
            "2. api.imgbb.com でAPIキーを取得\n"
            "3. Streamlit Secrets に IMGBB_API_KEY = \"キー\" を追加"
        )

    try:
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        # ファイル名から拡張子を除いた名前を使用
        name = os.path.splitext(filename)[0]

        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": api_key,
                "image": b64,
                "name": name,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            url = data["data"]["url"]
            logger.info("imgbb アップロード成功: %s → %s", filename, url)
            return url
        else:
            logger.error("imgbb アップロード失敗: %s / %s", filename, data)
            return None

    except requests.exceptions.Timeout:
        logger.error("imgbb タイムアウト: %s", filename)
        raise RuntimeError(f"画像アップロードがタイムアウトしました: {filename}")
    except Exception as e:
        logger.error("imgbb アップロードエラー: %s / %s", filename, str(e))
        raise


def upload_images_batch(
    files: list[tuple[bytes, str, str]],
    folder_id: Optional[str] = None,  # 互換性のため残す
) -> list[Optional[str]]:
    """
    複数画像を一括アップロードする。

    Args:
        files: [(file_bytes, filename, mime_type), ...] のリスト
        folder_id: 使用しない（互換性のため残す）

    Returns:
        URLのリスト（失敗したものは None）
    """
    urls = []
    for file_bytes, filename, mime_type in files:
        url = upload_image(file_bytes, filename, mime_type)
        urls.append(url)
    return urls
