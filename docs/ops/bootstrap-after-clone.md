---
node_type: runbook
title: Первичная сборка репозитория после свежего клона
service: _platform
status: active
updated: 2026-08-30
links:
  documents: [../../scripts/sync-package.sh, ../../AGENTS.md, ../../tests/test_gitmark.py]
  relates_to: [release-ontoship.md, ../reference/ontoship-package.md]
---

# Bootstrap после свежего клона

Корневой `.omp/` этого репозитория **не в git** — это генерируемая dogfood-копия
дерева `plugins/ontoship/{skills,commands,rules,scripts}` (см. AGENTS.md
§Topology decision). Без неё dogfood-навыки, команды и сам `gitmark` в этом
репо недоступны, поэтому после каждого свежего клона (или `git clean` в `.omp/`)
соберите окружение заново.

## Шаги

```bash
./scripts/sync-package.sh                            # plugins/ontoship/* -> .omp/
python3 .omp/skills/kb-search/gitmark.py index       # собрать поисковый индекс KB
python3 -m pytest tests/                             # канон — plugins/ontoship/.../gitmark.py
```

Ожидаемый результат:

- `sync-package.sh` печатает `sync: plugins/ontoship -> .omp выполнено`;
  в `.omp/` появляются `skills/`, `commands/`, `rules/`, `scripts/`
  (с очищенным `__pycache__`).
- `gitmark index` перестраивает `.gitmark/` (индекс производный, не коммитится).
- `pytest tests/` зелёный; тесты гоняются против канона
  [plugins/ontoship/skills/kb-search/gitmark.py](../../plugins/ontoship/skills/kb-search/gitmark.py),
  а не против копии.

Проверить, что копия не разошлась с источником:

```bash
./scripts/sync-package.sh --check    # ДРЕЙФ: <dir> → exit 1; иначе "sync: OK"
```

## Регулярное обслуживание

После любой правки документов в `docs/` (и вообще при работе с KB):

```bash
python3 .omp/skills/kb-search/gitmark.py index    # пересобрать индекс после правки docs
python3 .omp/skills/kb-search/gitmark.py lint     # проверить онтологию (I1–I7)
python3 .omp/skills/kb-search/gitmark.py map -o docs-map.html   # обновить граф (когда менялась структура)
```

Индекс и `*-map.html` — производные артефакты: только перегенерируются, никогда
не коммитятся и не правятся руками (принцип AGENTS.md §Principle).

## См. также

- [release-ontoship.md](release-ontoship.md) — цикл релиза плагина (тот же
  `sync-package.sh`, но с gate перед тегом).
