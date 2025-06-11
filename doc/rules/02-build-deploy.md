---
description: Automation & build (02) – generic maintainability; no language-specific build rules
alwaysApply: false
---

# Automation & Build (02)

This category holds **generic** automation, build, and deployment rules. Language-specific build rules (e.g. Go, Godot) live under 11–19 (e.g. 11-coding-go.mdc, 12-coding-godot.mdc).

## Long-term vs temporary

- **Do not add temporary or one-off fixes to long-term maintained files** (e.g. Makefile, core config). Keep Makefile and similar files for stable, lasting targets only. Fix the root cause or document the rule instead of special-case cleanup.

## When adding rules

- Create the rule in `.cursor/rules/` with prefix 02-, and add or update the backup in `doc/rules/02-build-deploy.md` (English only).
