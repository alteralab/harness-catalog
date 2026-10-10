---
type: guide
title: Quickstart — where to look for what
description: Task-routing map for this wiki. Which page answers which kind of question about harness-catalog, what is deliberately delegated to Graft, the source and DESIGN.md, and how these pages are refreshed and aged.
tags: [quickstart, navigation, routing]
sources:
  - id: openwiki-source-454154222c04f2c228fc4a20
    resource: repo://.claude/helpers/graft-ensure.sh
  - id: openwiki-source-80aabf5d700807c9b44ae3e8
    resource: repo://.claude/helpers/openwiki-age.sh
  - id: openwiki-source-1fe463fcf07912e5cdbb5a91
    resource: repo://.claude/settings.json
  - id: openwiki-source-6d4b4e707b8d60b6ccfa3425
    resource: repo://.github/workflows/openwiki-update.yml
  - id: openwiki-source-f5a489e5822d87c0b8fc66ef
    resource: repo://.mcp.json
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-ca9eabc24825e6ff0edc2967
    resource: repo://DESIGN.md
  - id: openwiki-source-70991026f1538e8215a8789e
    resource: repo://docs/development.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-5b54a58d1b51cd490b0e7162
    resource: repo://package.json
  - id: openwiki-source-1f7212efc41fd797b2b123e9
    resource: repo://packages/core/src/harness_catalog_core/settings.py
  - id: openwiki-source-31c5d408b8f1718dfd9d4e59
    resource: repo://PLAN.md
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Quickstart — where to look for what

This wiki explains **why and how** harness-catalog works. Reading it is pull-based and optional: call `openwiki_search` then `openwiki_read` when a task touches an unfamiliar part of the system or when source inspection leaves an important uncertainty, and stop once the question is grounded. The generated block that `CLAUDE.md` delegates to `@AGENTS.md` is explicit about this — do not enumerate, preload or search wikis at task start; treat source code and tests as authoritative; do not hand-edit generated pages. Two things are deliberately not here.

- **Where a symbol lives, who calls it, what an edit breaks** — ask Graft (`graft ask/grep/skeleton/callers`, or the `graft_*` MCP tools) or read the source. Graft indexes **Python only**: for shell, YAML, TOML, JSON, SQL, Dockerfiles and Markdown use Grep, and never read a `graft grep` result of zero hits as "does not exist". Every `file:line` in these pages describes the code as it was before your task started; the SessionStart hook `.claude/helpers/openwiki-age.sh` prints `openwiki: 마지막 갱신 이후 커밋 N개` when commits have landed since the baseline in `openwiki/.last-update.json`, and files changed since then should be read in the source instead. The sibling hook `.claude/helpers/graft-ensure.sh` runs `graft build` on every session start (the structural graph refreshes itself before each query, but the per-file cards under `graft/` are rebuilt only by `build`), and tells you to run `make graft` when `node_modules` is missing.
- **The full design argument and its history** — `DESIGN.md` (Korean) is the contract and §11 its dated ledger of decisions and adversarial reviews; execution plans live in `PLAN.md` (umbrella) and `plans/{service,distribution,pilot,skills}.md`, with the measurements in `plans/pilot/r1~r3.md`. Pages here cite sections rather than restating them. For configuration questions that span components (a compose variable, a Dex value, a CI secret), start with this wiki for the cross-component picture and then verify in the source.

## By question

| If you need to know… | Read |
|---|---|
| What the pieces are and how a request or a publication flows through them | [System overview](architecture/overview.md) |
| How `main` becomes an index: fetch, checks, the status machine, rewinds, past versions, limits, the archive cache | [Catalog app](architecture/catalog-app.md) |
| What the ten checks look at, errors vs warnings, exit codes, why gitleaks is fail-closed | [The ten check items](architecture/check-items.md) |
| How the repository is cloned and read, the deploy key, `safe.directory`, history resolution, deterministic `git archive` | [GitStore](architecture/git-content-store.md) |
| Login, token verification, the audience scope, why only `harness-readers` matters, why the archive route is outside bearer auth | [Authentication and authorization](architecture/auth.md) |
| The five MCP tools, their payloads and error codes, the span attributes, OTel wiring | [MCP server](architecture/mcp-server.md) |
| How a whole skill version is downloaded without passing through the model: the descriptor, the header token, the tar route, eviction | [Archive download](architecture/archive-download.md) |
| The `harness-catalog` commands — `check`, `init`, `config`, `ci base/check/evals` — base-commit rules, credential tables, gitleaks acquisition, the wiring-only workflow templates | [CLI and catalog CI](architecture/cli-and-ci.md) |
| The PostgreSQL schema, the replace transaction, the breaker, migrations and the enable gate | [PostgreSQL index](architecture/index-store.md) |
| Startup order, the fetch loop's backoff and per-tick archive eviction, `/healthz` vs `/readyz`, `reindex --accept-rewind` | [Scheduler and operational surface](architecture/scheduler-and-ops.md) |
| What a catalog repository must contain, what `init` seeds, how a skill is scaffolded, written, updated, retired, replaced, pinned | [Skill lifecycle](workflows/skill-lifecycle.md) |
| The Harbor shape of an eval case, how runs land in Langfuse, run metadata, the CI evals job and its credential check | [Evals and records](workflows/evals-langfuse.md) |
| The `docker/` layout, the three compose files, secret files, proxy paths, the LDAP overlay and hairpin, image tags | [Deployment](operations/deployment.md) |
| The six settings, `_FILE` secrets, where `docker/.env` and `SECRETS_DIR` live, the single source for Dex values, OTel variables | [Configuration](operations/configuration.md) |
| What each test suite proves and with which doubles; the archive and CI-logic suites; the static gates | [Test strategy](testing/test-strategy.md) |
| Why it is built this way: no write tools, derivative DB, Langfuse records, one group, no scope checks, compose under `docker/`, CI logic in the CLI, header-token downloads | [Design decisions in brief](concepts/design-decisions.md) |

## By task

- **Changing how skills are validated** → check items, then catalog app (how rejections surface), then skill lifecycle (what authors will experience).
- **Touching auth or Dex configuration** → auth, then design decisions (the three 2026-10-07 decisions), then deployment (overlay, proxy paths).
- **Changing the index or search** → PostgreSQL index, then catalog app (`STALE`/`UNAVAILABLE` semantics), then test strategy (the container tests to extend).
- **Adding a setting or a variable** → configuration first: the rule is that the registry has six settings (five required plus `fetch_interval_seconds`); most additions belong to another layer, and the archive feature shows how to add behaviour without a setting.
- **Changing the catalog CI or the templates `init` writes** → CLI and catalog CI (the logic lives in `ci.py`, the YAML only wires it), then skill lifecycle (what a new catalog receives), then test strategy (`tests/cli/test_ci.py`).
- **Changing how a skill is downloaded or pinned** → archive download (tool, token, route, cache), then skill lifecycle (the `pin-skill` procedure), then auth (why the route verifies only the header token).
- **Diagnosing a 503 or a degraded registry** → scheduler and operational surface (the `reasons`/`degraded`/`rejected` table), then the page for the subsystem named in the reason.
- **Standing up a new environment** → deployment, then §0 of `docs/configuration.md` for the minimal inputs; remember that every command is `docker compose -f docker/compose.yml …` and that `SECRETS_DIR` is resolved from `docker/`.

## Conventions used in these pages

Identifiers, paths, commands and error codes are verbatim from the code. "Design says" points at `DESIGN.md`; "measured" points at `plans/pilot/r*.md`. Human-facing operating guides live in `docs/` (Korean) — using, authoring, operations, configuration, development — and are not duplicated here.

These pages are generated, not hand-written. `.github/workflows/openwiki-update.yml` runs on a **daily schedule** (`0 19 * * *` UTC, 04:00 KST) and on `workflow_dispatch` with a boolean `force` input; it no longer runs on every push, because per-merge runs paid the fixed planning and finishing cost once per merge and cancelled each other. A "Detect source changes since the wiki baseline" step reads `gitHead` from `openwiki/.last-update.json` and diffs it against `HEAD` excluding `openwiki/**`, `AGENTS.md`, `CLAUDE.md` and the workflow file (the `OPENWIKI` blocks in `AGENTS.md`/`CLAUDE.md` are rewritten on every run, and the first merge of a wiki PR was measured to re-trigger the old push trigger); if nothing else changed and `force` is not set, every later step is skipped and the model is never called. When the baseline is missing or unreachable the run proceeds. `concurrency: openwiki-update` with `cancel-in-progress: true` keeps a manual run and the schedule from splitting the baseline commit; the later run wins. The checkout uses `fetch-depth: 0`, because `openwiki code --update` diffs `HEAD` against the commit it last documented and a shallow clone hides that commit, leaving the run with an empty change summary. The job installs `openwiki@0.6.1` globally (together with optional `mermaid` and `jsdom`, which add high-fidelity validation of Mermaid diagrams), runs `openwiki code --update --print` with `OPENWIKI_PROVIDER: anthropic`, the `ANTHROPIC_API_KEY` secret and the model from the repository variable `OPENWIKI_MODEL_ID` (default `claude-opus-5`; `claude-sonnet-5` is the documented cheaper choice), removes the transient `openwiki/.run.json`, and opens a pull request on branch `openwiki/update` through `peter-evans/create-pull-request`. The generation step is `continue-on-error: true`: a `failure` outcome still opens that PR, preserving only the pages completed before the failure, and a final step re-raises the failure with `exit 1`. The baseline recorded in `openwiki/.last-update.json` only advances once the PR is merged. Freshness between batches is the SessionStart hook's job, not the workflow's.

Do not run an update by hand inside an MR — the generated sidecar and the baseline commit split. Only run one from a clean `main`, and only when CI is blocked or the batch is too far away. The toolchain is pinned to `openwiki@0.6.1` in `package.json` and `.mcp.json`; `make wiki-install` rewrites that wiring (`.claude/skills/openwiki`, `.mcp.json`) and `make mcp-pin` re-pins the `graft` and `openwiki` servers in `.mcp.json` from `package.json`, because the init tools write them without a version. Before raising an MR, `make wiki-claims` lists the pages whose claims cite files the current branch changed (no model, a few seconds).
