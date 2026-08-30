---
node_type: reference
title: Анатомия плагина ontoship и dogfood-механизм
service: _platform
status: active
updated: 2026-08-30
links:
  documents: [../../plugins/ontoship/package.json, ../../scripts/sync-package.sh, ../../plugins/ontoship/scripts/deploy-check.sh]
  relates_to: [marketplace-catalog.md, commands.md, ../../AGENTS.md]
---

# Анатомия плагина `ontoship`

Пакет `plugins/ontoship/` — канонное дерево плагина (единственный источник истины):
GitMark KB (md+git, FTS5-поиск, онтология-линтер) + dev-flow «план → тикеты → ship».
Версия манифеста [`package.json`](../../plugins/ontoship/package.json) — `0.1.0`
(метаданные; для канала обновлений авторитетна версия каталога, см.
[контракт каталога](marketplace-catalog.md)).

## Дерево

```
plugins/ontoship/
  package.json                 метаданные пакета (name, version, description)
  skills/                      12 навыков
    kb-search/                 движок: gitmark.py (index/search/map/serve/stat/lint/inventory/version)
    kb-curate/                 чек-лист онтологии при правке KB
    dev-flow/                  конвейер план → тикеты → ship
    mp-grill-with-docs/        грилл + доменная модель → контракт плана
    grilling/                  грилл без записи в KB
    mp-diagnose/               цикл диагностики сложных багов
    mp-prototype/              одноразовый прототип для вопроса дизайна
    mp-handoff/                компактный handoff-документ сессии
    mp-to-tickets/             план → tracer-bullet тикеты
    mp-code-review/            двухосевой ревью (Standards/Spec)
    mp-improve-codebase-architecture/  скан deepening-возможностей → HTML-отчёт
    domain-modeling/           CONTEXT.md + docs/decisions/
  commands/                    12 команд: architecture, code-review, doc, grill,
                               grilling, handoff, kb, kb-map, onto-doc, prototype,
                               ship, to-tickets — реестр с аргументами: commands.md
  rules/                       4 правила:
    kb-first.md                (alwaysApply) искать в KB перед ответом о проекте
    kb-source-of-truth.md      (alwaysApply) md+git — истина; derived не коммитить
    ship-gate.md               (alwaysApply) код только через /ship, триггер — человек
    ship-1c.md                 (alwaysApply: false, opt-in) /ship с stop-before-commit в 1C-проектах
  scripts/deploy-check.sh      проверка развёртывания пакета в проекте
```

Полные описания команд/навыков — генерируемый [реестр](commands.md) (руками не
правится, синхронизация `gitmark inventory`).

## Dogfood-механизм

Этот репозиторий работает по собственным правилам, поэтому корневая `.omp/` —
**генерируемая копия** дерева плагина (в `.gitignore`):

```bash
./scripts/sync-package.sh           # plugins/ontoship/{skills,commands,rules,scripts} -> .omp/
./scripts/sync-package.sh --check   # доложить о дрейфе (exit 1), ничего не меняя
```

[`scripts/sync-package.sh`](../../scripts/sync-package.sh) делает `rm -rf` + `cp -r`
четырёх каталогов и вычищает `__pycache__`. Следствия:

- руками в `.omp/` не правят — правка умрёт при ближайшей синхронизации; источник —
  `plugins/ontoship/`;
- после изменения дерева плагина — `sync-package.sh`, иначе `gitmark lint` (I7) и
  реестр разъедутся с реальными командами;
- при свежем клоне репо `.omp/` нет вообще — бутстрап описан в
  [AGENTS.md](../../AGENTS.md) (sync → `gitmark index` → pytest);
- в плане поставки — будущие изменения: копировать в `.omp/` также `package.json`
  (иначе dogfood-копия не видит версию) и перевести пути CLI на `skill://`
  (состояние плана, не текущий факт).

## Проверка развёртывания

[`plugins/ontoship/scripts/deploy-check.sh`](../../plugins/ontoship/scripts/deploy-check.sh)
в проекте-потребителе: `exit 0` — пакет на месте и работает; `1` — критические
проблемы (нет ключевых файлов `.omp/`, SQLite без FTS5, сломан индекс); `2` —
предупреждения (нет trigram-токенайзера → ограничен fuzzy-поиск; `docs/` не
забутстраплен; `.gitmark/` не в `.gitignore`). Проверяет наличие файлов, FTS5/trigram,
пересборку индекса и смоук-поиск.

## Как потребители ставят плагин

Штатным каналом маркетплейса — `omp plugin install ontoship@sot-omp-marketplace`
(user- или project-scope). Контракт каталога, семантика scope и авторитет версии —
в [marketplace-catalog.md](marketplace-catalog.md).
