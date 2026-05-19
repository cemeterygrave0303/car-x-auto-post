"""
エントリーポイント
在庫投稿とPR・告知投稿を交互にローテーションしてXへ自動投稿する。

投稿ロジック:
  - 在庫車両とPR投稿を「最終投稿日時が古い順」で選択
  - 前回が在庫投稿なら今回はPR投稿（交互）、PR投稿がなければ在庫投稿
  - DRY_RUN=true の場合は投稿せず投稿予定文のみ表示する

"""
import sys

import config
from logger import get_logger
from post_generator import generate_post, validate_post
from pr_sheets_client import PRSheetsClient
from sheets_client import SheetsClient
from x_client import XClient

logger = get_logger("main")


def post_car(sheets: SheetsClient, x: XClient) -> int:
    """在庫車両を1件投稿する。成功=0, 失敗=1"""
    result = sheets.get_target_car()
    if result is None:
        logger.info("投稿対象の車両が見つかりませんでした。")
        return 0

    row_num, car = result
    logger.info("在庫投稿対象: %s %s (行%d)", car.get("maker", ""), car.get("car_name", ""), row_num)

    post_text = generate_post(car)
    if not validate_post(post_text):
        logger.error("投稿文の検証に失敗しました。処理を中止します。")
        return 1

    image_urls = [str(car.get(f"image_{i}", "")).strip() for i in range(1, 5)]
    image_urls = [u for u in image_urls if u]
    logger.info("--- 在庫投稿予定文 (%d文字) ---\n%s\n---", len(post_text), post_text)

    if config.DRY_RUN:
        logger.info("【DRY RUN】在庫投稿をスキップしました。")
        return 0

    tweet_id = x.post_tweet(post_text, image_urls=image_urls if image_urls else None)
    if tweet_id is None:
        logger.error("X投稿に失敗しました（在庫）。")
        return 1

    try:
        sheets.update_posted(row_num, tweet_id)
    except Exception as e:
        logger.warning("シート更新失敗（投稿は成功）: %s", type(e).__name__)

    logger.info("在庫投稿完了 tweet_id=%s", tweet_id)
    return 0


def post_pr(pr_sheets: PRSheetsClient, x: XClient) -> int:
    """PR・告知投稿を1件投稿する。成功=0, 対象なし=-1, 失敗=1"""
    result = pr_sheets.get_next_post()
    if result is None:
        logger.info("有効なPR投稿が見つかりませんでした。")
        return -1

    row_num, post = result
    post_text = str(post.get("投稿文", "")).strip()
    if not post_text:
        logger.warning("PR投稿の投稿文が空です（行%d）。スキップします。", row_num)
        return -1

    if len(post_text) > config.MAX_TWEET_LENGTH:
        logger.error("PR投稿文が280文字を超えています（行%d）。スキップします。", row_num)
        return -1

    image_urls = [str(post.get(f"写真{i}", "")).strip() for i in range(1, 5)]
    image_urls = [u for u in image_urls if u]
    logger.info("--- PR投稿予定文 (%d文字) ---\n%s\n---", len(post_text), post_text)

    if config.DRY_RUN:
        logger.info("【DRY RUN】PR投稿をスキップしました。")
        return 0

    tweet_id = x.post_tweet(post_text, image_urls=image_urls if image_urls else None)
    if tweet_id is None:
        logger.error("X投稿に失敗しました（PR）。")
        return 1

    try:
        pr_sheets.update_posted(row_num, tweet_id)
    except Exception as e:
        logger.warning("PR シート更新失敗（投稿は成功）: %s", type(e).__name__)

    logger.info("PR投稿完了 tweet_id=%s", tweet_id)
    return 0


def main() -> int:
    logger.info("=== 中古車自動投稿 開始 ===")
    if config.DRY_RUN:
        logger.info("【DRY RUN モード】Xへの投稿は行いません")

    # 環境変数の検証
    errors = config.validate_env()
    if errors:
        for err in errors:
            logger.error("設定エラー: %s", err)
        return 1

    # ── 在庫シートを読み込む ───────────────────────────────────────
    sheets = SheetsClient()
    try:
        sheets.load()
    except FileNotFoundError:
        logger.error("サービスアカウントJSONが見つかりません: %s", config.GOOGLE_SERVICE_ACCOUNT_JSON)
        return 1
    except Exception as e:
        logger.error("Google Sheets 読み込みエラー: %s", type(e).__name__)
        return 1

    # ── PR投稿シートを読み込む ────────────────────────────────────
    pr_sheets = PRSheetsClient()
    try:
        pr_sheets.load()
    except Exception as e:
        logger.warning("PR投稿シート読み込みエラー（在庫投稿のみ実行）: %s", type(e).__name__)
        pr_sheets = None

    x = XClient()

    # ── 投稿ロジック：在庫とPRを交互にローテーション ─────────────
    #
    # 「前回の投稿種別」を判定する簡易方式:
    #   在庫の最終投稿日時 vs PR の最終投稿日時を比較し、
    #   より新しい方が「前回の投稿」とみなして、もう一方を今回投稿する。
    #   どちらかが未投稿の場合は未投稿を優先。
    #
    car_result = sheets.get_target_car()
    pr_result  = pr_sheets.get_next_post() if pr_sheets else None

    # 在庫の最終投稿日時
    from datetime import datetime

    def _dt(s: str) -> datetime:
        if not s:
            return datetime.min
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return datetime.min

    car_last_dt = _dt(str(car_result[1].get("last_posted_at", ""))) if car_result else datetime.max
    pr_last_dt  = _dt(str(pr_result[1].get("最終投稿日時", "")))    if pr_result  else datetime.max

    # PR投稿がない場合は在庫投稿のみ
    if pr_result is None:
        logger.info("PR投稿なし → 在庫投稿を実行します")
        return post_car(sheets, x)

    # 在庫がない場合はPR投稿のみ
    if car_result is None:
        logger.info("在庫投稿対象なし → PR投稿を実行します")
        code = post_pr(pr_sheets, x)
        return 0 if code == -1 else code

    # 両方ある場合: 最終投稿日時が古い方を投稿（交互ローテーション）
    if car_last_dt <= pr_last_dt:
        logger.info("在庫の方が古い投稿 → 在庫投稿を実行します")
        return post_car(sheets, x)
    else:
        logger.info("PRの方が古い投稿 → PR投稿を実行します")
        code = post_pr(pr_sheets, x)
        if code == -1:
            logger.info("PR投稿をスキップ → 在庫投稿にフォールバック")
            return post_car(sheets, x)
        return code


if __name__ == "__main__":
    sys.exit(main())
