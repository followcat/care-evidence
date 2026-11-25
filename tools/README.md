# tools/ — 产品检索与购买链核验工具

本目录是「个护有据」的检索/核验工具链，只做小样本冒烟，不做全表核验（全表属 t3）。

| 文件 | 作用 |
|---|---|
| `haina_mcp.py` | 值得买 MCP（streamable-HTTP）命令行/可导入封装，覆盖 4 个工具 |
| `check_links.py` | 购买链可达性检查器（限速/重试/断点续跑/反爬标记） |
| `smoke/` | 真实冒烟证据：`mcp-tools-list.json`、`mcp-search-sample.json`、`link-smoke.jsonl` |

只依赖 Python3 标准库（`urllib`/`json`/`concurrent.futures` 等），不需要 `pip install`，因此不附 `requirements.txt`。

---

## 1. 环境准备与密钥注入

两个变量，**只从运行时读取，绝不写入任何被提交的文件**：

| 变量 | 含义 |
|---|---|
| `HAINA_MCP_HTTP` | MCP streamable-HTTP 端点 |
| `HAINA_MCP_KEY` | 鉴权头 `x-api-key` 的值 |

读取顺序：

1. 进程环境变量 `HAINA_MCP_HTTP` / `HAINA_MCP_KEY`；
2. 否则从脚本位置**向上查找仓库根 `.env`**（默认静默发现）；
3. 或用 `--env-file <path>` 显式指定 `.env`。

`.env` 已被 `.gitignore` 忽略，不进版本库。脚本内无任何硬编码密钥；缺少配置时以退出码 `2` 明确报错（不带出密钥值）。

```bash
# 方式 A：环境变量（CI/临时会话）
export HAINA_MCP_HTTP="https://.../mcp"
export HAINA_MCP_KEY="<key>"

# 方式 B：仓库根 .env（本地默认）
# .env 内容示例（不要提交）：
#   HAINA_MCP_HTTP=https://.../mcp
#   HAINA_MCP_KEY=xxxxx
```

出口网络走当前环境已配置的 `HTTP(S)_PROXY`（`urllib` 默认读取该变量），实测经代理可连通 MCP 与大部分购买链。

---

## 2. `haina_mcp.py` 用法

实现 MCP `initialize` → `tools/list` → `tools/call` 流程，处理 `mcp-session-id` 会话头，输出结构化 JSON。

```bash
# 列出工具（tools/list）
python3 tools/haina_mcp.py list

# 商品搜索（product_search_pro）：可按品牌/类目/价格/商城过滤
python3 tools/haina_mcp.py product-search --query "适乐肤 CeraVe 保湿洁面乳" \
    --brand "CeraVe/适乐肤" --price-min 20 --price-max 300 --mall 247 --limit 10

# 网页/资讯检索（universal_content_search）：支持时间范围
python3 tools/haina_mcp.py content-search --query "薇姿 Minéral 89 成分" \
    --time-range OneYear --limit 5

# 好价折扣（discount_search）：在售与价格信号
python3 tools/haina_mcp.py discount --query "防晒霜" --limit 10

# 图搜（image_search）
python3 tools/haina_mcp.py image-search --img-url "https://example.com/a.jpg" --auto-cate

# 也可直接传 tools/call arguments JSON（原样转发，适合新参数）
python3 tools/haina_mcp.py product-search --args '{"product_query":"面膜","size":5}'

# 显式指定 .env / 调整超时 / 查看原始 MCP 结构（全局参数须放在子命令前）
python3 tools/haina_mcp.py --env-file /path/to/.env --timeout 60 --raw list
```

工具名 → 子命令：`product-search`=`product_search_pro`，`content-search`=`universal_content_search`，`discount`=`discount_search`，`image-search`=`image_search`（也可直接用工具名作子命令）。

退出码：`0` 成功；`2` 配置缺失；`3`/`4` HTTP 或协议错误；`5` 超时；`6` 参数不足。

### 已知 MCP 参数坑

- `discount_search` 的 `question_id` 若为空字符串会返回 `data:null`；本封装默认填非空会话 id，可直接使用。
- `product_search_pro` 的品牌/类目/价格/商城字段名分别为 `brand_name`/`category_name`/`min_price`,`max_price`/`mall_id`。

---

## 3. `check_links.py` 用法

```bash
# 从自定义 JSONL 输入（每行 {"id","url","field"}）
python3 tools/check_links.py \
    --input links.jsonl \
    --output tools/smoke/link-smoke.jsonl \
    --domain-interval 2.0 --concurrency 4 --timeout 20 --retries 2

# 直接从 products.jsonl 抽取全部购买链（buyHref/jdHref/tmallHref/channels[].href，按 URL 去重）
python3 tools/check_links.py \
    --from-products skincare-discussion-pack-2026-11-24/data/products.jsonl \
    --output verification/links.jsonl

# 只抽取不请求；或忽略已有输出全部重查
python3 tools/check_links.py --from-products ... --extract-only
python3 tools/check_links.py --input links.jsonl --output out.jsonl --no-resume
```

参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` / `--from-products` | 二选一必填 | 输入 JSONL 或 products.jsonl |
| `--output` | 必填 | 输出 JSONL（默认可续跑追加；`--no-resume` 覆盖写） |
| `--domain-interval` | `2.0` | 同域名最小间隔秒数（≤1 次/2 秒/域名） |
| `--concurrency` | `4` | 全局并发上限 |
| `--timeout` | `20.0` | 单请求连接/读取超时秒数 |
| `--total-timeout` | `0`（不限） | 整批总预算秒数，超时条目记 `unknown` |
| `--retries` | `2` | 重试次数上限 |
| `--user-agent` | 常见 Chrome UA | 请求 UA |
| `--limit` | `0`（全部） | 只处理前 N 条 |
| `--no-resume` | 关 | 忽略已有输出全部重查 |
| `--extract-only` | 关 | 只打印抽取结果不发请求 |

输出字段（每 URL 一条）：

```json
{"url","final_url","http_status","redirect_chain","latency_ms",
 "markers":[],"verdict","error","checked_at","id","field"}
```

- `redirect_chain`：完整跳转链 `[{"status":302,"url":"..."}]`。
- `markers`：`http-403`/`http-429`、`challenge-page`、`login-wall`、`js-redirect-shell`、`tiny-body`、`retry-N@Xs`、`timeout`、`dns-error`、`tls-error`、`conn-error`、`retry-after`、`total-timeout-skip`。
- **断点续跑**：启动时读已有 `--output`，URL 在则跳过（`--no-resume` 关闭）。

重试/退避：对 `429/5xx/403` 及连接/超时错误做指数退避（`2s,4s,…` 上限 30s），命中 `Retry-After` 则优先按其值等待。

---

## 4. 判定规则（`judge()`，README 与代码一致）

三层判定，**HTTP 200 不等于可达**（已实测 `mall.jd.com` 200 但落到 `error.aspx`；`tmall.com` 200 但落到 `noshop.htm`；`s.click.taobao.com` 200 但正文是 JS 跳转壳）。按优先级：

| 优先级 | 条件 | verdict |
|---|---|---|
| 1 | 连接/DNS/TLS 失败（`error` 且 `markers` 含 `conn-error`/`dns-error`/`tls-error` 任一，重试标记可并存） | `domain-error` |
| 2 | 最终 URL 命中登录/风控名单（`login.`、`passport.`、`pass.tmall.com`、`pc-frequent-pro`、`punish` 等） | `blocked` |
| 3 | 小页面（≤40KB）正文含验证码/滑块/人机验证/频繁访问等特征 → `challenge-page`；或含「请登录」→ `login-wall` | `blocked` |
| 4 | HTTP 401/403/407/429/503 | `blocked` |
| 5 | 最终 URL 命中 `error.aspx`/`noshop`/`404` 等，或正文含「商品不存在/已下架/页面不存在」 | `dead` |
| 6 | HTTP 404/410/451 | `dead` |
| 7 | 跳转壳域名（`s.click.taobao.com`/`union-click.jd.com`/`u.jd.com`）且（正文含 `real_jump_address`/`京东网上商城` 或正文 <600B） | `unknown` |
| 8 | 2xx 且正文 ≥600B 且含在售标记（加入购物车/¥/价格/商品详情…） | `onsale` |
| 9 | 其他 | `unknown` |

标记语义：

- `onsale`：可达且有在售迹象。
- `dead`：可达但失效/下架（含 200 假阳性落到 error/noshop 的情况）。
- `blocked`：反爬/登录墙，**待人工核**（不是不可达）。
- `domain-error`：域名/DNS/TLS/连接异常。
- `unknown`：跳转壳、正文不足或无在售特征，无法判定。

> 反爬特征只在“小页面”里认定，避免把正常大站脚本里的 `recaptcha` 或导航「请登录」误判成 blocked。

---

## 5. 已知限制

- 不执行 JS：`s.click.taobao.com`/`union-click.jd.com` 这类跳转壳只能记 `unknown`，需人工点开核验。
- 不绕登录墙/验证码：命中即 `blocked`，不做绕过。
- 部分海外品牌站对数据中心 IP 返回 403（如 `laroche-posay.us`、`vichyusa.com`），记 `blocked` 而非不可达。
- 代理为出口；直连可能失败。MCP 与链接检查均走环境已有的 `HTTP(S)_PROXY`。
- 时间戳为 UTC（`checked_at`），与限速无关；限速只约束同域名的请求发起间隔。

---

## 6. 冒烟证据（`tools/smoke/`）

- `mcp-tools-list.json`：真实 `tools/list` 输出，含 `product_search_pro`/`universal_content_search`/`discount_search`/`image_search`。
- `mcp-search-sample.json`：四个工具各 1 次真实返回（`product_search_pro` 适乐肤 CeraVe 保湿洁面乳、`discount_search` 防晒霜、`universal_content_search` 薇姿 Minéral 89 成分、`image_search` 用商品主图），密钥字段已脱敏。
- `link-smoke.jsonl`：≥10 条真实检查记录，覆盖 `item.jd.com`/`item.m.jd.com`、`s.click.taobao.com`/`uland.taobao.com`、`www.jd.com`/`mall.jd.com`、`www.smzdm.com`、品牌官网/跨境站。
