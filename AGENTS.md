# sot-omp-marketplace — entry point

Personal **omp marketplace**: a catalog repo of plugins in omp format
(`.omp-plugin/marketplace.json`). This repo is the **catalog and its KB** — the
plugins it publishes live in their own repositories (first and flagship:
**OntoShip** — GitMark KB + dev-flow — in
[ntin60775/ontoship-omp](https://github.com/ntin60775/ontoship-omp)).

## Where things live

```
.omp-plugin/marketplace.json      the catalog (plugin entries, pinned refs, versions)
schemas/consumer-registry.schema.json   schema of the local consumer registry
.consumers.json                   the registry itself — gitignored, one per machine
scripts/consumers.py              consumer tool: discover/scan/check/upgrade/verify/migrate
docs/                             this repo's KB (GitMark: plans, decisions, ops)
tests/                            tests of the consumer tool
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
- The marketplace repo dogfoods its own plugin: `.omp/` here is an install
  (`omp plugin install --scope project ontoship@sot-omp-marketplace`), not a
  package source. The old `plugins/` and `scripts/sync-package.sh` were removed
  in `8b0a1c1`.
- **Consumers are tracked locally**: `.consumers.json` (gitignored) lists every
  project on this machine that consumes the catalog, with observed versions and
  flat copies — [docs/reference/consumer-registry.md](docs/reference/consumer-registry.md).
- **Consumer repo layout**: what a consumer versions and what it ignores (delivered
  files live in the plugin repos, not in the project) —
  [docs/reference/consumer-repo-layout.md](docs/reference/consumer-repo-layout.md).

## Start here

- **Topology** → [docs/decisions/plugin-delivery.md](docs/decisions/plugin-delivery.md)
- **OntoShip package source** → [ntin60775/ontoship-omp](https://github.com/ntin60775/ontoship-omp)
- **The catalog** → [.omp-plugin/marketplace.json](.omp-plugin/marketplace.json)

## Principle

Same as OntoShip's: markdown + git is the source of truth; everything derived
(`.gitmark/`, `*-map.html`) is regenerated, never committed.

## First clone (bootstrap)

Корневой `.omp/` не в git: он собирается **установкой плагина**, а не скриптом.
После свежего клона:

```bash
omp plugin install --scope project ontoship@sot-omp-marketplace
G=.omp/plugins/node_modules/ontoship/skills/kb-search/gitmark.py
python3 "$G" index
python3 -m pytest tests/
```

`gitmark` приходит из плагина. Собственной копии в репозитории нет намеренно:
вторая копия одного инструмента — ровно тот дрейф, от которого мы уходим.

## Maintain

```bash
G=.omp/plugins/node_modules/ontoship/skills/kb-search/gitmark.py
python3 "$G" index    # rebuild the index after editing docs
python3 "$G" lint     # check the ontology
python3 "$G" map -o docs-map.html
```
