# sot-omp-marketplace

Личный маркетплейс omp-плагинов (формат каталога — `.omp-plugin/marketplace.json`).
Репозиторий — одновременно **дом разработки** плагинов (`plugins/<name>/`) и их
**каталог-релиз**.

## Плагины

| Плагин | Что это | Статус |
|---|---|---|
| [ontoship](plugins/ontoship/) | GitMark KB (md+git, FTS5-поиск, онтология-линтер) + dev-flow: план → тикеты → ship | переезжает из `ntin60775/ontoship-omp` (работа по `docs/plans/marketplace-delivery/`) |

## Установка (после первой публикации)

```bash
# раз на машину
omp plugin marketplace add ntin60775/sot-omp-marketplace
# user-scope = доступен во всех проектах
omp plugin install ontoship@sot-omp-marketplace
# или project-scope (пин по версии, тенит user-scope)
cd <project> && omp plugin install --scope project ontoship@sot-omp-marketplace
```

Обновление: `omp plugin marketplace update sot-omp-marketplace && omp plugin upgrade ontoship@sot-omp-marketplace`.

## Релиз плагина

1. Изменения в `plugins/<name>/` (разработка — по dev-flow OntoShip, dogfood через
   `scripts/sync-package.sh`).
2. Bump `version` в `.omp-plugin/marketplace.json` (авторитетна только она —
   проверено на omp v18.0.6) и в `plugins/<name>/package.json`.
3. Тег `<name>-vX.Y.Z`, push.
4. Потребители: `marketplace update` + `upgrade`.

## Структура

См. [AGENTS.md](AGENTS.md). KB разработки — [docs/](docs/README.md).
