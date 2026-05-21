"""
FTPアップロードモジュール
生成したLPをXserver（sv17090.xserver.jp）にアップロードする。
パスワードは Streamlit Secrets / 環境変数から取得し、コードには含めない。
"""
import ftplib
import io
import os
from typing import Optional

import config
from lp_generator import make_slug, get_lp_url
from logger import get_logger

logger = get_logger(__name__)

# Xserver の FTP設定（コードには書かない・Secretsから取得）
FTP_HOST    = "sv17090.xserver.jp"
FTP_PORT    = 21
FTP_TIMEOUT = 30  # 秒

# Xserver のディレクトリ構造:
#   FTPログイン後のルート → kurumaurunara.com/public_html/cars/{slug}/
FTP_BASE_PATH = "kurumaurunara.com/public_html/cars"


def _get_ftp_password() -> str:
    """FTPパスワードをSecretsまたは環境変数から取得する"""
    return config._get("FTP_PASSWORD", "")


def _connect() -> ftplib.FTP:
    """FTPサーバーに接続してログインする"""
    password = _get_ftp_password()
    if not password:
        raise ValueError(
            "FTP_PASSWORD が設定されていません。\n"
            "Streamlit Secrets に FTP_PASSWORD = \"パスワード\" を追加してください。"
        )

    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=FTP_TIMEOUT)
    ftp.login("xs902392", password)
    ftp.set_pasv(True)   # クラウド環境ではパッシブモード必須
    ftp.encoding = "utf-8"
    logger.info("FTP接続成功: %s", FTP_HOST)
    return ftp


def _makedirs(ftp: ftplib.FTP, path: str) -> None:
    """FTP上にディレクトリを再帰的に作成する（既存の場合はスキップ）"""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    for part in parts:
        try:
            ftp.mkd(part)
            logger.debug("FTPディレクトリ作成: %s", part)
        except ftplib.error_perm:
            pass  # 既存ディレクトリ → スキップ
        ftp.cwd(part)


def upload_lp(car: dict, html_content: str) -> Optional[str]:
    """
    LP HTMLをXserverにアップロードして公開URLを返す。

    Args:
        car          : 車両情報辞書
        html_content : 生成されたHTML文字列

    Returns:
        公開URL (str) または None（失敗時）
    """
    slug = make_slug(car)
    public_url = get_lp_url(car)

    try:
        ftp = _connect()

        # FTPルートに移動してからベースパスへ
        ftp.cwd("/")
        _makedirs(ftp, FTP_BASE_PATH)
        _makedirs(ftp, slug)

        # index.html をアップロード
        html_bytes = html_content.encode("utf-8")
        ftp.storbinary("STOR index.html", io.BytesIO(html_bytes))
        logger.info("LP アップロード成功: %s → %s", slug, public_url)

        ftp.quit()
        return public_url

    except ftplib.all_errors as e:
        logger.error("FTP エラー: %s", str(e))
        raise RuntimeError(f"FTPアップロードに失敗しました: {e}")
    except Exception as e:
        logger.error("LP アップロードエラー: %s", str(e))
        raise
