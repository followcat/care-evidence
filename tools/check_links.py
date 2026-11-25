#!/usr/bin/env python3
"""购买链可达性检查器（Python3 标准库）。

输入：JSONL（每行 {"id","url","field"}）或直接从 products.jsonl 抽取购买链。
输出：JSONL（每行一条检查记录），支持断点续跑（已查 URL 跳过）。

判定规则集中在 judge() / 常量区，README 复述同一张表。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LINK_FIELDS = ("buyHref", "jdHref", "tmallHref")

# ---- 判定规则（README 判定表与此一致） -------------------------------

BLOCK_STATUS = {401, 403, 407, 429, 503}
BLOCK_URL_HINTS = (
    "login.",
    "passport.",
    "passport.jd.com",
    "pass.tmall.com",
    "verify.",
    "pc-frequent-pro",
    "risk_handler",
    "punish",
    "safe.jd.com",
    "captcha.",
)
# 反爬/登录-wall 只在“小页面”里认定，避免把正常大页面脚本里的
# recaptcha、“请登录”导航字样误判成 blocked。
CHALLENGE_BODY_HINTS = (
    "验证码",
    "滑块验证",
    "安全验证",
    "人机验证",
    "请输入验证码",
    "访问过于频繁",
    "访问频繁",
    "unusual traffic",
    "verify you are human",
    "robot check",
    "captcha",
)
LOGIN_BODY_HINTS = ("请登录", "登录后查看", "请先登录")
CHALLENGE_MAX_BYTES = 40 * 1024
DEAD_URL_HINTS = (
    "/error.aspx",
    "error.aspx",
    "shop/noshop",
    "noshop.htm",
    "item_not_found",
    "page-not-found",
    "/404",
    "404.html",
)
DEAD_BODY_HINTS = (
    "商品不存在",
    "商品已下架",
    "该商品已下架",
    "宝贝不存在",
    "页面找不到",
    "页面不存在",
    "店铺不存在",
    "无效的宝贝",
)
SHELL_URL_HINTS = ("union-click.jd.com", "s.click.taobao.com", "u.jd.com")
SHELL_BODY_HINTS = ("real_jump_address", "京东网上商城")
ONSALE_BODY_HINTS = (
    "加入购物车",
    "立即购买",
    "立即抢购",
    "去购买",
    "价格",
    "¥",
    "￥",
    "店铺",
    "商品详情",
    "add to cart",
    "buy now",
    "price",
)
MIN_CONTENT_BYTES = 600
MAX_BODY_BYTES = 400 * 1024


class RedirectRecorder(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({"status": code, "url": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def domain_of(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host.lower()


def body_text(raw: bytes) -> str:
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc, errors="ignore")
        except LookupError:
            continue
    return ""


def detect_antibot(text: str, markers: list) -> None:
    """小页面才认反爬/登录墙，避免正常大站脚本误伤。"""
    if not text or len(text) > CHALLENGE_MAX_BYTES:
        return
    low = text.lower()
    if any(h.lower() in low for h in CHALLENGE_BODY_HINTS):
        markers.append("challenge-page")
    if any(h in text for h in LOGIN_BODY_HINTS):
        markers.append("login-wall")


def judge(status: int | None, final_url: str, text: str, markers: list, error: str | None) -> str:
    """唯一判定入口：返回 onsale|dead|blocked|domain-error|unknown。"""
    low_url = (final_url or "").lower()

    if error:
        # 重试标记（retry-N@Xs）与 dns/tls/conn-error 并存，故用 any 而非 all。
        if any(m in ("dns-error", "tls-error", "conn-error") for m in markers):
            return "domain-error"
        return "unknown"

    if any(h in low_url for h in BLOCK_URL_HINTS):
        return "blocked"
    if "challenge-page" in markers or "login-wall" in markers:
        return "blocked"
    if status in BLOCK_STATUS:
        return "blocked"

    if any(h in low_url for h in DEAD_URL_HINTS):
        return "dead"
    if any(h in text for h in DEAD_BODY_HINTS):
        return "dead"
    if status in (404, 410, 451):
        return "dead"

    if any(h in low_url for h in SHELL_URL_HINTS) and (
        any(h in text for h in SHELL_BODY_HINTS) or len(text) < MIN_CONTENT_BYTES
    ):
        return "unknown"

    if status is not None and 200 <= status < 300:
        if len(text) >= MIN_CONTENT_BYTES and any(h in text.lower() for h in ONSALE_BODY_HINTS):
            return "onsale"
        return "unknown"

    return "unknown"


# ---------------------------------------------------------------------


class RateLimiter:
    def __init__(self, interval: float):
        self.interval = max(interval, 0.0)
        self._next = {}
        self._locks = {}
        self._guard = threading.Lock()

    def wait(self, domain: str) -> None:
        if self.interval <= 0:
            return
        with self._guard:
            lock = self._locks.setdefault(domain, threading.Lock())
        with lock:
            now = time.monotonic()
            ready = self._next.get(domain, 0.0)
            if ready > now:
                time.sleep(ready - now)
                now = time.monotonic()
            self._next[domain] = now + self.interval


def fetch(url: str, ua: str, timeout: float, retries: int):
    """返回 (status, final_url, text, redirect_chain, markers, retry_after, error)。"""
    markers: list[str] = []
    attempt = 0
    while True:
        recorder = RedirectRecorder()
        opener = urllib.request.build_opener(recorder)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            },
        )
        try:
            with opener.open(req, timeout=timeout) as resp:
                status = resp.status
                final_url = resp.geturl()
                raw = resp.read(MAX_BODY_BYTES)
                retry_after = resp.headers.get("Retry-After")
                text = body_text(raw)
                if len(raw) < MIN_CONTENT_BYTES:
                    markers.append("tiny-body")
                if any(h in text for h in SHELL_BODY_HINTS):
                    markers.append("js-redirect-shell")
                detect_antibot(text, markers)
                if status in BLOCK_STATUS:
                    markers.append(f"http-{status}")
                return status, final_url, text, recorder.chain, markers, retry_after, None
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            body = b""
            try:
                body = exc.read(MAX_BODY_BYTES)
            except Exception:
                pass
            text = body_text(body)
            final_url = exc.geturl() or url
            detect_antibot(text, markers)
            if exc.code in BLOCK_STATUS:
                markers.append(f"http-{exc.code}")
            if attempt < retries and (exc.code in BLOCK_STATUS or exc.code >= 500):
                delay = backoff(attempt, retry_after)
                markers.append(f"retry-{attempt + 1}@{delay:.1f}s")
                time.sleep(delay)
                attempt += 1
                continue
            return exc.code, final_url, text, recorder.chain, markers, retry_after, None
        except socket.timeout:
            if attempt < retries:
                delay = backoff(attempt, None)
                markers.append(f"timeout-retry-{attempt + 1}@{delay:.1f}s")
                time.sleep(delay)
                attempt += 1
                continue
            markers.append("timeout")
            return None, url, "", recorder.chain, markers, None, "timeout"
        except ssl.SSLError as exc:
            markers.append("tls-error")
            return None, url, "", recorder.chain, markers, None, f"tls: {exc}"
        except socket.gaierror as exc:
            markers.append("dns-error")
            return None, url, "", recorder.chain, markers, None, f"dns: {exc}"
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLError):
                markers.append("tls-error")
                return None, url, "", recorder.chain, markers, None, f"tls: {reason}"
            if isinstance(reason, socket.gaierror):
                markers.append("dns-error")
                return None, url, "", recorder.chain, markers, None, f"dns: {reason}"
            markers.append("conn-error")
            if attempt < retries:
                delay = backoff(attempt, None)
                markers.append(f"conn-retry-{attempt + 1}@{delay:.1f}s")
                time.sleep(delay)
                attempt += 1
                continue
            return None, url, "", recorder.chain, markers, None, f"conn: {reason}"
        except Exception as exc:  # 兜底，不让单条拖垮整批
            markers.append("client-error")
            return None, url, "", recorder.chain, markers, None, f"{type(exc).__name__}: {exc}"


def backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(2.0 * (2 ** attempt), 30.0)


def check_one(item, limiter, ua, timeout, retries) -> dict:
    url = item["url"]
    domain = domain_of(url)
    started = time.monotonic()
    limiter.wait(domain)
    status, final_url, text, chain, markers, retry_after, error = fetch(
        url, ua, timeout, retries
    )
    if retry_after is not None:
        markers.append("retry-after")
    verdict = judge(status, final_url, text, markers, error)
    record = {
        "url": url,
        "final_url": final_url,
        "http_status": status,
        "redirect_chain": chain,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "markers": markers,
        "verdict": verdict,
        "error": error,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if item.get("id") is not None:
        record["id"] = item["id"]
    if item.get("field") is not None:
        record["field"] = item["field"]
    return record


def read_input(path: str) -> list[dict]:
    items, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            url = (obj.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            items.append({"id": obj.get("id"), "url": url, "field": obj.get("field")})
    return items


def extract_from_products(path: str) -> list[dict]:
    items, seen = [], set()

    def add(url, pid, field):
        url = (url or "").strip()
        if not url or not url.startswith("http"):
            return
        if url in seen:
            return
        seen.add(url)
        items.append({"id": pid, "url": url, "field": field})

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            pid = obj.get("id")
            buy = obj.get("buy") or {}
            for field in LINK_FIELDS:
                add(buy.get(field), pid, field)
            for channel in buy.get("channels") or []:
                if isinstance(channel, dict):
                    add(channel.get("href"), pid, "channels[].href")
    return items


def read_done(path: str) -> set:
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("url"):
                done.add(obj["url"])
    return done


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_links.py", description="购买链可达性检查（限速/重试/断点续跑）"
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="输入 JSONL，每行 {id,url,field}")
    src.add_argument("--from-products", help="从 products.jsonl 抽取全部购买链")
    p.add_argument("--output", required=True, help="输出 JSONL 路径（追加写入）")
    p.add_argument(
        "--domain-interval",
        type=float,
        default=2.0,
        help="同域名最小请求间隔秒数（默认 2.0，即 ≤1 次/2 秒/域名）",
    )
    p.add_argument("--concurrency", type=int, default=4, help="全局并发上限（默认 4）")
    p.add_argument("--timeout", type=float, default=20.0, help="单请求连接/读取超时秒数")
    p.add_argument(
        "--total-timeout", type=float, default=0.0, help="整批总预算秒数，0 表示不限"
    )
    p.add_argument("--retries", type=int, default=2, help="重试次数上限（默认 2）")
    p.add_argument("--user-agent", default=DEFAULT_UA, help="请求 User-Agent")
    p.add_argument("--limit", type=int, default=0, help="只处理前 N 条，0 表示全部")
    p.add_argument(
        "--no-resume", action="store_true", help="忽略已有输出，全部重查"
    )
    p.add_argument("--extract-only", action="store_true", help="只打印抽取结果，不发请求")
    return p


def main(argv=None) -> int:
    args = make_parser().parse_args(argv)
    items = (
        extract_from_products(args.from_products)
        if args.from_products
        else read_input(args.input)
    )
    if args.limit > 0:
        items = items[: args.limit]
    if args.extract_only:
        for item in items:
            print(json.dumps(item, ensure_ascii=False))
        return 0

    done = set() if args.no_resume else read_done(args.output)
    todo = [item for item in items if item["url"] not in done]
    skipped = len(items) - len(todo)
    print(
        f"待查 {len(todo)} 条，续跑跳过 {skipped} 条（并发 {args.concurrency}，"
        f"域名间隔 {args.domain_interval}s，重试 {args.retries}）",
        file=sys.stderr,
    )

    limiter = RateLimiter(args.domain_interval)
    deadline = time.monotonic() + args.total_timeout if args.total_timeout > 0 else None
    counts: dict[str, int] = {}
    write_lock = threading.Lock()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    mode = "w" if args.no_resume else "a"
    with open(args.output, mode, encoding="utf-8") as out:

        def work(item):
            if deadline and time.monotonic() > deadline:
                record = {
                    "url": item["url"],
                    "final_url": None,
                    "http_status": None,
                    "redirect_chain": [],
                    "latency_ms": 0,
                    "markers": ["total-timeout-skip"],
                    "verdict": "unknown",
                    "error": "total-timeout",
                    "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "id": item.get("id"),
                    "field": item.get("field"),
                }
            else:
                record = check_one(
                    item, limiter, args.user_agent, args.timeout, args.retries
                )
            with write_lock:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
            return record

        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
            list(pool.map(work, todo))

    print("判定分布：" + json.dumps(counts, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
