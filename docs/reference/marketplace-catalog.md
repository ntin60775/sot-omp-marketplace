---
node_type: reference
title: Контракт каталога omp-маркетплейса
service: _platform
status: active
updated: 2026-08-30
links:
  documents: [../../.omp-plugin/marketplace.json, ../../README.md]
  relates_to: [../plans/marketplace-delivery/README.md, ontoship-package.md]
---

# Контракт каталога маркетплейса

Формат каталога omp — файл [`.omp-plugin/marketplace.json`](../../.omp-plugin/marketplace.json)
в корне репозитория. Этот репо — одновременно дом разработки плагинов
(`plugins/<name>/`) и их каталог-релиз.

## Структура

```json
{
  "name": "sot-omp-marketplace",
  "owner": { "name": "sothale" },
  "metadata": { "description": "…", "version": "0.0.0" },
  "plugins": []
}
```

- `name` — имя маркетплейса, входит в селектор установки `<plugin>@<marketplace>`;
- `owner` — владелец (только показывается);
- `metadata.version` — версия каталога;
- `plugins[]` — записи плагинов (name, source, версия/ref).

**Текущее состояние: `plugins: []`, version `0.0.0` — каталог пуст до первого
релиза.** Первая запись `ontoship` (`source: "./plugins/ontoship"`,
`version: "0.2.0"`) появится по плану
[marketplace-delivery](../plans/marketplace-delivery/README.md).

## Авторитет версии

Для `omp plugin upgrade` авторитетна **версия в каталоге** `marketplace.json` —
`package.json` плагина при upgrade не читается (проверено экспериментом на живом
omp v18.0.6: фолбэк на манифесты внутри плагина даёт 0.0.0; детали — в Context
плана). Отсюда правило релиза: bump `version` обязателен в `marketplace.json`
(и в `plugins/<name>/package.json` — для метаданных/`gitmark version`, но на канал
обновлений он не влияет). Bump версии → `installPath` переезжает в кэш новой версии.

## Формы source

| Форма | Статус здесь |
|---|---|
| relative: `"./plugins/ontoship"` | текущая топология — плагин публикуется из этого репо, без обходов |
| git-subdir (подкаталог другого репо, напр. скрытый `.omp`) | наследие старой топологии (`ontoship-omp`), больше не используется; работает, но не применяется |

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
# обновление каталога + плагина
omp plugin marketplace update sot-omp-marketplace && omp plugin upgrade ontoship@sot-omp-marketplace
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

1. Изменения в `plugins/<name>/` (разработка — по dev-flow, dogfood через
   `scripts/sync-package.sh`).
2. Bump `version` в `.omp-plugin/marketplace.json` (+ `plugins/<name>/package.json`).
3. Тег `<name>-vX.Y.Z`, push.
4. Потребители: `marketplace update` + `plugin upgrade`.

Runbook с шагами проверки — [docs/ops/release-ontoship.md](../ops/release-ontoship.md);
анатомия самого пакета — [ontoship-package.md](ontoship-package.md).
