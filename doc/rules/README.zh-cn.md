# Rules 备份 (doc/rules)

本目录存放 `.cursor/rules/` 下所有 Cursor rules 的 **备份**，按 **一个文件一个分类** 组织，便于浏览。Rule 备份 **仅英文**，不要求 `.zh-cn` 版本。

## 规则编号前缀

| 前缀 | 分类       | 备份文件           |
|------|------------|--------------------|
| 01   | 文档类     | `01-documentation.md` |
| 02   | 自动化与构建 | `02-build-deploy.md` |
| 10   | 编码（通用） | `10-coding.md`     |
| 11–19 | 编码（按语言） |（在 `10-coding.md` 中分节） |
| 99   | 元规则     | `99-meta.md`       |

元规则使用 **99-** 前缀，避免与其他分类混淆。

## 文件约定

- 每个 **分类** 一个 Markdown 文件（如 `01-documentation.md`、`99-meta.md`）。
- 每个文件包含还原该分类下 rule(s) 所需的完整内容（frontmatter + 正文）。
- 若某分类下有多条 rule，用清晰的小节标题（如 `## Rule: 11-coding-python.mdc`）分隔，便于还原时拆分。
- 此处备份 **不提供 .zh-cn**，仅英文。

## 还原步骤

1. 打开对应分类的备份（如 `doc/rules/99-meta.md`）。
2. 若文件中 **只有一条 rule**：将其完整内容复制到 `.cursor/rules/<name>.mdc`（如 `99-meta-rules-backup.mdc`）。
3. 若文件中有 **多条 rule**：按小节拆分，将每段写入对应的 `.cursor/rules/<name>.mdc`。

## 新增 rule 时

1. 在 `.cursor/rules/` 下按正确前缀（01、02、10–19 或 99）创建 `.mdc`。
2. 在 `doc/rules/` 下新增或更新该 **分类** 的备份（例如在 `10-coding.md` 中为新的 `11-coding-python.mdc` 增加一节）。Rule 备份保持仅英文。

## 原则

**此处的备份文档必须能完整还原** `.cursor/rules/` 中的每一条 rule，不丢失内容或行为。完整编号与备份策略见元规则（99-）。
