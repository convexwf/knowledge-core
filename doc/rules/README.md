# Rules Backup (doc/rules)

This directory holds **backup copies** of all Cursor rules from `.cursor/rules/`, organized **one file per category** for easier browsing. Rule backups are **English only** (no `.zh-cn` required here).

## Rule number prefixes

| Prefix | Category | Backup file |
|--------|----------|-------------|
| 01 | Documentation | `01-documentation.md` |
| 02 | Automation & build | `02-build-deploy.md` |
| 10 | Coding (general) | `10-coding.md` |
| 11–19 | Coding (per language) | (sections in `10-coding.md`) |
| 99 | Meta | `99-meta.md` |

Meta rules use **99-** to avoid confusion with other categories.

## File layout

- One Markdown file per **category** (e.g. `01-documentation.md`, `99-meta.md`).
- Each file contains the full content (frontmatter + body) needed to restore the rule(s) in that category.
- If a category has multiple rules, use clear section headers (e.g. `## Rule: 11-coding-python.mdc`) so they can be split when restoring.
- **No `.zh-cn` versions** for these backups; English only.

## Restore procedure

1. Open the category backup (e.g. `doc/rules/99-meta.md`).
2. If the file has **one rule**: copy its full content to `.cursor/rules/<name>.mdc` (e.g. `99-meta-rules-backup.mdc`).
3. If the file has **multiple rules**: split by the section headers and write each block to the corresponding `.cursor/rules/<name>.mdc`.

## Adding a new rule

1. Create the `.mdc` in `.cursor/rules/` with the correct prefix (01, 02, 10–19, or 99).
2. Add or update the **category** backup in `doc/rules/` (e.g. add a section to `10-coding.md` for a new `11-coding-python.mdc`). Rule backups stay English only.

## Principle

**Backup documents here must be sufficient to fully restore every rule** in `.cursor/rules/` without losing content or behavior. See the meta rule (99-) for the full numbering and backup policy.
