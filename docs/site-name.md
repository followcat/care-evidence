# 站名占位说明

站名只有一个开关：**`site/config.json` 里的 `siteName`**。当前填的是「个护有据」（repo 名 `care-evidence`）。

构建时 `site/build.py` 把这个值注入全站——首页标题、页头品牌、详情页标题、README 计数说明都读它。所以**改一处，全站生效**，别去 `dist/` 或模板里逐处改。

## 换成最终项目名

1. 改 `site/config.json`：

   ```json
   {
     "siteName": "最终项目名",
     "repoName": "care-evidence",
     ...
   }
   ```

2. 重新构建：

   ```bash
   python3 site/build.py
   ```

3. 想连 repo 名一起换，同时改 `repoName` 和 `site/build.py` 里的相对路径约定（项目页前缀 `/care-evidence/`），以及 `.github/workflows/pages.yml` 不用动（它只负责构建和发布，不关心站名）。

> `siteName` 与 `repoName` 分开：前者是页面上显示的站名，后者是 GitHub 仓库名（决定项目页 URL 前缀 `/<repoName>/`）。改名只动 `siteName` 即可。
