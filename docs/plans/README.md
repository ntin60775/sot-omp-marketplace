---
node_type: index
title: Plans — план-контракты разработки маркетплейса
service: _platform
status: active
updated: 2026-09-14
---

# Plans

Форма и жизненный цикл как в OntoShip (`kb-curate`): файл-план → `/to-tickets` →
папка с тикетами → `/ship` по одному тикету.

- [consumer-delivery.md](consumer-delivery.md) — поставка потребителям: реестр
  машины, `scripts/consumers.py` (check/upgrade/verify/migrate), снятие плоских
  копий в шести проектах, хук ворктри — **draft**, ждёт `/ship`
- [marketplace-delivery](marketplace-delivery/README.md) — переезд OntoShip в формат
  плагина этого каталога; поставка обновлений через `/marketplace` — **archived**
  (подход заменён решением «доставка плагинами», не исполнять)
