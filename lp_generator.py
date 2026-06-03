"""
LP（ランディングページ）生成モジュール
在庫管理データから車両紹介用のHTML/CSSを自動生成する。
"""
import hashlib
import html as html_escape_module
from typing import Any

SITE_BASE_URL = "https://kurumaurunara.com/cars/"
SHOP_NAME     = "くるまうるなら"
SHOP_NAME_SUB = "名古屋・愛知の中古車販売"
X_PROFILE_URL = "https://x.com/kurumayanagoya"  # DM誘導先


# ─────────────────────────────────────────────────────────────────────
# スラッグ・URL生成
# ─────────────────────────────────────────────────────────────────────
def make_slug(car: dict[str, Any]) -> str:
    """車両データからURL安全なスラッグを生成する"""
    car_id = str(car.get("id", "")).strip()
    if car_id:
        safe = "".join(c for c in car_id if c.isalnum() or c == "-")
        if safe:
            return f"car-{safe}"
    key = f"{car.get('maker','')}{car.get('car_name','')}{car.get('year','')}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
    return f"car-{h}"


def get_lp_url(car: dict[str, Any]) -> str:
    """車両のLP公開URLを返す"""
    return f"{SITE_BASE_URL}{make_slug(car)}/"


# ─────────────────────────────────────────────────────────────────────
# HTML 生成
# ─────────────────────────────────────────────────────────────────────
def _e(text: Any) -> str:
    """HTMLエスケープ"""
    return html_escape_module.escape(str(text or ""))


def _images(car: dict[str, Any]) -> list[str]:
    """有効な画像URLリスト（最大10枚）を返す"""
    urls = []
    for i in range(1, 11):
        u = str(car.get(f"image_{i}", "")).strip()
        if u:
            urls.append(u)
    return urls


def _equipment_tags(raw: str) -> str:
    """装備文字列をバッジHTMLに変換する（読点・スラッシュ・改行で分割）"""
    if not raw:
        return ""
    import re
    items = [x.strip() for x in re.split(r"[、,，/／\n]", raw) if x.strip()]
    tags = "".join(f'<span class="eq-tag">{_e(item)}</span>' for item in items)
    return tags


def generate_lp_html(car: dict[str, Any]) -> str:
    """
    車両辞書からLP用の完全なHTMLを生成して返す。
    """
    maker        = _e(car.get("maker", ""))
    car_name     = _e(car.get("car_name", ""))
    year         = _e(car.get("year", ""))
    mileage      = _e(car.get("mileage", ""))
    price        = _e(car.get("price", ""))
    inspection   = _e(car.get("inspection", "要確認"))
    repair       = _e(car.get("repair_history", "なし"))
    chassis_num  = _e(car.get("chassis_number", ""))
    plus_pt      = _e(car.get("plus_points", ""))
    minus_pt     = _e(car.get("minus_points", ""))
    equipment    = str(car.get("equipment", ""))
    review       = _e(car.get("review", ""))
    lp_url       = get_lp_url(car)

    title    = f"{maker} {car_name} {year}年式 | {SHOP_NAME}"
    og_desc  = f"{maker} {car_name} {year}年式 走行{mileage} 総額{price}。名古屋・愛知の中古車販売 {SHOP_NAME}。"
    images   = _images(car)
    first_img = images[0] if images else ""

    # ── ギャラリー HTML ──────────────────────────────────────────────
    if images:
        gallery_items = "".join(
            f'<img src="{_e(u)}" class="thumb{"  thumb-active" if i==0 else ""}" '
            f'onclick="changeMain(this,\'{_e(u)}\')" alt="写真{i+1}" loading="lazy" />'
            for i, u in enumerate(images)
        )
        gallery_html = f"""
        <section class="gallery-section">
          <div class="main-img-wrap" onclick="openLightbox(this.querySelector('img').src)">
            <img id="main-img" src="{_e(first_img)}" alt="{maker} {car_name} メイン写真" />
            <span class="zoom-hint">🔍 クリックで拡大</span>
          </div>
          <div class="thumbs-wrap">{gallery_items}</div>
          <p class="photo-count">写真 {len(images)} 枚</p>
        </section>"""
    else:
        gallery_html = '<section class="gallery-section"><p class="no-img">写真準備中</p></section>'

    # ── 装備バッジ ────────────────────────────────────────────────────
    eq_html = ""
    if equipment:
        eq_html = f"""
        <section class="section equipment-section">
          <h2 class="section-title">🔧 装備・オプション</h2>
          <div class="eq-tags">{_equipment_tags(equipment)}</div>
        </section>"""

    # ── プラス/マイナスポイント ───────────────────────────────────────
    points_html = ""
    if plus_pt or minus_pt:
        plus_block  = f'<div class="point-card plus-card"><span class="point-icon">◎</span>{plus_pt}</div>' if plus_pt else ""
        minus_block = f'<div class="point-card minus-card"><span class="point-icon">△</span>{minus_pt}</div>' if minus_pt else ""
        points_html = f"""
        <section class="section points-section">
          <h2 class="section-title">🚘 車両コメント</h2>
          {plus_block}
          {minus_block}
        </section>"""

    # ── お客様の声 ────────────────────────────────────────────────────
    review_html = ""
    if review:
        review_html = f"""
        <section class="section review-section">
          <h2 class="section-title">⭐ お客様の声</h2>
          <blockquote class="review-block">
            <p>{review}</p>
          </blockquote>
        </section>"""

    # ── 車体番号 ──────────────────────────────────────────────────────
    chassis_row = f"<tr><th>車体番号</th><td>{chassis_num}</td></tr>" if chassis_num else ""

    # ── 全体 HTML ─────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{og_desc}">
  <meta name="keywords" content="中古車,名古屋,愛知,{maker},{car_name},{year}年式,車売ります">
  <!-- OGP -->
  <meta property="og:type"        content="product">
  <meta property="og:title"       content="{title}">
  <meta property="og:description" content="{og_desc}">
  <meta property="og:image"       content="{_e(first_img)}">
  <meta property="og:url"         content="{_e(lp_url)}">
  <meta property="og:site_name"   content="{SHOP_NAME}">
  <!-- Twitter Card -->
  <meta name="twitter:card"        content="summary_large_image">
  <meta name="twitter:title"       content="{title}">
  <meta name="twitter:description" content="{og_desc}">
  <meta name="twitter:image"       content="{_e(first_img)}">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
            background: #f5f5f5; color: #222; line-height: 1.7; }}
    a {{ color: inherit; text-decoration: none; }}

    /* ── Header ── */
    header {{ background: #1a1a2e; color: #fff; padding: 14px 20px;
              display: flex; align-items: center; gap: 10px; }}
    header h1 {{ font-size: 1.1rem; font-weight: 700; }}
    header p  {{ font-size: 0.75rem; opacity: .7; }}

    /* ── Hero ── */
    .hero {{ background: #fff; padding: 20px 16px 14px; border-bottom: 3px solid #e8323c; }}
    .hero-title {{ font-size: 1.6rem; font-weight: 800; color: #1a1a2e; }}
    .hero-price {{ font-size: 2rem; font-weight: 900; color: #e8323c;
                   margin-top: 6px; letter-spacing: -1px; }}
    .hero-price span {{ font-size: 1rem; font-weight: 500; color: #666; }}

    /* ── Gallery ── */
    .gallery-section {{ background: #111; padding: 12px; }}
    .main-img-wrap {{ position: relative; cursor: zoom-in; text-align: center; }}
    #main-img {{ width: 100%; max-height: 400px; object-fit: contain;
                 border-radius: 6px; display: block; margin: 0 auto; }}
    .zoom-hint {{ position: absolute; bottom: 8px; right: 10px;
                  background: rgba(0,0,0,.55); color: #fff;
                  font-size: .7rem; padding: 2px 8px; border-radius: 12px; }}
    .thumbs-wrap {{ display: flex; gap: 6px; overflow-x: auto;
                    padding: 10px 0 2px; scrollbar-width: thin; }}
    .thumbs-wrap img {{ width: 72px; height: 54px; object-fit: cover;
                        border-radius: 4px; cursor: pointer; flex-shrink: 0;
                        border: 2px solid transparent; transition: border-color .2s; }}
    .thumb-active {{ border-color: #e8323c !important; }}
    .photo-count {{ color: #aaa; font-size: .75rem; text-align: right;
                    padding: 4px 2px 0; }}
    .no-img {{ color: #888; text-align: center; padding: 40px 0; }}

    /* ── Sections ── */
    .section {{ background: #fff; margin: 10px 0; padding: 18px 16px; }}
    .section-title {{ font-size: 1rem; font-weight: 700; color: #1a1a2e;
                      margin-bottom: 14px; padding-bottom: 8px;
                      border-bottom: 2px solid #e8e8e8; }}

    /* ── Spec table ── */
    .spec-table {{ width: 100%; border-collapse: collapse; font-size: .95rem; }}
    .spec-table th, .spec-table td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }}
    .spec-table th {{ width: 38%; color: #666; font-weight: 600;
                      background: #fafafa; text-align: left; }}
    .spec-table td {{ font-weight: 500; }}

    /* ── Equipment ── */
    .eq-tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .eq-tag {{ background: #eef2ff; color: #3a5bd4; border-radius: 20px;
               padding: 4px 14px; font-size: .85rem; font-weight: 500; }}

    /* ── Points ── */
    .point-card {{ border-radius: 8px; padding: 12px 16px;
                   margin-bottom: 10px; font-size: .9rem; line-height: 1.6; }}
    .plus-card  {{ background: #f0fdf4; border-left: 4px solid #22c55e; }}
    .minus-card {{ background: #fff7ed; border-left: 4px solid #f97316; }}
    .point-icon {{ font-weight: 700; margin-right: 6px; }}

    /* ── CTA ── */
    .cta-section {{ background: #1a1a2e; color: #fff; padding: 28px 16px; text-align: center; }}
    .cta-section h2 {{ font-size: 1.1rem; margin-bottom: 6px; }}
    .cta-section p  {{ font-size: .85rem; opacity: .75; margin-bottom: 18px; }}
    .dm-btn {{ display: inline-block; background: #e8323c; color: #fff;
               font-size: 1.05rem; font-weight: 700; padding: 14px 36px;
               border-radius: 50px; letter-spacing: .5px;
               box-shadow: 0 4px 14px rgba(232,50,60,.4);
               transition: transform .15s, box-shadow .15s; }}
    .dm-btn:hover {{ transform: translateY(-2px);
                     box-shadow: 0 6px 20px rgba(232,50,60,.5); }}
    .dm-btn:active {{ transform: translateY(0); }}

    /* ── Review ── */
    .review-block {{ background: #fffbea; border-left: 4px solid #f59e0b;
                     border-radius: 0 8px 8px 0; padding: 14px 18px;
                     font-size: .92rem; line-height: 1.7; color: #555; }}

    /* ── Footer ── */
    footer {{ background: #111; color: #888; font-size: .78rem;
              text-align: center; padding: 20px; }}

    /* ── Lightbox ── */
    #lightbox {{ display: none; position: fixed; inset: 0; z-index: 9999;
                 background: rgba(0,0,0,.92); align-items: center;
                 justify-content: center; flex-direction: column; }}
    #lightbox.open {{ display: flex; }}
    #lightbox img {{ max-width: 96vw; max-height: 88vh; object-fit: contain;
                     border-radius: 6px; }}
    #lb-close {{ position: absolute; top: 16px; right: 20px; background: none;
                 border: none; color: #fff; font-size: 2rem; cursor: pointer;
                 line-height: 1; }}

    @media (min-width: 640px) {{
      .hero {{ padding: 28px 32px; }}
      .hero-title {{ font-size: 2rem; }}
      .section {{ padding: 24px 32px; }}
      #main-img {{ max-height: 500px; }}
    }}
  </style>
</head>
<body>

<header>
  <div>
    <h1>🚗 {SHOP_NAME}</h1>
    <p>{SHOP_NAME_SUB}</p>
  </div>
</header>

<!-- ヒーロー -->
<div class="hero">
  <div class="hero-title">{maker} {car_name}</div>
  <div class="hero-price">{price} <span>（税込総額）</span></div>
</div>

<!-- ギャラリー -->
{gallery_html}

<!-- 車両スペック -->
<section class="section">
  <h2 class="section-title">📋 車両詳細</h2>
  <table class="spec-table">
    <tr><th>年式</th><td>{year}年式</td></tr>
    <tr><th>走行距離</th><td>{mileage}</td></tr>
    <tr><th>車検</th><td>{inspection}</td></tr>
    <tr><th>修復歴</th><td>{repair}</td></tr>
    {chassis_row}
  </table>
</section>

<!-- 装備 -->
{eq_html}

<!-- ポイント -->
{points_html}

<!-- CTA -->
<section class="cta-section">
  <h2>📩 お問い合わせはXのDMから</h2>
  <p>気になる点・試乗のご希望もお気軽にどうぞ</p>
  <a href="{X_PROFILE_URL}" target="_blank" rel="noopener" class="dm-btn">
    ✉️ DM を送る
  </a>
</section>

<!-- お客様の声 -->
{review_html}

<footer>
  <p>{SHOP_NAME} &copy; {SHOP_NAME_SUB}</p>
  <p style="margin-top:6px;"><a href="{X_PROFILE_URL}" target="_blank" rel="noopener">𝕏 @kurumayanagoya</a></p>
  <p style="margin-top:14px; border-top:1px solid #333; padding-top:14px; line-height:2;">
    運営会社：合同会社ワーケーションスタイル（本社 名古屋市西区）<br>
    古物商許可番号：愛知県公安委員会　第541042308500号
  </p>
</footer>

<!-- ライトボックス -->
<div id="lightbox">
  <button id="lb-close" onclick="closeLightbox()">&#x2715;</button>
  <img id="lb-img" src="" alt="拡大表示" />
</div>

<script>
  function changeMain(thumb, src) {{
    document.getElementById('main-img').src = src;
    document.querySelectorAll('.thumb').forEach(t => t.classList.remove('thumb-active'));
    thumb.classList.add('thumb-active');
  }}
  function openLightbox(src) {{
    document.getElementById('lb-img').src = src;
    document.getElementById('lightbox').classList.add('open');
    document.body.style.overflow = 'hidden';
  }}
  function closeLightbox() {{
    document.getElementById('lightbox').classList.remove('open');
    document.body.style.overflow = '';
  }}
  document.getElementById('lightbox').addEventListener('click', function(e) {{
    if (e.target === this) closeLightbox();
  }});
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closeLightbox();
  }});
</script>
</body>
</html>"""
