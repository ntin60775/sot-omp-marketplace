---
node_type: index
title: sot-omp-marketplace — KB
service: _platform
status: active
updated: 2026-09-14
---

# Knowledge base

This repo is a personal **omp marketplace** (catalog + KB). Entry
point: [../AGENTS.md](../AGENTS.md).

## Services

- [Сервисы](services/README.md) — карточки подсистем
  - [GitMark CLI](services/gitmark-cli/README.md) — движок KB: FTS5-поиск, lint I1–I8, реестр, карта
  - [dev-flow](services/dev-flow/README.md) — цикл поставки: план → тикеты → `/ship`

## Reference

- [Reference](reference/README.md) — справочники:
  [онтология GitMark](reference/gitmark-ontology.md),
  [контракт каталога](reference/marketplace-catalog.md),
  [реестр потребителей](reference/consumer-registry.md),
  [пакет ontoship](reference/ontoship-package.md),
  реестр команд

## Ops

- [Ops](ops/README.md) — процедуры:
  [релиз ontoship](ops/release-ontoship.md),
  [обновление потребителей](ops/upgrade-consumers.md),
  [bootstrap после клона](ops/bootstrap-after-clone.md)

## Decisions

- [Decisions](decisions/README.md) — ADR:
  [доставка плагинами](decisions/plugin-delivery.md) (принята 2026-09-11;
  заменяет [прежнюю топологию](decisions/marketplace-topology.md) от 2026-08-30)

## Plans

- [Plans](plans/README.md) — план-контракты (разработка идёт отсюда)
