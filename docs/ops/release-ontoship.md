---
node_type: runbook
title: Релиз плагина ontoship из sot-omp-marketplace
service: _platform
status: active
updated: 2026-08-30
links:
  documents: [../../.omp-plugin/marketplace.json, ../../plugins/ontoship/package.json, ../../scripts/sync-package.sh, ../../plugins/ontoship/scripts/deploy-check.sh]
  relates_to: [../plans/marketplace-delivery.md, ../reference/marketplace-catalog.md]
---

# Релиз плагина ontoship

Процедура публикации плагина из этого репозитория — детализация
[README §«Релиз плагина»](../../README.md). Каталог и теги в этом репо —
единственный канал доставки; `source` записи каталога относительный
(`./plugins/ontoship`), без git-subdir-обхода через другой репо.

## Текущее состояние (2026-08-30)

- Каталог [.omp-plugin/marketplace.json](../../.omp-plugin/marketplace.json)
  пуст: `plugins: []`, метаданные `version: 0.0.0`.
- [plugins/ontoship/package.json](../../plugins/ontoship/package.json) —
  `version: 0.1.0` (переездная заглушка, не опубликована).
- **Первый релиз (ontoship `0.2.0`) ещё не сделан** — он является предметом
  плана [marketplace-delivery.md](../plans/marketplace-delivery.md)
  (`status: draft`) и до его выполнения этот runbook описывает будущий
  повторяемый цикл, а не действующую операцию.

## Шаги релиза

### 1. Изменения в `plugins/ontoship/`

Разработка — по dev-flow (план → тикеты → ship). Дерево плагина — единственный
источник истины; корневая `.omp/` — генерируемая dogfood-копия, руками не
правится. После каждого изменения, затрагивающего `skills/`, `commands/`,
`rules/`, `scripts/`:

```bash
./scripts/sync-package.sh
```

### 2. Gate синхронности перед релизом

Обе проверки обязаны выйти с `exit 0` (см. AGENTS.md §Maintain):

```bash
python3 .omp/skills/kb-search/gitmark.py inventory --check   # дрейф KB-инвентаря → exit 1
./scripts/sync-package.sh --check                            # дрейф .omp/ vs plugins/ontoship/ → exit 1
```

### 3. Bump версии

Правятся **оба** файла на одну и ту же semver-версию:

- [.omp-plugin/marketplace.json](../../.omp-plugin/marketplace.json) —
  запись `ontoship` (`version`, `ref` на тег). **Авторитетна только она** —
  фолбэк omp на манифесты внутри плагина не читается (проверено на
  omp v18.0.6, даёт 0.0.0).
- [plugins/ontoship/package.json](../../plugins/ontoship/package.json) —
  метаданные и источник для `gitmark version`.

Версии — строгий semver, bump на каждый релиз.

### 4. Тег и push

Тег именуется `<name>-vX.Y.Z`:

```bash
git tag ontoship-vX.Y.Z
git push origin HEAD --tags
```

`ref` на несуществующий тег падает у потребителя явной ошибкой клона — тег
должен быть запушен до того, как запись каталога станет достижимой.

### 5. Потребители

Обновление установленной копии:

```bash
omp plugin marketplace update sot-omp-marketplace && omp plugin upgrade ontoship@sot-omp-marketplace
```

`gitmark index` — полное перестроение, миграций схемы нет: после upgrade
достаточно пересобрать индекс.

## Проверка после установки (потребитель)

В корне проекта-потребителя:

```bash
bash .omp/scripts/deploy-check.sh; echo "exit=$?"
```

Коды выхода: `0` — пакет на месте и работает; `1` — критические проблемы
(фикс обязателен); `2` — предупреждения (работает, но есть недочёты).

Что проверяет [deploy-check.sh](../../plugins/ontoship/scripts/deploy-check.sh):

1. **Ключевые файлы пакета**: `AGENTS.md`,
   `.omp/skills/kb-search/gitmark.py`, `.omp/commands/kb.md`,
   `.omp/commands/onto-doc.md`, `.omp/rules/kb-first.md` — отсутствие → `exit 1`.
2. **SQLite**: FTS5 обязателен; trigram-токенайзер опционален (нужен
   SQLite ≥ 3.34), без него fuzzy/substring-поиск ограничен → `exit 2`.
3. **Индекс + смоук-поиск**: пересборка `gitmark index` и поиск по «OntoShip»;
   пустой результат → индекс сломан → `exit 1`.
4. **Бутстрап KB и gitignore**: отсутствие `docs/` или строки `.gitmark/`
   в `.gitignore` → `exit 2`.

Примечание: по плану marketplace-delivery скрипт будет переработан под
плагин (движок через `skill://` с фолбэком на `.omp/skills/kb-search/gitmark.py`);
описанное выше — текущее поведение канона в этом репо.
