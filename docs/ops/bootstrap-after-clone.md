---
node_type: runbook
title: KB после свежего клона
service: _platform
status: active
updated: 2026-09-11
links:
  relates_to: [../../AGENTS.md, ../reference/gitmark-ontology.md]
---

# KB после свежего клона

Корневой `.omp/` не в git — он собирается **установкой плагина** `ontoship`, а не
скриптом синхронизации: собственной копии пакета в репозитории нет намеренно.

```bash
omp plugin install --scope project ontoship@sot-omp-marketplace
G=.omp/plugins/node_modules/ontoship/skills/kb-search/gitmark.py
python3 "$G" index
python3 "$G" lint
python3 -m pytest tests/
```

`tests/` проверяет тот же `gitmark`, что пришёл с плагином; канон инструмента
живёт в [ontoship-omp](https://github.com/ntin60775/ontoship-omp).

Индекс и граф — производные: `.gitmark/` и `*-map.html` не коммитятся, они
пересобираются из markdown.
