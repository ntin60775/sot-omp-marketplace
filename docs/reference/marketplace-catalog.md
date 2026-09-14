---
node_type: reference
title: Контракт каталога omp-маркетплейса
service: _platform
status: active
updated: 2026-09-14
links:
  documents: [../../.omp-plugin/marketplace.json, ../../README.md]
  relates_to: [../plans/marketplace-delivery/README.md, ontoship-package.md]
---

# Контракт каталога маркетплейса

Формат каталога omp — файл [`.omp-plugin/marketplace.json`](../../.omp-plugin/marketplace.json)
в корне репозитория. Этот репо — только каталог и база знаний; плагины
разрабатываются в своих репозиториях и подключаются каталогом по тегу.

## Структура

```json
{
  "name": "sot-omp-marketplace",
  "owner": { "name": "sothale" },
  "metadata": { "description": "…", "version": "0.2.0" },
  "plugins": [
    {
      "name": "ontoship",
      "source": {
        "source": "git-subdir",
        "url": "git@github.com:ntin60775/ontoship-omp.git",
        "path": ".omp",
        "ref": "v0.3.0"
      },
      "version": "0.3.0"
    }
  ]
}
```

- `name` — имя маркетплейса, входит в селектор установки `<plugin>@<marketplace>`;
- `owner` — владелец (только показывается);
- `metadata.version` — версия каталога;
- `plugins[]` — записи плагинов (name, source, версия/ref).

**Текущее состояние: version `0.2.0` (версия каталога), две записи** — `ontoship`
v0.3.0 (git-subdir, `path: ".omp"`, `ref: "v0.3.0"`) и `1c` v0.1.1 (url,
`ref: "v0.1.1"`). План [marketplace-delivery](../plans/marketplace-delivery/README.md)
архивирован и не исполняется.

## Авторитет версии

Для `omp plugin upgrade` авторитетна **версия в каталоге** `marketplace.json` —
`package.json` плагина при upgrade не читается (проверено экспериментом на живом
omp v18.0.6: фолбэк на манифесты внутри плагина даёт 0.0.0). Отсюда правило
релиза: bump `version` обязателен в `marketplace.json`; `package.json` живёт
в репозитории плагина и на канал обновлений не влияет. Bump версии →
`installPath` переезжает в кэш новой версии.

## Формы source

| Форма | Статус здесь |
|---|---|
| git-subdir (подкаталог другого репо, напр. скрытый `.omp`) | текущая топология для `ontoship` — плагин живёт в `ontoship-omp`, подключается по тегу |
| url (корень другого репозитория) | текущая топология для `1c` — плагин живёт в `1c-omp`, подключается по тегу |
| relative (относительный путь в каталоге) | отброшенная старая схема — плагин публиковался из этого репо; больше не используется |

`ref` на несуществующий тег падает явной ошибкой клона (проверено) — тег
`<name>-vX.Y.Z` должен быть запушен до релиза.

## Команды установки и обновления

Из [README.md](../../README.md) (работают после первой публикации):

```bash
# раз на машину
omp plugin marketplace add ntin60775/sot-omp-marketplace
# user-scope = доступен во всех проектах
omp plugin install ontoship@sot-omp-marketplace
# или project-scope (пин по версии, тенит user-scope)
cd <project> && omp plugin install --scope project ontoship@sot-omp-marketplace
# обновление каталога + плагина (--scope обязателен: без него — user-scope)
omp plugin marketplace update sot-omp-marketplace && omp plugin upgrade ontoship@sot-omp-marketplace --scope=project
```

## Семантика scope и кэш

- **user-scope** — плагин виден во всех проектах машины;
- **project-scope** — закрепление за проектом с пином по версии; **тенит
  user-scope** (при конфликте выигрывает проектная версия);
- повторный `upgrade` идемпотентен;
- содержимое выгружается в кэш `~/.omp/plugins/cache/` (абсолютные пути кэша
  хранит `installed_plugins.json` — он **не коммитится**);
- в потребителе команды префиксуются `<plugin>:<command>` и исполняются из кэша;
  rules из маркетплейс-плагина доставляются и `alwaysApply` срабатывает;
  `bash skill://<skill>/<file>` резолвится в реальный путь (в т.ч. внутри кэша) —
  поэтому CLI плагина должен ссылаться на `gitmark.py` через `skill://`, а не через
  относительный `.omp/`-путь потребителя.

## Релизный поток (кратко)

1. Изменения в репозитории плагина (разработка — по dev-flow).
2. Тег в репозитории плагина, push.
3. Bump `version` и `ref` записи в `.omp-plugin/marketplace.json`.
4. Потребители: `marketplace update` + `plugin upgrade`.

Runbook с шагами проверки — [docs/ops/release-ontoship.md](../ops/release-ontoship.md);
анатомия самого пакета — [ontoship-package.md](ontoship-package.md).
