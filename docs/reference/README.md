---
node_type: index
title: Reference — справочники разработки маркетплейса
service: _platform
status: active
updated: 2026-09-16
---

# Reference

- [commands.md](commands.md) — реестр команд и навыков плагина `ontoship`: таблицы
  генерируются `gitmark inventory` из установленного payload (собственного пакета
  репозиторий не несёт — команды живут в репозиториях плагинов)
- [gitmark-ontology.md](gitmark-ontology.md) — онтология GitMark: словари, инварианты
  I1–I8, мини-парсер frontmatter
- [marketplace-catalog.md](marketplace-catalog.md) — контракт каталога
  `.omp-plugin/marketplace.json`: версии, source, scope, кэш; источник каталога
  и имя как контракт
- [consumer-registry.md](consumer-registry.md) — реестр потребителей машины:
  `.consumers.json` + схема, заведение на новой машине (`init`, `discover --apply`),
  виды дрейфа, контракт инструмента `scripts/consumers.py`
- [consumer-repo-layout.md](consumer-repo-layout.md) — раскладка репозитория-потребителя
  и политика `.gitignore`: что доставлено (игнорируется) и что своё (версионируется);
  политику проверяет `check` (вид дрейфа `gitignore`)
- [ontoship-package.md](ontoship-package.md) — анатомия плагина `ontoship`
