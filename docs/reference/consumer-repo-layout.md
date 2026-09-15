---
node_type: reference
title: Раскладка репозитория-потребителя и политика .gitignore
service: _platform
status: active
updated: 2026-09-15
links:
  documents: [../../.consumers.json]
  depends_on: [../decisions/plugin-delivery.md, consumer-registry.md]
  relates_to: [../ops/upgrade-consumers.md, ../plans/consumer-delivery.md]
---

# Раскладка репозитория-потребителя

Одно правило: **доставленное не версионируется, своё — версионируется.** Всё, что
приходит плагинами каталога или машинным слоем, живёт в своих репозиториях; копия в
проекте — это вторая правда, которая расходится с первой (ровно тот дрейф, от которого
уходим, см. [решение о поставке](../decisions/plugin-delivery.md)).

## Что игнорируется

| Путь | Почему |
|---|---|
| `.omp/plugins/` | состояние установки и `node_modules` — машинное, воспроизводится `omp plugin install` |
| `.omp/skills/`, `.omp/commands/`, `.omp/scripts/` | payload плагинов: источник истины — их репозитории, версия пинится записью каталога |
| `.omp/RULES.md`, `.omp/APPEND_SYSTEM.md` | машинный слой (`sot-omp-core`), доставляется sync-скриптом |
| `.omp/mcp.json` | локальная конфигурация MCP (порты, пути машины) |
| `.omp/.backup-*` | локальные бэкапы перед снятием копий |
| `.gitmark/`, `*-map.html` | производное KB — пересобирается `gitmark index` / `map` из markdown |
| `.scratch/`, `.artifacts/` | локальные рабочие артефакты агента |

## Что версионируется

| Путь | Почему |
|---|---|
| `.omp/rules/` | **свои** правила проекта — под именами, не совпадающими с плагинными (ADR §6). После снятия копий здесь только своё |
| `.omp/extensions/` | проектные расширения-хуки (например, гейты `unica-gate.ts`) |
| `.omp/TECH_DEBT.md`, `.omp/unica-gate-escalations.txt` | решения и разрешённые исключения проекта |
| `.omp/skills/<свой>/`, `.omp/commands/<своя>.md` | если проект заводит собственные навыки/команды — force-add (`git add -f`) |
| `AGENTS.md`, `docs/`, `tasks/`, `src/`, `tests/`, `features/`, `fixtures/`, `tools/` | содержимое проекта |

## Канонический блок для `.gitignore`

```gitignore
# --- omp: поставка плагинами (каталог sot-omp-marketplace) ---
# Доставленное не версионируется здесь: источник истины — репозитории плагинов и
# машинный слой (sot-omp-core). В проекте версионируется только своё:
# .omp/rules/ (имена не совпадают с плагинными), .omp/extensions/,
# .omp/TECH_DEBT.md, .omp/unica-gate-escalations.txt.
.omp/plugins/
.omp/skills/
.omp/commands/
.omp/scripts/
.omp/RULES.md
.omp/APPEND_SYSTEM.md
.omp/mcp.json
.omp/.backup-*

# Производное KB (пересобирается из markdown) и локальные артефакты
.gitmark/
*-map.html
.scratch/
.artifacts/
```

Осторожно с огульным `.omp/`: он закрывает и `.omp/rules/`, а значит **потеряет свои
правила проекта** при клоне. Если в репозитории стоит именно `.omp/`, замените его на
блок выше и добавьте свои файлы (`git add -f .omp/rules/…`).

## Переходный случай: копии уже в git

До поставки копии пакета могли быть закоммичены (так было в `erp-main`, `retail`,
`subvost-xray-tun`, `rusbread-master-site`). После `migrate --apply` они удаляются из
рабочего дерева — это **трекаемые удаления**, их надо закоммитить вместе с новым
`.gitignore`, иначе репозиторий останется в полу-состоянии: файлы в индексе есть, на
диске их нет.

Проверить состояние потребителя целиком: `python3 scripts/consumers.py check`
(дрейф, свои файлы, хук ворктри) и `verify` (индекс, `deploy-check`, версия движка).

> **Оговорка на 2026-09-15.** Часть правил этого блока движок GitMark пока не
> понимает: правило с `/` без хвостового слэша (`.omp/.backup-*`, `.omp/RULES.md`,
> `.omp/mcp.json`) теряется молча, а шаблон каталога с путём (`.omp/skills/`,
> `.omp/commands/`) не матчится никогда. Для git эти файлы игнорируются, для индекса
> KB — нет: пока правка не выпущена, каталоги бэкапов и копий могут попадать в
> `gitmark search`. Симптом, обход и проверка — gotcha
> `ontoship-omp/docs/ops/gotcha-gitignore-rules-with-path.md`, правка — план
> `gitignore-parser.md` в том же репозитории.
