---
node_type: runbook
title: Bootstrap: плагин, реестр потребителей, KB
service: _platform
status: active
updated: 2026-09-16
links:
  relates_to: [../../AGENTS.md, ../reference/gitmark-ontology.md, ../reference/consumer-registry.md]
---

# Bootstrap: плагин, реестр потребителей, KB

Этот файл — канон последовательности свежего клона: `AGENTS.md` и `README.md`
ссылаются сюда и не дублируют команды.

Корневой `.omp/` не в git — он собирается **установкой плагина** `ontoship`, а не
скриптом синхронизации: собственной копии пакета в репозитории нет намеренно.

## Порядок

1. **Маркетплейс — раз на машине:**

   ```bash
   omp plugin marketplace add ntin60775/sot-omp-marketplace
   ```

   Без этого шага `omp plugin install` не находит `<plugin>@<marketplace>`.

2. **Установка плагина в проект:**

   ```bash
   omp plugin install --scope project ontoship@sot-omp-marketplace
   ```

3. **Проверка:** `omp plugin list` — должен показать
   `ontoship@sot-omp-marketplace (0.4.3) (project)`.

4. **KB:** индекс и линтер:

   ```bash
   G=.omp/plugins/node_modules/ontoship/skills/kb-search/gitmark.py
   python3 "$G" index
   python3 "$G" lint
   ```

   Индекс и граф — производные: `.gitmark/` и `*-map.html` не коммитятся, они
   пересобираются из markdown.

5. **Реестр потребителей** (если машина обслуживает проекты, потребляющие каталог):

   ```bash
   python3 scripts/consumers.py init --root <каталоги-корни>
   python3 scripts/consumers.py discover --apply
   ```

   `init` создаёт `.consumers.json` (отказывается, если он уже есть), `discover
   --apply` наполняет `consumers[]` наблюдением — каталоги с `.omp/`. Контракт
   и семантика — [реестр потребителей](../reference/consumer-registry.md).

## Проверки репозитория

`python3 -m pytest tests/` — тесты инструмента реестра потребителей
(`tests/test_consumers.py`); `gitmark` они не проверяют — тесты движка удалены
(`bcf040b`), канон движка живёт в
[ontoship-omp](https://github.com/ntin60775/ontoship-omp).
