# 个护有据（care-evidence） · 静态浏览站

「个护有据」覆盖护肤 / 洗护 / 口腔等日用个护全品类，不只护肤品。把讨论包（`skincare-discussion-pack-2026-11-24/`，r44 快照，476 条）做成本地可直接浏览的纯静态站。没有后端，没有构建期外网依赖：只用 Python 标准库生成 HTML/CSS/JS，浏览器端用原生 JS 读一份 JSON 渲染列表。

页面只整理公开证据与购买线索，供核对；不下单、不代付款，也不替代医生诊断。

## 站名与仓库

- 站名 = **个护有据**，名称集中在 `site/config.json` 的 `siteName` 一处，构建时注入全站（页面标题、页头、详情页标题、README 计数说明）。
- repo 名 `care-evidence`，**推送时创建**（本任务不做推送，属后续越权动作）。
- 目标部署为项目页 `https://<user>.github.io/care-evidence/`，base path `/care-evidence/`。站内所有资源与链接一律用**相对路径**（`assets/…`、`data/…`、`p/<id>/…`），放在 `/care-evidence/` 前缀下可直接工作，无需改路径。

## 目录结构

```
site/
├── config.json          # 站名/仓库名/basePath 配置（siteName=个护有据）
├── build.py             # 零依赖生成器：data + src → dist
├── verify.py            # 抽查：dist 详情页字段与 site/data 是否一致
├── data/
│   └── products.json    # 站点数据源（从讨论包拷贝的 476 条）
├── src/
│   ├── style.css        # 样式（响应式）
│   └── app.js           # 列表页交互：用途/品类 → 搜索/筛选/排序
└── dist/                # 构建产物（可直接静态托管）
    ├── index.html       # 首屏：先用用途、再选品类，然后看条目
    ├── assets/          # style.css + app.js
    ├── data/            # products.json（页面读取）+ meta.json
    └── p/<id>/index.html# 每条产品一个详情页（476 个）
```

## 构建与本地预览

```bash
# 生成 dist/（首次会自动拷贝数据；已有数据时直接构建）
python3 site/build.py

# 从讨论包重新拷贝最新 products.json 再构建
python3 site/build.py --refresh-data

# 本地起服务后浏览
python3 -m http.server -d site/dist 8000
# 打开 http://localhost:8000/
```

> 列表页通过 `fetch('data/products.json')` 载入数据。请用上面的本地服务器打开；直接 `file://` 双击 HTML 时浏览器会拦截 `fetch`，列表会提示改用本地服务器。详情页是预生成静态 HTML，不依赖 JS。

## 数据从讨论包重新生成

站点数据源是 `site/data/products.json`，**拷贝**自：

```
skincare-discussion-pack-2026-11-24/data/products.json
```

讨论包只读，任何构建都不会改动包内原件。更新方式：

```bash
python3 site/build.py --refresh-data   # 重新从 pack 拷贝全表 476 条并重建 dist
```

构建会校验条数必须为 476 且 id 唯一，否则直接失败。`site/data/products.json` 与包内 `products.json` 逐字节一致；构建时再复制一份到 `site/dist/data/` 供页面读取。

## 已实现的交互（按 v5 阅读路径）

- **先选用途，再选品类**：首屏只有「日常 / 治疗／创面」两个用途；选用途后才出现 10 个品类 + 「全部品类」。不做跨品类总分默认排序。
- **列表字段**：品名、`legacy.E`（E 证据档）、`legacy.score`（S 旧评分）、`v5.p_status`（P 选购档，未评写「未完成实用评估」）、`v5.d_tier`（D 差异层）、role/缺点、`cites`（证据出处）、购买链（标注「仅供核验」，缺链写「未知／待核」）。
- **搜索**：品名 / id / 品牌 / 品类 / 活性物等关键词，实时过滤。
- **筛选**：证据档（旧门 rec/consider/weak/skip）、P 档（含「未完成实用评估」）。
- **排序**：默认「P 档 → E 档」（同品类内，P 档优先、再证据档）；另有 E 证据档、S 旧评分、品名。
- **分组**：「全部品类」视图按品类分组，品类之间不排名。
- **详情页**：四档 chips（E/S/P/D）+ 旧门判定 + 全字段明细（含 `cites`、`official` 备案线、`channel` 渠道）+ 购买线索。
- **大白话说明**：首屏一段解释 E（证据有多硬）/ P（日常值不值得选）/ D（有没有新信号）。
- **响应式**：窄屏（≈390px）下卡片单列、工具栏竖排，仍可读可用。

## 文案口径（B4）

- 说人话、短句；E/P/D 各有一句白话解释。
- 不用空泛的互联网行话，不作个性化适合断言，不用主观荐购口气，不写医疗处方口吻或任何疗效担保。
- 未评 P 一律写「未完成实用评估」，不当成差评，也不改名「优选」。
- 购买链统一标「仅供核验」，下单前须再核对包装、店铺身份与实时价。

快速自检（用验收清单第 4 条给出的 grep 命令，在 `site/dist site/src` 上跑无命中即通过）。

## 字段与数据一致性抽查

```bash
python3 site/verify.py
```

对已评 P、有 D 案例、有双链等代表性条目，比对详情页渲染文本与 `site/data/products.json` 的 E/S、p_status、d_tier、购买链，并确认 476 个详情页齐全、`site/data` 与包内数据一致。

## 已知限制

- **未接入 t3 核验结果**：购买链目前用讨论包自带已解析 URL，未逐条重新实测可达性；后续可由 t3 的核验结果并入数据更新流程。
- **P 层仅 30 款试点**，其余 446 条为「未完成实用评估」；页面如实展示，不做批量贴标签。
- **D 层仅 12 个精选案例**，不是全表差异化评估。
- 用户肤质未知，页面只写适用条件，不作个人适合断言。
- 本包购买链仍有缺口（缺京东 207、缺天猫 409、两侧都缺 163），页面缺链处写「未知／待核」。

## 部署

推送、建仓库、开 Pages 均由用户完成（本任务不含越权动作）。`site/dist/` 为纯静态产物，可直接部署到 GitHub Pages 或任意静态托管；Pages 工作流与迭代更新流程见 t5。
