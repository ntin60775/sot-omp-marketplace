# sot-omp-marketplace — entry point

Personal **omp marketplace**: a catalog repo of plugins in omp format
(`.omp-plugin/marketplace.json`). This repo is the **development home** of the
plugins it publishes — first and flagship: **OntoShip** (GitMark KB + dev-flow),
which is being migrated here from `vakovalskii/ontoship-omp` → `ntin60775/ontoship-omp`.

## Where things live

```
.omp-plugin/marketplace.json   the catalog (plugin entries, pinned refs, versions)
docs/                          this repo's KB (GitMark: plans, decisions, ops)
```

Plugins are **not** developed here. Each lives in its own repository and is
referenced from the catalog by tag — see
[docs/decisions/plugin-delivery.md](docs/decisions/plugin-delivery.md).

## Topology decision (2026-09-11)

Supersedes the 2026-08-30 decision. Full record:
[docs/decisions/plugin-delivery.md](docs/decisions/plugin-delivery.md).

- Three homes: this repo is **only the catalog + KB**; the machine layer lives in
  `sot-omp-core` (delivered by a sync script — plugins cannot carry `RULES.md`,
  `WATCHDOG.md`, `TITLE_SYSTEM.md` or `config.yml`); each plugin lives in its own
  repository.
- Catalog entries pin a **tag**, never a relative path: a relative source follows
  the clone's HEAD, so two machines installing in different weeks get different
  rules.
- Private plugin repos are referenced by **SSH URL** — the installer clones over
  HTTPS, which cannot authenticate against a private repo.
- Plugins install **per project** (`--scope project`). Worktrees do not inherit
  `.omp/plugins/`, so a project's `tasks/init-worktree.sh` must install them.
- The marketplace repo itself no longer dogfoods a package: `plugins/` and
  `scripts/sync-package.sh` are leftovers of the old scheme.

## Start here

- **The plan** → [docs/plans/marketplace-delivery/](docs/plans/marketplace-delivery/README.md)
- **OntoShip package source** → [plugins/ontoship/](plugins/ontoship/)
- **The catalog** → [.omp-plugin/marketplace.json](.omp-plugin/marketplace.json)

## Principle

Same as OntoShip's: markdown + git is the source of truth; everything derived
(`.gitmark/`, `*-map.html`) is regenerated, never committed.

## First clone (bootstrap)

Корневой `.omp/` не в git (сгенерируемая копия) — после свежего клона соберите
его, иначе dogfood-навыки/команды и `gitmark` недоступны:

```bash
./scripts/sync-package.sh          # plugins/ontoship/{skills,commands,rules,scripts} -> .omp/
python3 .omp/skills/kb-search/gitmark.py index
python3 -m pytest tests/           # канон — plugins/ontoship/.../gitmark.py
```

## Maintain

```bash
python3 .omp/skills/kb-search/gitmark.py index    # rebuild the index after editing docs
python3 .omp/skills/kb-search/gitmark.py lint     # check the ontology
python3 .omp/skills/kb-search/gitmark.py map -o docs-map.html
```
