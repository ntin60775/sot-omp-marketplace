# sot-omp-marketplace

Личный маркетплейс omp-плагинов (формат каталога — `.omp-plugin/marketplace.json`).
Репозиторий — **только каталог и KB**. Плагины здесь не разрабатываются: каждый
живёт в своём репозитории и подключается из каталога по тегу.

Почему так — [ADR «доставка плагинами»](docs/decisions/plugin-delivery.md).

## Плагины

| Плагин | Что это | Репозиторий |
|---|---|---|
| `1c` | контур 1С-разработки: правила BSL, гейты Unica, навыки развёртывания | [ntin60775/1c-omp](https://github.com/ntin60775/1c-omp) |
| `ontoship` | GitMark KB (md+git, FTS5-поиск, онтология-линтер) + dev-flow | [ntin60775/ontoship-omp](https://github.com/ntin60775/ontoship-omp) |

Плагин `1c` **требует** `unica@unica` из маркетплейса
`IngvarConsulting/unica-marketplace`: без него нет ни `unica.*`, ни v8-runner.
Механизма зависимостей в схеме каталога нет — связку обеспечивает навык
развёртывания контура.

## Установка

```bash
# раз на машине
omp plugin marketplace add IngvarConsulting/unica-marketplace
omp plugin marketplace add ntin60775/sot-omp-marketplace

# в проекте: 1С-контур (в не-1С проекте нужен только ontoship)
cd <project>
omp plugin install --scope project unica@unica
omp plugin install --scope project 1c@sot-omp-marketplace
omp plugin install --scope project ontoship@sot-omp-marketplace
# перезапустить сессию: MCP и хуки поднимаются только при старте
```

Установка **в проект**, а не в машину: у контура есть проектный контекст (база,
учётка, состав расширений) и своя версия. Цена решения — ворктри не наследуют
`.omp/plugins/`, поэтому в проекте нужен шаг установки в `tasks/init-worktree.sh`.

Обновление: `omp plugin marketplace update sot-omp-marketplace && omp plugin upgrade <plugin>@sot-omp-marketplace --scope=project`.
Без `--scope` upgrade ставит плагин в user-scope — машинно, во все проекты.

## Релиз плагина

1. Изменения — в репозитории плагина, там же прогоняются его проверки.
2. Bump `version` в `package.json` плагина + коммит (метаданные; канал обновлений
   читает версию каталога, не манифеста).
3. Тег `vX.Y.Z` в репозитории плагина, push.
4. В каталоге: bump `version` и `ref` в записи плагина — это авторитетная версия
   для `omp plugin upgrade`.
5. Потребители: `omp plugin marketplace update` + `omp plugin upgrade <plugin>@sot-omp-marketplace --scope=project`
   (без `--scope` — user-scope, машинно).

## Структура

```
.omp-plugin/marketplace.json   каталог: записи плагинов, закреплённые ref, версии
docs/                          KB: решения, планы, справочники, сервисы
tests/                         тесты gitmark
```

См. также [AGENTS.md](AGENTS.md) и [KB](docs/README.md).
