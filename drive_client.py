"""
Google Drive アップロードモジュール
ローカルの写真ファイルをGoogle Driveにアップロードし、公開URLを返す。
サービスアカウントを使用するため、ユーザーのGoogleログイン不要。
"""
import io
import os
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

import config
from logger import get_logger

logger = get_logger(__name__)

# Drive API スコープ（ファイルの作成・管理）
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]

# アップロード先フォルダ名（存在しなければ自動作成）
DEFAULT_FOLDER_NAME = "中古車_写真"

# 対応MIMEタイプ
MIME_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


def _build_drive_service():
    """Drive API サービスを構築して返す"""
    sa_info = config.get_service_account_info()
    creds = Credentials.from_service_account_info(sa_info, scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_or_create_folder(service, folder_name: str, parent_id: Optional[str] = None) -> str:
    """
    指定名のフォルダをDriveで検索し、なければ作成してフォルダIDを返す。
    parent_id が指定された場合はその中に作成する。
    """
    # 既存フォルダを検索
    query = (
        f"name='{folder_name}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
    ).execute()

    files = results.get("files", [])
    if files:
        folder_id = files[0]["id"]
        logger.debug("既存フォルダを使用: %s (id=%s)", folder_name, folder_id)
        return folder_id

    # フォルダを新規作成
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    folder_id = folder["id"]
    logger.info("フォルダを新規作成: %s (id=%s)", folder_name, folder_id)
    return folder_id


def _make_public(service, file_id: str) -> None:
    """ファイルを「リンクを知っている全員が閲覧可能」に設定する"""
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()


def upload_image(
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> Optional[str]:
    """
    画像バイト列をGoogle Driveにアップロードし、公開共有URLを返す。

    Args:
        file_bytes : ファイルのバイトデータ
        filename   : 保存するファイル名（例: "car_front.jpg"）
        mime_type  : MIMEタイプ（省略時は拡張子から自動判定）
        folder_id  : アップロード先フォルダID（省略時は自動作成フォルダを使用）

    Returns:
        公開URL (str) または None（失敗時）
    """
    try:
        service = _build_drive_service()

        # MIMEタイプを自動判定
        if not mime_type:
            ext = os.path.splitext(filename)[1].lower()
            mime_type = MIME_TYPES.get(ext, "image/jpeg")

        # フォルダIDが未指定の場合は環境変数 or 自動作成
        if not folder_id:
            folder_id = os.getenv("DRIVE_FOLDER_ID", "")
        if not folder_id:
            folder_id = _get_or_create_folder(service, DEFAULT_FOLDER_NAME)

        # ファイルメタデータ
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }

        # アップロード実行
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True,
        )
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name",
        ).execute()

        file_id = uploaded["id"]
        logger.info("Drive アップロード成功: %s (id=%s)", filename, file_id)

        # 公開設定
        _make_public(service, file_id)

        # 共有URL（ダウンロード可能な形式）
        public_url = f"https://drive.google.com/file/d/{file_id}/view"
        return public_url

    except Exception as e:
        logger.error("Drive アップロード失敗: %s / %s", filename, type(e).__name__)
        logger.debug("詳細: %s", str(e))
        return None


def upload_images_batch(
    files: list[tuple[bytes, str, str]],
    folder_id: Optional[str] = None,
) -> list[Optional[str]]:
    """
    複数画像を一括アップロードする。

    Args:
        files: [(file_bytes, filename, mime_type), ...] のリスト
        folder_id: アップロード先フォルダID

    Returns:
        URLのリスト（失敗したものは None）
    """
    try:
        service = _build_drive_service()

        # フォルダを1回だけ解決する
        if not folder_id:
            folder_id = os.getenv("DRIVE_FOLDER_ID", "")
        if not folder_id:
            folder_id = _get_or_create_folder(service, DEFAULT_FOLDER_NAME)

        urls = []
        for file_bytes, filename, mime_type in files:
            if not mime_type:
                ext = os.path.splitext(filename)[1].lower()
                mime_type = MIME_TYPES.get(ext, "image/jpeg")

            file_metadata = {"name": filename, "parents": [folder_id]}
            media = MediaIoBaseUpload(
                io.BytesIO(file_bytes), mimetype=mime_type, resumable=True
            )
            uploaded = service.files().create(
                body=file_metadata, media_body=media, fields="id"
            ).execute()
            file_id = uploaded["id"]
            _make_public(service, file_id)
            url = f"https://drive.google.com/file/d/{file_id}/view"
            urls.append(url)
            logger.info("アップロード完了: %s → %s", filename, file_id)

        return urls

    except Exception as e:
        logger.error("一括アップロード失敗: %s / %s", type(e).__name__, str(e))
        raise  # 呼び出し元でエラー詳細を表示できるよう再送出
