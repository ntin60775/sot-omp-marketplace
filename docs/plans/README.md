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
  **active** (тикет [01](consumers-drift-fidelity/01-materialization-and-unversioned.md)
  archived, следующий — [02](consumers-drift-fidelity/02-policy-project-sticky-files.md))
- [consumer-delivery.md](consumer-delivery.md) — поставка потребителям: реестр
  машины, `scripts/consumers.py` (check/upgrade/verify/migrate), снятие плоских
  копий в шести проектах, хук ворктри — **active** (шаг 1 отгружен, шаг 2 — миграция
  потребителей — ждёт подтверждения оператора)
- [marketplace-delivery](marketplace-delivery/README.md) — переезд OntoShip в формат
  плагина этого каталога; поставка обновлений через `/marketplace` — **archived**
  (подход заменён решением «доставка плагинами», не исполнять)
