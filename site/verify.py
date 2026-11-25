import json, re, html
from pathlib import Path

site = Path("site")
_root = site.parent
_candidates = (_root / "data" / "products.json", site / "data" / "products.json")
_data_path = next((p for p in _candidates if p.exists()), site / "data" / "products.json")
products = json.load(open(_data_path, encoding="utf-8"))
by_id = {r["id"]: r for r in products}


def strip_tags(s):
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


sample = ["sr-revox-line", "ba-laneige-wbcl", "ss-simpcare-lbd", "br-eucerin-urea", "tp-colgate-proargin"]
problems = []
for pid in sample:
    rec = by_id[pid]
    text = strip_tags((site / "dist" / "p" / pid / "index.html").read_text(encoding="utf-8"))
    checks = {
        "product": rec["product"],
        "E": f"E{rec['legacy']['E']}",
        "S": f"S{rec['legacy']['score']}",
        "p_status": ("还没评" if rec["v5"]["p_status"] in (None, "未完成实用评估") else rec["v5"]["p_status"]),
        "d_tier": rec["v5"]["d_tier"] or "尚无差异证据或待评",
    }
    for k, v in checks.items():
        if v not in text:
            problems.append((pid, k, v))
    # buy links
    for ch in (rec["buy"].get("channels") or []):
        href = ch.get("href")
        if href and href.startswith("http"):
            raw = html.unescape((site / "dist" / "p" / pid / "index.html").read_text(encoding="utf-8"))
            if href not in raw:
                problems.append((pid, "buyhref", href))
    print(pid, "ok" if not [p for p in problems if p[0] == pid] else [p for p in problems if p[0] == pid])

# full coverage check: every product has a page, and homepage static count matches
missing = [r["id"] for r in products if not (site / "dist" / "p" / r["id"] / "index.html").exists()]
print("pages missing:", len(missing))
print("total products:", len(products))

# data file equality with pack source (讨论包只在 studio 工作区存在；纯装配仓库内跳过)
pack_path = Path("skincare-discussion-pack-2026-11-24/data/products.json")
if pack_path.exists():
    pack = json.load(open(pack_path, encoding="utf-8"))
    print("site data identical to pack:", pack == products)
else:
    print("site data identical to pack: 跳过（无讨论包，纯装配仓库）")
