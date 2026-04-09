# raw_paper_parse — 设计规划

## 目标

- 拉取论文页面，归一化为仓库统一的 **Document**（[`schemas/document.json`](../schemas/document.json)）并写入 **RawDoc**（[`raw_ingest/common/rawdoc_write.py`](../raw_ingest/common/rawdoc_write.py)）。
- **发表形态（variant）**：`preprint`（预印本）、`conference`（会议）、`journal`（期刊）。同一工作若三种都要 ingest，则产生 **三条 Document**（三个 `doc_id`），通过共享的 **work id** 在元数据中关联。
- **第一阶段**（本包实现）：仅 **arXiv HTML**（`https://arxiv.org/html/...`，LaTeXML / ar5iv 实验 HTML）。
- **第二阶段**（未实现）：会议站（如 OpenReview HTML）、期刊出版商 HTML 或 **PDF**（schema 中 `meta.source.type: pdf`）、Crossref / OpenAlex 发现、可选的 DOI 辅助工具。

## 从 arXiv 查找 DOI

许多预印本在 arXiv 上 **尚未** 登记期刊 DOI；正式发表后可能由作者或期刊回填。建议按顺序尝试：

1. **arXiv 摘要页** `https://arxiv.org/abs/<id>`：是否有 **Journal reference**、**DOI** 或出版社链接。
2. **arXiv Atom API**：`http://export.arxiv.org/api/query?id_list=<arxiv_id>`，查看条目中是否有 `<arxiv:doi>`。没有该字段不代表没有正式发表。
3. **OpenAlex**：按 arXiv ID 或标题检索 work，读取 `doi`（可能多条记录，需人工选对 variant）。
4. **Semantic Scholar Graph API**：`paper/arXiv:<id>?fields=externalIds,...`，使用 `externalIds.DOI`（遵守 API key 与限流）。
5. **Crossref**：用标题+作者+年份做 bibliographic 检索（误匹配多）；更适合用来 **校验** 已从 OpenAlex/S2 得到的 DOI。

第一阶段 **不** 自动解析 DOI：批处理里 `work_id` 可继续用 `arxiv:...`；会议/期刊行在人工查到 DOI 或官方 URL 后再填写。

## 与 raw_ingest 的对齐

| raw_ingest | raw_paper_parse |
|------------|-----------------|
| `sites/router.py` + `supported_sites.txt` | `sources/router.py` + `supported_sources.txt` |
| `sites/<module>.py` 的 `run_one` | `sources/arxiv_html.py` 的 `run_one`（可选 `work_id`、`variant`） |
| 公共逻辑 | 将 `raw_ingest/common` 加入 `sys.path`，复用 `normalize_doc`、`sink_doc` 等 |
| 输出目录 | 默认与仓库 Makefile 一致：`data/rawdocs`、`data/docs`、`data/assets` |

## work × variant 模型

- **work_id**：逻辑主键，如 `arxiv:2401.12345v2` 或 `doi:10.xxxx/...`（由批处理或 CLI 提供）。
- **variant**：`preprint` | `conference` | `journal`。
- 每条 Document 的 **`meta.tags`** 约定：
  - `paper:work_id:<work_id>`
  - `paper:variant:<variant>`

后续可选：扩展 `schemas/document.json` 的 `meta`，增加结构化 `paper` 字段。

## 批处理输入格式

制表符分隔，一行 = 一条记录、一次抓取：

```text
# work_id	variant	fetch_url	[canonical_url]
arxiv:2401.00001v1	preprint	https://arxiv.org/html/2401.00001v1	https://arxiv.org/abs/2401.00001v1
```

`#` 开头为注释。若为 **仅 URL 行**（无 TAB）且为 arXiv 链接，则默认 `work_id=arxiv:<id>`、`variant=preprint`、`canonical` 为对应 `abs` URL。

## arXiv HTML 解析要点（第一阶段）

- 将 `abs` / `pdf` URL 规范为 **`html`** URL（同版本 id）。
- 解析 `article.ltx_document`：标题、作者、嵌套 `section` / `subsection` / `subsubsection`、`ltx_para` 内的段落、图、表。
- 公式：先用 `get_text()` 做可读文本，可能损失数学结构。
- 图片：`img.ltx_graphics` → `figure` + `process_assets`，`base_url` 使用实际抓取 URL（配合页面 `<base href>`）。

## 风险

- arXiv HTML DOM 随 LaTeXML / ar5iv 变更。
- 会议/期刊：付费墙、反爬、以 PDF 为主 — 第二阶段按数据源单独适配。

## 相关文档

- [`README.md`](README.md) — 快速开始（英文）。
- [`README.zh-cn.md`](README.zh-cn.md) — 中文快速开始。
