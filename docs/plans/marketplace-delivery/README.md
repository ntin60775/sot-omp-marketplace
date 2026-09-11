---
node_type: plan
title: Поставка OntoShip через маркетплейс (переезд разработки в sot-omp-marketplace)
service: _platform
status: archived
updated: 2026-09-11
links:
  depends_on: [../README.md, ../../README.md]
  documents: [../../../plugins/ontoship/commands, ../../../plugins/ontoship/rules]
---

> **Не исполнять.** Подход этого плана (каталог и дом разработки в одном
> репозитории, относительный источник, догфуд-копия через `sync-package.sh`)
> заменён решением [«доставка плагинами»](../../decisions/plugin-delivery.md)
> от 2026-09-11: плагины живут в своих репозиториях и подключаются по тегу.
> Тикеты оставлены как история.

# Контракт: поставка обновлений через omp-маркетплейс

> Перенесён из `ntin60775/ontoship-omp` (там оставлен указатель-дубликат со
> `status: deprecated`). Топология обновлена 2026-08-30: разработка живёт
> **здесь**, плагин публикуется **отсюда** (`source: "./plugins/ontoship"`,
> без git-subdir-обхода через другой репо). `ontoship-omp` — первый клиент.

## Goal

OntoShip-движок (skills + commands + rules + `gitmark.py`) становится плагином
`ontoship` этого маркетплейса и доставляется в проекты штатным `/marketplace`:
один `omp plugin upgrade` — обновление, копирование `.omp/` руками уходит.
Проектные данные (`AGENTS.md`, `docs/` KB) плагином не поставляются и
обновлениями не затираются.

## Done

- Каталог `.omp-plugin/marketplace.json` засеян (`name: "sot-omp-marketplace"`,
  `plugins: []`); первый релиз добавляет запись `ontoship` с
  `source: "./plugins/ontoship"`, `version: "0.2.0"`.
- `plugins/ontoship/package.json` (`name: "ontoship"`, `version`) — метаданные
  и источник для `gitmark version`; авторитетна для upgrade версия каталога
  (фолбэк на манифесты внутри плагина не читается — проверено, даёт 0.0.0),
  bump обязателен в `marketplace.json`.
- Все ссылки на CLI в `plugins/ontoship/**` переведены с
  `python3 .omp/skills/kb-search/gitmark.py` на
  `python3 skill://kb-search/gitmark.py` (резолв `skill://` в bash проверен
  экспериментально: работает и из нативной установки, и из кэша плагина;
  старый путь в проекте-потребителе дохнет Errno 2 — перевод обязателен).
- Новые команды: `plugins/ontoship/commands/init.md` (`/ontoship:init` — пишет
  `AGENTS.md` из шаблона, gitignore-строки `.gitmark/`, `*-map.html`,
  `.scratch/`, зовёт `/ontoship:onto-doc`; идемпотентна) и `commands/upgrade.md`
  (`/ontoship:upgrade` — пакетный апгрейд по реестру `~/ontoship-projects.txt`,
  для каждого проекта: `omp plugin upgrade` + пересборка индекса; без реестра —
  текущий проект).
- `gitmark.py`: `version` читает `package.json` подъёмом от скрипта
  (канон `plugins/ontoship/package.json`, dogfood `.omp/package.json`, корень
  плагина в кэше потребителя); фолбэк — константа `VERSION`. Авто-резолв
  корня — по cwd (не по расположению скрипта) — проверить тестом.
- `scripts/sync-package.sh` копирует в `.omp/` также `package.json` (иначе
  dogfood-копия не видит версию).
- `deploy-check.sh` переработан под плагин: движок находится через `skill://`
  с фолбэком на `.omp/skills/kb-search/gitmark.py`; проверки AGENTS.md,
  bootstrap KB и gitignore-строк остаются.
- Миграция клиента `ontoship-omp`: install `ontoship@sot-omp-marketplace`
  (user-scope), снос `.omp/skills|commands|rules|scripts` и `tests/` из
  рабочего дерева репо (тесты gitmark живут здесь), `AGENTS.md`/`docs/`
  остаются; в `docs/ops/deploy-ontoship.md` (клиентский) — поток установки.
  Runbook релиза — `docs/ops/release-ontoship.md` здесь.
- ADR `docs/decisions/marketplace-delivery.md`: доставка = omp-маркетплейс,
  разработка в каталоге; уточняет ADR `omp-only-package` клиента (тот запрет
  был про Claude Code marketplace, omp-нативный канал не противоречит).
- Уже сделано при переезде (2026-08-30): каталог-заглушка,
  `plugins/ontoship/package.json` (0.1.0), `LICENSE`, `tests/test_gitmark.py`
  (канон — `plugins/ontoship/.../gitmark.py`, 9 passed), bootstrap-секция в
  `AGENTS.md`, реестр `docs/reference/commands.md` перенацелен на
  `plugins/ontoship/` вместо gitignore-копии.
- Уже сделано на сборке KB (2026-08-30): runbook `docs/ops/release-ontoship.md`,
  ADR топологии `docs/decisions/marketplace-topology.md`, вся остальная KB
  (`docs/services/`, `docs/reference/`, `docs/ops/`) — план переведён в
  форму папки этим прогоном `/to-tickets`.

## Scope

- `plugins/ontoship/**` (пути CLI, package.json, init.md, upgrade.md,
  gitmark.py), `.omp-plugin/marketplace.json`, `docs/` этого репо
  (runbooks, ADR, план), `scripts/sync-package.sh`.
- Клиент `ontoship-omp`: только миграционные действия (install, снос копий,
  депокейт-док, ADR-поправка) — отдельным прогоном после первого релиза.
- Не входит: прочие плагины маркетплейса; CI-релизы; подписи; миграция
  сторонних проектов (список появится позже — онтошип первый клиент).

## Constraints

- `stop-before-commit` (ship-gate).
- Префикс `ontoship:` в потребителях принят; короткие имена остаются в этом
  репо (native-провайдер приоритетнее claude-plugins) и в клиенте до сноса копий.
- Версии — строгий semver в каталоге, bump на каждый релиз.
- Корневой `.omp/` этого репо — генерируемая копия (gitignore), руками не
  правится; источник — `plugins/ontoship/`.

## Context

Проверено экспериментом на живом omp v18.0.6 (probe-маркетплейсы + установка
реального ontoship-omp по SSH):
1. rules из маркетплейс-плагина доставляются, `alwaysApply` срабатывает (вопреки
   перечню rules-провайдеров в доке `rulebook-matching-pipeline`);
2. команды префиксуются `<plugin>:<command>` и исполняются из кэша;
3. `bash skill://<skill>/<file>` резолвится в реальный путь (в т.ч. кэш
   `~/.omp/plugins/cache/...`); старый относительный путь в потребителе ломается;
4. user-scope виден во всех проектах; project-scope тенит user-scope; повторный
   upgrade идемпотентен; bump версии в каталоге → installPath переезжает в кэш
   новой версии;
5. `installed_plugins.json` хранит абсолютные пути в кэш — не коммитится;
6. `gitmark index` — полное перестроение (DELETE+INSERT), миграций схемы нет:
   после upgrade достаточно `gitmark index`;
7. `ref` на несуществующий тег падает явной ошибкой клона; git-subdir на скрытый
   `.omp` работает (наследие старой топологии — больше не используется, источник
   теперь relative `./plugins/ontoship`).

## Tickets

Порядок — по зависимостям; `/ship` — строго по одному, последовательно.

1. [01-версия-из-манифеста](01-version-from-manifest.md) — `gitmark version`
   читает `package.json`, sync копирует манифест в `.omp/` — draft, без блокировщиков.
2. [02-CLI на skill://](02-skill-path-migration.md) — перевод всех ссылок плагина
   + переработка `deploy-check.sh` — draft, без блокировщиков (независим от 01).
3. [03-init/upgrade](03-init-upgrade-commands.md) — новые команды плагина —
   draft, blocked by 02.
4. [04-релиз 0.2.0](04-first-release-020.md) — запись в каталоге, bump, тег,
   ADR доставки — draft, blocked by 01–03.
5. [05-миграция клиента](05-client-migration.md) — `ontoship-omp` ставит плагин,
   снос копий — draft, blocked by 04 (чужой репо, отдельный прогон).
