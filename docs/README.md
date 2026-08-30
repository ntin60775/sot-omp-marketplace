---
node_type: index
title: sot-omp-marketplace — KB
service: _platform
status: active
updated: 2026-08-30
---

# Knowledge base

This repo is a personal **omp marketplace** (catalog + plugin sources). Entry
point: [../AGENTS.md](../AGENTS.md).

## Services

- [Сервисы](services/README.md) — карточки подсистем
  - [GitMark CLI](services/gitmark-cli/README.md) — движок KB: FTS5-поиск, lint I1–I7, реестр, карта
  - [dev-flow](services/dev-flow/README.md) — цикл поставки: план → тикеты → `/ship`

## Reference

- [Reference](reference/README.md) — справочники:
  [онтология GitMark](reference/gitmark-ontology.md),
  [контракт каталога](reference/marketplace-catalog.md),
  [пакет ontoship](reference/ontoship-package.md),
  [реестр команд](reference/commands.md)

## Ops

- [Ops](ops/README.md) — процедуры:
  [релиз ontoship](ops/release-ontoship.md),
  [bootstrap после клона](ops/bootstrap-after-clone.md)

## Decisions

- [Decisions](decisions/README.md) — ADR:
  [топология маркетплейса](decisions/marketplace-topology.md) (принята 2026-08-30)

## Plans

- [Plans](plans/README.md) — план-контракты (разработка идёт отсюда)
