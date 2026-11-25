# 发布 runbook：把 care-evidence 推上 GitHub 并开 Pages

这份文档是**给你（用户）照着一步步做**的。仓库内容已由 studio 备好（见 `deploy/assemble.sh` 生成的 `deploy/care-evidence/`）。

**studio 不建仓库、不推送、不开 Pages**——这些是你的动作。studio 只把内容装配好、把命令写清。

> 前置：这台机器上已 `gh auth login`（或你打算用网页操作）。studio 不会替你找凭据、不会代推。

---

## 0. 先确认登录状态（必须先做）

```bash
gh auth status
```

- **通过**（显示已登录账号）→ 继续第 1 步。
- **不通过**（未登录 / token 失效）→ **停在这里**，先自己执行：

  ```bash
  gh auth login
  ```

  登录完再回来重跑 `gh auth status`。**在登录通过前，下面任何 `gh repo create` / `git push` / 开 Pages 都不要做**，也不要把 token 贴进任何文件。

---

## 1. 装配待推送内容（studio 侧已可复现）

在 studio 工作区根执行：

```bash
bash deploy/assemble.sh
```

产物是 `deploy/care-evidence/`：`data/`（476 条 + jsonl）、`site/`（源码与构建）、`.github/workflows/pages.yml`、`docs/`、`tools/`、`README.md`、`.gitignore`。**不含**讨论包（`skincare-discussion-pack-2026-11-24/` 只读、不公开）与任何 `.env`。

---

## 2. 建仓库并推送

```bash
cd deploy/care-evidence
git init -b main
git add -A
git commit -m "chore: 个护有据浏览站 + Pages 工作流"
gh repo create care-evidence --public --source=. --remote=origin --push
```

`gh repo create` 会用你本机已登录的凭据建公开仓库 `care-evidence` 并把 `main` 推上去。若你更习惯网页：在 GitHub 新建空仓库 `care-evidence`，再

```bash
git remote add origin https://github.com/<你的账号>/care-evidence.git
git push -u origin main
```

推送前快速核对：`git status --porcelain` 应为空；`git ls-files | grep -E "\.env|\.zip|skincare-discussion-pack"` 应无输出。

---

## 3. 把 Pages 来源设为 GitHub Actions

工作流用官方 `actions/deploy-pages`，**必须**把 Pages 源设成 GitHub Actions，否则部署会失败。

网页：仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**。

或命令行（需已登录）：

```bash
gh api -X POST repos/<你的账号>/care-evidence/pages -f build_type=workflow
```

> 若返回 409「already enabled」，说明已开过，可忽略，继续第 4 步。

---

## 4. 触发首次部署并访问

推送 `main` 已触发工作流；也可手动重跑：

```bash
gh workflow run pages.yml
gh run list --workflow=pages.yml --limit 3   # 看最近一次是否成功
```

跑绿后访问 `https://<你的账号>.github.io/care-evidence/`。

---

## 5. 首次发布后自查

- 首屏能先选用途（日常 / 治疗·创面）、再选品类，列表能用搜索过滤。
- 任意详情页打开正常，购买链标「仅供核验」，缺链写「未知／待核」。
- 改一条 `data/products.json` 里的字段 → 提交 → 合入 `main` → 等 Actions 自动重建，页面随之更新（完整流程见 `docs/update-flow.md`）。

---

## 卡住了怎么办

- `gh auth status` 不通：见第 0 步，先登录，不要找别的凭据。
- Pages 部署报「Get Pages site failed」：多半是第 3 步没做（源没设成 GitHub Actions）。
- 站点 404：确认 `gh run` 最近一次是成功，且 Pages 源已设为 Actions。
- 需要改名：只改 `site/config.json` 的 `siteName`，见 `docs/site-name.md`。
