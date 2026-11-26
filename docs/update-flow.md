# 产品更新流程：改数据 → 提 PR → 自动上线

这份文档回答四件事：**改哪个文件、怎么提、多久上线、怎么复核**，最后一节是**首次发布清单**。

站点是纯静态的：数据在 git 里，构建在 Actions 里跑，产物发布到 GitHub Pages。没有服务器，也不需要数据库。

---

## 1. 改哪个文件

产品数据只有一份：**`data/products.json`**（476 条，全表）。

在已发布的仓库里它是根目录的 `data/products.json`；studio 工作区里对应 `site/data/products.json`（`deploy/assemble.sh` 装配时拷到根 `data/`）。`site/build.py` 两处都会找，先看根 `data/` 再看 `site/data/`。

它的上游是讨论包里的 `products.json`。讨论包只读、不公开，发布仓库里没有它。两条更新路径：

```bash
# 路径 A：studio 工作区里，讨论包有了新快照，整表重新拷贝再构建
python3 site/build.py --refresh-data

# 路径 B：日常改字段，直接编辑 data/products.json，然后构建
python3 site/build.py
```

`site/build.py` 会校验条数必须为 476 且 id 唯一，否则直接失败退出，不会产出一份坏站点。构建产物在 `site/dist/`，**不要手动编辑 `dist/`**，它每次构建都会整体重建。

### 单条产品改动示例

比如给 `sr-revox-line` 补一个天猫购买链：

1. 打开 `data/products.json`，找到 `"id": "sr-revox-line"` 这条；
2. 改字段（示例：填 `buy.tmallHref`、`buy.tmallLabel`，并把 `buy.has_tmall` 改成 `true`）：

   ```json
   "buy": {
     "tmallHref": "https://detail.tmall.com/item.htm?id=xxxx",
     "tmallLabel": "天猫",
     "has_tmall": true,
     ...
   }
   ```

3. 本地构建一次，确认没报错：

   ```bash
   python3 site/build.py
   ```

4. 提交并开 PR（见下一节）。

字段以 `data/products.json` 里已有的键为准（结构说明见 `site/README.md` 与讨论包 schema，讨论包本身不公开）；不要自造字段名。不确定的值写「未知／待核」，不要编。

**不要改的东西**：密钥和 `.env` 不进仓库；`site/dist/` 是构建产物，不手改；任何看起来像官方、实际搜不到的链接不要填。

---

## 2. 怎么提

用分支 + PR，不直接推 `main`：

```bash
git checkout -b data/fix-tmall-links
# 改 data/products.json
python3 site/build.py            # 本地先构建一次，确认能过
git add data/products.json
git commit -m "data: 补齐 3 条天猫购买链"
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  git push -u origin data/fix-tmall-links
```

然后在 GitHub 上开 PR 指向 `main`。合并方式用 Squash 或普通 Merge 都行，关键是**最终落到 `main`**——Pages 工作流只监听 `main`（见第 3 节）。

### commit message 约定

前缀说明改的是哪一类内容，冒号后用一句话说清做了什么：

| 前缀 | 用途 | 例子 |
|---|---|---|
| `data:` | 产品数据字段 | `data: 修正 sr-vichy-89 的参考价` |
| `site:` | 页面模板、样式、交互 | `site: 窄屏下工具栏竖排` |
| `docs:` | 流程和说明文档 | `docs: 补充首次发布清单` |
| `tools:` | 核验工具 | `tools: check_links 增加重试上限` |
| `fix:` | 修 bug | `fix: 详情页购买链重复渲染` |

一次 PR 只做一件事，标题就是 commit 的那句话。PR 描述里写清改了哪几条、依据是什么（比如「按 2026-11-20 快照补链」）。

---

## 3. 多久上线

`main` 一有推送，Actions 自动跑（`.github/workflows/pages.yml`）：

```
push 到 main
  → checkout
  → python3 site/build.py        （生成 site/dist/）
  → actions/upload-pages-artifact（打包产物）
  → actions/deploy-pages          （发布到 Pages）
  → 站点可访问
```

- 工作流用官方 `actions/configure-pages`、`actions/upload-pages-artifact`、`actions/deploy-pages`，权限为 `pages: write` 与 `id-token: write`，并发组 `pages` 且新推送取消旧任务。
- PR **合入 `main` 之前**站点不会更新；合入并推送后，Actions 会自己构建发布，一般几分钟内完成，看 Actions 页面那次 run 变绿即可。
- 想手动重发：Actions 页面选这个工作流点 **Run workflow**（`workflow_dispatch`），不必改代码。
- 部署分支默认 `main`，要换分支时改工作流 `on.push.branches`，或按仓库实际情况调整。

---

## 4. 怎么复核

改动条目至少做本地复核。核验工具来自 t2，用法与 `tools/README.md` 一致，命令可直接照抄。

### 4.1 栏目与字段一致性

```bash
python3 site/verify.py
```

抽查代表性条目，比对详情页渲染文本与 `data/products.json` 的 E/S、P 档、D 层、购买链，并确认 476 个详情页齐全。（studio 工作区里若存在讨论包，还会额外核对站点数据与包内数据一致。）

### 4.2 购买链可达性

```bash
# 从全表抽取所有购买链并按 URL 去重（data/products.jsonl 由装配或构建时生成）
python3 tools/check_links.py \
    --from-products data/products.jsonl \
    --output verification/links.jsonl

# 或者只查你改过的那几条：自己写一个 JSONL（每行 {"id","url","field"}）
python3 tools/check_links.py \
    --input my-links.jsonl \
    --output verification/my-links.jsonl \
    --domain-interval 2.0 --concurrency 4 --timeout 20 --retries 2
```

判定规则见 `tools/README.md` 第 4 节：`onsale` 可达有在售迹象，`dead` 失效下架，`blocked` 反爬或登录墙（记「待人工核」，不是不可达），`domain-error` 域名/连接异常，`unknown` 跳转壳或无法判定。**HTTP 200 不等于可达**，只看 `verdict`。

`verification/` 里的输出是本地产物，按需忽略或不提交，别把大文件塞进 PR。

### 4.3 可选：在 CI 里跑复核（默认关闭）

下面是一个**手动触发**的可选 job，默认不会跑。它只跑 `check_links.py`，不需要密钥。若要同时跑 MCP 交叉验证（需要 `HAINA_MCP_HTTP` / `HAINA_MCP_KEY`），一律用 GitHub Secrets 引用，**不要写死在文件里**。

```yaml
# .github/workflows/verify-links.yml（可选，手动触发）
name: Verify buy links (optional)
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Check links
        run: |
          python3 tools/check_links.py \
            --from-products data/products.jsonl \
            --output verification/links.jsonl \
            --limit 50
      - name: Upload result
        uses: actions/upload-artifact@v4
        with:
          name: link-verification
          path: verification/links.jsonl
```

> 若要接 MCP 交叉验证，在仓库 Secrets 里配 `HAINA_MCP_HTTP`、`HAINA_MCP_KEY`，工作流里用 `${{ secrets.HAINA_MCP_KEY }}` 注入环境变量；密钥值只在 Secrets 里，不进任何提交文件。

### 4.4 和 t3 核验结果衔接（后续增强，本轮不阻塞）

t3 在 `verification/` 里产出的购买链可达性结果（`verdict` 字段等）可作为站点数据的增强来源：比如给每条购买链加一个「核验状态」字段，在详情页显示「最近核验：可达／待人工核／失效」。这需要在数据里加可选字段并改详情页模板，属后续迭代；本轮只把接口留在这里，不强行并入。

---

## 5. 首次发布清单（用户侧操作）

这一步需要你自己在 GitHub 上做；studio 不建仓库、不推送、不开 Pages。完整的命令级步骤见 **`docs/publish-runbook.md`**，这里给出概览。前提是 GitHub CLI 登录状态已通过（或已登录网页）。所有 GitHub/git 网络命令都要按 runbook 统一加 `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy` 代理置空前缀。

1. **装配内容**：`bash deploy/prepare-local-repo.sh` 生成并验证 `deploy/care-evidence/`，同时准备好 `main` 分支本地提交。
2. **建仓库并推送**：进入 `deploy/care-evidence/` 后，按 `docs/publish-runbook.md` 第 3 节执行带代理置空前缀的建库或 push 命令。
3. **设 Pages 来源**：仓库 Settings → Pages → Source 选 **GitHub Actions**（不是「Deploy from a branch」）。这一步不设，Actions 部署会失败。
4. **回填站名**：站名集中在 `site/config.json` 的 `siteName` 一处（当前为「个护有据」）。要改名只改这一处，重新构建即全站生效——详见 `docs/site-name.md`。
5. **触发首次部署**：推送 `main` 后 Actions 自动跑；或到 Actions 页面手动 Run workflow。跑绿后访问 `https://<你的账号>.github.io/care-evidence/`。

站点所有资源都用相对路径，放在 `/care-evidence/` 这个项目页前缀下可直接打开，不用改路径。

> 第一次部署后如果 404：先确认 Pages 来源已设为 GitHub Actions，再确认那次 run 的 deploy 步骤是否成功。
