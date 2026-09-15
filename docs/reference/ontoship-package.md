---
node_type: reference
title: Анатомия пакета ontoship
service: _platform
status: active
updated: 2026-09-15
links:
  relates_to: [marketplace-catalog.md, ../../AGENTS.md]
---

# Анатомия пакета `ontoship`

Пакет `ontoship` — GitMark KB (md+git, FTS5-поиск, онтология-линтер) +
dev-flow «план → тикеты → ship». Разрабатывается в собственном репозитории
`ntin60775/ontoship-omp`; в этот репозиторий он доставляется каталогом по
тегу: запись `git-subdir` с `path: ".omp"` и `ref: "v0.4.1"`
([контракт каталога](marketplace-catalog.md)). После установки пакет лежит в
`.omp/plugins/node_modules/ontoship/` (gitignore).

Для `omp plugin upgrade` авторитетна **версия записи каталога**
`marketplace.json`; `package.json` пакета живёт в `ontoship-omp` и на канал
обновлений не влияет.

## Состав доставляемого пакета

```
.omp/plugins/node_modules/ontoship/
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
  commands/                    13 команд: architecture, code-review, doc, grill,
                               grilling, handoff, init, kb, kb-map, onto-doc,
                               prototype, ship, to-tickets — реестр с аргументами:
                               commands.md
  rules/                       4 правила:
    kb-first.md                (alwaysApply) искать в KB перед ответом о проекте
    kb-source-of-truth.md      (alwaysApply) md+git — истина; derived не коммитить
    ship-gate.md               (alwaysApply) код только через /ship, триггер — человек
    acceptance-rounds.md       (alwaysApply) раунды приёмки и багфикс после основного цикла
  scripts/deploy-check.sh      проверка развёртывания пакета в проекте
```

Полные описания команд/навыков — генерируемый реестр (руками не
правится, синхронизация `gitmark inventory`).

## Проверка развёртывания

`deploy-check.sh` из доставленного пакета
(`.omp/plugins/node_modules/ontoship/scripts/deploy-check.sh`)
в проекте-потребителе. Корень пакета резолвится от расположения самого скрипта
(`pkg="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"`), поэтому скрипт
работает и в плоской установке (`<проект>/.omp/scripts/`), и в плагинной
(`<проект>/.omp/plugins/node_modules/<плагин>/scripts/`) — раскладка не хардкодится.

Проверки:

1. Ключевые файлы — от корня пакета: `skills/kb-search/gitmark.py`,
   `commands/kb.md`, `commands/onto-doc.md`, `rules/kb-first.md`, плюс `AGENTS.md`
   от корня проекта.
2. Страж мёртвого пути: FAIL, если payload ссылается на плоский
   `.omp/skills/kb-search/gitmark.py` (payload обязан использовать
   `skill://kb-search/gitmark.py`).
3. SQLite: FTS5 обязателен (exit 1 при отсутствии), trigram опционален (exit 2).
4. Движок берётся из пакета: `index` + смоук `search "OntoShip" -k 1 --json`
   (ошибка движка → FAIL, пустой результат → WARN).
5. `docs/` существует (WARN) и `.gitignore` содержит `.gitmark/`, `*-map.html`,
   `.scratch/` (WARN за каждую отсутствующую строку).

Коды возврата: `0` — ОК; `1` — критические проблемы; `2` — предупреждения.

## Как потребители ставят плагин

Штатным каналом маркетплейса — `omp plugin install ontoship@sot-omp-marketplace`
(user- или project-scope). Контракт каталога, семантика scope и авторитет версии —
в [marketplace-catalog.md](marketplace-catalog.md).
