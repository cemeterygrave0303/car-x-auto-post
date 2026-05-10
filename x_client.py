"""
X (Twitter) API クライアントモジュール
OAuth 1.0a User Context を使い POST /2/tweets で投稿する。
画像は v1.1 media/upload でアップロード後、tweet に添付する。
"""
import os
import re
import tempfile
from typing import Optional

import requests
import tweepy

import config
from logger import get_logger

logger = get_logger(__name__)

# X API が受け付ける画像 MIME タイプ
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# 1ツイートに添付できる画像の上限
MAX_MEDIA_COUNT = 4


def _extract_gdrive_file_id(url: str) -> Optional[str]:
    """Google Drive URL からファイルIDを抽出する"""
    # パターン1: /file/d/{ID}/
    match = re.search(r"/file/d/([a-zA-Z0-9_\-]+)", url)
    if match:
        return match.group(1)
    # パターン2: ?id={ID} または &id={ID}
    match = re.search(r"[?&]id=([a-zA-Z0-9_\-]+)", url)
    if match:
        return match.group(1)
    return None


def _download_image(url: str) -> Optional[str]:
    """
    URLから画像をダウンロードし、一時ファイルのパスを返す。
    Google Drive URL は複数の形式を試みる。
    失敗時は None を返す。
    """
    url = str(url).strip()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    # Google Drive URL の場合、ダウンロード用URLを複数生成して順に試す
    candidate_urls = [url]
    file_id = _extract_gdrive_file_id(url)
    if file_id:
        candidate_urls = [
            # 最新の直接ダウンロード形式
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0",
            # 従来形式
            f"https://drive.google.com/uc?export=download&id={file_id}",
            # 元のURL
            url,
        ]

    for attempt_url in candidate_urls:
        try:
            resp = session.get(attempt_url, timeout=30, stream=True, allow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")

            # HTML が返ってきた場合（確認ページ・ログインページ）
            if "text/html" in content_type:
                # 新形式の confirm トークンを探す
                html = resp.text
                confirm_match = re.search(r'name="confirm"\s+value="([^"]+)"', html)
                uuid_match = re.search(r'name="uuid"\s+value="([^"]+)"', html)
                if confirm_match and uuid_match and file_id:
                    confirm_url = (
                        f"https://drive.usercontent.google.com/download"
                        f"?id={file_id}&export=download"
                        f"&confirm={confirm_match.group(1)}&uuid={uuid_match.group(1)}"
                    )
                    resp = session.get(confirm_url, timeout=30, stream=True)
                    resp.raise_for_status()
                    content_type = resp.headers.get("Content-Type", "")
                else:
                    # このURLでは取得できなかった → 次の候補URLを試す
                    continue

            # 画像コンテンツかチェック
            if not any(m in content_type for m in ["image/", "application/octet-stream"]):
                continue

            # 拡張子を決定
            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "gif" in content_type:
                ext = ".gif"
            elif "webp" in content_type:
                ext = ".webp"

            # 一時ファイルに保存
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp.close()

            # 空ファイルチェック
            if os.path.getsize(tmp.name) == 0:
                os.unlink(tmp.name)
                continue

            logger.debug("画像ダウンロード完了: %s (%d bytes)", attempt_url, os.path.getsize(tmp.name))
            return tmp.name

        except requests.RequestException:
            continue

    logger.warning(
        "画像ダウンロード失敗（全候補URL試行済み）: %s\n"
        "  → Google Drive の共有設定を「リンクを知っている全員が閲覧可能」にしてください。",
        url,
    )
    return None


class XClient:
    def __init__(self) -> None:
        self._client: Optional[tweepy.Client] = None
        self._api: Optional[tweepy.API] = None

    def _get_client(self) -> tweepy.Client:
        """tweepy v2 Client を遅延初期化する（ツイート投稿用）"""
        if self._client is None:
            self._client = tweepy.Client(
                consumer_key=config.X_API_KEY,
                consumer_secret=config.X_API_SECRET,
                access_token=config.X_ACCESS_TOKEN,
                access_token_secret=config.X_ACCESS_TOKEN_SECRET,
                wait_on_rate_limit=True,
            )
            logger.info("X API v2 クライアント初期化完了")
        return self._client

    def _get_api(self) -> tweepy.API:
        """tweepy v1.1 API を遅延初期化する（メディアアップロード用）"""
        if self._api is None:
            auth = tweepy.OAuth1UserHandler(
                consumer_key=config.X_API_KEY,
                consumer_secret=config.X_API_SECRET,
                access_token=config.X_ACCESS_TOKEN,
                access_token_secret=config.X_ACCESS_TOKEN_SECRET,
            )
            self._api = tweepy.API(auth)
            logger.info("X API v1.1 クライアント初期化完了（メディアアップロード用）")
        return self._api

    def _upload_images(self, image_urls: list[str]) -> list[int]:
        """
        画像URLリストをダウンロードして X にアップロードし、media_id のリストを返す。
        アップロード失敗した画像はスキップする。最大 MAX_MEDIA_COUNT 枚まで。
        """
        if not image_urls:
            return []

        api = self._get_api()
        media_ids: list[int] = []
        tmp_files: list[str] = []

        try:
            for url in image_urls[:MAX_MEDIA_COUNT]:
                url = str(url).strip()
                if not url:
                    continue

                # ダウンロード
                tmp_path = _download_image(url)
                if tmp_path is None:
                    logger.warning("画像のダウンロードをスキップ: %s", url)
                    continue
                tmp_files.append(tmp_path)

                # X にアップロード
                try:
                    media = api.media_upload(filename=tmp_path)
                    media_ids.append(media.media_id)
                    logger.info("画像アップロード成功: media_id=%s", media.media_id)
                except tweepy.TweepyException as e:
                    logger.warning("画像アップロード失敗（スキップ）: %s", type(e).__name__)

        finally:
            # 一時ファイルを必ず削除
            for path in tmp_files:
                try:
                    os.unlink(path)
                except OSError:
                    pass

        return media_ids

    def post_tweet(self, text: str, image_urls: Optional[list[str]] = None) -> Optional[str]:
        """
        指定テキストと画像をXに投稿する。

        Args:
            text: 投稿本文（280文字以内）
            image_urls: 画像URLのリスト（最大4枚、省略可）

        Returns:
            投稿成功時は tweet_id (str)、失敗時は None
        """
        if len(text) > config.MAX_TWEET_LENGTH:
            logger.error("投稿文が280文字を超えているため投稿を中止: %d文字", len(text))
            return None

        # 画像のアップロード
        media_ids: Optional[list[int]] = None
        if image_urls:
            valid_urls = [u for u in image_urls if str(u).strip()]
            if valid_urls:
                logger.info("画像アップロード開始: %d枚", len(valid_urls))
                uploaded = self._upload_images(valid_urls)
                if uploaded:
                    media_ids = uploaded
                    logger.info("画像添付: %d枚 / media_ids=%s", len(media_ids), media_ids)
                else:
                    logger.warning("画像が1枚もアップロードできませんでした。テキストのみで投稿します。")

        try:
            client = self._get_client()
            kwargs: dict = {"text": text}
            if media_ids:
                kwargs["media_ids"] = media_ids

            response = client.create_tweet(**kwargs)
            tweet_id = str(response.data["id"])
            logger.info("X投稿成功: tweet_id=%s（画像%d枚添付）", tweet_id, len(media_ids) if media_ids else 0)
            return tweet_id

        except tweepy.errors.Forbidden as e:
            logger.error("X投稿失敗 - 権限エラー: %s", e)
            logger.error("X Developer Portal で Read and Write 権限を確認してください。")
            return None

        except tweepy.errors.Unauthorized as e:
            logger.error("X投稿失敗 - 認証エラー: %s", e)
            return None

        except tweepy.errors.TooManyRequests as e:
            logger.error("X投稿失敗 - レート制限: %s", e)
            return None

        except tweepy.errors.TweepyException as e:
            logger.error("X投稿失敗 - TweepyException: %s", e)
            return None

        except Exception as e:
            logger.error("X投稿失敗 - 予期せぬエラー: %s", type(e).__name__)
            return None

    def verify_credentials(self) -> bool:
        """API認証情報が有効かどうかを確認する"""
        try:
            me = self._get_client().get_me()
            if me.data:
                logger.info("X認証確認成功: @%s", me.data.username)
                return True
            return False
        except Exception as e:
            logger.error("X認証確認失敗: %s", type(e).__name__)
            return False
