#!/usr/bin/env python3
import html
import json
import re
import sys
from pathlib import Path

site = Path("site")
root = site.parent
candidates = (root / "data" / "products.json", site / "data" / "products.json")
data_path = next((p for p in candidates if p.exists()), site / "data" / "products.json")


def strip_tags(value):
    value = re.sub(r"<script.*?</script>", "", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def expected_buy_links(rec):
    links = []
    seen = set()
    buy = rec.get("buy") or {}
    for channel in buy.get("channels") or []:
        href = channel.get("href")
        if isinstance(href, str) and href.startswith(("https://", "http://")) and href not in seen:
            seen.add(href)
            links.append(href)
    href = buy.get("buyHref")
    if isinstance(href, str) and href.startswith(("https://", "http://")) and href not in seen:
        seen.add(href)
        links.append(href)
    return links


try:
    products = json.load(open(data_path, encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
    print(f"verify result: FAIL data_load={exc}")
    sys.exit(1)

problems = []
if not isinstance(products, list):
    problems.append(("data", "type", type(products).__name__))
    products = []

ids = []
by_id = {}
for row in products:
    row_id = row.get("id") if isinstance(row, dict) else None
    if isinstance(row_id, str) and row_id:
        ids.append(row_id)
        by_id[row_id] = row
    else:
        problems.append(("data", "missing_id", row_id if isinstance(row, dict) else "non-dict"))
duplicate_ids = sorted({pid for pid in ids if ids.count(pid) > 1})
for pid in duplicate_ids:
    problems.append(("data", "duplicate_id", pid))

sample = ["sr-revox-line", "ba-laneige-wbcl", "ss-simpcare-lbd", "br-eucerin-urea", "tp-colgate-proargin"]
for pid in sample:
    if pid not in by_id:
        problems.append((pid, "missing_product", pid))
        print(pid, "missing product")
        continue
    rec = by_id[pid]
    page_path = site / "dist" / "p" / pid / "index.html"
    if not page_path.exists():
        problems.append((pid, "missing_page", str(page_path)))
        print(pid, "missing page")
        continue
    raw = html.unescape(page_path.read_text(encoding="utf-8"))
    text = strip_tags(raw)
    legacy = rec.get("legacy") or {}
    v5 = rec.get("v5") or {}
    checks = {
        "product": rec.get("product") or "",
        "E": f"E{legacy.get('E')}",
        "S": f"S{legacy.get('score')}",
        "p_status": v5.get("p_status") or "未完成实用评估",
        "d_tier": v5.get("d_tier") or "尚无差异证据或待评",
    }
    for key, expected in checks.items():
        if expected and expected not in text:
            problems.append((pid, key, expected))
    for href in expected_buy_links(rec):
        if href not in raw:
            problems.append((pid, "buyhref", href))
    pid_problems = [p for p in problems if p[0] == pid]
    print(pid, "ok" if not pid_problems else pid_problems)

index_exists = (site / "dist" / "index.html").is_file()
if not index_exists:
    problems.append(("index", "missing", "site/dist/index.html"))

detail_root = site / "dist" / "p"
detail_paths = sorted(detail_root.glob("*/index.html")) if detail_root.is_dir() else []
detail_ids = {path.parent.name for path in detail_paths}
expected_ids = set(ids)
missing = sorted(expected_ids - detail_ids)
extra = sorted(detail_ids - expected_ids)
print("pages missing:", len(missing))
print("pages extra:", len(extra))
print("total products:", len(products))

pack_path = Path("skincare-discussion-pack-2026-11-24/data/products.json")
if pack_path.exists():
    try:
        pack = json.load(open(pack_path, encoding="utf-8"))
        print("site data identical to pack:", pack == products, "（信息项；站点数据可能包含购买链更新）")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print("site data identical to pack: 无法读取（信息项）", exc)
else:
    print("site data identical to pack: 跳过（无讨论包，纯装配仓库）")

if problems or missing or extra or len(products) != 476 or duplicate_ids:
    print(
        "verify result: FAIL "
        f"problems={len(problems)} missing={len(missing)} extra={len(extra)} "
        f"products={len(products)} duplicate_ids={len(duplicate_ids)} index={1 if index_exists else 0}"
    )
    sys.exit(1)

print(f"verify result: PASS products={len(products)} detail_pages={len(detail_paths)} index=1")
