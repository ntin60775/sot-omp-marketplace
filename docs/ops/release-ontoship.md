---
node_type: runbook
title: Релиз плагина
service: _platform
status: active
updated: 2026-09-11
links:
  documents: [../../.omp-plugin/marketplace.json]
  relates_to: [../decisions/plugin-delivery.md]
---

# Релиз плагина

Плагины разрабатываются в своих репозиториях, здесь живёт только запись каталога.
Релиз — это тег в репозитории плагина плюс обновление записи.

1. **В репозитории плагина**: изменения, его собственные проверки, тег, push.

   ```bash
   cd ~/home/dev/personal/1c-omp
   git tag -a v0.2.0 -m "v0.2.0 — что изменилось"
   git push --tags
   ```

2. **В каталоге** — `.omp-plugin/marketplace.json`: bump `version` и `ref` записи.

3. **Потребители**:

   ```bash
   omp plugin marketplace update sot-omp-marketplace
   omp plugin upgrade <plugin>@sot-omp-marketplace
   ```

## Почему источник — отдельный репозиторий с тегом

Относительный путь (`./plugins/x`) не пинится ничем: установка берёт содержимое
из клона каталога, то есть HEAD ветки. Две машины, поставившие плагин в разные
недели, получают разные правила, и «у нас одинаково» не гарантируется. Тег
фиксирует содержимое. Подробнее — [ADR «доставка плагинами»](../decisions/plugin-delivery.md).

## Приватные репозитории

Источник — SSH-URL: установщик клонирует по HTTPS и на приватном репозитории
получает `Repository not found. Authentication failed`, если не настроен
credential helper.
