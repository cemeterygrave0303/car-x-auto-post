"""
中古車在庫管理 UI
Streamlit を使ったスプレッドシート連動の入力・投稿プレビュー画面
起動: streamlit run app.py
"""
import sys
import os
from datetime import datetime
from typing import Any, Optional

import streamlit as st
import pandas as pd

# 作業ディレクトリをスクリプトのフォルダに固定（service_account.json を確実に参照するため）
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from sheets_client import SheetsClient, _col_index_to_letter, _build_column_map
from post_generator import generate_post, validate_post
from x_client import XClient
from image_client import upload_images_batch
from pr_sheets_client import PRSheetsClient

# ─────────────────────────────────────────────
# ページ設定
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="中古車在庫管理",
    page_icon="🚗",
    layout="wide",
)

# ─────────────────────────────────────────────
# セッション初期化
# ─────────────────────────────────────────────
if "sheets" not in st.session_state:
    st.session_state.sheets = None
if "df" not in st.session_state:
    st.session_state.df = None
if "headers" not in st.session_state:
    st.session_state.headers = []
if "col_map" not in st.session_state:
    st.session_state.col_map = {}
if "pr_client" not in st.session_state:
    st.session_state.pr_client = None
if "pr_posts" not in st.session_state:
    st.session_state.pr_posts = []


# ─────────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────────
def get_sheets_client() -> SheetsClient:
    """SheetsClient を生成して返す"""
    client = SheetsClient()
    client.load()
    return client


def reload_data():
    """スプレッドシートを再読み込みしてセッションに格納する"""
    try:
        sheets = get_sheets_client()
        st.session_state.sheets = sheets

        headers = sheets._headers
        rows = sheets._all_rows
        col_map = sheets._col_map

        st.session_state.headers = headers
        st.session_state.col_map = col_map

        if rows:
            df = pd.DataFrame(rows, columns=headers)
            st.session_state.df = df
        else:
            st.session_state.df = pd.DataFrame(columns=headers)
        return True
    except Exception as e:
        st.error(f"スプレッドシートの読み込みに失敗しました: {e}")
        return False


def reload_pr_data():
    """PR投稿シートを再読み込みしてセッションに格納する"""
    try:
        pr = PRSheetsClient()
        pr.load()
        st.session_state.pr_client = pr
        st.session_state.pr_posts = pr.get_all_posts()
        return True
    except Exception as e:
        st.error(f"PR投稿シートの読み込みに失敗しました: {e}")
        return False


def get_col(car: dict, key: str, default: str = "") -> str:
    """内部キーで車両データを取得する"""
    return str(car.get(key, default) or default).strip()


def display_name(internal_key: str) -> str:
    """内部キーをスプレッドシートの列名に変換する"""
    col_map = st.session_state.col_map
    if internal_key in col_map:
        idx = col_map[internal_key]
        headers = st.session_state.headers
        if idx < len(headers):
            return headers[idx]
    return internal_key


def upload_photos_to_drive(uploaded_files: list) -> list[str]:
    """
    Streamlit の UploadedFile リストを Google Drive にアップロードし、
    公開URLのリストを返す。アップロードしなかったスロットは空文字。
    """
    if not uploaded_files:
        return []

    files_to_upload = []
    for uf in uploaded_files:
        if uf is not None:
            files_to_upload.append((uf.read(), uf.name, uf.type))
        else:
            files_to_upload.append(None)

    # None を除いたものだけアップロード
    valid = [(b, n, m) for item in files_to_upload for b, n, m in ([item] if item else [])]
    if not valid:
        return [""] * len(uploaded_files)

    urls_iter = iter(upload_images_batch(valid))
    result = []
    for item in files_to_upload:
        if item is not None:
            result.append(next(urls_iter) or "")
        else:
            result.append("")
    return result


def render_photo_uploader(
    label_prefix: str,
    current_urls: Optional[list[str]] = None,
    num_photos: int = 10,
) -> tuple[list, list[str]]:
    """
    写真アップロードUIを描画する（最大10枚・クリックで拡大表示付き）。
    戻り値: (uploaded_files_list, current_url_list)
    """
    if current_urls is None:
        current_urls = [""] * num_photos

    # URLリストを num_photos 長に正規化
    current_urls = list(current_urls) + [""] * num_photos
    current_urls = current_urls[:num_photos]

    uploaded = []
    col1, col2 = st.columns(2)
    cols = [col1, col2] * (num_photos // 2 + 1)

    for i in range(num_photos):
        with cols[i]:
            existing_url = current_urls[i]

            # 既存URLがある場合：クリックで拡大できるサムネイル表示
            if existing_url:
                st.markdown(
                    f'<a href="{existing_url}" target="_blank" title="クリックで拡大表示">'
                    f'<img src="{existing_url}" '
                    f'style="width:100%;border-radius:8px;cursor:zoom-in;'
                    f'border:2px solid #e0e0e0;margin-bottom:4px;" />'
                    f'</a>'
                    f'<div style="font-size:11px;color:#888;margin-bottom:6px;">'
                    f'🔍 写真{i+1}（クリックで拡大）</div>',
                    unsafe_allow_html=True,
                )

            uf = st.file_uploader(
                f"写真{i+1}{'　変更する場合は選択' if existing_url else ''}",
                type=["jpg", "jpeg", "png", "gif", "webp"],
                key=f"{label_prefix}_photo_{i+1}",
            )

            # 新しくアップロードされた場合のプレビュー
            if uf is not None:
                st.image(uf, caption=f"写真{i+1} 新しい画像", use_container_width=True)

            uploaded.append(uf)

    return uploaded, current_urls


def write_row_to_sheet(row_num: int, car_data: dict[str, str]):
    """
    編集した車両データをスプレッドシートの指定行に書き戻す。
    row_num: 1-indexed（ヘッダー行=1、データは2〜）
    """
    sheets = st.session_state.sheets
    col_map = st.session_state.col_map
    updates = []

    for key, value in car_data.items():
        if key in col_map:
            col_letter = _col_index_to_letter(col_map[key])
            cell = f"{col_letter}{row_num}"
            updates.append({"range": cell, "values": [[value]]})

    if updates:
        sheets._sheet.batch_update(updates, value_input_option="USER_ENTERED")


def append_row_to_sheet(car_data: dict[str, str]):
    """新しい車両行をスプレッドシートの末尾に追加する"""
    sheets = st.session_state.sheets
    headers = st.session_state.headers
    col_map = st.session_state.col_map

    # ヘッダー順に値を並べる
    row_values = []
    for header in headers:
        # ヘッダー名から内部キーを逆引き
        internal_key = next(
            (k for k, idx in col_map.items() if idx < len(headers) and headers[idx] == header),
            None
        )
        if internal_key and internal_key in car_data:
            row_values.append(car_data[internal_key])
        else:
            row_values.append("")

    sheets._sheet.append_row(row_values, value_input_option="USER_ENTERED")


# ─────────────────────────────────────────────
# サイドバー
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("🚗 中古車在庫管理")
    st.caption(f"シート: {config.SHEET_NAME}")

    if st.button("🔄 データを再読み込み", use_container_width=True):
        with st.spinner("読み込み中..."):
            reload_data()
            reload_pr_data()
        st.success("更新しました")

    st.divider()
    dry_run = st.toggle("DRY RUN（投稿しない）", value=True)
    st.caption("OFF にすると実際にXへ投稿します")

    st.divider()
    st.caption("スプレッドシートID")
    st.code(config.SPREADSHEET_ID[:20] + "...", language=None)

# 初回ロード
if st.session_state.df is None:
    with st.spinner("スプレッドシートを読み込んでいます..."):
        reload_data()
        reload_pr_data()

# ─────────────────────────────────────────────
# メインタブ
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 在庫一覧", "➕ 車両登録", "✏️ 車両編集", "📢 PR・告知投稿", "🚀 投稿プレビュー"])


# ══════════════════════════════════════════════
# タブ1: 在庫一覧
# ══════════════════════════════════════════════
with tab1:
    st.header("在庫一覧")

    df = st.session_state.df
    if df is None or df.empty:
        st.info("在庫データがありません。")
    else:
        col_map = st.session_state.col_map

        # サマリー指標
        total = len(df)
        status_col = st.session_state.headers[col_map["status"]] if "status" in col_map else None
        posted_col = st.session_state.headers[col_map["posted"]] if "posted" in col_map else None

        on_sale = total
        posted = 0
        if status_col and status_col in df.columns:
            on_sale = df[status_col].isin(config.ACTIVE_STATUSES).sum()
        if posted_col and posted_col in df.columns:
            posted = df[posted_col].isin(config.POSTED_TRUE_VALUES).sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("総在庫数", f"{total} 台")
        m2.metric("販売中", f"{on_sale} 台")
        m3.metric("投稿済み", f"{posted} 台")

        st.divider()

        # フィルター
        filter_col, _ = st.columns([2, 5])
        with filter_col:
            show_posted = st.checkbox("投稿済みも表示する", value=True)

        if not show_posted and posted_col and posted_col in df.columns:
            display_df = df[~df[posted_col].isin(config.POSTED_TRUE_VALUES)]
        else:
            display_df = df

        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            hide_index=False,
        )
        st.caption(f"表示: {len(display_df)} 件")


# ══════════════════════════════════════════════
# タブ2: 車両登録
# ══════════════════════════════════════════════
with tab2:
    st.header("車両を新規登録")
    st.caption("入力後「登録する」を押すとスプレッドシートに追加されます")

    with st.form("register_form"):
        c1, c2 = st.columns(2)
        with c1:
            status          = st.selectbox("ステイタス *", ["販売中", "商談中", "売約済み", "在庫切れ"])
            maker           = st.text_input("メーカー *", placeholder="例: ダイハツ")
            car_name        = st.text_input("車種名 *", placeholder="例: タント")
            grade           = st.text_input("グレード", placeholder="例: X SA3")
            year            = st.text_input("年式 *", placeholder="例: 2020")
            chassis_number  = st.text_input("車体番号", placeholder="例: NHP10-1234567")
        with c2:
            mileage    = st.text_input("走行距離 *", placeholder="例: 30000")
            price      = st.text_input("価格 *", placeholder="例: 580000")
            inspection = st.text_input("車検", placeholder="例: 2026年3月")
            repair     = st.selectbox("修復歴", ["なし", "あり"])

        st.divider()
        c3, c4 = st.columns(2)
        with c3:
            plus_points  = st.text_area("プラス要素", placeholder="例: 走行少なめ、内外装きれい", height=80)
        with c4:
            minus_points = st.text_area("マイナス要素", placeholder="例: フロントガラスに飛び石痕あり", height=80)

        equipment = st.text_area(
            "装備",
            placeholder="例: ナビ、バックカメラ、ETC、オートエアコン、電動スライドドア、アイドリングストップ",
            height=80,
        )

        st.divider()
        st.subheader("📷 写真（最大10枚）")
        st.caption("JPG / PNG / GIF / WEBP に対応。imgbb に自動アップロードされます。")

        submitted = st.form_submit_button("✅ 登録する", use_container_width=True, type="primary")

    # フォーム外で file_uploader を配置（Streamlit の制約のため）
    st.subheader("📷 写真アップロード（最大10枚）")
    st.caption("登録ボタンを押す前に写真を選択してください（任意）")
    reg_uploaded, _ = render_photo_uploader("reg", num_photos=10)

    if submitted:
        if not maker or not car_name or not year or not mileage or not price:
            st.error("* の項目は必須です")
        else:
            photo_urls = [""] * 10

            # imgbb アップロード
            files_to_upload = [f for f in reg_uploaded if f is not None]
            if files_to_upload:
                with st.spinner(f"📤 写真をアップロード中... ({len(files_to_upload)}枚)"):
                    uploaded_urls = upload_images_batch(
                        [(uf.read(), uf.name, uf.type or "image/jpeg") for uf in files_to_upload]
                    )
                idx = 0
                for i, uf in enumerate(reg_uploaded):
                    if uf is not None and idx < len(uploaded_urls):
                        photo_urls[i] = uploaded_urls[idx] or ""
                        idx += 1

                success_count = sum(1 for u in photo_urls if u)
                if success_count:
                    st.success(f"✅ 写真 {success_count} 枚をアップロードしました")
                else:
                    st.warning("写真のアップロードに失敗しました。URLは空で登録されます。")

            car_data = {
                "status": status, "maker": maker, "car_name": car_name,
                "year": year, "mileage": mileage, "price": price,
                "inspection": inspection, "repair_history": repair,
                "chassis_number": chassis_number, "equipment": equipment,
                "plus_points": plus_points, "minus_points": minus_points,
                **{f"image_{i+1}": photo_urls[i] for i in range(10)},
                "posted": "", "post_count": "0",
            }

            try:
                with st.spinner("スプレッドシートに登録中..."):
                    append_row_to_sheet(car_data)
                    reload_data()
                st.success(f"✅ {maker} {car_name} を登録しました！")
                st.balloons()
            except Exception as e:
                st.error(f"登録エラー: {e}")


# ══════════════════════════════════════════════
# タブ3: 車両編集
# ══════════════════════════════════════════════
with tab3:
    st.header("車両を編集")

    df = st.session_state.df
    col_map = st.session_state.col_map

    if df is None or df.empty:
        st.info("在庫データがありません。")
    else:
        # 車両選択
        def car_label(row):
            maker = row.get(display_name("maker"), "")
            name  = row.get(display_name("car_name"), "")
            year  = row.get(display_name("year"), "")
            return f"{maker} {name}（{year}年式）"

        records_all = df.to_dict("records")

        # ── 空白行を除いてリストと「実際の行番号」を対応づける ──────────────
        # スプレッドシート行番号 = データインデックス(0始まり) + 2（ヘッダー1行目分）
        non_blank_records: list = []
        non_blank_row_nums: list[int] = []
        for raw_idx, r in enumerate(records_all):
            maker_v = str(r.get(display_name("maker"), "") or "").strip()
            name_v  = str(r.get(display_name("car_name"), "") or "").strip()
            if maker_v or name_v:          # メーカーか車種名どちらかがあれば有効
                non_blank_records.append(r)
                non_blank_row_nums.append(raw_idx + 2)

        if not non_blank_records:
            st.warning("有効な車両データがありません。スプレッドシートを確認してください。")
            st.stop()

        # ── 検索フィルター ──────────────────────────────────────────────
        search_query = st.text_input("🔍 車両を検索", placeholder="メーカー名・車種名で絞り込み（例：トヨタ、シエンタ）")
        if search_query.strip():
            q = search_query.strip().lower()
            filtered_pairs = [
                (r, n) for r, n in zip(non_blank_records, non_blank_row_nums)
                if q in car_label(r).lower()
            ]
            if filtered_pairs:
                non_blank_records  = [r for r, n in filtered_pairs]
                non_blank_row_nums = [n for r, n in filtered_pairs]
            else:
                st.warning(f"「{search_query}」に一致する車両が見つかりません")

        options = [car_label(r) for r in non_blank_records]
        selected_idx = st.selectbox("編集する車両を選択", range(len(options)),
                                    format_func=lambda i: options[i])

        selected_row = non_blank_records[selected_idx]
        row_num = non_blank_row_nums[selected_idx]   # 実際のスプレッドシート行番号

        # 保存先の確認表示（保存ミス防止）
        _s_maker = str(selected_row.get(display_name("maker"), "")).strip()
        _s_name  = str(selected_row.get(display_name("car_name"), "")).strip()
        st.info(f"💾 保存先：スプレッドシート **{row_num}行目** ／ {_s_maker} {_s_name}")

        st.divider()

        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                status   = st.selectbox("ステイタス", ["販売中", "商談中", "売約済み", "在庫切れ"],
                                        index=["販売中","商談中","売約済み","在庫切れ"].index(
                                            selected_row.get(display_name("status"), "販売中")
                                        ) if selected_row.get(display_name("status"), "販売中") in ["販売中","商談中","売約済み","在庫切れ"] else 0)
                maker           = st.text_input("メーカー",   value=selected_row.get(display_name("maker"), ""))
                car_name        = st.text_input("車種名",     value=selected_row.get(display_name("car_name"), ""))
                year            = st.text_input("年式",       value=selected_row.get(display_name("year"), ""))
                chassis_number  = st.text_input("車体番号",   value=selected_row.get(display_name("chassis_number"), ""))
            with c2:
                mileage    = st.text_input("走行距離", value=selected_row.get(display_name("mileage"), ""))
                price      = st.text_input("価格",     value=selected_row.get(display_name("price"), ""))
                inspection = st.text_input("車検",     value=selected_row.get(display_name("inspection"), ""))
                repair_val = selected_row.get(display_name("repair_history"), "なし")
                repair     = st.selectbox("修復歴", ["なし", "あり"],
                                          index=0 if repair_val in ["", "なし"] else 1)

            st.divider()
            c3, c4 = st.columns(2)
            with c3:
                plus_points  = st.text_area("プラス要素",
                    value=selected_row.get(display_name("plus_points"), ""), height=80)
            with c4:
                minus_points = st.text_area("マイナス要素",
                    value=selected_row.get(display_name("minus_points"), ""), height=80)

            equipment = st.text_area(
                "装備",
                value=selected_row.get(display_name("equipment"), ""),
                placeholder="例: ナビ、バックカメラ、ETC、オートエアコン、電動スライドドア",
                height=80,
            )

            # 投稿済みリセット
            reset_posted = st.checkbox("投稿済みフラグをリセットする（再投稿したい場合）", value=False)

            save_btn = st.form_submit_button("💾 保存する", use_container_width=True, type="primary")

        # 写真アップロード（フォーム外・10枚対応）
        st.divider()
        st.subheader("📷 写真の変更（最大10枚・クリックで拡大）")
        st.caption("新しい写真を選択するとアップロードして上書きします。選択しなければ現在の写真を維持します。")
        current_urls = [
            selected_row.get(display_name(f"image_{i}"), "") for i in range(1, 11)
        ]
        edit_uploaded, existing_urls = render_photo_uploader("edit", current_urls, num_photos=10)

        if save_btn:
            # 写真処理：新しくアップロードされたものだけimgbbへ
            photo_urls = list(existing_urls[:10]) + [""] * (10 - len(existing_urls))
            files_to_upload = [(i, uf) for i, uf in enumerate(edit_uploaded) if uf is not None]

            if files_to_upload:
                with st.spinner(f"📤 写真をアップロード中... ({len(files_to_upload)}枚)"):
                    batch = []
                    for _, uf in files_to_upload:
                        uf.seek(0)
                        batch.append((uf.read(), uf.name, uf.type or "image/jpeg"))
                    try:
                        new_urls = upload_images_batch(batch)
                    except Exception as e:
                        st.error(f"❌ アップロードエラー: {e}")
                        new_urls = [None] * len(batch)
                        st.stop()

                success_count = 0
                for (slot_idx, _), new_url in zip(files_to_upload, new_urls):
                    if new_url:
                        photo_urls[slot_idx] = new_url
                        success_count += 1

                if success_count > 0:
                    st.success(f"✅ 写真 {success_count} 枚をアップロードしました")
                else:
                    st.error("❌ アップロードに失敗しました。")
                    st.stop()

            car_data = {
                "status": status, "maker": maker, "car_name": car_name,
                "year": year, "mileage": mileage, "price": price,
                "inspection": inspection, "repair_history": repair,
                "chassis_number": chassis_number, "equipment": equipment,
                "plus_points": plus_points, "minus_points": minus_points,
                **{f"image_{i+1}": photo_urls[i] for i in range(10)},
            }
            if reset_posted:
                car_data["posted"] = ""
                car_data["x_post_id"] = ""

            try:
                with st.spinner("保存中..."):
                    write_row_to_sheet(row_num, car_data)
                    reload_data()
                photo_summary = [u[:40]+"..." if u else "（なし）" for u in photo_urls]
                st.success(
                    f"✅ **{maker} {car_name}**（行{row_num}）を保存しました\n\n"
                    f"写真URL: {photo_summary}"
                )
            except Exception as e:
                st.error(f"保存エラー: {e}")


# ══════════════════════════════════════════════
# タブ4: PR・告知投稿
# ══════════════════════════════════════════════
with tab4:
    st.header("PR・告知投稿")
    st.caption("スプレッドシートの「PR投稿」シートで管理。有効にした投稿が在庫投稿と交互に自動投稿されます。")

    # PR初回ロード
    if not st.session_state.pr_posts and st.session_state.pr_client is None:
        with st.spinner("PR投稿シートを読み込み中..."):
            reload_pr_data()

    # ── 操作モード選択 ────────────────────────────────────
    pr_mode = st.radio(
        "操作",
        ["📋 一覧・手動投稿", "➕ 新規登録", "✏️ 編集"],
        horizontal=True,
        key="pr_mode",
    )

    st.divider()

    # ════════════════════════════
    # PR一覧・手動投稿
    # ════════════════════════════
    if pr_mode == "📋 一覧・手動投稿":
        posts = st.session_state.pr_posts

        if not posts:
            st.info("PR投稿がまだ登録されていません。「➕ 新規登録」から追加してください。")
        else:
            for p in posts:
                active_flag = str(p.get("有効", "")).strip()
                is_active = active_flag in {"true", "TRUE", "True", "1", "有効", "○", "✓", "yes", "YES"}
                badge = "🟢 自動投稿ON" if is_active else "⚫ 自動投稿OFF"
                last = p.get("最終投稿日時", "") or "未投稿"
                count = p.get("投稿回数", "0") or "0"

                with st.expander(f"{badge}｜{p.get('タイトル', '（タイトルなし）')}　投稿{count}回 / 最終:{last}"):
                    st.text_area("投稿文", value=p.get("投稿文", ""), height=150,
                                 disabled=True, key=f"pr_view_{p['_row_num']}")
                    imgs = [p.get(f"写真{i}", "") for i in range(1, 5) if p.get(f"写真{i}", "")]
                    if imgs:
                        st.caption(f"添付画像: {len(imgs)}枚")

                    # 手動投稿ボタン
                    post_text_pr = p.get("投稿文", "").strip()
                    pr_valid = bool(post_text_pr) and len(post_text_pr) <= config.MAX_TWEET_LENGTH
                    btn_lbl = "📝 DRY RUN" if dry_run else "🚀 Xに投稿する"
                    if st.button(btn_lbl, key=f"pr_post_{p['_row_num']}", disabled=not pr_valid):
                        if dry_run:
                            st.success("【DRY RUN】投稿文の確認が完了しました。")
                        else:
                            with st.spinner("Xに投稿中..."):
                                x = XClient()
                                tweet_id = x.post_tweet(
                                    post_text_pr,
                                    image_urls=imgs if imgs else None,
                                )
                            if tweet_id:
                                st.session_state.pr_client.update_posted(p["_row_num"], tweet_id)
                                reload_pr_data()
                                st.success(f"✅ 投稿成功！ Tweet ID: {tweet_id}")
                                st.balloons()
                            else:
                                st.error("❌ 投稿に失敗しました。")

    # ════════════════════════════
    # PR新規登録
    # ════════════════════════════
    elif pr_mode == "➕ 新規登録":
        st.subheader("PR投稿を新規登録")

        # テンプレート選択
        PR_TEMPLATES = {
            "自由入力": "",
            "新着入庫のお知らせ": "【新着入庫🚗】\n\n新しい車が入庫しました！\n詳細はプロフィールのリンクをご覧ください。\n\n気になる方はDMください✉️\n\n#中古車 #名古屋 #愛知 #車売ります #中古車販売",
            "キャンペーン告知":   "【キャンペーン開催中🎉】\n\n（キャンペーン内容をここに入力）\n\n詳細はDMにてお問い合わせください！\n\n#中古車 #名古屋 #愛知 #車売ります",
            "営業時間・お知らせ": "【営業時間のご案内🕙】\n\n月〜土：10:00〜19:00\n日・祝：10:00〜18:00\n\nお気軽にご来店・DMください😊\n\n#中古車販売 #名古屋 #愛知",
            "在庫一掃・特価":     "【特価車両のご案内💥】\n\n在庫処分のため、お値打ち価格でご提供中！\n詳細はDMまたはお電話でお気軽に。\n\n#中古車 #名古屋 #愛知 #車売ります",
            "ご成約・お礼":       "【ご成約ありがとうございます🙏】\n\nこの度はご購入いただきありがとうございました！\nまたのご利用をお待ちしております。\n\n#中古車 #名古屋 #愛知 #中古車販売",
        }
        tpl_key = st.selectbox("テンプレート", list(PR_TEMPLATES.keys()), key="pr_reg_tpl")

        with st.form("pr_register_form"):
            pr_title = st.text_input("タイトル（管理用）*", placeholder="例：GWキャンペーン告知")
            pr_body  = st.text_area("投稿文 *", value=PR_TEMPLATES[tpl_key],
                                    height=220, placeholder="280文字以内で入力してください")
            pr_active = st.checkbox("自動投稿に含める（有効）", value=True,
                                    help="チェックONで在庫投稿と交互に自動投稿されます")
            pr_reg_btn = st.form_submit_button("✅ 登録する", use_container_width=True, type="primary")

        # 写真アップロード（フォーム外）
        st.subheader("📷 写真（任意・最大4枚）")
        pr_reg_uploaded, _ = render_photo_uploader("pr_reg")

        if pr_reg_btn:
            if not pr_title.strip():
                st.error("タイトルは必須です")
            elif not pr_body.strip():
                st.error("投稿文は必須です")
            elif len(pr_body) > config.MAX_TWEET_LENGTH:
                st.error(f"投稿文が{len(pr_body)}文字です。280文字以内にしてください。")
            else:
                photo_urls = ["", "", "", ""]
                files_to_up = [f for f in pr_reg_uploaded if f is not None]
                if files_to_up:
                    with st.spinner("📤 写真をアップロード中..."):
                        try:
                            up_urls = upload_images_batch(
                                [(f.read(), f.name, f.type or "image/jpeg") for f in files_to_up]
                            )
                            for i, url in enumerate(up_urls):
                                if i < 4:
                                    photo_urls[i] = url or ""
                        except Exception as e:
                            st.error(f"写真アップロードエラー: {e}")

                pr_data = {
                    "タイトル": pr_title,
                    "投稿文":   pr_body,
                    "写真1": photo_urls[0], "写真2": photo_urls[1],
                    "写真3": photo_urls[2], "写真4": photo_urls[3],
                    "有効":   "TRUE" if pr_active else "FALSE",
                    "最終投稿日時": "", "投稿回数": "0", "X投稿ID": "",
                }
                try:
                    with st.spinner("スプレッドシートに登録中..."):
                        st.session_state.pr_client.add_post(pr_data)
                        reload_pr_data()
                    st.success(f"✅「{pr_title}」を登録しました！")
                    st.balloons()
                except Exception as e:
                    st.error(f"登録エラー: {e}")

    # ════════════════════════════
    # PR編集
    # ════════════════════════════
    else:  # ✏️ 編集
        posts = st.session_state.pr_posts
        if not posts:
            st.info("PR投稿がまだ登録されていません。")
        else:
            pr_options = [
                f"{p.get('タイトル', '（タイトルなし）')}（行{p['_row_num']}）"
                for p in posts
            ]
            pr_sel_idx = st.selectbox("編集するPR投稿を選択", range(len(pr_options)),
                                      format_func=lambda i: pr_options[i])
            sel_pr = posts[pr_sel_idx]
            pr_row_num = sel_pr["_row_num"]

            st.info(f"💾 保存先：PR投稿シート **{pr_row_num}行目**")

            with st.form("pr_edit_form"):
                pr_edit_title  = st.text_input("タイトル（管理用）", value=sel_pr.get("タイトル", ""))
                pr_edit_body   = st.text_area("投稿文", value=sel_pr.get("投稿文", ""), height=220)
                pr_edit_active = st.checkbox(
                    "自動投稿に含める（有効）",
                    value=str(sel_pr.get("有効", "")).strip() in
                          {"true", "TRUE", "True", "1", "有効", "○", "✓", "yes", "YES"},
                )
                pr_edit_btn = st.form_submit_button("💾 保存する", use_container_width=True, type="primary")

            # 写真編集（フォーム外）
            st.subheader("📷 写真の変更")
            pr_cur_urls = [sel_pr.get(f"写真{i}", "") for i in range(1, 5)]
            pr_edit_uploaded, pr_existing_urls = render_photo_uploader("pr_edit", pr_cur_urls)

            if pr_edit_btn:
                if not pr_edit_title.strip():
                    st.error("タイトルは必須です")
                elif len(pr_edit_body) > config.MAX_TWEET_LENGTH:
                    st.error(f"投稿文が{len(pr_edit_body)}文字です。280文字以内にしてください。")
                else:
                    # 写真処理
                    photo_urls = list(pr_existing_urls[:4]) + [""] * (4 - len(pr_existing_urls))
                    files_to_up = [(i, f) for i, f in enumerate(pr_edit_uploaded) if f is not None]
                    if files_to_up:
                        with st.spinner("📤 写真をアップロード中..."):
                            batch = []
                            for _, uf in files_to_up:
                                uf.seek(0)
                                batch.append((uf.read(), uf.name, uf.type or "image/jpeg"))
                            try:
                                new_urls = upload_images_batch(batch)
                                for (slot_idx, _), new_url in zip(files_to_up, new_urls):
                                    if new_url:
                                        photo_urls[slot_idx] = new_url
                                st.success(f"✅ 写真 {len([u for u in new_urls if u])} 枚をアップロードしました")
                            except Exception as e:
                                st.error(f"写真アップロードエラー: {e}")

                    pr_update_data = {
                        "タイトル": pr_edit_title,
                        "投稿文":   pr_edit_body,
                        "写真1": photo_urls[0], "写真2": photo_urls[1],
                        "写真3": photo_urls[2], "写真4": photo_urls[3],
                        "有効":   "TRUE" if pr_edit_active else "FALSE",
                    }
                    try:
                        with st.spinner("保存中..."):
                            st.session_state.pr_client.update_post(pr_row_num, pr_update_data)
                            reload_pr_data()
                        st.success(f"✅「{pr_edit_title}」（行{pr_row_num}）を保存しました")
                    except Exception as e:
                        st.error(f"保存エラー: {e}")


# ══════════════════════════════════════════════
# タブ5: 投稿プレビュー & 手動投稿
# ══════════════════════════════════════════════
with tab5:
    st.header("投稿プレビュー & 手動投稿")

    df = st.session_state.df
    col_map = st.session_state.col_map

    if df is None or df.empty:
        st.info("在庫データがありません。")
    else:
        records = df.to_dict("records")

        def car_label_post(row):
            maker = row.get(display_name("maker"), "")
            name  = row.get(display_name("car_name"), "")
            posted = row.get(display_name("posted"), "")
            badge = " ✅投稿済" if posted in config.POSTED_TRUE_VALUES else ""
            return f"{maker} {name}{badge}"

        options_post = [car_label_post(r) for r in records]
        sel_idx = st.selectbox("車両を選択", range(len(options_post)),
                               format_func=lambda i: options_post[i])

        selected = records[sel_idx]
        row_num_post = sel_idx + 2

        # 車両データを内部キー形式に変換
        car = {}
        for key, idx in col_map.items():
            header = st.session_state.headers[idx] if idx < len(st.session_state.headers) else ""
            car[key] = selected.get(header, "")

        st.divider()

        # 投稿文プレビュー
        post_text = generate_post(car)
        is_valid  = validate_post(post_text)

        col_prev, col_info = st.columns([3, 2])
        with col_prev:
            st.subheader("投稿プレビュー")
            st.text_area("投稿文", value=post_text, height=280, disabled=True)
            char_color = "green" if is_valid else "red"
            st.markdown(
                f"文字数: <span style='color:{char_color}; font-weight:bold'>"
                f"{len(post_text)} / 280</span>",
                unsafe_allow_html=True
            )

        with col_info:
            st.subheader("画像")
            all_image_urls = [str(car.get(f"image_{i}", "")).strip() for i in range(1, 11)]
            all_image_urls = [u for u in all_image_urls if u]
            # X投稿に使う画像（先頭4枚まで）
            image_urls = all_image_urls[:4]

            if all_image_urls:
                # サムネイルグリッド表示（クリックで拡大）
                thumb_cols = st.columns(2)
                for idx, url in enumerate(all_image_urls):
                    with thumb_cols[idx % 2]:
                        st.markdown(
                            f'<a href="{url}" target="_blank" title="クリックで拡大">'
                            f'<img src="{url}" style="width:100%;border-radius:6px;'
                            f'cursor:zoom-in;margin-bottom:4px;'
                            f'{"border:2px solid #4CAF50;" if idx < 4 else "opacity:0.7;"}" />'
                            f'</a>'
                            f'<div style="font-size:10px;color:{"#4CAF50" if idx < 4 else "#999"};">'
                            f'写真{idx+1}{"　✅X投稿対象" if idx < 4 else "　（LP用）"}</div>',
                            unsafe_allow_html=True,
                        )
                st.info(f"全{len(all_image_urls)}枚 ／ X投稿: 先頭4枚まで")
            else:
                st.warning("画像URLが設定されていません")

            st.divider()
            st.subheader("投稿状況")
            posted_val = str(car.get("posted", "")).strip()
            if posted_val in config.POSTED_TRUE_VALUES:
                last_at = car.get("last_posted_at", "")
                count   = car.get("post_count", "")
                post_id = car.get("x_post_id", "")
                st.success("✅ 投稿済み")
                if last_at:
                    st.caption(f"最終投稿: {last_at}")
                if count:
                    st.caption(f"投稿回数: {count} 回")
                if post_id:
                    st.caption(f"Tweet ID: {post_id}")
            else:
                st.info("未投稿")

        st.divider()

        # 投稿ボタン
        if not is_valid:
            st.error("投稿文が280文字を超えています。内容を修正してください。")
        else:
            btn_label = "📝 DRY RUN（プレビューのみ）" if dry_run else "🚀 Xに投稿する"
            btn_type  = "secondary" if dry_run else "primary"

            if not dry_run:
                st.warning("⚠️ 実際にXへ投稿されます。サイドバーの DRY RUN を ON にすると確認のみになります。")

            if st.button(btn_label, use_container_width=True, type=btn_type):
                if dry_run:
                    st.success("【DRY RUN】投稿文の確認が完了しました。実際の投稿はサイドバーの DRY RUN を OFF にしてください。")
                else:
                    with st.spinner("Xに投稿中..."):
                        x = XClient()
                        tweet_id = x.post_tweet(post_text, image_urls=image_urls if image_urls else None)

                    if tweet_id:
                        # スプレッドシートを更新
                        sheets = st.session_state.sheets
                        try:
                            sheets.update_posted(row_num_post, tweet_id)
                            reload_data()
                        except Exception as e:
                            st.warning(f"スプレッドシート更新エラー（投稿は成功）: {e}")

                        st.success(f"✅ 投稿成功！ Tweet ID: {tweet_id}")
                        st.balloons()
                    else:
                        st.error("❌ 投稿に失敗しました。ログを確認してください。")
