"""
Google Sheets 操作モジュール
在庫一覧の読み込み・投稿対象の選択・投稿結果の書き戻しを行う
"""
import json
from datetime import datetime
from typing import Any, Optional

import gspread
from google.oauth2.service_account import Credentials

import config
from logger import get_logger

logger = get_logger(__name__)

# Google API スコープ
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _build_column_map(headers: list[str]) -> dict[str, int]:
    """
    ヘッダー行からカラム名 → 列インデックスのマッピングを構築する。
    config.COLUMN_ALIASES の表記ゆれに対応する。
    戻り値: {内部キー: 0-indexed列番号}
    """
    col_map: dict[str, int] = {}
    for idx, header in enumerate(headers):
        header_stripped = str(header).strip()
        for internal_key, aliases in config.COLUMN_ALIASES.items():
            if header_stripped in aliases:
                if internal_key not in col_map:
                    col_map[internal_key] = idx
                break
    return col_map


def _row_to_dict(row: list[Any], col_map: dict[str, int]) -> dict[str, Any]:
    """1行データを内部キーの辞書に変換する"""
    result: dict[str, Any] = {}
    for key, idx in col_map.items():
        result[key] = row[idx] if idx < len(row) else ""
    return result


def _is_postable(car: dict[str, Any]) -> bool:
    """投稿対象の条件をチェックする"""
    # ステータスが販売中
    status = str(car.get("status", "")).strip()
    if status and status not in config.ACTIVE_STATUSES:
        return False

    # 投稿済みでない
    posted = str(car.get("posted", "")).strip()
    if posted in config.POSTED_TRUE_VALUES:
        return False

    # 必須カラムが揃っている
    for col in config.REQUIRED_COLUMNS:
        if not str(car.get(col, "")).strip():
            logger.debug("必須カラム '%s' が空のためスキップ: %s", col, car.get("id", "?"))
            return False

    return True


class SheetsClient:
    def __init__(self) -> None:
        self._gc: Optional[gspread.Client] = None
        self._sheet: Optional[gspread.Worksheet] = None
        self._headers: list[str] = []
        self._col_map: dict[str, int] = {}
        self._all_rows: list[list[Any]] = []

    def _connect(self) -> None:
        """Google Sheets API に接続する"""
        if self._gc is not None:
            return

        sa_json = config.GOOGLE_SERVICE_ACCOUNT_JSON
        try:
            # JSON文字列として渡された場合（GitHub Actions の環境変数展開）
            sa_info = json.loads(sa_json)
            creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        except (json.JSONDecodeError, ValueError):
            # ファイルパスとして渡された場合
            creds = Credentials.from_service_account_file(sa_json, scopes=SCOPES)

        self._gc = gspread.authorize(creds)
        logger.info("Google Sheets API 接続成功")

    def load(self) -> None:
        """スプレッドシートを読み込みヘッダーと行データをキャッシュする"""
        self._connect()
        spreadsheet = self._gc.open_by_key(config.SPREADSHEET_ID)
        self._sheet = spreadsheet.worksheet(config.SHEET_NAME)

        all_values = self._sheet.get_all_values()
        if not all_values:
            raise ValueError("スプレッドシートにデータがありません")

        self._headers = all_values[0]
        self._all_rows = all_values[1:]  # ヘッダー除く
        self._col_map = _build_column_map(self._headers)

        logger.info(
            "スプレッドシート読み込み完了: %d件 / 認識カラム: %s",
            len(self._all_rows),
            list(self._col_map.keys()),
        )

        # 未認識の必須カラムを警告
        for req in config.REQUIRED_COLUMNS:
            if req not in self._col_map:
                logger.warning("必須カラム '%s' がスプレッドシートに見つかりません", req)

    def get_target_car(self) -> Optional[tuple[int, dict[str, Any]]]:
        """
        投稿対象の車両を1件選ぶ。
        priority カラムがあれば数値が大きい（または小さい）ものを優先。
        なければ行順（上から）で最初の1件。

        戻り値: (行番号1-indexed, 車両辞書) or None
        """
        candidates: list[tuple[int, dict[str, Any]]] = []

        for row_idx, row in enumerate(self._all_rows):
            car = _row_to_dict(row, self._col_map)
            if _is_postable(car):
                # 実際の行番号（ヘッダーが1行目なのでrow_idx+2）
                candidates.append((row_idx + 2, car))

        if not candidates:
            return None

        # priority カラムがある場合は数値変換して降順ソート
        if "priority" in self._col_map:
            def priority_key(item: tuple[int, dict]) -> float:
                try:
                    return float(item[1].get("priority", 0) or 0)
                except (ValueError, TypeError):
                    return 0.0

            candidates.sort(key=priority_key, reverse=True)

        row_num, car = candidates[0]
        logger.info("投稿対象車両: 行%d / %s %s", row_num, car.get("maker", ""), car.get("car_name", ""))
        return row_num, car

    def update_posted(self, row_num: int, tweet_id: str) -> None:
        """
        投稿成功後にスプレッドシートへ結果を書き戻す。
        投稿済み=TRUE / 最終投稿日時 / 投稿回数+1 / X投稿ID を更新する。
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates: list[dict] = []

        def _cell(col_key: str, value: Any) -> None:
            if col_key in self._col_map:
                col_letter = _col_index_to_letter(self._col_map[col_key])
                cell = f"{col_letter}{row_num}"
                updates.append({"range": cell, "values": [[value]]})

        # 投稿済みフラグ
        _cell("posted", "TRUE")
        # 最終投稿日時
        _cell("last_posted_at", now_str)
        # X投稿ID
        _cell("x_post_id", tweet_id)

        # 投稿回数はインクリメント（現在値を読んで+1）
        if "post_count" in self._col_map:
            current_row = self._all_rows[row_num - 2]  # 0-indexed
            current_count = current_row[self._col_map["post_count"]] if self._col_map["post_count"] < len(current_row) else ""
            try:
                new_count = int(current_count) + 1
            except (ValueError, TypeError):
                new_count = 1
            _cell("post_count", new_count)

        if updates:
            self._sheet.batch_update(updates, value_input_option="USER_ENTERED")
            logger.info("スプレッドシート更新完了: 行%d tweet_id=%s", row_num, tweet_id)
        else:
            logger.warning("更新対象のカラムが見つかりませんでした（col_map=%s）", self._col_map)


def _col_index_to_letter(index: int) -> str:
    """0-indexed列番号をA1表記の列文字に変換する（例: 0→A, 25→Z, 26→AA）"""
    result = ""
    index += 1  # 1-indexed に変換
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result
