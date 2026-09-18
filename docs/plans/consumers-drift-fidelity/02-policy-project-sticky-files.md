---
node_type: ticket
title: Политика проектных sticky-файлов — .omp/RULES.md и .omp/APPEND_SYSTEM.md версионируются
service: _platform
status: draft
updated: 2026-09-18
links:
  part_of: [README.md]
---

# 02: Политика проектных sticky-файлов

**What to build:** политика перестаёт требовать от проектов игнорировать их
собственные файлы.

`REQUIRED_IGNORES` (в `scripts/consumers.py`) и канонический блок
[consumer-repo-layout](../../reference/consumer-repo-layout.md) держат
`.omp/RULES.md` и `.omp/APPEND_SYSTEM.md` как «машинный слой, доставляется
sync-скриптом». Для проектных путей это неверно:

- `sot-omp-core/sync.sh` кладёт машинный слой в `~/.omp/agent/` — в проекты он не
  пишет;
- `<cwd>/.omp/APPEND_SYSTEM.md` и `<cwd>/.omp/RULES.md` omp читает как **проектные**
  файлы (project-first discovery: `system-prompt-customization`, `context-files`);
- практика это подтверждает: `erp-demo` держит в `.omp/APPEND_SYSTEM.md` «Роль
  проекта» и сознательно версионирует его — и получает красный `gitignore`-дрейф;
  `retail`, `zupupr`, `erp-main`, `project-bp` версионируют `.omp/RULES.md`.

Правка: убрать обе строки из константы **и** из канонического блока (тест сверяет
одно с другим — меняются обе стороны одним коммитом), перенести их в раздел «Что
версионируется» с оговоркой: **копия плагинного правила** под этими именами —
по-прежнему вторая правда, но ловится она ревью и миграцией, а не
gitignore-проверкой (проверка смотрит пути, а не содержимое).

**Blocked by:** None (can start immediately).

- [ ] `REQUIRED_IGNORES` не содержит `.omp/RULES.md` и `.omp/APPEND_SYSTEM.md`
- [ ] Канонический блок `consumer-repo-layout.md` обновлён теми же строками; тест
      сверки константы с документом зелёный
- [ ] Раздел «Что версионируется» называет оба пути и объясняет, почему (проектные
      файлы omp; машинный слой живёт в `~/.omp/agent/`), с оговоркой про копии
      плагинных правил
- [ ] Фикстура «`.omp/*` + `!` для своих каталогов» не регрессирует; фикстура
      «доставленное не игнорируется» продолжает краснеть на настоящем доставленном
      (`.omp/plugins/`, `.omp/mcp.json`, `.gitmark/`)
- [ ] `python3 -m pytest tests/` зелёный; `gitmark lint` зелёный
- [ ] На живой машине: `check` зелёный на `erp-demo` **без правок в проекте**;
      остальные 11 потребителей не изменились
