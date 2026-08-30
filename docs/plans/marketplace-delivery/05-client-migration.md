---
node_type: ticket
title: Миграция клиента ontoship-omp
service: _platform
status: draft
updated: 2026-08-30
links:
  part_of: [README.md]
  depends_on: [04-first-release-020.md]
---

# 05: Миграция клиента ontoship-omp

**What to build:** `ontoship-omp` становится первым клиентом маркетплейса:
в нём ставится `ontoship@sot-omp-marketplace` (user-scope), из рабочего дерева
сносятся ручные копии `.omp/skills|commands|rules|scripts` и `tests/` (тесты
gitmark живут в этом репо), проектные `AGENTS.md` и `docs/` остаются нетронутыми.
В клиентском `docs/ops/deploy-ontoship.md` — поток установки; после `upgrade`
достаточно пересборки индекса (миграций схемы у gitmark нет — полное
перестроение). Работа в **чужом репо** — отдельный прогон `/ship` после релиза.

**Blocked by:** 04 (ставить нечего до первого релиза).

- [ ] В ontoship-omp: `omp plugin install ontoship@sot-omp-marketplace` (user-scope) успешен
- [ ] Копии движка/команд/правил/тестов удалены из рабочего дерева клиента; `AGENTS.md` и `docs/` клиента целы, git-история не тронута
- [ ] `deploy-check.sh` в клиенте: exit 0 (движок найден через skill://)
- [ ] Смоук в клиенте: `/ontoship:kb <запрос>` находит местный docs; `gitmark index` пересобирается
- [ ] Клиентский `docs/ops/deploy-ontoship.md` описывает install/upgrade-поток; ссылки клиента на удалённые копии исправлены (lint клиента чистый)
- [ ] Правки KB клиента закоммичены в клиенте по его правилам (stop-before-commit — человек смотрит диф)
