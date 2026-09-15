---
node_type: runbook
title: Обновление потребителей каталога — реестр, раздача, снятие плоских копий
service: _platform
status: active
updated: 2026-09-14
links:
  documents: [../../scripts/consumers.py, ../../.consumers.json]
  depends_on: [../reference/consumer-registry.md, release-ontoship.md]
  relates_to: [../plans/consumer-delivery.md, ../decisions/plugin-delivery.md]
---

# Обновление потребителей каталога

Кого обновлять и что у них стоит — реестр потребителей (`.consumers.json`) и инструмент
`scripts/consumers.py`. Формат, виды дрейфа и коды выхода —
[реестр потребителей](../reference/consumer-registry.md). Здесь — порядок действий.

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

## 5. Частые отказы

| Симптом | Причина | Что делать |
|---|---|---|
| дрейф `scope` | плагин стоит в `user`-scope | `upgrade --yes` переставит в `project` |
| дрейф `legacy` держится | под плагинными именами лежат копии пакета | `migrate` (отчёт) → `migrate --apply`; расходящиеся копии — `--accept-divergent` или перенос под неплагинное имя |
| дрейф `legacy-unverified` | под `.omp/<dir>` файлы есть, а пакетов нет — копия это или своё, не видно | сначала `upgrade --yes`, затем `migrate` |
| дрейф `own-rules` (помечен `•`) | в проекте есть свои файлы под неплагинными именами | не дрейф: так и должно быть. Снять их можно только осознанно — `--accept-unique` |
| `verify`: `deploy-check ⚠` | предупреждения (exit 2) — пакет работает | не провал; в строке ниже видно чего не хватает (обычно строки в `.gitignore`) |
| `verify`: `deploy-check ✗` | критика (exit 1) | по тексту строки: чаще всего нет `AGENTS.md` — нужен `/init`; бывает мёртвый путь движка в payload |
| `upgrade` «ничего не делает» | кэш каталога не обновлён | `check --refresh`, затем `upgrade --yes` |
| дрейф `pinned` | проект сознательно держит версию | не ошибка; снять `pin` в реестре, когда решите обновиться |
| дрейф `stale` при заданном `pin` | пин нарушен — стоит не та версия | разобраться, почему: пин или установка |
| ворктри без плагинов | `tasks/init-worktree.sh` их не ставит (`worktree-gap`) | добавить шаг установки в скрипт проекта |
| `не в реестре (кандидаты)` | проект с `.omp/` не описан | добавить в `consumers` или в `exclude` |

## Ловушка: `--dry-run` у omp не dry-run

`omp plugin upgrade --dry-run` флаг **игнорирует** и выполняет обновление (проверено
2026-09-14: `erp-demo`, плагин `1c` 0.1.1 → 0.1.2 при `--dry-run`). План без изменений
даёт только `consumers.py upgrade --dry-run`: он не вызывает `omp` вовсе.
