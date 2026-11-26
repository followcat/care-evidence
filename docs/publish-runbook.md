# 发布 runbook：把 care-evidence 推上 GitHub 并开 Pages

这份文档是**给你（用户）照着一步步做**的。studio 只负责把 `deploy/care-evidence/` 装配、构建、验证并做好**本地 git 提交**；**studio 不建仓库、不推送、不开 Pages**。

> 前置：这台机器上已完成 GitHub CLI 登录（或你打算用网页操作）。不要把 token 贴进任何文件。
>
> 代理说明：本机代理可能截断 `api.github.com` 的 POST。本文所有 GitHub/git 网络命令都用 `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy` 逐条置空代理；每条都可单独复制执行。

---

## 0. 确认登录状态

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh auth status
```

- 显示已登录账号 → 继续。
- 未登录或 token 失效 → 先自己执行：

  ```bash
  env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
    gh auth login
  ```

  登录完再重跑上面的状态检查。在登录通过前，不要执行建库、推送或 Pages 操作。

---

## 1. 装配与本地准备（可复跑）

在 studio 工作区根执行：

```bash
bash deploy/prepare-local-repo.sh
```

它会依次完成：

1. 装配最新 `deploy/care-evidence/`；若目录已有 `.git`，保留本地 git 历史；
2. 校验数据为 476 条、id 唯一，且与 `site/data/products.json` 完全一致；
3. 确认装配内容不含 `.env`、zip 文件或原始讨论包目录/文件；
4. 在装配目录内运行 `python3 site/build.py` 与 `python3 site/verify.py`；
5. 默认用只读 `git fetch` 获取公开仓库当前 `main` 作为父级，初始化或更新 `deploy/care-evidence/.git` 的 `main` 分支本地提交；**不配置 remote、不 push**；
6. 输出明确的 `PASS` / `FAIL` 和关键计数。

重跑同一脚本不会丢失 `.git`；内容没有变化时不会制造空提交。脚本不会修改 git 配置；如果本机缺少提交身份，它会明确失败并提示你先配置身份或设置一次性身份环境变量。

---

## 2. 推送前快速核对

```bash
cd deploy/care-evidence
git status --porcelain
git log --oneline -3
```

预期：`git status --porcelain` 无输出；`git log` 能看到脚本准备好的本地提交。若脚本读取过远程基线，远程 `main` 应是本地历史的祖先，因此推送通常是 fast-forward。

可选核对禁入文件：

```bash
git ls-files | grep -E '(^|/)\.env($|\.)|\.zip$|skincare-discussion-pack'
```

预期无输出。

---

## 3. 建公开仓库并推送

### 3.1 仓库还不存在：最短主路径

在 `deploy/care-evidence/` 内执行：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh repo create care-evidence --public --source=. --remote=origin --push
```

预期：GitHub 上创建公开仓库 `care-evidence`，并把本地 `main` 推送上去。

### 3.2 仓库已经存在

先确认远程仓库确实是你要用的目标仓库：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh repo view <你的账号>/care-evidence
```

在 `deploy/care-evidence/` 内检查 remote：

```bash
git remote -v
```

若没有 `origin`：

```bash
git remote add origin https://github.com/<你的账号>/care-evidence.git
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  git push -u origin main
```

若已有 `origin` 且地址正确：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  git push -u origin main
```

---

## 4. 把 Pages 来源设为 GitHub Actions

工作流使用官方 `actions/deploy-pages`，必须把 Pages 源设成 **GitHub Actions**。

网页操作：仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**。

命令行操作（把 `<你的账号>` 换成实际账号）：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh api -X POST repos/<你的账号>/care-evidence/pages -f build_type=workflow
```

若返回 409「already enabled」，说明 Pages 已开启；检查当前来源：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh api repos/<你的账号>/care-evidence/pages --jq '.build_type'
```

预期输出：

```text
workflow
```

如果不是 `workflow`，到仓库 Settings → Pages，把 Source 改成 **GitHub Actions**；或用更新接口修正：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh api -X PUT repos/<你的账号>/care-evidence/pages -f build_type=workflow
```

---

## 5. 查看或重跑 Actions

推送 `main` 会触发首次部署。查看运行：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh run list --repo <你的账号>/care-evidence --workflow=pages.yml --limit 3
```

如需手动触发：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh workflow run pages.yml --repo <你的账号>/care-evidence
```

如需重跑某个失败 run：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  gh run rerun --repo <你的账号>/care-evidence <run-id>
```

跑绿后访问：

```text
https://<你的账号>.github.io/care-evidence/
```

---

## 6. 如果 push 被拒绝为 non-fast-forward

看到 `non-fast-forward` 或 `fetch first` 时，**不要强推**。先做只读检查：

```bash
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
  git fetch origin main
git log --oneline --graph --left-right main...origin/main
```

安全处理顺序：

1. 如果输出显示本地 `main` 已包含远程提交，只是 remote-tracking 信息旧了，重新执行第 3.2 节的代理置空 push。
2. 如果远程只有少量新提交、本地落后但可快进，执行：

   ```bash
   git merge --ff-only origin/main
   env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
     git push -u origin main
   ```

3. 如果两侧分叉或历史无关，停下来人工确认远程内容。不要 `--force`；可以选择改用一个新的空仓库，或先备份/复制远程内容后再做人工合并。未弄清楚前不要继续推。

---

## 7. 首次发布后自查

- 首屏能先选用途（日常 / 治疗·创面）、再选品类，列表能用搜索过滤。
- 任意详情页打开正常，购买链标「仅供核验」，缺链写「未知／待核」。
- 改一条 `data/products.json` 里的字段 → 提交 → 合入 `main` → 等 Actions 自动重建，页面随之更新（完整流程见 `docs/update-flow.md`）。

---

## 卡住了怎么办

- 登录状态检查不通：先完成第 0 步登录，不要寻找或复制 token。
- 建库命令说仓库已存在：回到第 3.2 节。
- Pages 部署报「Get Pages site failed」：多半是第 4 步没做，先把 Pages 源设为 GitHub Actions，再重跑 workflow。
- 首次 workflow 失败：先找失败 run：

  ```bash
  env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
    gh run list --repo <你的账号>/care-evidence --workflow=pages.yml --limit 3
  ```

  再查看日志：

  ```bash
  env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
    gh run view --repo <你的账号>/care-evidence <run-id> --log
  ```

  若失败原因是 Pages 未启用，按第 4 步处理后重跑：

  ```bash
  env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
    gh run rerun --repo <你的账号>/care-evidence <run-id>
  ```

  或重新触发：

  ```bash
  env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy \
    gh workflow run pages.yml --repo <你的账号>/care-evidence
  ```

- 站点 404：确认最近一次 Actions run 成功，且 Pages 源检查输出为 `workflow`。
- 需要改名：只改 `site/config.json` 的 `siteName`，见 `docs/site-name.md`。
