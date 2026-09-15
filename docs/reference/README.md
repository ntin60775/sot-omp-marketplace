---
node_type: index
title: Reference — справочники разработки маркетплейса
service: _platform
status: active
updated: 2026-09-14
---

# Reference

- [commands.md](commands.md) — реестр команд и навыков; пуст, потому что
  репозиторий собственного omp-пакета не несёт (команды живут в репозиториях
  плагинов). Таблицы генерируются `gitmark inventory`
- [gitmark-ontology.md](gitmark-ontology.md) — онтология GitMark: словари, инварианты
  I1–I8, мини-парсер frontmatter
- [marketplace-catalog.md](marketplace-catalog.md) — контракт каталога
  `.omp-plugin/marketplace.json`: версии, source, scope, кэш
- [consumer-registry.md](consumer-registry.md) — реестр потребителей машины:
  `.consumers.json` + схема, виды дрейфа, контракт инструмента `scripts/consumers.py`
- [consumer-repo-layout.md](consumer-repo-layout.md) — раскладка репозитория-потребителя
  и политика `.gitignore`: что доставлено (игнорируется) и что своё (версионируется)
- [ontoship-package.md](ontoship-package.md) — анатомия плагина `ontoship`
