---
description: Meta (99-) - rule numbering, backup in doc/rules (one file per category, English only)
alwaysApply: true
---

# Meta: Rule Numbering and Backup (99-)

This rule defines how rules are numbered and how backups work. **Prefix numbers** indicate category; 99- is reserved for meta rules to avoid confusion with other categories.

## Rule number prefixes

| Prefix | Category | Description |
|--------|----------|-------------|
| 01 | Documentation | Bilingual docs (EN primary, .zh-cn for Chinese) |
| 02 | Automation & build | Build tools, CI, deployment, automation |
| 10 | Coding (general) | Cross-language or general coding standards |
| 11–19 | Coding (per language) | Language-specific rules (e.g. 11-python, 12-typescript) |
| 99 | Meta | Rules about rules (this file); use 99- to avoid confusion |

## Backup in doc/rules

- **Every rule under `.cursor/rules/` must have a backup** under `doc/rules/`.
- **One file per category** (not one file per rule): e.g. `doc/rules/01-documentation.md`, `doc/rules/02-build-deploy.md`, `doc/rules/10-coding.md`, `doc/rules/99-meta.md`. This makes backups easier to browse.
- **Rule backups are English only.** No `.zh-cn` version is required for files in `doc/rules/`; this is an exception to the documentation bilingual rule.
- **Backup content:** The category file must contain enough to **fully restore** all rule(s) in that category (full frontmatter + body for each). Use clear section headers if a category file contains multiple rules (e.g. `## Rule: 11-coding-python.mdc`).

## Restore procedure

1. Open the category backup (e.g. `doc/rules/99-meta.md`).
2. If the file has one rule: copy its content to `.cursor/rules/<name>.mdc`.
3. If the file has multiple rules: split by sections and write each block to the corresponding `.cursor/rules/<name>.mdc`.

## When adding a new rule

1. Create the `.mdc` in `.cursor/rules/` with the correct prefix (01, 02, 10–19, or 99).
2. Add or update the category backup in `doc/rules/` (e.g. add a section to `doc/rules/10-coding.md` for a new 11- or 12- rule). Rule backups stay English only.
