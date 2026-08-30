---
node_type: reference
title: OntoShip slash commands
service: _platform
status: active
updated: 2026-08-28
tags: [commands, slash-commands, reference]
links:
  documents: [../../.omp/commands/kb.md, ../../.omp/commands/kb-map.md, ../../.omp/commands/doc.md, ../../.omp/commands/onto-doc.md, ../../.omp/commands/grill.md, ../../.omp/commands/grilling.md, ../../.omp/commands/architecture.md, ../../.omp/commands/code-review.md, ../../.omp/commands/to-tickets.md, ../../.omp/commands/handoff.md, ../../.omp/commands/prototype.md, ../../.omp/commands/ship.md]
  relates_to: [../services/gitmark-cli/README.md, ../services/dev-flow/README.md]
---

# OntoShip slash commands

Reference for the slash commands shipped by the **OntoShip** omp package. Each command is
a thin `.omp/commands/*.md` definition that drives a skill or engine. Four families:

- **KB curation & search** — `/kb`, `/kb-map`, `/doc`, `/onto-doc` — drive the GitMark
  CLI (`.omp/skills/kb-search/gitmark.py`) and the `kb-curate` ontology rules.
- **Design & knowledge** — `/grill` (plain grill — the same interview, no KB output),
  `/grilling` (grill + build the domain model → parent
  contract), `/architecture` (scan for deepening opportunities → HTML report → grill the
  chosen candidate), `/to-tickets` (break a plan into tracer-bullet tickets), `/handoff`
  (session bridge), `/prototype` (throwaway prototype for a design question).
- **Review** — `/code-review` (two-axis Standards/Spec review of a diff → report in
  `.scratch/`, read-only).
- **Dev-flow** — `/ship` — drives the gated `dev-flow` pipeline, **one ticket at a
  time**, strictly sequential.

The GitMark CLI is `.omp/skills/kb-search/gitmark.py` (relative to the repo root; stable
when the `.omp/` package is copied into another project).

## Summary

<!-- BEGIN inventory:commands -->
| Command | What it does | Args | Drives |
|---|---|---|---|
| `/architecture` | Scan the codebase for deepening opportunities, present them as a visual HTML report, then grill through the chosen candidate — ending in a plan contract file (docs/plans/<slug>.md). Argument = optional direction (module, subsystem, or pain point). | [direction] (empty → infer hot spots from git history) | mp-improve-codebase-architecture skill |
| `/code-review` | Two-axis review of the diff since a fixed point — Standards (repo rules + Fowler smell baseline) and Spec (originating plan/ticket), run as parallel sub-agents, reported side by side. Argument = the fixed point (commit, branch, tag, merge-base). | <fixed-point> (empty → ask) | mp-code-review skill |
| `/doc` | Compose or update a knowledge-base document for the given topic following the OntoShip ontology (node_type, frontmatter, typed links, folder README index). Wraps the kb-curate skill. | <topic> | kb-curate skill + GitMark CLI |
| `/grill` | Grill the user relentlessly about a plan, decision, or idea — rounds over the design tree until shared understanding, WITHOUT writing anything to the KB (no CONTEXT.md, no decisions, no plan contract). Русские триггеры: погрилл, погриль меня, грилл. Argument = the topic to grill. | <topic> (empty → ask what to grill) | grilling skill |
| `/grilling` | Grill the user relentlessly about a plan, decision, or idea — rounds over the design tree until shared understanding, building the domain model (CONTEXT.md + decisions) as it goes, ending in a plan contract file (docs/plans/<slug>.md). Argument = the topic to grill. | <topic> (empty → ask what to grill) | mp-grill-with-docs skill |
| `/handoff` | Compact the current conversation into a handoff document under .scratch/ so another agent can continue the work. Argument = what the next session will be used for. | [what the next session will do] | mp-handoff skill |
| `/kb-map` | Build the OntoShip KB graph (gitmark map) — collapsible tree + rendered markdown + force/radial link graph as a self-contained HTML — and point the user to it. | [output-path] (default docs-map.html) | GitMark CLI map / index |
| `/kb` | Search the project knowledge base via GitMark (FTS5 bm25 + trigram/fuzzy). Argument = query; no argument shows stat. | <query> (empty → stat + usage) | GitMark CLI search / stat / index |
| `/onto-doc` | Build the ENTIRE knowledge base for this repo — survey the codebase, then dispatch kb-curate curator agents per area to produce docs/ (per-service READMEs, reference specs, runbooks, decisions, entry point) following the OntoShip ontology, then lint + index + map. Use to bootstrap or rebuild a project's whole KB. | [scope] (empty → whole repo) | kb-curate skill via Task fan-out + GitMark CLI |
| `/prototype` | Build a throwaway prototype to answer a design question — logic/state (single HTML file) or UI (radically different variations on one route). Returns data + a recommendation, never commits code. Argument = the question. | <question> (empty → ask) | mp-prototype skill |
| `/ship` | Run the OntoShip dev-flow on one ticket from a plan (docs/plans/<slug>/) or a whole file plan (docs/plans/<slug>.md) or an ad-hoc description — worktree → implement → tests → review → dev-tests → prod-tests → ship. One ticket (or one file plan) per run, strictly sequential. Launched only by hand. | [plan path] / [ticket path] / <ad-hoc> (empty → most recent plan) | dev-flow skill |
| `/to-tickets` | Break a plan (docs/plans/<slug>.md or docs/plans/<slug>/) or the current conversation into tracer-bullet tickets with blocking edges under the plan folder. Argument = plan path or topic; empty = most recent plan. | [plan path] (empty → most recent plan) | mp-to-tickets skill |
<!-- END inventory:commands -->

<!-- BEGIN inventory:skills -->
| Skill | What it does |
|---|---|
| `dev-flow` | The spec-driven development loop for shipping a feature/fix fast and safely on top of a GitMark KB — one ticket (or one file plan) at a time: worktree → implement → tests → independent review → dev-tests → prod-tests → ship (MR → dev → main). Use when starting a feature or fix, or when asked "how do we build/ship a change here". |
| `domain-modeling` | Build and sharpen the project's domain model — challenge terms against CONTEXT.md, stress-test with edge-case scenarios, and update CONTEXT.md and docs/decisions/ inline. Use when discussing codebase terminology, writing or editing CONTEXT.md, or recording or editing a decision. |
| `grilling` | Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases. |
| `kb-curate` | Rules for maintaining a markdown knowledge base (GitMark) — apply when adding, editing, moving, or deleting documentation (.md). A lightweight code-ontology: every document has a type, properties (frontmatter), and typed links. Keeps the KB structured instead of a pile of files. Use on "add a doc", "record a decision", "update the docs", "reorganize docs". |
| `kb-search` | Search a project's markdown knowledge base (docs/, README files, *.md) via the GitMark CLI — FTS5 ranking (bm25) plus trigram/fuzzy matching — instead of grepping across files. Use when you need to find where something is documented, "where do the docs say X", before reading files at random, or to generate an HTML overview/graph of the knowledge base. Handles substrings, typos, and non-Latin scripts. |
| `mp-code-review` | Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this repo's documented standards?) and Spec (does the code match the originating plan/ticket?). Runs both reviews in parallel sub-agents and reports them side by side. Use when the user wants to review a branch, a PR, work-in-progress changes, or a named piece of code. |
| `mp-diagnose` | Diagnosis loop for hard bugs and performance regressions — find the root cause and a minimal repro, then hand the fix to /ship. Use when the user says "diagnose"/"debug this", or reports something broken/throwing/failing/slow. |
| `mp-grill-with-docs` | A relentless interview to sharpen a plan or design, which also builds the project's domain model (CONTEXT.md glossary + decision docs) as it goes, ending in a plan contract (docs/plans/<slug>.md). Use when the user wants to stress-test a plan or idea before implementing. |
| `mp-handoff` | Compact the current conversation into a handoff document for another agent to pick up — a bridge between sessions, not a source of knowledge. Use to continue work in a fresh session, or to hand a research/prototype result back to the main session. |
| `mp-improve-codebase-architecture` | Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick — ending in an OntoShip plan contract (docs/plans/<slug>.md). Driven by the /architecture command. |
| `mp-prototype` | Build a throwaway prototype to answer a design question — returns data and a recommendation for the decision-maker, it does not commit anything to the code. Use when the user wants to sanity-check a state model or logic, or explore what a UI should look like. |
| `mp-to-tickets` | Break a plan (docs/plans/<slug>.md or docs/plans/<slug>/) or the current conversation into tracer-bullet tickets with blocking edges, written as docs/plans/<slug>/NN-<ticket>.md. Use when the user says "разбей на тикеты" or runs /to-tickets. |
<!-- END inventory:skills -->

---

## `/kb` — search the knowledge base

- **Definition:** `.omp/commands/kb.md`
- **What it does:** searches every `.md` in the project (docs/, READMEs, etc.) via GitMark
  (FTS5 bm25 ranking + trigram/fuzzy matching), then summarizes the top hits and answers
  from the 1–2 most relevant files.
- **Args:** `$ARGUMENTS` = the search query. **Empty** → runs `gitmark.py stat` and shows
  the `/kb <query>` syntax instead of searching.
- **Behavior:**
  1. Empty query → `gitmark.py stat` + usage hint.
  2. Otherwise: refresh index if needed (`gitmark.py index`), then
     `gitmark.py search "$ARGUMENTS" -k 8`, summarize hits as `file:line` (no full
     snippets), and open the most relevant files to answer.
- **Drives:** GitMark CLI (`kb-search` skill).

## `/kb-map` — render the KB graph

- **Definition:** `.omp/commands/kb-map.md`
- **What it does:** generates a self-contained HTML map of the knowledge base — a
  collapsible tree, rendered markdown, and a force/radial link graph built from the typed
  links in frontmatter.
- **Args:** `$ARGUMENTS` = output path. **Default `docs-map.html`** when omitted.
- **Behavior:**
  1. Refresh the index: `gitmark.py index`.
  2. Build the map: `gitmark.py map -o "${ARGUMENTS:-docs-map.html}"`.
  3. Report the output path and offer to `open <path>` or `serve` it.
- **Drives:** GitMark CLI `map` (`kb-search` skill).

## `/doc` — compose/update one KB document

- **Definition:** `.omp/commands/doc.md`
- **What it does:** composes or updates a **single** KB document for a topic, following the
  `kb-curate` ontology (node_type, frontmatter, typed links, folder README index).
- **Args:** `$ARGUMENTS` = the topic/document subject.
- **Behavior (per `kb-curate`):**
  1. **Search first** (`gitmark.py search`) — if the topic exists, edit that doc; never
     create a duplicate.
  2. **Pick a `node_type`** (`service` · `reference` · `runbook` · `gotcha` · `decision` ·
     `plan` · `guide` · `report` · `index`) and the right folder.
  3. **Write frontmatter** — `node_type`, `title`, `service`, `status: active`,
     `updated: <today>`.
  4. **Add ≥1 typed link** (to code or a sibling doc) — no orphans.
  5. **Add a line to the folder `README.md`** index.
  6. **Lint + reindex** — `gitmark.py lint` then `gitmark.py index`.
- **Drives:** `kb-curate` skill + GitMark CLI.

## `/onto-doc` — build the whole KB

- **Definition:** `.omp/commands/onto-doc.md`
- **What it does:** builds (or rebuilds) the **entire** OntoShip KB for the repo by
  surveying the codebase and fanning out `kb-curate` curator subagents per area, then
  linting, indexing, and mapping. Used to bootstrap or rebuild a project's whole KB.
- **Args:** `$ARGUMENTS` = scope hint. **Empty** → whole repo; or a subset
  (e.g. `services/api services/billing`, or "only reference docs").
- **Behavior:**
  1. **Survey** the repo (dirs, services, entry points, build/deploy, existing docs);
     check coverage with `gitmark.py stat`.
  2. **Decompose** into doc areas — service READMEs (`service`), cross-cutting specs
     (`reference`), ops procedures (`runbook`/`gotcha`), decisions (`decision`).
  3. **Dispatch curators (fan-out)** — one `Task` subagent per area, each following
     `kb-curate` on its slice only (search first, pick node_type + folder, frontmatter,
     ≥1 typed link, README index line). Independent areas run in parallel, scoped to avoid
     collisions.
  4. **Entry point + indexes** — ensure `AGENTS.md` exists, `docs/README.md`
     is the master index, every folder has a README index.
  5. **Verify & derive** — `gitmark.py lint` (fix broken links/orphans/missing
     frontmatter), then `gitmark.py index`, then `gitmark.py map -o docs-map.html`.
  6. **Report** — docs created/updated, coverage before→after, lint result, map path,
     areas needing a human decision.
- **Drives:** `kb-curate` skill via `Task` fan-out + GitMark CLI.

## `/grill` — plain grill, no KB output

- **Definition:** `.omp/commands/grill.md`
- **What it does:** runs the `grilling` skill directly — the same relentless
  round-by-round interview over the design tree (the whole frontier per round,
  numbered, each with a recommended answer; the agent finds facts itself, the
  decisions are the user's), but **without** `domain-modeling`. It writes nothing
  durable: no `CONTEXT.md` terms, no `docs/decisions/`, no plan contract. This is the
  **optical entry** — think out loud when nothing is worth recording yet.
- **Args:** `$ARGUMENTS` = the plan, decision, or idea to stress-test. **Empty** → ask
  what to grill. Russian triggers («погрилл», «грилл») live in the command description.
- **Behavior:** map the design tree, ask the whole frontier in one round, recompute the
  frontier after each round; done when the frontier is empty and the user confirms
  shared understanding — then stop (no file is written).
- **When to use `/grilling` instead:** if the conclusions deserve the KB, re-run
  `/grilling` (`mp-grill-with-docs`) on the same thread — it builds the domain model
  inline and ends in a plan contract (`docs/plans/<slug>.md`).
- **Drives:** `grilling` skill (the interview primitive, no domain-modeling).

## `/grilling` — grill a plan, decision, or idea

- **Definition:** `.omp/commands/grilling.md`
- **What it does:** runs the `mp-grill-with-docs` skill — a relentless round-by-round
  interview over the design tree (the `grilling` primitive) with `domain-modeling`
  active: glossary terms go to `CONTEXT.md`, load-bearing choices to `docs/decisions/`
  as they crystallise. When the frontier is empty and the user confirms shared
  understanding, it writes the **plan contract** — `docs/plans/<slug>.md`
  (`node_type: plan`, `status: draft`) — and stops. The folder with tickets is created
  later, only by `/to-tickets`.
- **Args:** `$ARGUMENTS` = the plan, decision, or idea to stress-test. **Empty** → ask
  what to grill.
- **Behavior:** the skill holds the discipline — map the design tree, ask the whole
  frontier in one round (numbered, each with a recommended answer), recompute the
  frontier after each round. The agent finds facts itself (read-only scout sub-agents);
  the decisions are the user's. Done when the frontier is empty; do not act until the user confirms.
- **Drives:** `mp-grill-with-docs` skill (grilling + domain-modeling).

## `/architecture` — deepen the architecture

- **Definition:** `.omp/commands/architecture.md`
- **What it does:** runs the `mp-improve-codebase-architecture` skill — surfaces
  architectural friction and proposes **deepening opportunities** (refactors that turn
  shallow modules into deep ones) using a fixed vocabulary (module, interface, depth,
  seam, adapter, leverage, locality) and the deletion test.
- **Args:** `$ARGUMENTS` = an optional direction (a module, subsystem, or pain point).
  **Empty** → the skill infers hot spots by walking `git log` (YAGNI: weight where change
  is landing).
- **Behavior:**
  1. **KB first** — `gitmark search` for `CONTEXT.md` vocabulary and `docs/decisions/`;
     recorded decisions are not re-litigated.
  2. **Scan** via a sub-agent for friction; apply the deletion test to suspects.
  3. **HTML report** — self-contained, written to the OS temp dir (never into the repo),
     one card per candidate with before/after and a recommendation badge, plus a top
     recommendation. Then: "Which of these would you like to explore?"
  4. **Grill the chosen candidate** — the `/grilling` loop (`mp-grill-with-docs`) walks
     the decision tree; terms go to `CONTEXT.md`, choices to `docs/decisions/`; the
     outcome is the **plan contract** `docs/plans/<slug>.md`.
- **Stops there:** no refactoring, no tickets, no `/ship` — the operator runs
  `/to-tickets` and starts `/ship` by hand.
- **Drives:** `mp-improve-codebase-architecture` skill → `mp-grill-with-docs`.

## `/code-review` — two-axis review of a diff

- **Definition:** `.omp/commands/code-review.md`
- **What it does:** runs the `mp-code-review` skill — reviews the diff between `HEAD` and
  a fixed point along two deliberately separate axes, each handled by its own parallel
  sub-agent:
  - **Standards** — conformance to the repo's documented standards (`.omp/rules/`,
    `AGENTS.md`, `CONTEXT.md` vocabulary, `docs/decisions/`) plus a fixed Fowler smell
    baseline (12 smells). A documented repo standard overrides the baseline; smells are
    always judgement calls, never hard violations.
  - **Spec** — faithfulness to the originating plan contract / ticket in `docs/plans/`
    (missing requirements, scope creep, wrong implementation). No spec → the axis skips
    and reports it.
- **Args:** `$ARGUMENTS` = the fixed point (a SHA, branch, tag, `main`, `HEAD~5`).
  **Empty** → ask for it. The skill verifies the ref resolves and the diff is non-empty
  before spawning sub-agents.
- **Behavior:** pin the fixed point → find the spec in the KB → collect standards sources
  → spawn both sub-agents in parallel → aggregate the two reports **side by side, never
  merged or reranked across axes** → write the report to
  `.scratch/code-review-<timestamp>.md`.
- **Boundaries:** read-only — no fixes, no plan contract, no tickets, no `/ship`. The
  report is ephemeral (`.scratch/`), not a KB doc. If the operator decides to fix, the
  findings go to `/grilling` → `/to-tickets` → `/ship`; a durable trap becomes a `gotcha`.
- **Drives:** `mp-code-review` skill.


## `/to-tickets` — break a plan into tickets

- **Definition:** `.omp/commands/to-tickets.md`
- **What it does:** runs the `mp-to-tickets` skill — breaks a plan (or the current
  conversation) into **tracer-bullet vertical slices**, each declaring the tickets that
  block it. Each ticket is sized to fit in a single fresh context window (one `/ship`
  run).
- **Args:** `$ARGUMENTS` = a plan path (`docs/plans/<slug>.md`, `docs/plans/<slug>/`, or
  its `README.md`) or a topic. **Empty** → use the most recent plan (a file or a folder,
  by `updated:`).
- **Behavior:** if the plan is a **file**, first promote it to the folder form
  (`git mv docs/plans/<slug>.md docs/plans/<slug>/README.md`, rewrite the plan's outgoing
  links for the extra depth and the incoming links from other docs). Then drafts the
  slices, gives each its blocking edges, quizzes the user on granularity and edges, and
  writes `docs/plans/<slug>/NN-<ticket>.md` (blockers first) and updates the plan's
  `Tickets` section. Lints + reindexes and stops.
- **Drives:** `mp-to-tickets` skill.

## `/handoff` — session bridge

- **Definition:** `.omp/commands/handoff.md`
- **What it does:** runs the `mp-handoff` skill — compacts the current conversation into
  a handoff document under `.scratch/` so a fresh agent can continue. A bridge between
  sessions, not a KB doc: it references the KB rather than restating it.
- **Args:** `$ARGUMENTS` = what the next session will focus on. **Empty** → summarize
  the whole conversation.
- **Drives:** `mp-handoff` skill.

## `/prototype` — throwaway prototype

- **Definition:** `.omp/commands/prototype.md`
- **What it does:** runs the `mp-prototype` skill — builds a throwaway prototype to
  answer a design question (logic/state → single HTML file; UI → several radically
  different variations on one route). Returns **data and a recommendation**, never
  commits code.
- **Args:** `$ARGUMENTS` = the design question. **Empty** → ask what to prototype.
- **Drives:** `mp-prototype` skill.

## `/ship` — ship one ticket (or one file plan)

- **Definition:** `.omp/commands/ship.md`
- **What it does:** drives **one ticket** from a plan folder (or a whole **file plan**
  as a single slice) through the gated OntoShip dev-flow pipeline. Launched **only by
  hand**, **one ticket (or one file plan) at a time**, strictly sequential.
- **Args:** `$ARGUMENTS` = a **plan folder** (`docs/plans/<slug>/`), a **file plan**
  (`docs/plans/<slug>.md`), a **ticket path** (`docs/plans/<slug>/NN-<ticket>.md`), an
  ad-hoc description, or **empty** (most recent plan — a file or a folder, by
  `updated:`). `docs/plans/<slug>` without an extension resolves to whichever exists.
- **Entry (plan folder):** pick the **first ticket** (by `NN` order) whose `status` is
  not `archived`. Check its `Blocked by` tickets are all archived (if not, report
  blockers and stop). Check `Context` in the parent contract is still accurate; set
  ticket `status: active`.
- **Entry (file plan):** execute the plan as a **single slice** — the full loop on the
  plan's `Goal`/`Done`/acceptance criteria, no tickets. Check `Context` is still
  accurate; set the plan `status: active`.
- **Pipeline (per the `dev-flow` skill, end to end):**
  1. **Research** — understand from facts (logs, traces, code); reproduce before fixing.
  2. **Goal** — take from the ticket's `What to build` + acceptance criteria (or the plan's `Goal`/`Done` for a file plan).
  3. **Isolate** — work in a dedicated `git worktree`.
  4. **Implement** — code to the ticket's acceptance criteria.
  5. **Tests** — write/adjust unit + E2E.
  6. **Independent review** — run the bundled `reviewer` omp sub-agent (read-only) over
     the diff, on the `@reviewer` model role (fallback `@slow`).
  7. **Dev-tests** — MR + commits into `dev`; run the full suite. Red → fix, don't merge.
  8. **Prod-tests** — E2E/smoke against the real prod contour.
  9. **Ship** — merge `dev → main` and deploy (build-before-stop + healthcheck-poll).
     Mark the ticket (or the file plan) `status: archived` once merged.
- **Stop-points (from the plan contract's `Constraints`):** `stop-before-commit`
  (pause with uncommitted diff after review), `stop-after-mr` (pause after MR),
  `no-deploy` (skip deploy). A stop-point is a hard pause — the agent reports and waits,
  never resumes on its own.
- **Sequential discipline:** one ticket (or one file plan) per `/ship` run. After a
  ticket is archived, the operator launches `/ship` again for the next. Never batch
  multiple tickets.
- **Gates:** tests + independent review are not skippable.
- **Drives:** `dev-flow` skill.
