# raw_ingest

Python 流水线：**拉取 HTML** → 写入 `data/rawdocs/` 的 **RawDoc** → 按统一 **文档 schema** 归一化 → 处理 **资源** → 输出 `data/docs/` 下的 **JSON + Markdown**（以及 `data/assets/`）。

仓库根目录 **Makefile** 提供 `raw-ingest`、`raw-ingest-batch`、`raw-ingest-list`；**文章**入口是 `sites/router.py`，按 **抓取 URL 的 hostname** 分发（并对 Internet Archive 做了特殊处理）。**文章列表**（RSS / 聚合页）由 `list/` 单独处理。

---

## 快速开始

在**仓库根目录**：

```bash
make raw-ingest-deps
make raw-ingest URL='https://example.com/article'
```

批量（每行一个 URL；`#` 开头为注释）：

```bash
make raw-ingest-batch FILE=raw_ingest/examples/example_urls.txt
```

或在 `raw_ingest/` 下：

```bash
cd raw_ingest && python sites/router.py --url 'https://...'
cd raw_ingest && python sites/router.py --urls-file /path/to/urls.txt
```

可选 **`CANONICAL=`**（配合 `make raw-ingest`）或 URL 文件中的 **`fetch|canonical`**：HTML 从第一个地址下载，但 `source_uri` / 元数据使用 canonical（Freedium、Wayback + 官网等场景）。

### 文章列表（RSS / 聚合页快照）

在**仓库根目录**，先 `make raw-ingest-deps` 后：

```bash
make raw-ingest-list
# 或: make raw-ingest-list FILE=path/to/site_list.url
```

默认读取 **`examples/site_list.url`**：每行一个站点，制表符分隔 **`site_id<TAB>list_url`**（`#` 开头为注释）。`site_id` 与 `sites/<module>.py` 模块名一致（如 `engineering_fb`）。多数站点填 RSS/Atom 地址；**`blog_x_com`** 填 engineering **聚合页** URL（若官网返回 Cloudflare，宜用 **Wayback** 包裹的地址）。**`blog.google`** 请使用 **`https://blog.google/rss/`**（`/feed/` 为前端壳页面，不是 feed）。

每次运行会在 **`data/post_lists/<site_id>_<UTC>.json`** 写入结果，含 `posts`（`title`、`url`、`published`、`summary`）、`parser`（`rss` 或 `html`）；若抓取失败会带 `error` 字段。

---

## 结构说明

| 部分 | 作用 |
|------|------|
| `sites/router.py` | 根据 fetch URL 查表，加载对应模块的 `run_one` |
| `sites/supported_sites.txt` | 制表符分隔：`hostname` → `module`（无 `.py`），每个主机别名一行 |
| `sites/<module>.py` | 实现 `run_one(fetch_url, canonical_url, rawdocs_dir, assets_dir, docs_dir, timeout, do_validate)` |
| `list/fetch_post_lists.py` | CLI：读 `site_list.url`，拉取列表，写入 `data/post_lists/*.json` |
| `list/feed_parse.py` | 用 `feedparser` 解析 RSS/Atom，归一成 `posts` |
| `list/blog_x_list.py` | engineering 聚合页 HTML → 文章链接（复用 `blog_x_com` 的 Cloudflare 检测） |
| `common/` | 共用：`rawdoc_write`、`normalize_doc`、`assets_doc`、`sink_doc`、`schema_validate`、`repo_paths` |

执行 `python sites/router.py` 时，Python 会把**脚本所在目录**（`raw_ingest/sites/`）加入 `sys.path`，因此注册表里的模块以顶层名导入（如 `blog_google`）。

### Internet Archive（`web.archive.org`）

若 fetch URL 形如 `https://web.archive.org/web/<时间戳>/https://原始主机/...`，router 会**解析内嵌的原始 URL**，并按**内嵌 URL 的 host** 选择解析器。批量文件可写为：Wayback 作 fetch、官网作 canonical，例如：

```text
https://web.archive.org/web/20240304231722/https://blog.x.com/...|https://blog.x.com/...
```

---

## 已支持站点（注册表）

以 `sites/supported_sites.txt` 为准。文档更新时大致包括（**非完整列表**，以后以该文件为准）：

| 模块 | 典型主机 |
|------|----------|
| `medium_freedium` | `freedium-mirror.cfd` |
| `engineering_fb` | `engineering.fb.com` |
| `meituan_tech` | `tech.meituan.com` |
| `vickiboykis` | `vickiboykis.com`、`www.vickiboykis.com` |
| `allthings_distributed` | `www.allthingsdistributed.com` 等 |
| `brendan_gregg_blog` | `www.brendangregg.com` 等 |
| `blog_google` | `blog.google` |
| `smashing_magazine` | `www.smashingmagazine.com`、`smashingmagazine.com` |
| `blog_x_com` | `blog.x.com`、`blog.twitter.com` |

批量文件中不支持的 host 会在 stderr 打 **`UNSUPPORTED`** 并跳过（除非有支持的 URL 失败，否则退出码为 0）。

---

## 前序对话上下文（给新会话用）

以下概括**此前对话里做过的事与设计取舍**，便于新开 chat 时不依赖超长上下文。

1. **Smashing Magazine**（`smashing_magazine.py`）：正文在 `article div.c-garfield-the-cat`。按结构遍历，用 class 跳过广告/侧栏/feature 等；处理摘要块与常见块级元素。`article:published_time` 等可能带 `+0000 UTC`，会归一成 ISO/Z。

2. **X 工程博客**（`blog_x_com.py`）：直连 `blog.x.com` 常被 **Cloudflare** 或 **403** 拦截，`requests` 拿不到正文。解析器按历史页面 DOM（如 `div.column.column-6`、`bl13-rich-text-editor`、`bl14-image`、作者卡片、`data-src` 图片）。**建议**：用 **Wayback** 作 fetch、`fetch|canonical` 保留官网 `source_uri`；router 通过内嵌 URL 解析到 `blog_x_com`。

3. **example_urls.txt**：维护为**每个已支持解析器约一条示例**；直连 blog.x 在批量里可能失败，文件头注释说明可改用 Wayback。

4. **Meta Engineering**（`engineering_fb.py`）：WordPress，`main article.hentry` + `div.entry-content`；跳过 Jetpack 分享区；YouTube `iframe` 转为带链接的段落；作者来自 `.entry-authors`；日期来自 meta 或 Yoast `@graph` 里的 `Article`。

5. **Vicki Boykis**（`vickiboykis.py`）：Hugo Bear，正文在 `<main><content>`。默认作者 **Vicki Boykis**；标签来自 `main` 下 `/tags/` 链接。

6. **新增站点清单（可重复）**  
   - 新增 `sites/<name>.py`，`run_one` 签名与现有模块一致（块级遍历可参考 `brendan_gregg_blog.py` / `blog_google.py`）。  
   - 在 `sites/supported_sites.txt` 为每个会出现的 hostname 增加一行（含 `www.` 若需要）。  
   - 一般**不必改 router**（Wayback 已支持）。  
   - 可选：在 `examples/example_urls.txt` 加一行示例。  
   - 用 `make raw-ingest URL='...'` 跑通；若 `validate_document` 报错再对齐 schema。

---

## 相关 Makefile 目标

- `raw-ingest` / `raw-ingest-batch` — 统一走文章 router。  
- `raw-ingest-list` — 从 `examples/site_list.url`（或 `FILE=...`）拉取各站 post 列表快照。  
- `raw-ingest-freedium` / `raw-ingest-meituan-tech` — 直接调对应站点脚本（历史便利入口）。

---

## 英文版

与本文内容对应的英文说明见 [README.md](README.md)。
