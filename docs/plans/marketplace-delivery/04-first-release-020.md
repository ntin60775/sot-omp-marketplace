---
node_type: ticket
title: Первый релиз ontoship 0.2.0
service: _platform
status: draft
updated: 2026-08-30
links:
  part_of: [README.md]
  depends_on: [01-version-from-manifest.md, 02-skill-path-migration.md, 03-init-upgrade-commands.md]
---

# 04: Первый релиз ontoship 0.2.0

**What to build:** маркетплейс перестаёт быть пустой заглушкой: в
`.omp-plugin/marketplace.json` появляется запись `ontoship` с
`source: "./plugins/ontoship"` и `version: "0.2.0"`, версии bumped в обеих
точках (каталог — авторитетная; package.json — метаданные), проставлен тег
`ontoship-v0.2.0`, push. Потребитель может поставить плагин штатной командой
`omp plugin install ontoship@sot-omp-marketplace` и обновлять его
`marketplace update` + `plugin upgrade`. Вместе с релизом фиксируется ADR
`docs/decisions/marketplace-delivery.md` (доставка = omp-маркетплейс, разработка
в каталоге; уточняет клиентский ADR `omp-only-package` — тот запрет был про
Claude Code marketplace).

**Blocked by:** 01, 02, 03 (релизить skill://-ссылки и команды до их миграции —
выложить битый в потребителе пакет).

- [ ] Gates зелёные перед тегом: `gitmark inventory --check`, `sync-package.sh --check`, `pytest tests/`
- [ ] `marketplace.json`: запись `ontoship` v0.2.0, relative-source; `package.json` — та же версия
- [ ] Пробная установка из локального каталога в чистый probe-репо: install → команды с префиксом `ontoship:` резолвятся из кэша → `deploy-check` exit 0
- [ ] Повторный upgrade идемпотентен; bump версии в каталоге переезжает installPath в кэш новой версии
- [ ] Тег `ontoship-v0.2.0` запушен; ADR доставки в `docs/decisions/`, ссылки на неё из индексов
- [ ] `gitmark lint` чистый (ADR не сирота, план переведён в актуальный статус по мере закрытия)
