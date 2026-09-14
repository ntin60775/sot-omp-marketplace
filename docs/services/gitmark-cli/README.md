---
node_type: service
title: GitMark CLI — движок базы знаний
service: gitmark-cli
status: active
updated: 2026-09-14
links:
  documents: [../../../tests/test_gitmark.py]
  relates_to: [../../reference/gitmark-ontology.md]
---

# GitMark CLI

Подсистема базы знаний: [GitMark-онтология](../../reference/gitmark-ontology.md) живёт в
обычном markdown, а поверх неё работает CLI-движок
gitmark.py. Источник истины —
**md + README-индексы + git**; всё производное (поисковый индекс, HTML-обзор, граф)
регенерируется из md. Движок — чистый Python stdlib, работает оффлайн; поиск — SQLite
FTS5: `bm25()` по терминам ∪ trigram-токенайзер (подстроки, опечатки, кириллица).

## Дом и доставка движка

- Движок разрабатывается в репозитории `ntin60775/ontoship-omp` — там правится код.
- В этот репозиторий он доставляется установленным плагином `ontoship`
  (каталог, git-subdir по тегу):
  `.omp/plugins/node_modules/ontoship/skills/kb-search/gitmark.py` —
  именно к нему обращаются скиллы и команды из рабочего проекта.
- [tests/test_gitmark.py](../../../tests/test_gitmark.py) грузит модуль через `importlib`
  по пути установленного плагина.

## Подкоманды CLI

| Команда | Назначение |
|---|---|
| `index [--root .] [--force]` | построить/обновить `.gitmark/index.db` (FTS5-таблицы `fts` + `tri`) |
| `search "<q>" [-k 8] [--json]` | поиск bm25 ∪ trigram ∪ fuzzy, вывод `file:line · heading · snippet` |
| `map [-o docs-map.html]` | self-contained HTML: дерево + рендер md + радиальный граф |
| `serve [-p 8799]` | локальный HTTP для просмотра карты |
| `stat` | статистика: файлы/чанки/ссылки/папки/состояние trigram |
| `lint [paths…] [--strict]` | проверка инвариантов онтологии I1–I7 |
| `inventory [--check]` | перегенерация (или проверка) таблиц реестра команд/навыков |
| `version` | версия движка |

## Поиск и деградация

Ранжирование склеивает три канала с разными весами: точные термины `bm25` (вес 1.0),
фразовый trigram — точная подстрока (вес 0.6), fuzzy — OR по 4-символьным окнам запроса
с порогом покрытия (вес 0.3; отсекает мусор, цепляющий одно частое окно). Доступность
trigram-токенайзера проверяется пробным `CREATE VIRTUAL TABLE` при индексации и
сохраняется в `meta('trigram')`: на SQLite < 3.34 индекс строится без таблицы `tri` и
поиск **деградирует** до одного bm25 — substring/fuzzy-каналы просто молча отключаются.
`deploy-check.sh` зафиксировал это как контракт: FTS5 обязателен (exit 1 при отсутствии),
trigram опционален (exit 2, «fuzzy/substring-поиск будет ограничен»).

## Lint: инварианты онтологии I1–I7

`lint` обходит все md-файлы репозитория (обходя папки из рукописного подмножества
`.gitignore`) и проверяет:

- **I1** (ERR) — «несущий» документ в `docs/reference|ops|plans|decisions|services/`
  без frontmatter с `node_type` (README-индексы папок исключены);
- **I2** — значения вне словарей: `node_type` вне `NODE_TYPES` → ERR; `service`/`status`
  вне словарей → WARN. Словари зашиты в код как зеркало
  [gitmark-ontology.md](../../reference/gitmark-ontology.md): `NODE_TYPES` —
  service, reference, runbook, gotcha, decision, plan, ticket, guide, report, index,
  memory; `STATUSES` — active, draft, deprecated, archived; `LINK_KEYS` — documents,
  depends_on, supersedes, relates_to, implemented_by, part_of; `LOAD_BEARING` —
  service, reference, runbook, plan, decision, ticket. Реестр сервисов выводится
  per-repo: `services_vocab = {_platform} ∪ имена всех каталогов под docs/`, то есть
  появление папки `docs/services/<svc>/` легализует `service: <svc>` без правки кода;
- **I3** (WARN) — сирота: документ несущего типа без входящих и исходящих связей;
- **I4** (ERR) — битая markdown-ссылка на `.md`-файл;
- **I5** (WARN) — папка под `docs/` без `README.md`-индекса;
- **I6** (WARN) — цель `supersedes:` не помечена `deprecated`/`archived`;
- **I7** (ERR) — рассинхрон реестра команд (см. ниже).

`--strict` даёт exit 1 при любой ошибке.

## Реестр: inventory и маркеры

`inventory` сканирует команды и навыки двух слоёв: проект
(`<проект>/.omp/commands/*.md`, `<проект>/.omp/skills/*/SKILL.md`) и пакет
(`<пакет>/commands/*.md`, `<пакет>/skills/*/SKILL.md`; корень пакета резолвится от
расположения самого движка — `PKG_ROOT`). При совпадении имён побеждает слой проекта
(тот же приоритет, что у провайдеров omp: нативный выше плагинного). Frontmatter
команд: `description`, `args`, `drives`. Перегенерирует сводные таблицы в
docs/reference/commands.md между HTML-маркерами
`<!-- BEGIN inventory:commands -->` / `<!-- END inventory:commands -->` (аналогично
`inventory:skills`) — всё вне маркеров не трогается, операция идемпотентна.
`inventory --check` ничего не пишет и докладывает рассинхрон — ту же логику
(`inventory_issues`) вызывает `lint` как I7: отсутствие/несовпадение таблиц между
маркерами, команда без `args:`/`drives:`, секция `## /cmd` без файла команды и наоборот.
Поэтому таблицы реестра руками не правятся — только перегенерацией.

## Производные артефакты

`.gitmark/` (индекс SQLite) и `*-map.html` (карта) — производные, в `.gitignore`, в git
не коммитятся; при подозрении на устаревание — `gitmark index --force`.

## Смоук развёртывания

deploy-check.sh проверяет, что пакет
на месте: ключевые файлы (`.omp/skills/kb-search/gitmark.py`, команды, правила), FTS5
обязателен / trigram опционален, `index` + контрольный `search "OntoShip"` возвращают
непустой результат, `docs/` забутстраплен, `.gitmark/` в `.gitignore`. Коды возврата:
0 — ОК, 1 — критично, 2 — предупреждения.
