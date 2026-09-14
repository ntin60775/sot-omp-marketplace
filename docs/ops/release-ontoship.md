---
node_type: runbook
title: Релиз плагина
service: _platform
status: active
updated: 2026-09-14
links:
  documents: [../../.omp-plugin/marketplace.json]
  relates_to: [../decisions/plugin-delivery.md]
---

# Релиз плагина

Плагины разрабатываются в своих репозиториях, здесь живёт только запись каталога.
Релиз — это тег в репозитории плагина плюс обновление записи.

1. **В репозитории плагина**: изменения, его собственные проверки, bump версии в
   манифесте, тег, push.

   ```bash
   cd ~/home/dev/personal/ontoship-omp
   # bump version в package.json (метаданные пакета) и коммит:
   #   chore(release): 0.4.0 — версия пакета в манифесте
   git tag -a v0.4.0 -m "v0.4.0 — что изменилось"
   git push --tags
   ```

   **Разделение авторитета.** Версия в `package.json` плагина — метаданные: она
   видна `gitmark version` и людям, но канал обновлений её не читает. Версию для
   `omp plugin upgrade` задаёт **запись каталога** (`version` + `ref` в
   `.omp-plugin/marketplace.json`). Бампятся обе: манифест — чтобы релиз был
   опознаваем в репозитории плагина, запись каталога — чтобы потребители получили
   новую версию.

2. **В каталоге** — `.omp-plugin/marketplace.json`: bump `version` и `ref` записи.

3. **Потребители**:

   ```bash
   omp plugin marketplace update sot-omp-marketplace
   omp plugin upgrade <plugin>@sot-omp-marketplace --scope=project
   ```

   Все потребители машины разом — реестром: `python3 scripts/consumers.py check`
   (что обновится и где стоит `pin`) → `upgrade` → `verify`. Реестр, виды дрейфа и
   контракт инструмента — [реестр потребителей](../reference/consumer-registry.md).

   > **ВНИМАНИЕ: ловушка `--scope` по умолчанию.** `omp plugin install` и
   > `omp plugin upgrade` **без** `--scope` ставят плагин в **user-scope** — он
   > становится виден во всех проектах машины. Проекты, которые пинят плагин
   > per-project, обязаны передавать `--scope=project`; иначе вместо проектной
   > установки молча появится машинная (и будет тенить/путать версии).

## Почему источник — отдельный репозиторий с тегом

Относительный путь (`./<путь>`) не пинится ничем: установка берёт содержимое
из клона каталога, то есть HEAD ветки. Две машины, поставившие плагин в разные
недели, получают разные правила, и «у нас одинаково» не гарантируется. Тег
фиксирует содержимое. Подробнее — [ADR «доставка плагинами»](../decisions/plugin-delivery.md).

## Приватные репозитории

Источник — SSH-URL: установщик клонирует по HTTPS и на приватном репозитории
получает `Repository not found. Authentication failed`, если не настроен
credential helper.
