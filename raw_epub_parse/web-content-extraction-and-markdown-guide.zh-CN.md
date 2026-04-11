# 网页内容提取与 Markdown 生成全面总结

## 1. 这件事到底在解决什么问题

“网页内容提取 + Markdown 生成”本质上是在做两件事：

1. 从网页里找出“真正值得保存的内容”。
2. 把这些内容变成稳定、可读、可复用的 Markdown。

看起来像一个步骤，实际上通常至少要经过下面这条流水线：

1. 获取页面内容
2. 解析 DOM / 渲染结果
3. 识别正文与元数据
4. 清理噪音和无关节点
5. 标准化 HTML 结构
6. 转换为 Markdown
7. 套模板生成最终笔记或文档

如果只做第 6 步，不先做正文提取，最后得到的 Markdown 往往会混入：

- 导航栏
- 页脚
- 推荐阅读
- 广告
- 社交按钮
- 评论区
- 弹窗遮罩
- 站内“你可能还喜欢”

所以行业里通常会把“正文抽取”和“HTML 转 Markdown”拆开处理。

---

## 2. 一条完整工程流水线长什么样

一个可维护的实现，通常长这样：

```text
HTML / 当前页面 DOM
  -> 预处理
  -> 元数据提取
  -> 正文候选区识别
  -> 噪音移除
  -> 主内容确定
  -> HTML 标准化
  -> Markdown 转换
  -> 模板填充 / 存储
```

如果是浏览器插件场景，数据源通常不是“原始 HTML”，而是“当前浏览器已经渲染出来的 DOM”。这点非常重要，因为：

- 很多网站是前端渲染，初始 HTML 几乎没有正文
- 用户可能已经选中了部分文本
- 页面可能有高亮、批注、展开状态
- Shadow DOM、懒加载图片、相对链接都要处理

如果是服务端爬虫场景，还要额外考虑：

- 是否需要无头浏览器执行 JavaScript
- 是否要等待异步内容加载完成
- 反爬、限频、Cookie、地域化内容
- 站点编码与异常 HTML

---

## 3. 网页内容提取的几种主流方法

### 3.1 用户显式指定

这是最稳的一类：

- 用户选择了一段文字
- 用户高亮了几个块
- 用户右键选中了某个元素
- 用户给出 CSS Selector / XPath

优点：

- 准确率最高
- 不依赖通用正文识别算法
- 对复杂站点最稳定

缺点：

- 自动化程度低
- 不适合批量抓取

这个思路在 Web Clipper 里很常见，因为“用户知道自己想保存什么”。

### 3.2 基于模板和选择器

这类方法直接针对网站结构写规则，比如：

- 标题：`h1`
- 作者：`.author`
- 发布时间：`time[datetime]`
- 正文：`article .content`

优点：

- 准确
- 可控
- 输出稳定

缺点：

- 强依赖站点结构
- 站点改版后容易失效
- 很难跨站通用

适合：

- 公司内部知识站
- 固定几个媒体站点
- 电商 / 影视 / 图书等结构高度规律的网站

### 3.3 基于结构化元数据

很多网页会提供结构化信息，例如：

- HTML `meta`
- Open Graph
- Twitter Card
- `schema.org` / JSON-LD

它们通常特别适合提取：

- 标题
- 作者
- 发布时间
- 描述
- 封面图
- 站点名
- 类型（如 `Article`、`Recipe`、`Product`）

优点：

- 对 metadata 很有效
- 站点常常已经帮你整理好了
- 可用于模板自动匹配

缺点：

- 正文本身通常仍需另外提取
- 有些站点字段缺失或填得不规范

### 3.4 基于启发式正文抽取

这是最常见的“自动抓文章正文”方案。典型库包括：

- Mozilla Readability
- Defuddle
- Trafilatura

核心思想通常是：

1. 先移除明显不是正文的节点
2. 对剩余内容区块打分
3. 选出最像“正文容器”的那一块
4. 再对选中的内容做清洗和标准化

这类算法常见的判断维度有：

- 文本长度
- 段落数量
- 链接密度
- 标点密度
- 标题层级
- 节点标签语义（`article`、`main`、`section`、`nav`、`aside`）
- 可见性
- 图片尺寸
- 是否像评论区、推荐区、工具条

优点：

- 跨站点通用
- 用户零配置也能用

缺点：

- 对特殊页面并不总是准确
- 不是所有网页都天然有“正文”
- 容易在长列表页、论坛页、产品页、SPA 页失手

### 3.5 站点专用提取器

对于一些结构特殊的平台，通用算法可能不够。工程上经常会补充：

- YouTube 字幕提取器
- X / Twitter 线程提取器
- GitHub 页面规范化提取
- Reddit / Hacker News 评论提取

优点：

- 效果好
- 可以覆盖通用算法弱项

缺点：

- 维护成本高
- 容易碎片化

### 3.6 LLM 辅助提取

大模型在这里更适合做“后处理”或“非规则化信息抽取”，例如：

- 提炼摘要
- 识别作者、主题、标签
- 从杂乱页面中抽特定字段
- 统一输出成 JSON

不太建议让 LLM 直接替代底层 DOM/HTML 提取，因为：

- 成本高
- 延迟高
- 可重复性差
- 容易幻觉
- 难以做稳定回归测试

更合理的用法是：

1. 先用规则和提取库拿到稳定正文
2. 再让 LLM 做总结、分类、补字段

---

## 4. 正文提取到底基于哪些规则

### 4.1 先做预处理

提取前通常要先清理页面：

- 删除 `script`、`style`
- 去掉内联样式或无关属性
- 把相对链接转成绝对链接
- 处理 `srcset`
- 还原 Shadow DOM
- 收集当前 selection/highlights
- 移除隐藏元素

这一步的目标是：把“浏览器里的复杂页面”变成“适合提取的干净文档”。

### 4.2 识别显式无关内容

第一批被删掉的内容通常来自选择器规则：

- `header`
- `footer`
- `nav`
- `.sidebar`
- `.share`
- `.social`
- `.ad`
- `.banner`
- `.popup`
- `.modal`
- `.subscribe`
- `.recommend`
- `.related`

规则一般有两种：

- 精确匹配：明确的标签、类名、id
- 模糊匹配：类名或 id 中包含 `ad`、`share`、`social`、`promo` 之类关键词

### 4.3 根据可见性筛掉节点

常见规则包括：

- `display: none`
- `visibility: hidden`
- `hidden` 属性
- 零尺寸
- 被 CSS 完全折叠

原因很简单：如果用户根本看不到，这些节点通常就不该出现在剪藏结果里。

### 4.4 给候选内容打分

这一步是很多正文提取算法的核心。

典型思路：

- 段落多、文本长的块加分
- 链接比例太高的块减分
- 短文本列表减分
- `article`、`main` 之类语义标签加分
- `nav`、`aside`、评论容器减分
- 标点丰富、句子完整的块更像正文
- 被多个正文候选包裹的父节点也可能获得加权

常见判断信号：

- 文本长度 `text length`
- 链接密度 `link density`
- 标点数量
- 子段落数量
- 标题与正文的邻接关系
- 是否包含大量列表 / 按钮 / 表单

### 4.5 选出主内容容器

最终算法通常会在多个候选块中选一个“主容器”，比如：

- 最大正文块
- 分数最高节点
- 得分最高节点及其若干兄弟节点
- 明确命中的 `article` / `main`

之后再对这个容器内部做二次清洗。

### 4.6 保守和激进的取舍

正文抽取永远有一个张力：

- 太保守：会漏内容
- 太激进：会把广告、推荐、评论一起带进来

不同库的风格不同：

- Readability 更经典，偏“阅读视图”
- Defuddle 更强调标准化输出和 Markdown 友好
- Trafilatura 更偏大规模提取、研究和评估

---

## 5. 元数据提取通常怎么做

正文之外，真正好用的笔记通常还需要 metadata。

推荐优先级通常是：

1. 用户模板 / 手动指定
2. `schema.org` / JSON-LD
3. Open Graph / Twitter Card / `meta`
4. DOM 选择器
5. 页面标题或启发式回退

常见字段：

- `title`
- `author`
- `published`
- `description`
- `site`
- `domain`
- `image`
- `favicon`
- `language`
- `tags` / `category`

一个稳定实现通常不会只信一个来源，而是会做 fallback：

```text
title = schema.headline ?? og:title ?? document.title
author = schema.author ?? meta.author ?? selector('.author')
published = schema.datePublished ?? article:published_time ?? time[datetime]
```

---

## 6. HTML 转 Markdown 不是简单替换标签

很多人第一次做这件事会想：

- `h1` -> `#`
- `p` -> 段落
- `a` -> link

但真正落地时，复杂度远高于这个映射表。

### 6.1 先标准化，再转换

好的方案通常会先把 HTML 统一成“更可预测的结构”，然后再转 Markdown。

例如：

- 去掉重复标题
- 统一标题层级
- 清理锚点链接
- 规范代码块
- 规范脚注
- 规范数学公式
- 规范 callout / alert

如果不先标准化，转换器往往会因为不同网站的奇怪 HTML 结构产生不稳定结果。

### 6.2 需要处理的核心结构

至少要覆盖这些元素：

- 标题：`h1` 到 `h6`
- 段落：`p`
- 强调：`em`、`strong`
- 列表：`ul`、`ol`、`li`
- 链接：`a`
- 图片：`img`
- 代码：`pre`、`code`
- 引用：`blockquote`
- 分隔线：`hr`
- 表格：`table`
- 换行：`br`
- 脚注
- 数学公式

### 6.3 最难的往往不是语法，而是边界

重点难点通常在：

- 空白如何折叠
- 多层列表如何缩进
- 行内代码与普通文本如何转义
- 表格能否用纯 Markdown 表达
- 图片 alt、srcset、相对 URL 如何处理
- 链接文本为空时怎么办
- HTML 中本来就有 Markdown 特殊字符时如何 escape

### 6.4 有些内容无法完整映射到纯 Markdown

例如：

- 复杂表格
- 折叠面板
- 自定义组件
- 布局型 div
- 视频播放器
- 交互控件

工程上通常有三种处理方式：

1. 降级成纯文本
2. 保留为原始 HTML
3. 转成目标系统支持的扩展语法

如果目标是 Obsidian，还可以利用其扩展语法处理：

- callout
- wikilink
- 数学公式
- 脚注

---

## 7. 一个优秀的 Markdown 生成器应该具备哪些规则

### 7.1 结构保真

至少要尽量保留：

- 标题层级
- 列表层级
- 代码语言
- 链接目标
- 图片地址
- 表格结构

### 7.2 文本清洁

输出前最好处理：

- 多余空行
- 行尾空白
- 不必要的空格
- 重复标题
- 页面工具条残留文案

### 7.3 Markdown 转义

必须正确处理：

- `*`
- `_`
- `#`
- `-`
- `>`
- `[` `]`
- `(` `)`
- 反引号

否则结果会变成意外的列表、标题或链接。

### 7.4 链接和图片 URL 绝对化

如果不把相对路径转成绝对 URL，离开原网页环境后通常就会失效。

例如：

- `/images/a.png`
- `../post/1`
- `?ref=abc`

都应该在转换前结合 `baseURI` 处理。

### 7.5 代码块规范化

推荐做法：

- 去掉行号
- 去掉语法高亮注入的多余 span
- 保留语言信息
- 统一成 fenced code block

### 7.6 脚注、数学、Callout

如果目标是知识库或笔记系统，最好显式支持：

- 脚注
- KaTeX / MathJax
- 提示框 / 警告框 / 说明框

否则内容虽然“转成功了”，但信息表达会明显退化。

---

## 8. Obsidian Web Clipper 的实现思路

这部分基于当前工作区里的 `obsidian-clipper` 源码和文档。

### 8.1 它的核心依赖

本地仓库 `package.json` 显示：

- `defuddle` 用于内容提取和 Markdown 转换
- `dompurify` 用于 HTML 清理
- `linkedom` 用于 DOM 处理相关场景

见：

- `obsidian-clipper/package.json`
- `obsidian-clipper/README.md`

### 8.2 它的提取优先级

根据本地文档，Web Clipper 打开页面后会先抽取页面数据，但最终保存内容有覆盖优先级：

1. 如果模板自定义了提取规则，按模板
2. 如果当前有 selection，优先用 selection
3. 如果有高亮，优先用 highlights
4. 否则使用默认“智能正文提取”

见：

- `obsidian-clipper/docs/Clip web pages.md`
- `obsidian-clipper/docs/Variables.md`

### 8.3 它如何抓页面内容

从 `obsidian-clipper/src/content.ts` 和 `src/utils/content-extractor.ts` 可以看到大致流程：

1. 先尝试 flatten Shadow DOM
2. 读取当前 selection 的 HTML
3. 用 `Defuddle(document, { url: document.URL })` 做页面解析
4. 优先走 `parseAsync()`，超时后回退到 `parse()`
5. 收集 Defuddle 结果中的：
   - `title`
   - `author`
   - `content`
   - `description`
   - `image`
   - `published`
   - `site`
   - `language`
   - `wordCount`
   - `schemaOrgData`
   - `metaTags`
6. 对原始页面 HTML 再做一轮清洗：
   - 删除 `script` / `style`
   - 删除所有 `style` 属性
   - 将 `src` / `href` / `srcset` 转为绝对 URL
7. 如果有 highlights，根据设置把高亮内容嵌回正文或直接替换正文
8. 最后用 `createMarkdownContent(...)` 把 HTML 转为 Markdown

这说明它不是“直接把 DOM 原样转 Markdown”，而是：

`提取 -> 清洗 -> 标准化 -> Markdown 化 -> 模板变量填充`

### 8.4 它如何生成 Markdown

在本地代码中，Markdown 转换由 `defuddle/full` 提供的 `createMarkdownContent()` 完成，主要入口可见：

- `obsidian-clipper/src/content.ts`
- `obsidian-clipper/src/api.ts`
- `obsidian-clipper/src/utils/filters/markdown.ts`

这也解释了它模板里的 `markdown` filter：

```twig
{{selectorHtml:body|markdown}}
```

这类写法实际上就是“先取 HTML，再调用同一套 Markdown 转换器”。

### 8.5 它支持哪些提取变量

本地文档显示 Web Clipper 的模板变量分为五类：

- Preset variables
- Prompt variables
- Meta variables
- Selector variables
- Schema.org variables

其中最关键的是：

- `{{content}}`：默认正文 Markdown
- `{{contentHtml}}`：默认正文 HTML
- `{{fullHtml}}`：完整页面 HTML
- `{{selection}}` / `{{selectionHtml}}`
- `{{highlights}}`
- `{{meta:...}}`
- `{{selector:...}}`
- `{{selectorHtml:...}}`
- `{{schema:...}}`

这套设计很实用，因为它把“通用自动提取”和“手动精确指定”都留给了用户。

### 8.6 它的本质策略

可以把 Obsidian Web Clipper 理解成四层能力叠加：

1. 通用正文提取
2. 元数据提取
3. 选择器精确提取
4. 模板拼装与格式化输出

这比“单纯一个 HTML 转 Markdown 工具”强很多。

---

## 9. Defuddle 这类提取器在做什么

根据 Defuddle 的公开说明，它的定位是：

- 找出网页主内容
- 去掉噪音
- 标准化 HTML
- 返回 HTML 或 Markdown

它公开列出的能力包括：

- 删除精确选择器命中的噪音元素
- 删除模糊匹配到的噪音元素
- 删除隐藏元素
- 删除低分内容块
- 删除小图片
- 提取 `schema.org` 数据
- 标准化脚注、标题、代码块、数学公式、callout

从工程角度看，这种设计有两个很大的好处：

1. 抽取层和 Markdown 层不是完全耦合的
2. 输出 HTML 先被“整形”，后续转换器更稳定

---

## 10. Mozilla Readability、Defuddle、Trafilatura、Turndown、Pandoc 分别适合干什么

| 工具 | 更适合的角色 | 强项 | 短板 |
| --- | --- | --- | --- |
| Mozilla Readability | 正文提取 | 经典、成熟、阅读模式经验丰富 | 对 Markdown 输出不是核心关注点 |
| Defuddle | 正文提取 + HTML 标准化 + Markdown 友好输出 | 对 Web Clipper 场景友好，强调结构标准化 | 生态没有 Readability 普及 |
| Trafilatura | 大规模网页文本提取 | 批量处理、评估充分、支持多输出格式 | 更偏抓取/研究管线，不是前端插件导向 |
| Turndown | HTML -> Markdown 转换 | 规则系统清晰，易扩展 | 不负责“找正文”，只负责“转格式” |
| Pandoc | 通用文档格式转换 | 兼容面广，文档格式支持强 | 不负责网页正文识别，网页清洗能力不是重点 |

一个很重要的原则：

- `Readability / Defuddle / Trafilatura` 解决的是“提取什么”
- `Turndown / Pandoc` 解决的是“怎么转成 Markdown”

如果把这两类工具混用职责，经常会得到不理想结果。

---

## 11. 如果你要自己实现，推荐的系统分层

### 11.1 最基础版本

适合快速验证：

1. 获取页面 HTML
2. 用 Readability 或 Defuddle 抽正文
3. 用 Turndown 或内置转换器转 Markdown
4. 提取 `title`、`author`、`published`
5. 输出一个 `.md`

### 11.2 实用版本

适合剪藏工具或内部知识库：

1. 支持 selection / highlighter
2. 支持 selector 模板
3. 支持 `schema.org` 和 meta fallback
4. 支持图片 URL 绝对化
5. 支持表格、代码块、脚注、数学
6. 支持按站点自动匹配模板
7. 支持清洗 HTML 和 Markdown 后处理

### 11.3 企业级版本

适合大规模抓取和知识入库：

1. 渲染层和提取层分离
2. 支持 SPA、无头浏览器、登录态页面
3. 提供站点专用 extractor
4. 提供质量评估指标和回归测试
5. 支持结构化 JSON 中间层
6. Markdown 只是最终一种导出格式
7. 支持重试、缓存、速率限制、去重、版本化

---

## 12. 推荐的数据模型

不要只保存一份 Markdown。更好的做法是保留中间层：

```json
{
  "url": "...",
  "title": "...",
  "author": "...",
  "published": "...",
  "site": "...",
  "language": "...",
  "metadata": {},
  "schema_org": {},
  "content_html": "...",
  "content_markdown": "...",
  "selection_html": "...",
  "selection_markdown": "...",
  "highlights": []
}
```

原因：

- HTML 是最接近原文的结构化版本
- Markdown 适合阅读、检索和存储
- 中间层方便以后重跑转换器
- 不同下游可以复用同一份提取结果

---

## 13. 什么时候该用哪种提取策略

### 场景 A：普通文章页

优先：

1. 正文提取库
2. `schema.org` / meta 补 metadata
3. Markdown 转换

### 场景 B：固定站点，结构稳定

优先：

1. 站点模板
2. CSS selector
3. 缺失字段再回退通用提取

### 场景 C：用户只想保存局部内容

优先：

1. selection
2. highlighter
3. fragment link
4. 不要强行跑整页正文提取

### 场景 D：视频页、社交媒体、论坛

优先：

1. 专用 extractor
2. transcript / thread / comments 结构化抽取
3. 再转 Markdown

### 场景 E：批量采集

优先：

1. Trafilatura / Readability / Defuddle 这类自动提取
2. 结构化 JSON 中间层
3. 统一 Markdown 渲染

---

## 14. 评估一个提取器要看什么

不要只看“能不能出结果”，而要看：

- 正文召回率：有没有漏段落
- 噪音率：有没有混进广告和侧栏
- metadata 准确率：标题、作者、日期对不对
- Markdown 可读性：层级、空行、代码块是否正常
- 跨站稳定性：换站点是否还能工作
- 回归稳定性：升级依赖后输出是否漂移

推荐至少建立一套 fixtures：

- 新闻页
- 博客页
- 文档页
- 电商页
- 视频页
- GitHub README 页
- 带数学公式的技术文章
- 带复杂代码块的教程页
- 带表格的页面
- 前端渲染 SPA 页面

然后固定比较：

- 提取后的 HTML
- 生成的 Markdown
- 字段 JSON

---

## 15. 常见失败模式

### 15.1 SPA 页面内容为空

原因：

- 初始 HTML 里没有正文
- 提取发生得太早

处理：

- 等待渲染完成
- 使用浏览器上下文 DOM 而不是抓源代码
- 必要时用无头浏览器

### 15.2 提取过于保守

表现：

- 正文丢一半
- 代码块或图片消失

处理：

- 关闭部分 aggressive 清洗规则
- 用模板手动指定 `contentSelector`
- 直接用 selection / highlights

### 15.3 Markdown 格式混乱

表现：

- 列表断裂
- 表格变纯文本
- 链接格式错乱

处理：

- 先标准化 HTML
- 补针对表格/代码块/脚注的规则
- 加 escape 和空白清洗

### 15.4 metadata 不准

表现：

- 标题拿到了站点名
- 作者为空
- 日期错成更新时间

处理：

- 建立优先级链路
- 同时看 `schema.org`、meta、DOM
- 针对关键站点补模板

---

## 16. 一套推荐实现方案

如果目标是“像 Obsidian Web Clipper 一样做得足够实用”，推荐下面这套：

### 提取层

- 浏览器插件场景：直接使用当前页面 DOM
- 服务端场景：必要时用浏览器渲染后取 DOM

### 正文识别层

- 默认使用 Readability / Defuddle / Trafilatura 之一
- 对特殊站点提供专用 extractor
- 提供 `contentSelector` 作为人工兜底

### 元数据层

- 优先 `schema.org`
- 再看 Open Graph / `meta`
- 再看 DOM selector
- 最后回退到页面标题

### HTML 标准化层

- 删除噪音元素
- 绝对化 URL
- 规范代码块
- 规范脚注 / 数学 / callout
- 清洗隐藏元素和无意义小图

### Markdown 层

- 使用稳定转换器
- 支持扩展语法
- 统一空白、转义和换行

### 模板层

- 支持变量
- 支持 filters
- 支持逻辑判断和循环
- 支持按 URL / schema 自动匹配模板

### AI 层

- 只做摘要、标签、抽字段、改写
- 不替代底层提取逻辑

---

## 17. 一个务实的结论

网页内容提取不是单一算法问题，而是一个“多层 fallback 系统”：

1. 默认自动正文提取
2. metadata 补全
3. 用户选择 / 高亮覆盖
4. 站点模板修正
5. 结构化数据辅助
6. Markdown 后处理
7. 必要时 AI 补充

真正好用的工具，往往不是“默认算法特别神”，而是：

- 默认算法够用
- 覆盖策略清晰
- 模板系统足够强
- 输出结构稳定

这也是 Obsidian Web Clipper 这类工具比较合理的地方：它没有把希望全压在单一正文提取算法上，而是把自动提取、选择器、模板、结构化数据和 Markdown 生成组合在了一起。

---

## 18. 结合当前仓库可直接关注的文件

如果你后面还要继续深入这个项目，优先看这些文件：

- `obsidian-clipper/README.md`
- `obsidian-clipper/docs/Clip web pages.md`
- `obsidian-clipper/docs/Variables.md`
- `obsidian-clipper/docs/Filters.md`
- `obsidian-clipper/docs/Troubleshoot Web Clipper.md`
- `obsidian-clipper/src/content.ts`
- `obsidian-clipper/src/utils/content-extractor.ts`
- `obsidian-clipper/src/utils/filters/markdown.ts`
- `obsidian-clipper/src/api.ts`

---

## 19. 参考资料

### 当前工作区本地资料

- `obsidian-clipper/README.md`
- `obsidian-clipper/docs/Clip web pages.md`
- `obsidian-clipper/docs/Variables.md`
- `obsidian-clipper/docs/Filters.md`
- `obsidian-clipper/docs/Troubleshoot Web Clipper.md`
- `obsidian-clipper/src/content.ts`
- `obsidian-clipper/src/utils/content-extractor.ts`
- `obsidian-clipper/src/utils/filters/markdown.ts`
- `obsidian-clipper/package.json`

### 官方 / 一手资料

- Obsidian Web Clipper 文档: <https://help.obsidian.md/web-clipper>
- Obsidian Web Clipper 仓库: <https://github.com/obsidianmd/obsidian-clipper>
- Defuddle 仓库: <https://github.com/kepano/defuddle>
- Mozilla Readability: <https://github.com/mozilla/readability>
- Trafilatura: <https://github.com/adbar/trafilatura>
- Turndown: <https://github.com/mixmark-io/turndown>
- Pandoc Manual: <https://pandoc.org/MANUAL.html>

---

## 20. 一句话版总结

网页内容提取解决的是“从复杂网页里拿到干净、结构化、可保存的主内容”，Markdown 生成解决的是“把这些结构稳定地表达出来”；最实用的做法永远不是只靠一个转换器，而是“正文提取 + 元数据提取 + HTML 标准化 + Markdown 转换 + 模板覆盖 + 人工兜底”的组合方案。
