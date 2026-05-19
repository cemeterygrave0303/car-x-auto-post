"""
設定管理モジュール
環境変数の読み込みと列名マッピングを定義する。
ローカル: .env ファイル
Streamlit Cloud: st.secrets（secrets.toml）
の両方に対応する。
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str = "") -> str:
    """
    環境変数を取得する。
    優先順位: 環境変数(.env) → Streamlit secrets → デフォルト値
    """
    # 1. 環境変数（.env / GitHub Secrets / OS環境変数）
    val = os.getenv(key)
    if val:
        return val
    # 2. Streamlit secrets（クラウドデプロイ時）
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


def get_service_account_info() -> dict:
    """
    サービスアカウント情報を辞書で返す。
    優先順位:
      1. Streamlit secrets の [gcp_service_account] セクション
      2. 環境変数 GOOGLE_SERVICE_ACCOUNT_JSON の JSON 文字列
      3. ファイルパスとして読み込み
    """
    # 1. Streamlit secrets のセクション形式（推奨）
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        pass

    # 2. JSON 文字列（環境変数 or st.secrets の文字列キー）
    sa_val = _get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    try:
        info = json.loads(sa_val)
        if isinstance(info, dict):
            return info
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. ファイルパス
    with open(sa_val, encoding="utf-8") as f:
        return json.load(f)


# --- Google Sheets 設定 ---
GOOGLE_SERVICE_ACCOUNT_JSON = _get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
SPREADSHEET_ID = _get("SPREADSHEET_ID", "1rlArsppsqnmfwqd7EU-CneYvu79Ipr3TWl8Ufngy4Ns")
SHEET_NAME = _get("SHEET_NAME", "在庫一覧")

# --- X (Twitter) API 設定 ---
X_API_KEY = _get("X_API_KEY")
X_API_SECRET = _get("X_API_SECRET")
X_ACCESS_TOKEN = _get("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = _get("X_ACCESS_TOKEN_SECRET")

# --- 動作モード ---
DRY_RUN = _get("DRY_RUN", "false").lower() == "true"

# --- ログファイルパス ---
LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")

# --- 投稿設定 ---
HASHTAGS = "#中古車 #名古屋 #愛知 #車販売 #中古車販売"
MAX_TWEET_LENGTH = 280

# --- 列名マッピング（スプレッドシートの列名 → 内部キー）---
# 複数の表記ゆれに対応する
COLUMN_ALIASES = {
    "id": ["管理番号", "id", "ID", "管理ID", "No", "no"],
    "status": ["ステータス", "ステイタス", "status", "Status", "状態"],
    "maker": ["メーカー", "maker", "Maker", "ブランド", "brand"],
    "car_name": ["車種", "車種名", "car_name", "車名", "CarName", "車両名", "モデル"],
    "year": ["年式", "year", "Year", "製造年", "初年度登録"],
    "mileage": ["走行距離", "mileage", "Mileage", "走行", "km"],
    "price": ["価格", "price", "Price", "総額", "販売価格", "売価"],
    "inspection": ["車検", "inspection", "Inspection", "車検有効期限", "車検期限"],
    "repair_history": ["修復歴", "repair_history", "RepairHistory", "事故歴"],
    "location": ["地域", "location", "Location", "所在地", "エリア"],
    "appeal": ["アピールポイント", "appeal", "Appeal", "コメント", "備考", "特記事項"],
    "plus_points": ["プラス要素", "plus_points", "プラス", "良い点", "メリット", "アピール"],
    "minus_points": ["マイナス要素", "minus_points", "マイナス", "気になる点", "デメリット", "瑕疵"],
    "chassis_number": ["車体番号", "chassis_number", "ChassisNumber", "車台番号", "フレーム番号", "車台No"],
    "equipment": ["装備", "equipment", "Equipment", "装備品", "オプション", "オプション装備"],
    "image_url":  ["画像URL",  "image_url",  "ImageURL",  "画像",   "image"],
    "image_1":    ["写真１",   "写真1",   "photo1",  "image1",  "画像1",  "画像１",  "写真（1）"],
    "image_2":    ["写真２",   "写真2",   "photo2",  "image2",  "画像2",  "画像２",  "写真（2）"],
    "image_3":    ["写真３",   "写真3",   "photo3",  "image3",  "画像3",  "画像３",  "写真（3）"],
    "image_4":    ["写真４",   "写真4",   "photo4",  "image4",  "画像4",  "画像４",  "写真（4）"],
    "image_5":    ["写真５",   "写真5",   "photo5",  "image5",  "画像5",  "画像５",  "写真（5）"],
    "image_6":    ["写真６",   "写真6",   "photo6",  "image6",  "画像6",  "画像６",  "写真（6）"],
    "image_7":    ["写真７",   "写真7",   "photo7",  "image7",  "画像7",  "画像７",  "写真（7）"],
    "image_8":    ["写真８",   "写真8",   "photo8",  "image8",  "画像8",  "画像８",  "写真（8）"],
    "image_9":    ["写真９",   "写真9",   "photo9",  "image9",  "画像9",  "画像９",  "写真（9）"],
    "image_10":   ["写真１０", "写真10",  "photo10", "image10", "画像10", "画像１０","写真（10）"],
    "posted": ["投稿済み", "posted", "Posted", "投稿フラグ", "X投稿済み"],
    "last_posted_at": ["最終投稿日時", "last_posted_at", "LastPostedAt", "投稿日時", "投稿日"],
    "post_count": ["投稿回数", "post_count", "PostCount", "投稿数"],
    "x_post_id": ["X投稿ID", "x_post_id", "XPostID", "TweetID", "tweet_id"],
    "priority": ["優先順位", "priority", "Priority", "優先度"],
}

# 投稿対象とみなすステータス文字列
ACTIVE_STATUSES = ["販売中", "在庫あり", "available", "Active", "active", "OK", "ok"]

# 投稿済みとみなす値（これ以外はすべて未投稿扱い）
POSTED_TRUE_VALUES = ["true", "TRUE", "True", "1", "済", "投稿済", "投稿済み", "yes", "YES"]

# 必須カラム（これらがなければ投稿しない）
REQUIRED_COLUMNS = ["car_name", "year", "mileage", "price"]


def validate_env() -> list[str]:
    """必須環境変数の検証。不足があればエラーリストを返す"""
    errors = []
    if not SPREADSHEET_ID:
        errors.append("SPREADSHEET_ID が設定されていません")
    if not DRY_RUN:
        # DRY_RUN時はX APIキー不要
        if not X_API_KEY:
            errors.append("X_API_KEY が設定されていません")
        if not X_API_SECRET:
            errors.append("X_API_SECRET が設定されていません")
        if not X_ACCESS_TOKEN:
            errors.append("X_ACCESS_TOKEN が設定されていません")
        if not X_ACCESS_TOKEN_SECRET:
            errors.append("X_ACCESS_TOKEN_SECRET が設定されていません")
    return errors
