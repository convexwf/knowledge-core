# knowledge-core

## Directory layout

- **Code (repo root):** `cmd/` (Go executables), `fetch/` (Go acquisition logic), `ingest/` (Python parse, normalize, assets, sink), `configs/`, `schemas/`, `doc/`, `reference/`. **Entry:** use the **Makefile** (`make build`, `make fetch`, `make ingest`, `make run URL=...`, `make docker-up`).
- **Runtime data (under `data/`, gitignored):** `data/rawdocs/` (raw fetched/imported content), `data/assets/` (extracted images), `data/docs/` (normalized JSON and Markdown). All ingestion outputs go here so the root stays code-only.
- **Samples:** Optional sample HTML files under `reference/samples/` (e.g. `make run FILE=reference/samples/...`).
- **Build:** `make build` or `go build -o bin/acquire ./cmd/acquire`; `bin/` is gitignored.

## html 抽取 （早期的一些想法）

对于每个站点，编写对应的抽取规则，比如说 `mp.weixin.qq.com`，编写对应的 `mp_weixin.yaml` 作为抽取规则文件，放到 `adapters/html_extractor/rules` 目录下。

注意点

1. 图片需要以 png 格式存储到本地目录，json 文件里记录相对路径；
2. 网页信息需要存储 title, url, author, publish_time 等字段；
3. 目前都是传入 html 文件内容进行抽取，后续可以考虑传入 url 直接抓取网页内容进行抽取，但是优先级不高。
4. html 文件里有记录拉取时间，即 `save_time` 字段，可以考虑存储到 json 里。
5. 支持提取表格内容，在 json 里以二维数组形式存储。
6. 支持提取代码块，需要记录代码语言类型，整个代码块作为字符串存储到 json 里。

## 完整想法 （草案）

## 1) 需求总结（你要做的东西是什么）

你要做一个 **Knowledge Base 数据摄取（Ingestion）引擎**，负责从不同来源采集内容，并解析成统一结构，供后续知识库/RAG使用。

### 核心输入来源

* **在线网页**：通过 HTTP 抓取
* **离线网页**：通过 Chrome 插件 SingleFile 保存的 HTML 导入
* **PDF 文档**：本地或下载后解析
* **EPUB 电子书**：本地或下载后解析

### 核心输出

输出一份“统一范式”的结构化文档（JSON/Markdown 都行），包含：

* 标题、章节、段落等文本结构
* 元数据（来源、URL、抓取时间、解析器版本等）
* **图片资源（必须落盘/对象存储，并可追溯回原文位置）**
* 可用于后续：

  * chunking
  * embedding
  * 向量入库
  * 搜索/检索

---

## 2) 关键约束与难点

### 1) 数据源差异巨大

不同网站 DOM 结构完全不同，解析规则必须可插拔、可扩展。

### 2) 解析规则会越来越多

你预计会有大量“站点级 parser”，必须有治理能力：

* 注册机制
* 路由匹配
* 单测与回放
* 失败隔离

### 3) PDF/EPUB 解析生态问题

Go 的文档解析生态明显弱于 Python，因此解析层需要 Python（尤其 PDF）。

### 4) 图片必须保存

图片来源包括：

* HTML `<img src>`（可能是相对路径、CDN、data URL）
* SingleFile 内联 base64
* PDF 内嵌图片/页面截图
* EPUB 内资源文件

必须做到：

* 统一下载/抽取
* 存储到指定目录或对象存储
* 文档结构中记录图片引用关系（可用于渲染/检索）

---

## 3) 总体方案（架构）

### 设计原则

* **抓取通用化（Go）**
* **解析插件化（Python）**
* 二者通过标准数据协议交互（JSON）
* 解析与抓取解耦，解析失败不影响引擎稳定性

---

### Pipeline（流水线）

```
Input → Acquire → RawDoc → Parse → Normalize → Assets → Sink
```

* **Acquire（获取）**

  * URL 抓取（Go）
  * SingleFile HTML 导入（Go）
  * 本地 PDF/EPUB 导入（Go）

* **RawDoc（原始文档）**

  * 存原始内容（建议落盘 + 引用）
  * 记录来源与元数据

* **Parse（解析）**

  * Python 解析器运行时
  * 按来源选择 parser
  * HTML/PDF/EPUB 分别处理

* **Normalize（统一结构）**

  * 输出统一 Document Schema（JSON）
  * 保证后续 chunk/embedding 不依赖数据源差异

* **Assets（图片资源处理）**

  * 下载/抽取图片
  * 统一命名、去重、存储
  * Document 中保留图片引用（位置、caption、原始链接等）

* **Sink（落库/输出）**

  * 文件系统 / 数据库
  * 后续可接向量库（Milvus/Qdrant/pgvector）

---

## 4) 技术栈建议（稳定且扩展性好）

### Go（引擎层）

负责：

* 并发调度、任务队列
* 抓取（HTTP）
* 导入（本地文件）
* 去重、重试、限流
* RawDoc 管理、回放

建议组件：

* `net/http` + 自己封装 retry/timeout
* worker pool
* 配置路由（YAML）

---

### Python（解析层）

负责：

* HTML 清洗与解析（lxml/bs4）
* PDF 解析（docling）
* EPUB 解析（ebooklib + lxml）
* 图片抽取/下载/重写引用

建议组件：

* HTML：`lxml`, `beautifulsoup4`
* PDF：`docling`
* EPUB：`ebooklib`
* 图片：requests/httpx + base64 decode

---

### 通信方式

初期推荐：

* **Go ↔ Python：stdin/stdout JSON**
* 一个 Python runtime 进程加载多个 parser（插件注册）

后期扩展：

* gRPC / HTTP parser service
* parser worker pool

---

### 存储（图片与原文）

建议一开始就按“可回放”设计，运行时数据统一放在 `data/` 下（该目录已 gitignore）：

* `data/rawdocs/`：原始 HTML/PDF/EPUB
* `data/assets/`：图片资源（统一命名）
* `data/docs/`：解析后的标准 JSON/Markdown

---

## 5) 推荐目录结构（可长期演进）

```
repo/
├── cmd/                    # Go acquire 等
├── engine/                 # Python normalize、assets
├── parsers/                # Python parser 插件
│   ├── html/adapters/
│   ├── pdf/
│   ├── epub/
│   └── common/
├── configs/
│   └── routes.yaml
├── schemas/
│   ├── rawdoc.json
│   └── document.json
├── data/                   # 运行时数据（gitignore）
│   ├── rawdocs/
│   ├── assets/
│   └── docs/
└── docker/
```

---

## 6) 最终输出（你真正要的“产品形态”）

你最终会得到一个系统，能做到：

* 输入：URL / SingleFile HTML / PDF / EPUB
* 输出：统一结构化文档 + 图片资源
* 支持：不断新增解析器（一个来源一个 parser）
* 支持：失败回放与重跑
* 为知识库/RAG提供稳定数据源
