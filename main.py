"""
エントリーポイント
Google Sheets から在庫を読み込み、投稿文を生成してXへ投稿する。

DRY_RUN=true の場合は投稿せず投稿予定文のみ表示する。
"""
import sys

import config
from logger import get_logger
from post_generator import generate_post, validate_post
from sheets_client import SheetsClient
from x_client import XClient

logger = get_logger("main")


def main() -> int:
    """
    メイン処理。終了コードを返す。
    0: 正常終了（投稿成功 or 対象なし）
    1: エラー終了
    """
    logger.info("=== 中古車自動投稿 開始 ===")
    if config.DRY_RUN:
        logger.info("【DRY RUN モード】Xへの投稿は行いません")

    # 1. 環境変数の検証
    errors = config.validate_env()
    if errors:
        for err in errors:
            logger.error("設定エラー: %s", err)
        return 1

    # 2. Google Sheetsから在庫一覧を取得
    sheets = SheetsClient()
    try:
        sheets.load()
    except FileNotFoundError:
        logger.error(
            "サービスアカウントJSONが見つかりません: %s",
            config.GOOGLE_SERVICE_ACCOUNT_JSON,
        )
        return 1
    except Exception as e:
        logger.error("Google Sheets 読み込みエラー: %s", type(e).__name__)
        return 1

    # 3. 投稿対象車両を1件選ぶ
    result = sheets.get_target_car()
    if result is None:
        logger.info("投稿対象の車両が見つかりませんでした。正常終了します。")
        return 0

    row_num, car = result
    logger.info(
        "投稿対象: %s %s (行%d)",
        car.get("maker", ""),
        car.get("car_name", ""),
        row_num,
    )

    # 4. 投稿文を生成
    post_text = generate_post(car)
    if not validate_post(post_text):
        logger.error("投稿文の検証に失敗しました。処理を中止します。")
        return 1

    # 5. 画像URLを取得（写真１〜写真４）
    image_urls = [
        str(car.get(f"image_{i}", "")).strip()
        for i in range(1, 5)
    ]
    image_urls = [url for url in image_urls if url]
    if image_urls:
        logger.info("添付画像: %d枚", len(image_urls))
    else:
        logger.info("添付画像: なし")

    logger.info("--- 投稿予定文 (%d文字) ---\n%s\n---", len(post_text), post_text)

    # 6. DRY RUN の場合はここで終了
    if config.DRY_RUN:
        if image_urls:
            logger.info("【DRY RUN】添付予定画像URL: %s", image_urls)
        logger.info("【DRY RUN】投稿をスキップしました。実際の投稿は DRY_RUN=false で実行してください。")
        return 0

    # 7. Xへ投稿（画像あれば添付）
    x = XClient()
    tweet_id = x.post_tweet(post_text, image_urls=image_urls if image_urls else None)
    if tweet_id is None:
        logger.error("X投稿に失敗しました。スプレッドシートは更新しません。")
        return 1

    # 8. 成功したらGoogle Sheetsを更新
    try:
        sheets.update_posted(row_num, tweet_id)
    except Exception as e:
        # 投稿は成功しているのでエラーでも 0 を返すが警告を出す
        logger.warning(
            "スプレッドシートの更新に失敗しました（投稿自体は成功）: %s", type(e).__name__
        )

    logger.info("=== 中古車自動投稿 完了 === tweet_id=%s", tweet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
