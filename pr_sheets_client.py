"""
PR・告知投稿 スプレッドシート操作モジュール
「PR投稿」シートの読み込み・登録・編集・投稿結果書き戻しを行う。
シートが存在しない場合は自動で作成する。
"""
from datetime import datetime
from typing import Any, Optional

import gspread
from google.oauth2.service_account import Credentials

import config
from logger import get_logger
from sheets_client import _col_index_to_letter

logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

PR_SHEET_NAME = "PR投稿"

# PR投稿シートの列定義（順序を変えないこと）
PR_HEADERS = [
    "タイトル",       # 管理用の名前
    "投稿文",         # Xに投稿するテキスト
    "写真1",          # 画像URL
    "写真2",
    "写真3",
    "写真4",
    "有効",           # 自動投稿対象: TRUE / FALSE
    "最終投稿日時",
    "投稿回数",
    "X投稿ID",
]

# ヘッダー名 → 0-indexed 列番号
PR_COL: dict[str, int] = {h: i for i, h in enumerate(PR_HEADERS)}

# 「有効」とみなす値
ACTIVE_VALUES = {"true", "TRUE", "True", "1", "有効", "○", "✓", "yes", "YES"}


class PRSheetsClient:
    def __init__(self) -> None:
        self._gc: Optional[gspread.Client] = None
        self._sheet: Optional[gspread.Worksheet] = None
        self._all_rows: list[list[Any]] = []

    # ─── 接続 ─────────────────────────────────────────────────────────
    def _connect(self) -> None:
        if self._gc is not None:
            return
        sa_info = config.get_service_account_info()
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        self._gc = gspread.authorize(creds)

    # ─── 読み込み ─────────────────────────────────────────────────────
    def load(self) -> None:
        """PR投稿シートを読み込む。存在しなければ自動作成。"""
        self._connect()
        spreadsheet = self._gc.open_by_key(config.SPREADSHEET_ID)

        try:
            self._sheet = spreadsheet.worksheet(PR_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            # シートを新規作成してヘッダーを書き込む
            self._sheet = spreadsheet.add_worksheet(
                title=PR_SHEET_NAME, rows=200, cols=len(PR_HEADERS)
            )
            self._sheet.append_row(PR_HEADERS, value_input_option="USER_ENTERED")
            logger.info("PR投稿シートを新規作成しました")

        all_values = self._sheet.get_all_values()
        # ヘッダーが空のシートや初回作成直後の対応
        if len(all_values) <= 1:
            self._all_rows = []
        else:
            self._all_rows = all_values[1:]

        logger.info("PR投稿シート読み込み完了: %d件", len(self._all_rows))

    # ─── 読み取りヘルパー ─────────────────────────────────────────────
    def _row_to_dict(self, row: list[Any], row_num: int) -> dict[str, Any]:
        """1行データを辞書に変換する"""
        d: dict[str, Any] = {"_row_num": row_num}
        for key, idx in PR_COL.items():
            d[key] = row[idx] if idx < len(row) else ""
        return d

    def get_all_posts(self) -> list[dict[str, Any]]:
        """全PR投稿を辞書リストで返す（行番号付き）"""
        return [
            self._row_to_dict(row, i + 2)
            for i, row in enumerate(self._all_rows)
        ]

    def get_active_posts(self) -> list[dict[str, Any]]:
        """有効フラグがONのPR投稿だけ返す"""
        return [
            p for p in self.get_all_posts()
            if str(p.get("有効", "")).strip() in ACTIVE_VALUES
        ]

    def get_next_post(self) -> Optional[tuple[int, dict[str, Any]]]:
        """
        最終投稿日時が最も古い有効なPR投稿を返す。
        自動投稿のローテーション選択に使用。
        戻り値: (行番号1-indexed, 投稿辞書) or None
        """
        active = self.get_active_posts()
        if not active:
            return None

        def parse_dt(p: dict) -> datetime:
            raw = str(p.get("最終投稿日時", "")).strip()
            if not raw:
                return datetime.min
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
            return datetime.min

        active.sort(key=parse_dt)
        post = active[0]
        logger.info(
            "PR投稿対象: 行%d / %s (最終投稿: %s)",
            post["_row_num"],
            post.get("タイトル", ""),
            post.get("最終投稿日時", "未投稿"),
        )
        return post["_row_num"], post

    # ─── 書き込み ─────────────────────────────────────────────────────
    def add_post(self, data: dict[str, str]) -> None:
        """PR投稿を末尾に追加する"""
        row = [data.get(h, "") for h in PR_HEADERS]
        self._sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info("PR投稿を追加: %s", data.get("タイトル", ""))

    def update_post(self, row_num: int, data: dict[str, str]) -> None:
        """指定行のPR投稿を更新する"""
        updates = []
        for key, value in data.items():
            if key in PR_COL:
                col_letter = _col_index_to_letter(PR_COL[key])
                updates.append({"range": f"{col_letter}{row_num}", "values": [[value]]})
        if updates:
            self._sheet.batch_update(updates, value_input_option="USER_ENTERED")
            logger.info("PR投稿を更新: 行%d", row_num)

    def update_posted(self, row_num: int, tweet_id: str) -> None:
        """投稿成功後に最終投稿日時・投稿回数・X投稿IDを更新する"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 投稿回数をインクリメント
        raw_row = self._all_rows[row_num - 2] if (row_num - 2) < len(self._all_rows) else []
        count_idx = PR_COL.get("投稿回数", -1)
        try:
            current_count = int(raw_row[count_idx]) if 0 <= count_idx < len(raw_row) else 0
        except (ValueError, TypeError):
            current_count = 0

        updates = [
            {
                "range": f"{_col_index_to_letter(PR_COL['最終投稿日時'])}{row_num}",
                "values": [[now_str]],
            },
            {
                "range": f"{_col_index_to_letter(PR_COL['投稿回数'])}{row_num}",
                "values": [[current_count + 1]],
            },
            {
                "range": f"{_col_index_to_letter(PR_COL['X投稿ID'])}{row_num}",
                "values": [[tweet_id]],
            },
        ]
        self._sheet.batch_update(updates, value_input_option="USER_ENTERED")
        logger.info("PR投稿シート更新完了: 行%d tweet_id=%s", row_num, tweet_id)
