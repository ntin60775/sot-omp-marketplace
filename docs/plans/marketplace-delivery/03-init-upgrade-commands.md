---
node_type: ticket
title: Команды init и upgrade
service: _platform
status: draft
updated: 2026-08-30
links:
  part_of: [README.md]
  depends_on: [02-skill-path-migration.md]
---

# 03: Команды init и upgrade

**What to build:** две новые команды плагина. `/ontoship:init` — развёртывание
OntoShip в новом проекте: пишет `AGENTS.md` из шаблона, добавляет в `.gitignore`
строки `.gitmark/`, `*-map.html`, `.scratch/`, затем зовёт `/ontoship:onto-doc`
для бутстрапа KB; **идемпотентна** (повтор не множит строки и не затирает
правки). `/ontoship:upgrade` — пакетный апгрейд по реестру проектов
(`~/ontoship-projects.txt`): для каждого проекта `omp plugin upgrade` +
пересборка индекса; без реестра — только текущий проект.

**Blocked by:** 02 (тексты команд обязаны ссылаться на CLI через skill://, иначе
рождаются команды с дохлыми в потребителе путями).

- [ ] На probe-репо: `/ontoship:init` создаёт AGENTS.md + gitignore-строки; второй прогон не меняет файлы (идемпотентность)
- [ ] `/ontoship:upgrade` с реестром проходит по всем проектам списка; без реестра работает в текущем
- [ ] Команды имеют frontmatter `args:`/`drives:` и попадают в реестр: `gitmark inventory --check` зелёный
- [ ] `gitmark lint` чистый
