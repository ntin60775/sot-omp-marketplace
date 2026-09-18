---
node_type: index
title: Plans — план-контракты разработки маркетплейса
service: _platform
status: active
updated: 2026-09-18
---

# Plans

Форма и жизненный цикл как в OntoShip (`kb-curate`): файл-план → `/to-tickets` →
папка с тикетами → `/ship` по одному тикету.

- [consumers-drift-fidelity](consumers-drift-fidelity/README.md) — точность дрейфа:
  материализация поставки, непроверяемые плагины, политика проектных sticky-файлов —
  **archived** (оба тикета отгружены 2026-09-18: MR
  [#1](https://github.com/ntin60775/sot-omp-marketplace/pull/1),
  [#2](https://github.com/ntin60775/sot-omp-marketplace/pull/2))
- [consumer-delivery.md](consumer-delivery.md) — поставка потребителям: реестр
  машины, `scripts/consumers.py` (check/upgrade/verify/migrate), снятие плоских
  копий в шести проектах, хук ворктри — **active** (шаг 1 отгружен, шаг 2 — миграция
  потребителей — ждёт подтверждения оператора)
- [marketplace-delivery](marketplace-delivery/README.md) — переезд OntoShip в формат
  плагина этого каталога; поставка обновлений через `/marketplace` — **archived**
  (подход заменён решением «доставка плагинами», не исполнять)
