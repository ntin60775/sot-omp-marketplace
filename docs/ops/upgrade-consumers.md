---
node_type: runbook
title: Обновление потребителей каталога — реестр, раздача, снятие плоских копий
service: _platform
status: active
updated: 2026-09-19
links:
  documents: [../../scripts/consumers.py, ../../.consumers.json]
  depends_on: [../reference/consumer-registry.md, release-ontoship.md]
  relates_to: [../plans/consumer-delivery.md, ../decisions/plugin-delivery.md, bootstrap-after-clone.md]
---

# Обновление потребителей каталога

Кого обновлять и что у них стоит — реестр потребителей (`.consumers.json`) и инструмент
`scripts/consumers.py`. Формат, виды дрейфа и коды выхода —
[реестр потребителей](../reference/consumer-registry.md). Здесь — порядок действий.

## 0. Реестра нет (новая машина, свежий клон)

`.consumers.json` — машинный файл (в `.gitignore`); в свежем клоне его нет, и
`check`/`discover` падают с exit 2 «реестр не найден». Восстановление:

```bash
python3 scripts/consumers.py init --root <каталоги-корни>   # создаёт реестр; отказывается, если он уже есть
python3 scripts/consumers.py discover                       # отчёт: кандидаты (каталоги с .omp/) и наблюдаемое
python3 scripts/consumers.py discover --apply               # принимает кандидатов в consumers[]
python3 scripts/consumers.py check                          # дальше — обычный порядок
```

Кандидаты, которые не потребители (репозитории-источники плагинов, машинный слой),
уходят в `exclude` (`--exclude PATH` — только с `--apply`; без `--apply` — ошибка
использования). Контракт и почему `init` не принимает кандидатов сам —
[реестр потребителей](../reference/consumer-registry.md).

## 1. Релиз плагина

В репозитории плагина: изменения, его проверки, bump версии в манифесте, тег, push
(подробности — [релиз плагина](release-ontoship.md)).

## 2. Запись каталога

Bump `version` и `ref` в `.omp-plugin/marketplace.json`, commit, push. Версию для
`omp plugin upgrade` задаёт **запись каталога** — манифест плагина на канал обновлений
не влияет.

## 3. Раздача потребителям

```bash
python3 scripts/consumers.py check --refresh   # что обновится и где стоит pin; exit 1 при дрейфе
python3 scripts/consumers.py upgrade           # план; без --yes ничего не меняет
python3 scripts/consumers.py upgrade --yes     # применить: marketplace update + install/upgrade --scope=project
python3 scripts/consumers.py verify            # индекс, deploy-check.sh, версия движка у каждого
python3 scripts/consumers.py scan              # зафиксировать наблюдаемое в реестре
```

`check` без `--refresh` сравнивает с уже скачанным кэшем каталога — так видно, что
получат потребители, не трогая сеть.

## 4. Плоские копии пакета

Пока рядом с плагином лежат копии, побеждает копия (нативный провайдер, приоритет 100
против 90) — две правды расходятся. Порядок для такого потребителя:

**сначала `upgrade --yes`** (ставит плагины; копии им не мешают и продолжают
действовать), **затем `migrate`** — только теперь классификация файлов осмысленна:
эталоном служат уже поставленные пакеты. Дальше `migrate --apply` → `verify`.

```bash
python3 scripts/consumers.py upgrade --yes                              # плагины поставлены, копии ещё работают
python3 scripts/consumers.py migrate                                    # отчёт: совпадает / расходится / нет в пакетах
python3 scripts/consumers.py migrate --apply --keep .omp/rules/own.md   # снять, сохранив названное
python3 scripts/consumers.py verify
```

`migrate --apply` снимает **копии пакета** (совпавшие — сразу, расходящиеся — по
решению) и **оставляет собственные файлы проекта**: файл под неплагинным именем — не
копия, а знание проекта, и по ADR §6 ему здесь и место.

```bash
python3 scripts/consumers.py migrate --apply                    # снять копии, свои файлы оставить
python3 scripts/consumers.py migrate --apply --accept-divergent # и расходящиеся копии — осознанно
python3 scripts/consumers.py migrate --apply --accept-unique    # и свои файлы — только если надо
```

**Расходящаяся копия — сигнал, а не мусор.** Если файл под плагинным именем отличается
от пакетного, сначала посмотрите, что именно отличается: старая генерация пакета
(например, путь `.omp/skills/…` там, где в пакете уже `skill://`) снимается, а вот
проектная конкретика (имена баз, расширений, реквизитов фикстур) — это знание проекта,
и его надо **перенести под имя, не совпадающее с плагинным**, тогда оно перестанет
перекрывать пакет и останется в проекте:

```bash
git mv .omp/rules/test-contour.md .omp/rules/erp-main-test-contour.md   # пример: своё правило erp-main
```

`unverifiable` не принимается никогда: без поставленных пакетов сравнивать не с чем —
сначала `upgrade`. `--keep` сильнее любого `--accept*`: названное остаётся.

## 5. Проект перестаёт быть потребителем

`omp plugin uninstall` **не сносит** `.omp/`: остаётся скелет
`.omp/plugins/{installed_plugins.json, omp-plugins.lock.json, node_modules}`.
Наличие `.omp/` — сентинель потребителя для инструмента, поэтому порядок:

1. `omp plugin uninstall <plugin>@<marketplace> --scope=project`;
2. снести `.omp/` целиком (скелет — не знание проекта, его не жалеть);
3. убрать проект из `consumers` в реестре (или в `exclude`, если он не должен
   появляться как кандидат).

Если проект **остаётся** потребителем (снят только один плагин) — скелет
безвреден: `.omp/plugins/` игнорируется, а наблюдаемое состояние обновится при
следующем `scan`/`check`.

## 6. Частые отказы

| Симптом | Причина | Что делать |
|---|---|---|
| дрейф `scope` | плагин стоит в `user`-scope | `upgrade --yes` переставит в `project` |
| дрейф `materialization` | реестр установки говорит «плагин есть», а payload недоступен: мёртвый `installPath` (кэш снесён), нет записи в `node_modules` или битый симлинк | `omp plugin upgrade <id>@<marketplace> --scope=project` в затронутом проекте — перепривязывает запись на живую версию (для машинной установки — тот же вызов с `--scope=user`). Строка отчёта называет путь записи и цель симлинка |
| дрейф `legacy` держится | под плагинными именами лежат копии пакета | `migrate` (отчёт) → `migrate --apply`; расходящиеся копии — `--accept-divergent` или перенос под неплагинное имя |
| дрейф `legacy-unverified` | под `.omp/<dir>` файлы есть, а пакетов нет — копия это или своё, не видно | сначала `upgrade --yes`, затем `migrate` |
| дрейф `own-rules` (помечен `•`) | в проекте есть свои файлы под неплагинными именами | не дрейф: так и должно быть. Снять их можно только осознанно — `--accept-unique` |
| дрейф `unversioned` (помечен `•`) | каталог плагин знает, а версии не объявил (так выглядит `redaktura-skills@redaktura-skills`) | не дрейф: обновлять нечего. `upgrade` такой плагин пропускает и остаётся зелёным; в состав потребителей его не вносит `discover --apply` |
| `verify`: `deploy-check ⚠` | предупреждения (exit 2) — пакет работает | не провал; в строке ниже видно чего не хватает (обычно строки в `.gitignore`) |
| `verify`: `deploy-check ✗` | критика (exit 1) | по тексту строки: чаще всего нет `AGENTS.md` — нужен `/init`; бывает мёртвый путь движка в payload |
| `upgrade` «ничего не делает» | кэш каталога не обновлён | `check --refresh`, затем `upgrade --yes` |
| дрейф `pinned` | проект сознательно держит версию | не ошибка; снять `pin` в реестре, когда решите обновиться |
| дрейф `stale` при заданном `pin` | пин нарушен — стоит не та версия | разобраться, почему: пин или установка |
| ворктри без плагинов | `tasks/init-worktree.sh` их не ставит (`worktree-gap`) | добавить шаг установки в скрипт проекта |
| `не в реестре (кандидаты)` | проект с `.omp/` не описан | добавить в `consumers` или в `exclude` |
| дрейф `gitignore` | доставленное не игнорируется — попадёт в git | дополнить `.gitignore` каноническим блоком из [consumer-repo-layout](../reference/consumer-repo-layout.md); `upgrade` по нему ничего не делает |
| `реестр не найден` (exit 2) | свежий клон / новая машина — `.consumers.json` отсутствует | `init` + `discover --apply` (шаг 0) |
| `upgrade` падает: `Runtime package name "X" conflicts with installed package "X"` | в `<project>/.omp/plugins/omp-plugins.lock.json` осталась запись по **runtime-имени** пакета (`1c-omp` при плагине `1c`) от прежней установки — установщик видит её как «установленный пакет» | убрать запись плагина из `lock` → `omp plugin upgrade <id>@<marketplace> --scope=project`. Не помогают `--force`, `uninstall`, `doctor --fix` и удаление симлинка (проверено 2026-09-17 на omp 18.2.4: 6 проектов из 7) |
| после апгрейда в других проектах `<project>/.omp/plugins/node_modules/<pkg>` — битый симлинк | первый апгрейд снёс общий кэш `~/.omp/plugins/cache/plugins/<каталог>___<плагин>___<старая версия>`, а симлинки остальных проектов смотрели на него | `omp plugin upgrade <id>@<marketplace> --scope=project` в каждом затронутом проекте — перепривязывает на живую версию. `check` называет это дрейфом `materialization` (exit 1) с путём записи и её целью — раньше он показывал «чисто», потому что читал реестр маркетплейса, а не материализацию в `node_modules` |

**Апгрейд одного проекта сносит кэш у всех — раскатка машинно-атомарна.** Кэш
`~/.omp/plugins/cache/plugins/<каталог>___<плагин>___<версия>` общий на машину, а
`node_modules` проектов — симлинки в него; `omp plugin upgrade` удаляет замещаемую
версию. Поэтому «сначала один проект, потом остальные» само по себе не работает: либо
все разом (`upgrade --yes`), либо ни один.

Если проверить апгрейд на одном проекте всё же нужно (dogfood каталога, проверка
релиза), старую версию возвращают в кэш из тега плагина — тогда остальные проекты
продолжают работать на ней до общей раскатки:

```bash
CACHE=~/.omp/plugins/cache/plugins/<каталог>___<плагин>___<старая версия>
git -C <репо плагина> archive vX.Y.Z .omp | tar -x -C "$CACHE" --strip-components=1
```

Проверено 2026-09-19: апгрейд каталога на `ontoship 0.4.7` оставил 11 потребителей с
битыми симлинками; кэш `0.4.5` восстановлен из тега `v0.4.5`, `check` снова показывает
у них `stale` (а не `materialization`), `deploy-check` зелёный. Восстановленный каталог
omp считает обычным попаданием в кэш — книга учёта версий не ведётся по содержимому.

## Ловушка: `--dry-run` у omp не dry-run

`omp plugin install --dry-run` и `omp plugin upgrade --dry-run` флаг **игнорируют** и
ставят/обновляют по-настоящему: флаг разбирается в `flags.dryRun`, но обработчик
установки его не читает. Проверено дважды — 2026-09-14 на `upgrade` (`erp-demo`,
плагин `1c` 0.1.1 → 0.1.2 при `--dry-run`) и 2026-09-16 на `install` (omp v18.2.0:
`omp plugin install --scope project --dry-run ontoship@sot-omp-marketplace` создал
`.omp/plugins/installed_plugins.json` и поставил плагин). План без изменений даёт
только `consumers.py upgrade --dry-run`: он не вызывает `omp` вовсе.
