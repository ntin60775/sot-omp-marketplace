---
node_type: service
title: dev-flow — цикл поставки поверх KB
service: dev-flow
status: active
updated: 2026-08-30
links:
  documents: [../../../plugins/ontoship/skills/dev-flow/SKILL.md, ../../../plugins/ontoship/commands/ship.md, ../../../plugins/ontoship/rules/ship-gate.md, ../../../plugins/ontoship/commands/to-tickets.md]
  relates_to: [../../plans/marketplace-delivery.md, ../../reference/gitmark-ontology.md]
---

# dev-flow

Сервис поставки: спецификацией служит сама база знаний (GitMark-онтология, см.
[gitmark-ontology](../../reference/gitmark-ontology.md)), а работа идёт по циклу
**план → тикеты → ship**. Скилл
[dev-flow/SKILL.md](../../../plugins/ontoship/skills/dev-flow/SKILL.md) описывает цикл,
команда [/ship](../../../plugins/ontoship/commands/ship.md) запускает его вручную,
правило [ship-gate](../../../plugins/ontoship/rules/ship-gate.md) закрывает объезд.
Ориентир цикла — тикет до продакшена за ~40 минут–2 часа; пример активного плана —
[marketplace-delivery](../../plans/marketplace-delivery.md).

## Форма плана-контракта

- **Файл** `docs/plans/<slug>.md` (`node_type: plan`) — пока план не разбит на тикеты.
  Поля контракта: `Goal`, `Done`, `Scope`, `Constraints` (stop-points), `Context`,
  `Tickets`.
- **Папка** `docs/plans/<slug>/` — создаёт только `mp-to-tickets`
  ([/to-tickets](../../../plugins/ontoship/commands/to-tickets.md)): он делает
  `git mv` файла в `README.md` (история сохраняется, ссылки перепишиваются на
  дополнительную глубину) и добавляет тикеты `NN-<ticket>.md` (`node_type: ticket`) —
  tracer-bullet вертикальные срезы, каждый со своими `Blocked by`.
- Жизненный цикл: plan `draft` (написан `mp-grill-with-docs`) → `active` (`/ship`
  начался) → `archived` (слит). Тикеты — аналогично. Автор контракта — только
  `mp-grill-with-docs`, тикетов — только `mp-to-tickets`.

## Роли входных скиллов

Входные скиллы (`mp-grill-with-docs`, `mp-diagnose`, `mp-prototype`, `mp-handoff`,
`mp-to-tickets`, `mp-code-review`, `mp-improve-codebase-architecture`) **код не
трогают**: они заканчиваются план-контрактом/тикетом в `docs/plans/` или отчётом
handoff/review в `.scratch/` — это предписывает ship-gate.

## /ship: только вручную, один тикет за прогон

Три жёстких правила из
[ship-gate.md](../../../plugins/ontoship/rules/ship-gate.md):

1. Изменения кода в репозитории идут **только** через dev-flow (`/ship`).
2. `/ship` запускает **только оператор руками**, агент никогда не запускает его сам.
3. Один тикет (или один файл-план) за прогон, строго последовательно; батчинг тикетов
   запрещён.

Вход `/ship` принимает: папку плана (берётся первый не-archived тикет по `NN`),
файл-план (исполняется как один срез), путь тикета, ad-hoc описание, либо пусто —
самый свежий план по `updated:`. При входе через тикет проверяется, что все `Blocked by`
уже `archived`, и что `Context` контракта не устарел; статус входа — `active`.

## Цикл

1. Research — по фактам (логи, трейсы, код), воспроизвести до починки.
2. Goal — из `What to build` тикета или `Goal`/`Done` файла-плана.
3. Isolate — отдельный `git worktree` (main чист, параллельные агенты не сталкиваются,
   откат = удалить worktree).
4. Implement — по критериям приёмки, doc↔code связаны (`implemented_by`).
5. Tests — unit + E2E как часть фичи.
6. Independent review — read-only сабагент `reviewer` по диффу (роль модели
   `@reviewer`, фолбэк `@slow`): вторая модель ловит то, что пропускает модель автора.
7. Dev-tests — MR в `dev`, полный прогон; красный — чинить в worktree, не мержить.
8. Prod-tests — E2E/smoke против реального продакшен-контура.
9. Ship — merge `dev → main` + деплой (build-before-stop, healthcheck-poll), затем
   тикет/план → `archived`.

## Stop-points

Берутся из `Constraints` контракта и являются жёсткой паузой — агент докладывает и
ждёт, сам не продолжается:

- `stop-before-commit` — после ревью остановиться с незакоммиченным диффом в worktree
  (дефолт для 1C-проектов, правило `ship-1c`);
- `stop-after-mr` — после открытия MR;
- `no-deploy` — пропустить деплой на шаге 9.
