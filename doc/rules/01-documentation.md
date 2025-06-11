## Rule: 01-documentation-bilingual.mdc

---
description: Documentation - all docs must have EN + ZH, English primary, .zh-cn suffix for Chinese; keep in sync
globs: "**/*.md"
alwaysApply: true
---

# Documentation: Bilingual (EN + ZH)

- **All project documents must exist in two languages:** English and Chinese.
- **Primary language is English.** The canonical file is the English version (e.g. `README.md`).
- **Chinese version:** Use the same base name with a `.zh-cn` suffix before the extension (e.g. `README.zh-cn.md`).
- **Keep both versions in sync.** When updating one, update the other so content stays equivalent.

## Examples

| English (primary) | Chinese |
|-------------------|---------|
| `README.md`       | `README.zh-cn.md` |
| `doc/rules/foo.md` | `doc/rules/foo.zh-cn.md` |

## Exception: doc/rules backups

- **Rule backups** in `doc/rules/` are **English only**. No `.zh-cn` version is required for these files (see meta rule 99-).

## When editing docs

1. Prefer editing the English file first, then update the `.zh-cn` counterpart.
2. Do not remove or rename the `.zh-cn` file when renaming the English file; rename both.

## Rule: 01-documentation-structure.mdc

---
description: Documentation structure – what qualified docs under doc/ should contain (TOC, Mermaid, tree format)
globs: doc/**/*.md
alwaysApply: false
---

# Documentation structure (doc/)

Qualified documentation under `doc/` (design and feature docs) must include the following.

## Table of contents

- **Every Markdown document under `doc/`** must include a `## Table of Contents` section.
- The TOC must list headings down to the 4th level (`##`, `###`, `####`) where the document has such headings. Use indentation (e.g. 2 spaces per level) and markdown links to the corresponding heading anchors. For very long documents (e.g. 50+ top-level sections), listing down to `###` with key `####` subsections is acceptable.
- **Placement:** Put the TOC after the document title (and any metadata table or front matter) and the first `---` separator, and before the first content section (`## ...`).
- **Anchor format:** Use GitHub-style anchors: lowercase, spaces replaced by hyphens, non-alphanumeric characters (except hyphens) removed. Example: `## Foo Bar` → `#foo-bar`, `### 1.1 Section` → `#11-section`.
- When adding or significantly restructuring a doc under `doc/`, add or update the TOC so it stays accurate to level 4.

## Diagrams (Mermaid)

- **All flow diagrams and interaction diagrams** in documentation under `doc/` **must be written in Mermaid** (e.g. `sequenceDiagram`, `flowchart`, `stateDiagram`).
- Do not use ASCII-art boxes or hand-drawn-style text diagrams for flows or interactions; use Mermaid code blocks (```mermaid ... ```) so they render consistently.
- Architecture overviews, component relationships, and data flows should also use Mermaid where a diagram is needed.
- When adding or updating documentation that describes a process, user flow, or system interaction, add or update the corresponding Mermaid diagram rather than a non-Mermaid diagram.

## Directory / file tree format

- When showing **directory or file tree structure** in any doc under `doc/` (e.g. project layout, folder hierarchy), use a **tree-style format with lines**, not plain indentation-only.
- Use: `├──` for an item that has siblings below it, `└──` for the last item at that level, and `│` for the vertical line continuing from a parent. The root can be `.`.
- Example:
  ```
  .
  ├── app/
  │   ├── layout.tsx
  │   └── page.tsx
  └── package.json
  ```
- When adding or editing a doc that includes a directory or file tree, use this format so the hierarchy is clear and consistent.

## Rule: 01-mermaid-writing.mdc

---
description: Mermaid diagram syntax – avoid ()[]{} in labels; GitLab 8.13.10 compat (graph, ASCII subgraph ID, etc.)
globs: "**/*.md"
alwaysApply: false
---

# Mermaid writing rules

When writing Mermaid diagrams in Markdown, avoid the following syntax pitfalls or you may get parse errors and broken rendering.

## 1. Special characters in flowchart node labels

- **Parentheses `()`:** In Mermaid they denote a stadium-shaped node; inside `[...]` they can be parsed as syntax and cause errors (e.g. Expecting 'SQE'... got 'PS').
- **Square brackets `[]`:** Denote a rectangle; extra `[]` inside the label can close the node early.
- **Curly braces `{}`:** Denote a diamond; extra `{}` inside can close early.

**Correct approach:**

- Wrap the **entire label** in double quotes when it may contain `()`, `[]`, or `{}`, e.g. `A["e.g. RF_xxx(ctx, ...)"]`.
- Or **rephrase** to remove or replace special characters, e.g. `RF_xxx(ctx, ...)` → `RF_xxx etc`, `func ExprFunc_xxx(ctx){ return script }` → `wrapper expression function`.

```mermaid
%% BAD: parentheses inside []
A[RF_BankAccountFillInfo(ctx, ...)]

%% GOOD: quoted or rephrased
A["e.g. RF_BankAccountFillInfo etc"]
B[wrapper expression function]
```

## 2. Diamond nodes `{...}`

- Characters like `?` or parentheses inside the diamond can be misparsed; **wrap the whole label in double quotes** when in doubt: `C{"Expression compiled?"}`.

## 3. sequenceDiagram message text

- **Avoid** unescaped `()`, `[]`, semicolons, or nested double quotes in arrow labels; they often cause errors.
- **Prefer** short natural-language descriptions instead of code snippets, e.g. `RegisterFunc(ctx, map[RF_xxx]code)` → `RegisterFunc registers RF_xxx etc`, `ExecuteExpr(ctx, "RF_xxx(...)")` → `ExecuteExpr runs feature script`.

## 4. GitLab Mermaid 8.13.10 compatibility (when docs render on GitLab)

If docs must render correctly on **GitLab** (often Mermaid 8.13.10), in addition to the above:

- **Use `graph` not `flowchart`:** Write `graph LR` or `graph TB`, not `flowchart LR`, for older parser compatibility.
- **Subgraph IDs must be pure ASCII:** The subgraph **identifier** may only use letters, digits, underscores; no Chinese or spaces.
  - BAD: `subgraph 演练阶段["演练阶段"]`
  - GOOD: `subgraph phase1["演练阶段 nonlive"]` (ID is phase1, Chinese only in the label)
- **Use `/` and `+` carefully in node/edge labels:** Unquoted they can be parsed as syntax and cause errors. Rephrase (e.g. `全量/增量` → `全量增量`, `Platform + DB` → `Platform DB`) or wrap the whole label in double quotes: `A["Function Checkin / 代码合入"]`.
- **No `<br/>` inside nodes:** HTML support in 8.13.10 is unreliable; use spaces or split into multiple nodes for line breaks.
- **Do not link subgraphs directly:** Use "last node in subgraph A → first node in subgraph B" to show flow between phases; avoid `subgraphId1 --> subgraphId2` (especially with non-ASCII IDs).
  - GOOD: `A5 -->|演练通过 问题收敛| B1` (A5, B1 are nodes inside two subgraphs)

## 5. Self-check list

- flowchart/graph nodes: If the label contains `( ) [ ] { }`, either wrap the whole label in `"..."` or rephrase to a short sentence without those characters.
- **GitLab:** Use `graph`; subgraph ID pure ASCII; avoid `/` and `+` in labels or quote them; link subgraphs via nodes.
- sequenceDiagram: Keep message and Note text in natural language; avoid code-style parentheses and nested quotes.
- When unsure, **rephrase to short natural language** first, then consider quoting the original.
