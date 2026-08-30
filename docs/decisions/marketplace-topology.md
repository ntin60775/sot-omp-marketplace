---
node_type: decision
title: Топология маркетплейса: один репо = каталог + дом разработки
service: _platform
status: active
updated: 2026-08-30
links:
  documents: [../../.omp-plugin/marketplace.json, ../../scripts/sync-package.sh]
  relates_to: [../../AGENTS.md, ../plans/marketplace-delivery/README.md]
---

# ADR: Топология маркетплейса (принята 2026-08-30)

## Контекст

OntoShip (GitMark KB + dev-flow) переезжает в этот репозиторий из отдельного
`ntin60775/ontoship-omp`. Прежний канал доставки — ручное копирование `.omp/`
в проекты-потребители — не масштабируется: обновления не штатные, а
разработка плагина и её публикация разведены по разным репо. Нужна схема, при
которой обновления доставляются стандартным `omp plugin upgrade`.

## Решение

Зафиксирована в [AGENTS.md](../../AGENTS.md) (секция «Topology decision
(2026-08-30)»):

1. **Дом разработки — репозиторий-каталог.** Дальнейшая разработка плагина
   `ontoship` живёт в `sot-omp-marketplace` (`plugins/ontoship/`), а не в
   `ontoship-omp`.
2. **Публикация — отсюда же.** Запись каталога `.omp-plugin/marketplace.json`
   указывает на `source: "./plugins/ontoship"` (relative) — без
   git-subdir-обхода через другой репозиторий.
3. **`ontoship-omp` — первый клиент маркетплейса.** Он ставит
   `ontoship@sot-omp-marketplace` как обычный потребитель и хранит у себя
   только свои KB-данные (`AGENTS.md`, `docs/`).
4. **Репозиторий dogfood'ит собственный пакет.** Корневая `.omp/` —
   генерируемая копия `plugins/ontoship/{skills,commands,rules,scripts}`
   (gitignore). Источник истины — дерево плагина; синхронизация —
   [`scripts/sync-package.sh`](../../scripts/sync-package.sh) (есть режим
   `--check` на дрейф).

## Следствия

- Один репозиторий совмещает каталог и дом разработки — нет рассинхрона
  «код там, каталог тут».
- Релиз = bump `version` в каталоге (+ `package.json`) и тег; каталог сейчас
  — заглушка (`plugins: []`), запись `ontoship` появится с первым релизом по
  плану.
- Правки корневой `.omp/` руками запрещены — они затираются при следующей
  синхронизации.
- Прежний канал доставки (копирование `.omp/` в проекты вручную) уходит.

## Статус

Принята 2026-08-30. Граница: здесь фиксируется **только топология**. ADR о
самой доставке (`docs/decisions/marketplace-delivery.md`) — ещё не выполненный
пункт [плана поставки](../plans/marketplace-delivery/README.md) (раздел «Done»), и
она появится вместе с его реализацией.
