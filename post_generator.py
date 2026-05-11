"""
投稿文生成モジュール
車両情報を受け取り、280文字以内のX投稿文を生成する
プラス要素・マイナス要素を自然に組み込む
毎回異なるPRテキストをランダム生成する
"""
import hashlib
import re
from datetime import datetime
from typing import Any

import config
from logger import get_logger

logger = get_logger(__name__)

# 欠損値の代替表現
UNKNOWN_TEXT = "お問い合わせください"

# ハッシュタグ候補（文字数超過時に削減できるよう順序を管理）
HASHTAG_SETS = [
    "#中古車 #名古屋 #愛知 #車販売 #中古車販売",  # 5個
    "#中古車 #名古屋 #愛知 #車販売",               # 4個
    "#中古車 #名古屋 #愛知",                        # 3個
]

# ヘッダーバリエーション（毎回変わる）
HEADER_TEMPLATES = [
    "【中古車 入庫情報】",
    "【本日のおすすめ】",
    "【在庫車 ご紹介】",
    "【お買い得情報】",
    "【今週の一台】",
    "【新着入庫のご案内】",
    "【厳選中古車】",
]

# CTAバリエーション（毎回変わる）
CTA_TEMPLATES = [
    "気になる方はDMください。",
    "お気軽にDMどうぞ！",
    "ご興味あればDMください✉️",
    "詳細はDMにてお気軽に。",
    "お問い合わせはDMから！",
    "試乗もできます。DMください。",
    "現車確認歓迎！まずはDMを。",
]

# オープニング文バリエーション
OPENING_TEMPLATES = [
    "",  # オープニングなし
    "名古屋の中古車屋です🚗\n",
    "愛知県でお探しの方へ🔍\n",
    "コスパ重視の方におすすめ！\n",
    "状態の良い一台が入りました✨\n",
    "お値打ち価格でご提供します🎯\n",
]


def _get_variation_seed(car: dict[str, Any]) -> int:
    """
    車両IDと現在時刻の時間帯を組み合わせてシードを生成する。
    同じ車両でも投稿のたびに異なるテキストになる。
    """
    car_id = str(car.get("id", car.get("car_name", "")))
    # 時間単位でシードを変化させる（1時間ごとに変わる）
    time_key = datetime.now().strftime("%Y%m%d%H")
    seed_str = f"{car_id}_{time_key}"
    return int(hashlib.md5(seed_str.encode()).hexdigest(), 16)


def _pick(templates: list, seed: int, offset: int = 0) -> str:
    """シードを使ってテンプレートリストから1つを選ぶ"""
    return templates[(seed + offset) % len(templates)]


def _format_price(raw: Any) -> str:
    """
    価格を「○○万円」表記に整形する。
    入力例: "150", "150万", "1500000", "¥200,000"
    """
    if not raw:
        return UNKNOWN_TEXT

    text = str(raw).strip()
    if "万円" in text:
        return re.sub(r"[^\d万円.]", "", text)

    # ¥記号・カンマ・円記号を除去してから数値を抽出
    cleaned = text.replace("¥", "").replace("￥", "").replace(",", "").replace("円", "")
    nums = re.findall(r"[\d.]+", cleaned)
    if not nums:
        return text

    value = float(nums[0])

    if value >= 10000:
        man = value / 10000
        return f"{int(man)}万円" if man == int(man) else f"{man:.1f}万円"
    if value >= 100:
        return f"{int(value)}万円" if value == int(value) else f"{value:.1f}万円"
    return f"{text}万円"


def _format_mileage(raw: Any) -> str:
    """
    走行距離を「○○km」または「○○万km」表記に整形する。
    入力例: "45000", "4.5万km", "45000km"
    """
    if not raw:
        return UNKNOWN_TEXT

    text = str(raw).strip()
    if not text:
        return UNKNOWN_TEXT

    if "万km" in text or "万キロ" in text:
        nums = re.findall(r"[\d.]+", text)
        return f"{nums[0]}万km" if nums else text

    nums = re.findall(r"[\d,]+", text.replace("km", "").replace("キロ", ""))
    if not nums:
        return text

    value = int(nums[0].replace(",", ""))
    if value >= 10000:
        man = value / 10000
        return f"{int(man)}万km" if man == int(man) else f"{man:.1f}万km"
    return f"{value:,}km"


def _format_year(raw: Any) -> str:
    """年式を整形する（例: "2018" → "2018年式"）"""
    if not raw:
        return UNKNOWN_TEXT
    text = str(raw).strip()
    if not text:
        return UNKNOWN_TEXT
    if "年" in text:
        return text
    if re.match(r"^\d{4}$", text):
        return f"{text}年式"
    return text


def _format_inspection(raw: Any) -> str:
    """車検情報を整形する"""
    if not raw:
        return "要確認"
    text = str(raw).strip()
    if not text:
        return "要確認"
    if text in ["なし", "無", "車検なし", "なし（整備渡し）", "整備渡し"]:
        return "車検なし"
    return text


def _format_repair_history(raw: Any) -> str:
    """修復歴を整形する"""
    if not raw:
        return "なし"
    text = str(raw).strip()
    return text if text else "なし"


def _trim(raw: Any, max_len: int) -> str:
    """テキストを max_len 文字以内に整形する（改行→スペース変換）"""
    if not raw:
        return ""
    text = " ".join(str(raw).split())  # 改行・連続スペースを整理
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def _build_points_block(plus_raw: Any, minus_raw: Any, max_each: int) -> str:
    """
    プラス要素・マイナス要素を組み合わせた1ブロックを返す。
    両方空なら空文字列を返す。
    """
    plus = _trim(plus_raw, max_each)
    minus = _trim(minus_raw, max_each)

    lines = []
    if plus:
        lines.append(f"◎ {plus}")
    if minus:
        lines.append(f"△ {minus}")

    return "\n".join(lines)


def generate_post(car: dict[str, Any]) -> str:
    """
    車両情報辞書から投稿文を生成する。
    毎回異なるヘッダー・CTA・オープニングを使い、バリエーションのある投稿文を生成する。
    280文字を超える場合は各テキストを段階的に短縮する。
    最終的に280文字以内であることを保証する。
    """
    maker      = str(car.get("maker", "")).strip()
    car_name   = str(car.get("car_name", "")).strip()
    year       = _format_year(car.get("year"))
    mileage    = _format_mileage(car.get("mileage"))
    price      = _format_price(car.get("price"))
    inspection = _format_inspection(car.get("inspection"))
    repair     = _format_repair_history(car.get("repair_history"))
    plus_raw   = str(car.get("plus_points", "") or car.get("appeal", "") or "").strip()
    minus_raw  = str(car.get("minus_points", "")).strip()

    car_title = f"{maker} {car_name}".strip() if maker else car_name

    # バリエーション選択（車両・時刻ベースのシード）
    seed    = _get_variation_seed(car)
    header  = _pick(HEADER_TEMPLATES, seed, offset=0)
    cta     = _pick(CTA_TEMPLATES, seed, offset=1)
    opening = _pick(OPENING_TEMPLATES, seed, offset=2)

    # 車両基本情報ブロック
    def _make_base(include_inspection: bool = True, include_repair: bool = True) -> str:
        lines = [f"{header}\n"]
        if opening:
            lines.append(opening)
        lines.append(f"{car_title}\n")
        lines.append(f"年式：{year}\n")
        lines.append(f"走行距離：{mileage}\n")
        if include_inspection:
            lines.append(f"車検：{inspection}\n")
        if include_repair:
            lines.append(f"修復歴：{repair}\n")
        lines.append(f"総額：{price}\n")
        return "".join(lines)

    # プラス・マイナスの文字数を段階的に短縮して280字以内に収める
    for hashtags in HASHTAG_SETS:
        for inc_insp, inc_rep in [(True, True), (True, False), (False, False)]:
            base = _make_base(inc_insp, inc_rep)
            for max_each in [40, 25, 15, 0]:
                points_block = _build_points_block(plus_raw, minus_raw, max_each)

                if points_block:
                    body = base + f"\n{points_block}\n\n{cta}\n\n{hashtags}"
                else:
                    body = base + f"\n{cta}\n\n{hashtags}"

                if len(body) <= config.MAX_TWEET_LENGTH:
                    logger.debug(
                        "投稿文生成完了: %d文字 header=%s cta=%s",
                        len(body), header, cta
                    )
                    return body

    # フォールバック（通常到達しない）
    fallback = (
        f"{header}\n"
        f"{car_title} {year} {mileage}\n"
        f"総額：{price}\n"
        f"{cta}\n"
        f"#中古車 #名古屋 #愛知"
    )
    return fallback[:config.MAX_TWEET_LENGTH]


def validate_post(text: str) -> bool:
    """投稿文が280文字以内かを検証する"""
    length = len(text)
    if length > config.MAX_TWEET_LENGTH:
        logger.error("投稿文が280文字を超えています: %d文字", length)
        return False
    return True
