---
node_type: ticket
title: Версия движка из манифеста пакета
service: _platform
status: draft
updated: 2026-08-30
links:
  part_of: [README.md]
---

# 01: Версия движка из манифеста пакета

**What to build:** `gitmark version` докладывает версию пакета, а не зашитую
константу: скрипт поднимается от своего расположения до `package.json`
(канон `plugins/ontoship/`, dogfood-копия `.omp/`, корень плагина в кэше
потребителя) и читает `version`; если манифеста нет — фолбэк на константу
`VERSION`. Чтобы dogfood-копия тоже видела версию, `scripts/sync-package.sh`
копирует в `.omp/` и `package.json`.

**Blocked by:** None (can start immediately).

- [ ] В этом репо `gitmark version` печатает версию из `plugins/ontoship/package.json` (сейчас 0.1.0), а не константу
- [ ] После `./scripts/sync-package.sh` в `.omp/` появляется `package.json`, и копия показывает ту же версию
- [ ] `./scripts/sync-package.sh --check` учитывает `package.json` (дрейф по нему ловится)
- [ ] Резолв корня по cwd (не по расположению скрипта) покрыт тестом в `tests/` против канона; `python3 -m pytest tests/` зелёный
- [ ] Фолбэк на константу при отсутствии манифеста покрыт тестом
