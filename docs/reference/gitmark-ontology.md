---
node_type: reference
title: Онтология GitMark — словари, инварианты I1–I7, мини-парсер frontmatter
service: _platform
status: active
updated: 2026-08-30
links:
  documents: [../../plugins/ontoship/skills/kb-search/gitmark.py, ../../plugins/ontoship/skills/kb-curate/SKILL.md]
  relates_to: [commands.md, ../services/gitmark-cli/README.md]
---

# Онтология GitMark

Словарь и инварианты базы знаний. Движок — [`gitmark.py`](../../plugins/ontoship/skills/kb-search/gitmark.py)
(подкоманды `lint`, `index`, `inventory`), операционный чек-лист для человека/агента —
навык `kb-curate`. Принцип: **md + git — источник истины, поверх — онтология**
(типы объектов / свойства / типизированные связи). Всё производное (`.gitmark/`,
`*-map.html`) регенерится из md и не коммитится.

## Словари (значения вне словаря — ошибка линта)

### `node_type` (11 значений)

| Тип | Смысл |
|---|---|
| `service` | документ сервиса (папка `docs/services/<svc>/`) |
| `reference` | спецификация/контракт/справочник |
| `runbook` | операционная процедура (`docs/ops/`) |
| `gotcha` | ловушка, грабли, неочевидное поведение |
| `decision` | ADR — принятое решение (`docs/decisions/`) |
| `plan` | контракт плана (`docs/plans/<slug>.md`) |
| `ticket` | тикет плана (`docs/plans/<slug>/NN-<ticket>.md`) |
| `guide` | how-to, обучение |
| `report` | отчёт (ревью, handoff, результат исследования) |
| `index` | индекс папки (README-файл) |
| `memory` | долгоживущая заметка вне основных категорий |

Несущие (load-bearing) типы — `service`, `reference`, `runbook`, `plan`, `decision`,
`ticket`: к ним применяются повышенные требования (полный frontmatter, связи).

### `status`

`active` · `draft` · `deprecated` · `archived`. Жизненный цикл плана/тикета:
`draft` → `active` → `archived`; устаревание документа — `status: deprecated` плюс
`supersedes: [old.md]` в новом документе (см. инвариант I6).

### Ключи связей (`links:`)

| Ключ | Направление |
|---|---|
| `documents` | документ → код, который он описывает (путь от файла документа) |
| `implemented_by` | документ → код реализации (обратное к `documents`) |
| `depends_on` | документ → документ/составляющая, от которой зависит |
| `supersedes` | новый документ → вытесненный (тот обязан быть `deprecated`/`archived`) |
| `relates_to` | неклассифицированная ассоциация документ ↔ документ |
| `part_of` | документ → родительская сущность (тикет → план) |

### `service`

Словарь **не глобальный, а per-repo**: `cmd_lint` выводит его из имён всех папок под
`docs/` (`docs/ops/` → `ops`, `docs/services/gitmark-cli/` → `gitmark-cli` и т.д.) плюс
кросс-срезовой sentinel `_platform` — для документов, не принадлежащих одному сервису
(этот репозиторий использует `_platform` для всех кросс-документов). Значение вне
выведенного словаря — WARN (не ERR: словарь зависит от структуры папок).

## Инварианты I1–I7 (что проверяет `gitmark lint`)

Код проверки — `cmd_lint` в
[`gitmark.py`](../../plugins/ontoship/skills/kb-search/gitmark.py) (строки ~344–481)
и `inventory_issues` (~550–582).

| # | Уровень | Инвариант |
|---|---|---|
| I1 | ERR | Несущий документ в bearing-папке (`docs/reference/`, `docs/ops/`, `docs/plans/`, `docs/decisions/`, `docs/services/`) обязан иметь frontmatter с `node_type`. `README.md` папок — исключение (индексы получают frontmatter по соглашению, но линт их не требует). |
| I2 | ERR/WARN | Значения строго в словарях: `node_type` вне словаря — ERR; `service`/`status` вне — WARN. |
| I3 | WARN | Нет сирот: несущий тип обязан иметь хотя бы одну связь — входящую или исходящую markdown-ссылку в теле, либо непустой блок `links:`. |
| I4 | ERR | Битых `.md`-ссылок в теле нет: каждая markdown-ссылка, оканчивающаяся на `.md` (не `http`/`mailto`), обязана резолвиться в существующий документ. Ссылки внутри fenced/inline-кода вырезаются (`strip_code`) и не проверяются. |
| I5 | WARN | На каждую папку под `docs/` — свой `README.md` (индекс). |
| I6 | WARN | Цель `supersedes:` помечена `deprecated` или `archived` — иначе вытеснение не оформлено. |
| I7 | ERR | Реестр [`commands.md`](commands.md) синхронен дереву `.omp/`: таблицы между маркерами `<!-- BEGIN inventory:commands|skills -->` совпадают с генерацией, у каждой команды есть `args:` и `drives:` во frontmatter, секции `## /cmd` и файлы команд образуют одну пару. Лечится `gitmark inventory`. |

## Мини-парсер frontmatter (почему нельзя вложенный YAML)

`parse_frontmatter` — рукописный, на stdlib (без pyyaml). Понимает ровно два
конструкта:

- скаляр: `key: value`;
- плоский inline-список: `key: [a, b, c]`.

Следствия, которые нужно принимать всерьёз:

1. Блок `links:` с вложенными ключами (`links:` и на следующей строке с отступом
   `documents: [...]`) парсится так: `links` становится пустым маркером `{}`, а
   вложенные ключи **поднимаются на верхний уровень**. Значения сохраняются,
   вложенность — нет. Поэтому согласованное репо написание (скаляры + inline-списки
   под `links:`) работает, а многострочные YAML-блоки `- item` внутри `links:` или
   вложенные мапы вида `links: { documents: { ... } }` — лгут читателю: линт их не
   увидит.
2. Комментариев внутри frontmatter парсер фактически нет — строки `#` пропускаются,
   всё остальное без `:` игнорируется: опечатка в синтаксисе тихо съедает поле, а не
   падает ошибкой. Отсюда правило: минимальный набор полей (`node_type`, а для
   несущих — `title`, `service`, `status`, `updated`) и ничего экзотического.
3. Граф связей для `index` строится из **markdown-ссылок в теле** (`LINK_RE` +
   `resolve_link`), а не из frontmatter. Поэтому ≥1 реальная ссылка в теле — не
   косметика, а то, что делает документ несиротой в графе и проверяет I4.

## Source of truth vs derived

| Артефакт | Природа |
|---|---|
| `docs/**.md`, README-индексы, frontmatter | источник истины (git) |
| `.gitmark/index.db` (FTS5 + trigram, таблицы `files`/`links`) | derived — `gitmark index`, в gitignore |
| `*-map.html` (обзор/граф) | derived — `gitmark map`, в gitignore |
| [`commands.md`](commands.md) между маркерами `inventory:*` | derived-секции внутри source-файла — руками не правятся, чинятся `gitmark inventory` |

## См. также

- [Реестр команд и навыков](commands.md) — объект инварианта I7
- [GitMark CLI (сервис)](../services/gitmark-cli/README.md) — движок онтологии
