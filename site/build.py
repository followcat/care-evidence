#!/usr/bin/env python3
"""零依赖静态站生成器。

用法：
  python3 site/build.py             # 用 site/data/products.json 生成 site/dist/
  python3 site/build.py --refresh-data  # 先从讨论包重新拷贝 products.json 再生成
"""
import argparse
import html
import json
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
PACK_DATA = ROOT / "skincare-discussion-pack-2026-11-24" / "data" / "products.json"


def resolve_data():
    """定位数据源：装配仓库用 repo 根 data/，studio 工作区用 site/data/。"""
    for candidate in (ROOT / "data" / "products.json", SITE / "data" / "products.json"):
        if candidate.exists():
            return candidate
    return SITE / "data" / "products.json"


DATA_OUT = resolve_data()
DIST = SITE / "dist"
SRC = SITE / "src"


def h(value):
    return html.escape("" if value is None else str(value), quote=True)


def safe_href(url):
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url
    return None


def load_json(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def e_band(e):
    if e is None:
        return "未知"
    if e >= 6:
        return "证据较硬"
    if e >= 3:
        return "证据中等"
    return "证据偏少"


P_ORDER = {
    "基础用途优选": 0,
    "条件适用": 1,
    "对照·选购成立": 2,
    "对照·条件适用": 3,
    "待核": 4,
    None: 5,
}


def p_label(rec):
    status = rec["v5"].get("p_status") or "未完成实用评估"
    return status


def d_label(rec):
    return rec["v5"].get("d_tier") or "尚无差异证据或待评"


def buy_links(rec):
    links = []
    seen = set()
    buy = rec.get("buy") or {}
    for ch in buy.get("channels") or []:
        href = safe_href(ch.get("href"))
        label = ch.get("label") or "渠道"
        if href and href not in seen:
            seen.add(href)
            links.append((label, href))
    href = safe_href(buy.get("buyHref"))
    if href and href not in seen:
        seen.add(href)
        links.append((buy.get("buyLabel") or "购买页", href))
    return links


def build_index(products, config):
    total = len(products)
    daily = sum(1 for r in products if r["board"] == "daily")
    rx = sum(1 for r in products if r["board"] == "rx")
    p_done = sum(1 for r in products if r["v5"].get("p_evaluated"))
    d_done = sum(1 for r in products if r["v5"].get("d_case"))
    name = config["siteName"]

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(name)}</title>
<meta name="description" content="{h(config['siteTagline'])}">
<link rel="stylesheet" href="assets/style.css">
</head>
<body data-page="index">
<header class="topbar">
  <a class="brand" href="index.html">{h(name)}</a>
  <span class="topbar-link">共 {total} 条 · 先选用途再看条目</span>
</header>
<main>
  <section class="hero">
    <h1>{h(name)}</h1>
    <p class="tagline">{h(config['siteTagline'])}</p>
    <p class="lede" id="lede">先选用途，再选品类，然后看单个条目。不做跨品类总分排名。</p>
    <ul class="stats">
      <li><strong>{total}</strong><span>条目</span></li>
      <li><strong>{daily}</strong><span>日常</span></li>
      <li><strong>{rx}</strong><span>治疗／创面</span></li>
      <li><strong>{p_done}</strong><span>P 已评</span></li>
      <li><strong>{d_done}</strong><span>D 案例</span></li>
    </ul>
  </section>

  <section class="howto" aria-labelledby="howto-title">
    <h2 id="howto-title">三个数字，各看一件事</h2>
    <dl>
      <dt><span class="chip chip-e">E · 证据有多硬</span></dt>
      <dd>公开研究里，能核对到的人体证据有多确定。数字高说明研究做得实、能查到出处；但证据硬不等于效果更大。</dd>
      <dt><span class="chip chip-p">P · 日常值不值得选</span></dt>
      <dd>日常买得值不值。看已核对的配方线索、用途是否对得上、风险和使用限制。目前只评了一部分；没评的写「未完成实用评估」，这不是差评。</dd>
      <dt><span class="chip chip-d">D · 有没有新信号</span></dt>
      <dd>有没有别人没有的研究点，比如特定人群、特殊剂型或新机制线索。有小研究也不代表比基础款更好。</dd>
    </dl>
    <p class="note">页面只整理公开证据与购买线索，供你核对；不下单、不代付款，也不替代医生诊断。</p>
  </section>

  <div id="app" aria-live="polite">
    <p class="loading">正在载入数据…</p>
  </div>
</main>
<footer>
  <p>{h(config['footerNote'])}</p>
  <p class="small">数据来自讨论包 2026-11-24（r44 快照，476 条）。购买链接「{h(config['purchaseLabel'])}」，下单前请再核对包装、店铺身份与实时价。</p>
</footer>
<script src="assets/app.js" defer></script>
</body>
</html>
"""
    (DIST / "index.html").write_text(page, encoding="utf-8")


def field_row(label, value, cls=""):
    text = value if (isinstance(value, str) and value.strip()) else "未知／待核"
    return f'<div class="field {cls}"><dt>{h(label)}</dt><dd>{h(text)}</dd></div>'


def build_detail(rec, config):
    name = config["siteName"]
    buy = rec.get("buy") or {}
    links = buy_links(rec)
    if links:
        buy_html = "".join(
            f'<li><a href="{h(href)}" rel="noopener noreferrer nofollow" target="_blank">{h(label)}</a> '
            f'<span class="tag">{h(config["purchaseLabel"])}</span></li>'
            for label, href in links
        )
        buy_html = f'<ul class="buylist">{buy_html}</ul>'
    else:
        buy_html = '<p class="unknown">购买线索：未知／待核（本轮未核到可用链接）</p>'

    buy_note = buy.get("buyNote")
    note_html = f'<p class="note">{h(buy_note)}</p>' if buy_note else ""

    legacy = rec.get("legacy") or {}
    rows = "".join([
        field_row("品名", rec.get("product")),
        field_row("条目 id", rec.get("id"), "mono"),
        field_row("品类", rec.get("cat_label")),
        field_row("用途", rec.get("board_label")),
        field_row("价位带", rec.get("band_label")),
        field_row("参考价", rec.get("price")),
        field_row("主打作用", rec.get("role")),
        field_row("缺点与限制", rec.get("drawback")),
        field_row("活性／配方线索", rec.get("actives")),
        field_row("主终点与测法", rec.get("endpoint")),
        field_row("证据出处", rec.get("cites")),
        field_row("合规／备案线索", rec.get("official")),
        field_row("渠道", rec.get("channel")),
        field_row("使用注意", rec.get("caution")),
        field_row("适用情景", rec.get("suit")),
    ])

    e = legacy.get("E")
    s = legacy.get("score")
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(rec.get('product'))} · {h(name)}</title>
<link rel="stylesheet" href="../../assets/style.css">
</head>
<body data-page="detail">
<header class="topbar">
  <a class="brand" href="../../index.html">{h(name)}</a>
  <a class="topbar-link" href="../../index.html">返回浏览</a>
</header>
<main class="detail">
  <p class="crumbs"><a href="../../index.html">全部条目</a> / {h(rec.get('cat_label'))} / {h(rec.get('board_label'))}</p>
  <h1>{h(rec.get('product'))}</h1>
  <p class="mono subtle">id: {h(rec.get('id'))}</p>

  <div class="scores">
    <div class="chip chip-e"><span class="num">E{h(e if e is not None else '?')}</span><span class="sub">{h(e_band(e))}</span></div>
    <div class="chip chip-s"><span class="num">S{h(s if s is not None else '?')}</span><span class="sub">旧门总分</span></div>
    <div class="chip chip-p"><span class="num">{h(p_label(rec))}</span><span class="sub">P 选购档</span></div>
    <div class="chip chip-d"><span class="num">{h(d_label(rec))}</span><span class="sub">D 差异层</span></div>
  </div>
  <p class="note">E 说明证据有多确定，S 是 v4.2 旧评分（满分 13），P 说明日常值不值得选，D 说明有没有独特研究点。三者互不等价。</p>

  <section class="panel">
    <h2>旧门判定</h2>
    <p>{h(legacy.get('verdict_label') or '未知／待核')} · parts: <span class="mono">{h(legacy.get('parts') or '未知')}</span></p>
    <p class="note">{h(legacy.get('grade') or '评分说明：未知／待核')}</p>
    <p class="note">旧门标签只说明证据确定性，不等于更值得买。</p>
  </section>

  <section class="panel">
    <h2>字段明细</h2>
    <dl class="fields">{rows}</dl>
  </section>

  <section class="panel">
    <h2>购买线索（{h(config['purchaseLabel'])}）</h2>
    {buy_html}
    {note_html}
  </section>
</main>
<footer><p>{h(config['footerNote'])}</p></footer>
</body>
</html>
"""
    out = DIST / "p" / str(rec["id"]) / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-data", action="store_true", help="从讨论包重新拷贝 products.json")
    args = parser.parse_args()

    if args.refresh_data or not DATA_OUT.exists():
        DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACK_DATA, DATA_OUT)

    config = load_json(SITE / "config.json")
    products = load_json(DATA_OUT)
    if len(products) != 476:
        sys.exit(f"数据条数异常：{len(products)}（应为 476）")
    ids = [r["id"] for r in products]
    if len(set(ids)) != len(ids):
        sys.exit("数据存在重复 id")

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    (DIST / "data").mkdir(parents=True)

    shutil.copyfile(DATA_OUT, DIST / "data" / "products.json")
    (DIST / "data" / "meta.json").write_text(
        json.dumps({"siteName": config["siteName"], "count": len(products)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    shutil.copyfile(SRC / "style.css", DIST / "assets" / "style.css")
    shutil.copyfile(SRC / "app.js", DIST / "assets" / "app.js")

    build_index(products, config)
    for rec in products:
        build_detail(rec, config)

    print(f"已生成 {DIST}：{len(products)} 个条目页 + 首页")


if __name__ == "__main__":
    main()
