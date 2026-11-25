# 个护有据 · care-evidence

覆盖护肤 / 洗护 / 口腔等日用个护全品类的产品浏览站。把公开证据和购买线索整理成一张能筛、能搜的表，**不下单、不代付款，也不替代医生诊断**。

站点是纯静态的：数据在 git 里，GitHub Actions 构建后发布到 GitHub Pages。

- **浏览站**：`https://<你的账号>.github.io/care-evidence/`（首次发布后可用）
- **站点源码与构建说明**：`site/README.md`
- **产品更新流程**（改哪个文件、怎么提、多久上线、怎么复核）：`docs/update-flow.md`
- **首次发布 + 推送步骤**：`docs/publish-runbook.md`
- **站名怎么改**：`docs/site-name.md`
- **核验工具说明**：`tools/README.md`

## 仓库结构

```
data/products.json       # 476 条产品数据（站点唯一数据源）
data/products.jsonl      # 同上，逐行 JSON，给核验工具用
site/                    # 零依赖 Python 生成器 + 模板 + 配置
  build.py               # 构建：data + src → site/dist/
  verify.py              # 抽查产物与数据一致性
  config.json            # 站名等集中配置
  src/                   # 样式与交互（原生 JS）
tools/                   # 购买链核验 / MCP 检索封装（可选复核手段）
.github/workflows/       # Pages 部署工作流
docs/                    # 更新流程、发布 runbook、站名说明
```

## 本地构建与预览

```bash
python3 site/build.py                       # 用 data/products.json 生成 site/dist/
python3 -m http.server -d site/dist 8000    # 打开 http://localhost:8000/
python3 site/verify.py                      # 抽查详情页与数据一致性
```

只依赖 Python3 标准库，不需要 `pip install`。

## 更新产品数据

改 `data/products.json`，提交并合入 `main`，Actions 会自动重建发布。完整四问见 `docs/update-flow.md`。

## 发布

见 `docs/publish-runbook.md`。推送、建仓库、开 Pages 由你（用户）完成；本仓库只备好内容。

## 维护者：这个仓库是怎么装配出来的

已发布的 care-evidence 仓库由 studio 工作区用脚本装配，内容可复现：

```bash
bash deploy/assemble.sh    # 在 studio 工作区根执行，产物在 deploy/care-evidence/
```

它把 `site/data/products.json` 拷到根 `data/`（并生成 `.jsonl`），连同 `site/` 源码、`.github/workflows/pages.yml`、`docs/`、`tools/`、本 README 与 `.gitignore` 一起装配成一个干净、无讨论包、无 `.env` 的仓库。装配后即可按 `docs/publish-runbook.md` 推送。

