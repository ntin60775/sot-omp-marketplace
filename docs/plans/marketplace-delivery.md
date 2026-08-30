---
node_type: plan
title: Поставка OntoShip через маркетплейс (переезд разработки в sot-omp-marketplace)
service: _platform
status: draft
updated: 2026-08-30
links:
  depends_on: [README.md, ../README.md]
  documents: [../../plugins/ontoship/commands, ../../plugins/ontoship/rules]
---

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
