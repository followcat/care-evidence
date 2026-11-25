#!/usr/bin/env python3
"""值得买 (Haina) MCP streamable-HTTP 命令行封装。

只依赖 Python3 标准库。密钥/端点运行时取得：
  1. 环境变量 HAINA_MCP_HTTP / HAINA_MCP_KEY
  2. 否则从脚本位置向上查找仓库根 .env（可用 --env-file 显式指定）

密钥值永不打印、永不落盘；错误信息只报“缺少配置”，不带值。

用法示例见 tools/README.md。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

CLIENT_NAME = "skincare-haina-cli"
CLIENT_VERSION = "1.0.0"
PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
DEFAULT_TIMEOUT = 40.0

EXIT_CONFIG = 2
EXIT_HTTP = 3
EXIT_PROTOCOL = 4
EXIT_TIMEOUT = 5
EXIT_USAGE = 6

# 验收要求的四个工具，以及命令行别名。
TOOL_ALIASES = {
    "product-search": "product_search_pro",
    "product_search_pro": "product_search_pro",
    "content-search": "universal_content_search",
    "universal_content_search": "universal_content_search",
    "discount": "discount_search",
    "discount_search": "discount_search",
    "image-search": "image_search",
    "image_search": "image_search",
}


class ConfigError(Exception):
    pass


class ProtocolError(Exception):
    pass


def _parse_env_file(path: Path) -> dict:
    values = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values.setdefault(key, value)
    return values


def find_env_file(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    start = Path(__file__).resolve().parent
    for directory in [start, *start.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_config(env_file: str | None) -> tuple[str, str, Path | None]:
    endpoint = os.environ.get("HAINA_MCP_HTTP")
    api_key = os.environ.get("HAINA_MCP_KEY")
    used = None
    if not endpoint or not api_key:
        used = find_env_file(env_file)
        if env_file and used is None:
            raise ConfigError(f"指定的 --env-file 不存在：{env_file}")
        if used is not None:
            values = _parse_env_file(used)
            endpoint = endpoint or values.get("HAINA_MCP_HTTP")
            api_key = api_key or values.get("HAINA_MCP_KEY")
    if not endpoint:
        raise ConfigError("缺少端点：请设置 HAINA_MCP_HTTP 或在仓库根 .env 中配置")
    if not api_key:
        raise ConfigError("缺少密钥：请设置 HAINA_MCP_KEY 或在仓库根 .env 中配置")
    return endpoint, api_key, used


class HainaMCP:
    """最小的 MCP streamable-HTTP 客户端：initialize → tools/list → tools/call。"""

    def __init__(self, endpoint: str, api_key: str, timeout: float = DEFAULT_TIMEOUT):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self._next_id = 0

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "x-api-key": self.api_key,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _next(self) -> int:
        self._next_id += 1
        return self._next_id

    def _post(self, payload: dict) -> tuple[dict | None, dict]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                headers = {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise ProtocolError(f"HTTP {exc.code}：{detail}") from None
        except socket.timeout:
            raise TimeoutError(f"请求超时（{self.timeout}s）") from None
        except urllib.error.URLError as exc:
            raise ProtocolError(f"网络错误：{exc.reason}") from None

        if headers.get("mcp-session-id"):
            self.session_id = headers["mcp-session-id"]
        if headers.get("mcp-protocol-version"):
            self.protocol_version = headers["mcp-protocol-version"]
        if not body.strip():
            return None, headers
        return self._parse_body(body, payload.get("id")), headers

    @staticmethod
    def _parse_body(body: str, want_id) -> dict:
        body = body.strip()
        if body.startswith("{"):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise ProtocolError("响应不是合法 JSON") from None
        # SSE：按空行分事件，取 data: 负载
        messages = []
        for event in body.split("\n\n"):
            payload = []
            for line in event.splitlines():
                if line.startswith("data:"):
                    payload.append(line[5:].lstrip())
            if not payload:
                continue
            chunk = "\n".join(payload).strip()
            if not chunk:
                continue
            try:
                messages.append(json.loads(chunk))
            except json.JSONDecodeError:
                continue
        for msg in messages:
            if msg.get("id") == want_id:
                return msg
        if messages:
            return messages[-1]
        raise ProtocolError("响应中没有可解析的 JSON-RPC 消息")

    @staticmethod
    def _raise_on_error(msg: dict) -> None:
        if "error" in msg and msg["error"] is not None:
            err = msg["error"]
            raise ProtocolError(
                f"JSON-RPC 错误 {err.get('code')}：{err.get('message')}"
            )

    def initialize(self) -> dict:
        last_error = None
        for version in PROTOCOL_VERSIONS:
            payload = {
                "jsonrpc": "2.0",
                "id": self._next(),
                "method": "initialize",
                "params": {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                },
            }
            try:
                msg, _ = self._post(payload)
            except ProtocolError as exc:
                last_error = exc
                continue
            if msg is None:
                last_error = ProtocolError("initialize 返回空响应")
                continue
            if msg.get("error"):
                last_error = ProtocolError(
                    f"initialize 失败：{msg['error'].get('message')}"
                )
                continue
            self.protocol_version = (
                self.protocol_version
                or (msg.get("result") or {}).get("protocolVersion")
                or version
            )
            self._notify_initialized()
            return msg.get("result") or {}
        raise ProtocolError(f"initialize 未能完成：{last_error}")

    def _notify_initialized(self) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except (ProtocolError, TimeoutError):
            pass

    def list_tools(self) -> dict:
        msg, _ = self._post(
            {"jsonrpc": "2.0", "id": self._next(), "method": "tools/list"}
        )
        if msg is None:
            raise ProtocolError("tools/list 返回空响应")
        self._raise_on_error(msg)
        return msg.get("result") or {}

    def call_tool(self, name: str, arguments: dict) -> dict:
        msg, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if msg is None:
            raise ProtocolError("tools/call 返回空响应")
        self._raise_on_error(msg)
        result = msg.get("result") or {}
        if result.get("isError"):
            raise ProtocolError(f"工具 {name} 返回错误：{result}")
        return result


def unwrap(result: dict):
    """把 MCP content 数组尽量还原成结构化对象。"""
    content = result.get("content")
    if not isinstance(content, list):
        return result
    texts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except (json.JSONDecodeError, TypeError):
            return texts[0]
    if texts:
        return texts
    return result


def dump(obj) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _query(args):
    return getattr(args, "query", None) or getattr(args, "product_query", None)


def build_arguments(tool_name: str, args) -> dict:
    if getattr(args, "args", None):
        try:
            extra = json.loads(args.args)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"--args 不是合法 JSON：{exc}") from None
        if not isinstance(extra, dict):
            raise ConfigError("--args 必须是 JSON 对象")
        return extra

    g = lambda name: getattr(args, name, None)
    query = _query(args)
    if tool_name == "product_search_pro":
        mapping = {
            "product_query": query,
            "brand_name": g("brand"),
            "category_name": g("category"),
            "min_price": g("price_min"),
            "max_price": g("price_max"),
            "mall_id": g("mall"),
            "size": g("limit"),
        }
    elif tool_name == "universal_content_search":
        mapping = {
            "query": query,
            "time_range": g("time_range"),
            "recall_num": g("limit"),
            "search_type": g("search_type"),
        }
    elif tool_name == "discount_search":
        mapping = {
            "product_query": query,
            "size": g("limit"),
        }
    else:  # image_search
        mapping = {
            "img_url": g("img_url") or g("image_url"),
            "is_auto_first_cate_name": 1 if g("auto_cate") else 0,
        }
    return {k: v for k, v in mapping.items() if v is not None}


REQUIRED_DEFAULTS = {
    # discount_search 的 question_id 为空时会返回 data:null；给非空会话 id。
    "product_search_pro": {"request_from": "mcp", "question_id": "mcp-cli"},
    "discount_search": {"request_from": "mcp", "question_id": "mcp-cli"},
}


def fill_defaults(tool_name: str, arguments: dict) -> dict:
    merged = dict(arguments)
    for key, value in REQUIRED_DEFAULTS.get(tool_name, {}).items():
        merged.setdefault(key, value)
    return merged


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="haina_mcp.py",
        description="值得买 MCP streamable-HTTP 命令行封装（stdlib 实现）",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="指定 .env 路径；默认从脚本位置向上查找仓库根 .env",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次请求超时秒数"
    )
    parser.add_argument("--raw", action="store_true", help="输出原始 MCP result 结构")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="调用 tools/list，列出可用工具")
    sub.add_parser("tools-list", help="同 list（别名）")
    sub.add_parser("ping", help="initialize 并输出服务端信息")

    def add_common(p):
        p.add_argument("--args", default=None, help="直接传 tools/call arguments 的 JSON 对象")
        p.add_argument("--query", default=None, help="检索关键词（商品/内容）")

    p = sub.add_parser("product-search", help="商品搜索 product_search_pro")
    add_common(p)
    p.add_argument("--brand", default=None, help="品牌名 brand_name")
    p.add_argument("--category", default=None, help="分类名 category_name")
    p.add_argument("--price-min", dest="price_min", type=float, default=None)
    p.add_argument("--price-max", dest="price_max", type=float, default=None)
    p.add_argument("--mall", default=None, help="商城 ID mall_id")
    p.add_argument("--limit", type=int, default=None, help="返回数量 size")

    p = sub.add_parser("content-search", help="网页/资讯检索 universal_content_search")
    add_common(p)
    p.add_argument(
        "--time-range",
        dest="time_range",
        default=None,
        choices=["OneDay", "OneWeek", "OneMonth", "OneYear", "TwoYear", "NoLimit"],
        help="时间范围，默认 TwoYear",
    )
    p.add_argument("--search-type", dest="search_type", default=None, choices=["web", "image", "video"])
    p.add_argument("--limit", type=int, default=None, help="返回条数 recall_num")

    p = sub.add_parser("discount", help="好价折扣 discount_search")
    add_common(p)
    p.add_argument("--limit", type=int, default=None, help="返回数量 size")

    p = sub.add_parser("image-search", help="图片检索 image_search")
    add_common(p)
    p.add_argument("--img-url", dest="img_url", default=None, help="图片 URL")
    p.add_argument("--image-url", dest="image_url", default=None, help="图片 URL（别名）")
    p.add_argument(
        "--auto-cate",
        dest="auto_cate",
        action="store_true",
        help="开启识别分类（is_auto_first_cate_name=1）",
    )

    alias_map = {
        "product_search_pro": "product-search",
        "universal_content_search": "content-search",
        "discount_search": "discount",
        "image_search": "image-search",
    }
    for alias, base in alias_map.items():
        p = sub.add_parser(alias, help=f"同 {base}（tools/call {alias}）")
        add_common(p)

    return parser


def main(argv=None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    try:
        endpoint, api_key, _used = load_config(args.env_file)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG

    client = HainaMCP(endpoint, api_key, timeout=args.timeout)
    try:
        client.initialize()
        if args.command in ("list", "tools-list"):
            dump(client.list_tools())
            return 0
        if args.command == "ping":
            dump(
                {
                    "endpoint": endpoint,
                    "session_id": bool(client.session_id),
                    "protocol_version": client.protocol_version,
                }
            )
            return 0
        tool_name = TOOL_ALIASES[args.command]
        arguments = build_arguments(tool_name, args)
        if not arguments:
            print(
                f"缺少参数：{args.command} 需要 --query 或 --args",
                file=sys.stderr,
            )
            return EXIT_USAGE
        filled = fill_defaults(tool_name, arguments)
        result = client.call_tool(tool_name, filled)
        dump(result if args.raw else unwrap(result))
        return 0
    except TimeoutError as exc:
        print(f"超时：{exc}", file=sys.stderr)
        return EXIT_TIMEOUT
    except ProtocolError as exc:
        print(f"协议/HTTP 错误：{exc}", file=sys.stderr)
        return EXIT_PROTOCOL
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
