"""
ログ管理モジュール
ファイルとコンソール両方に出力する。APIキー等の秘密情報はマスクする。
"""
import logging
import os
import re
from pathlib import Path

from config import LOG_FILE


def _mask_secrets(message: str) -> str:
    """ログメッセージ内のAPIキー・トークンをマスクする"""
    # Bearer token
    message = re.sub(r"Bearer\s+\S+", "Bearer ***MASKED***", message)
    # OAuth signature等の長い英数字文字列（40文字以上）をマスク
    message = re.sub(r"[A-Za-z0-9+/=]{40,}", "***MASKED***", message)
    return message


class SecretFilter(logging.Filter):
    """ログレコードから秘密情報をフィルタリングするクラス"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _mask_secrets(str(record.msg))
        if record.args:
            record.args = tuple(
                _mask_secrets(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def get_logger(name: str = "car_post") -> logging.Logger:
    """アプリ共通ロガーを返す"""
    logger = logging.getLogger(name)

    if logger.handlers:
        # 既にセットアップ済みであれば再設定しない
        return logger

    logger.setLevel(logging.DEBUG)
    logger.addFilter(SecretFilter())

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイルハンドラ（ログディレクトリを自動作成）
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
