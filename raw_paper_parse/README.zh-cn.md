# raw_paper_parse

拉取 **论文** HTML（第一阶段：**arXiv** 实验性 HTML），归一化为与 [`raw_ingest`](../raw_ingest/README.zh-cn.md) 相同的 **Document** + **RawDoc** 流水线。

完整设计、DOI 查找说明、work/variant 语义见 **[PLAN.zh-cn.md](PLAN.zh-cn.md)**（英文：[PLAN.md](PLAN.md)）。

## 快速开始

在**仓库根目录**：

```bash
make paper-parse-deps
make paper-parse URL='https://arxiv.org/html/2401.00001v1'
```

批处理（制表符分隔，见 [examples/example_papers.tsv](examples/example_papers.tsv)）：

```bash
make paper-parse-batch FILE=raw_paper_parse/examples/example_papers.tsv
```

或在本目录：

```bash
cd raw_paper_parse && pip install -r requirements.txt
python sources/router.py --url 'https://arxiv.org/html/2401.00001v1'
python sources/router.py --urls-file examples/example_papers.tsv
```

单条 URL 可选元数据：

```bash
python sources/router.py --url 'https://arxiv.org/abs/2401.00001v1' \
  --work-id 'arxiv:2401.00001v1' --variant preprint
```

`--variant` 取值：`preprint`、`conference`、`journal`（会议/期刊数据源尚未实现；仍会写入 tags 供下游使用）。

每次成功 ingest 会在 **stdout** 打一行，例如：

`rawdoc_id=<uuid> doc_id=<uuid> doc_json=.../data/docs/<doc_id>.json doc_md=.../data/docs/<doc_id>.md`

`data/rawdocs/<rawdoc_id>.meta.json` 里的 `metadata` 在写入时也会带上 **`doc_id`**，便于和 Document 对齐。

## 引用与表格（arXiv HTML）

- LaTeXML 的 `\citep` / `<cite class="ltx_cite">` 会变为 `items` 里的 `{"cite": [{"ref_id": "bib.bib35", "label": "35"}, ...]}`。**`ref_id`** 对应 HTML 锚点（去掉 `#`），例如 `bib.bib35`。导出 **Markdown 时会省略** 这些块，因此 `.md` 里不会出现 `[35, 2, 5]` 这类角标；**JSON 保留** 与参考文献条目的对应关系，供下游使用。
- Document JSON **顶层**有 **`references`** 数组：每项含 **`ref_id`**、**`text`**（整条参考文献的纯文本）、可选 **`label`**（如 `[2]`）、可选 **`blocks`**（LaTeXML 的 `ltx_bibblock` 分段）。正文里 `cite` 的 `ref_id` 与 **`references[].ref_id`** 一致即可对齐全文。
- `<table>` 若在 `ltx_para` 里与段落并列，会落成 **table** 小节；若在 `<p>` 内，则作为段落 `items` 里的 `{"table": {"rows": [[单元格,…],…]}}`。Markdown 里对 `rows` 使用 **GFM 管道表格**。

若两个引用组紧挨（例如 “such as [a] and [b]”），去掉角标后 Markdown 可能略拗口；**JSON 里的 `cite` 结构仍是完整、可解析的**。

## 第二阶段（未实现）

规划方向（详见 [PLAN.zh-cn.md](PLAN.zh-cn.md)）：

- **会议**：OpenReview 或会议开放获取页面的 HTML（按站点写解析器，注意限流与 robots）。
- **期刊**：出版商 HTML 或 **PDF** 管线（文档 schema 中 `meta.source.type: pdf`）；可能与 HTML 分两条 acquire 路径。
- **发现**：Crossref / OpenAlex（可选 Semantic Scholar）辅助同一工作的 DOI 与 arXiv 对应关系；自动结果应保留 **人工确认** 环节。

## 相关说明

- 默认输出目录：`data/rawdocs`、`data/docs`、`data/assets`（与 `make raw-ingest` 一致）。
- 英文 README：[README.md](README.md)。
