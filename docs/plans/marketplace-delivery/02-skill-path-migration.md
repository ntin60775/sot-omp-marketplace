---
node_type: ticket
title: CLI плагина на skill://-пути
service: _platform
status: draft
updated: 2026-08-30
links:
  part_of: [README.md]
---

# 02: CLI плагина на skill://-пути

**What to build:** все обращения к gitmark-CLI в дереве плагина (тексты команд,
правил, навыков) используют форму `python3 skill://kb-search/gitmark.py` —
резолв проверен экспериментом и из нативной установки, и из кэша плагина.
После установки плагина в проект-потребитель команды работают из кэша и не
ломаются на относительном `.omp/`-пути (в потребителе он дохнет Errno 2).
`deploy-check.sh` переработан под плагин: движок ищется через `skill://` с
фолбэком на `.omp/skills/kb-search/gitmark.py`; проверки AGENTS.md, bootstrap
KB и gitignore-строк остаются.

**Blocked by:** None (can start immediately; независим от 01 — общие файлы
отсутствуют).

- [ ] В `plugins/ontoship/**` не осталось вызовов `python3 .omp/skills/kb-search/gitmark.py` (кроме фолбэка в deploy-check)
- [ ] `./scripts/sync-package.sh && ./scripts/sync-package.sh --check` зелёные
- [ ] Смоук в этом репо: `/kb <запрос>` и `/onto-doc`-шаг stat работают через skill:// (резолвится в dogfood-копию)
- [ ] `deploy-check.sh` в этом репо: exit 0; в чистом probe-проекте с установленным плагином — движок найден через skill://
- [ ] `gitmark lint` чистый
