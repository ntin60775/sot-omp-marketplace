---
node_type: index
title: Ops — эксплуатационные процедуры
service: _platform
status: active
updated: 2026-08-30
links:
  relates_to: [../README.md]
---

# Ops

Процедуры обслуживания этого репозитория и выпуска плагинов.

- [Релиз плагина](release-ontoship.md) — тег в репозитории плагина → bump записи
  каталога → upgrade у потребителей
- [Обновление потребителей](upgrade-consumers.md) — реестр машины, раздача
  (`check` → `upgrade` → `verify`), снятие плоских копий, частые отказы
- [KB после свежего клона](bootstrap-after-clone.md) — установка плагина, индекс,
  линтер, тесты; регулярное обслуживание KB
