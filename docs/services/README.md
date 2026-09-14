---
node_type: index
title: Сервисы
service: _platform
status: active
updated: 2026-09-14
links:
  relates_to: [gitmark-cli/README.md, dev-flow/README.md]
---

# Сервисы

Карточки подсистем репозитория — по папке на сервис, `service:` во frontmatter
документов совпадает с именем папки (словарь сервисов `lint` выводит из неё).

- [GitMark CLI](gitmark-cli/README.md) — движок базы знаний: индекс FTS5 (bm25 ∪
  trigram/fuzzy), проверка онтологии I1–I8, генерация реестра команд, HTML-карта.
- [dev-flow](dev-flow/README.md) — цикл поставки поверх KB: план-контракт → тикеты →
  `/ship` вручную, один тикет за прогон, worktree → тесты → ревью → ship.
