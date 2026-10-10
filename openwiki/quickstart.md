---
type: guide
title: Quickstart — where to look for what
description: Task-routing map for this wiki. Which page answers which kind of question about harness-catalog, and what is deliberately not here — locations and signatures belong to Graft and the source, the full rationale to DESIGN.md.
tags: [quickstart, navigation, routing]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-80aabf5d700807c9b44ae3e8
    resource: repo://.claude/helpers/openwiki-age.sh
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-70991026f1538e8215a8789e
    resource: repo://docs/development.md
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Quickstart — where to look for what

This wiki explains **why and how** harness-catalog works. It is optional, just-in-time context: read a page when a task touches an unfamiliar part of the system or when the source leaves a question open, then stop. Two things are deliberately not here.

- **Where a symbol lives, who calls it, what an edit breaks** — ask Graft (`graft ask`, `graft callers`, `graft skeleton`, or the `graft_*` MCP tools) or read the source. Every `file:line` in these pages describes the code as it was when the page was last updated; the session-start hook prints how many commits have landed since.
- **The full design argument and its history** — `DESIGN.md` (Korean) is the contract and §11 its dated ledger of decisions and adversarial reviews; `plans/*.md` hold the execution plans and measurements. Pages here cite sections rather than restating them.

## By question

| If you need to know… | Read |
|---|---|
| What the pieces are and how a request or a publication flows through them | [System overview](architecture/overview.md) |
| How `main` becomes an index: fetch, checks, the status machine, rewinds, past versions, limits | [Catalog app](architecture/catalog-app.md) |
| What the ten checks look at, errors vs warnings, exit codes, why gitleaks is fail-closed | [The ten check items](architecture/check-items.md) |
| How the repository is cloned and read, the deploy key, `safe.directory`, history resolution | [GitStore](architecture/git-content-store.md) |
| Login, token verification, the audience scope, why only `harness-readers` matters | [Authentication and authorization](architecture/auth.md) |
| The four MCP tools, their payloads and error codes, the span attributes, OTel wiring | [MCP server](architecture/mcp-server.md) |
| The PostgreSQL schema, the replace transaction, the breaker, migrations and the enable gate | [PostgreSQL index](architecture/index-store.md) |
| Startup order, the fetch loop's backoff, `/healthz` vs `/readyz`, `reindex --accept-rewind` | [Scheduler and operational surface](architecture/scheduler-and-ops.md) |
| What a catalog repository must contain, how a skill is written, updated, retired, replaced, pinned | [Skill lifecycle](workflows/skill-lifecycle.md) |
| How evals run with Harbor and land in Langfuse, run metadata, the CI switch and its credential check | [Evals and records](workflows/evals-langfuse.md) |
| The three compose files, secret files, proxy paths, the LDAP overlay and hairpin, image tags | [Deployment](operations/deployment.md) |
| The six settings, `_FILE` secrets, the single source for Dex values, OTel variables, the generated reference | [Configuration](operations/configuration.md) |
| What each test suite proves and with which doubles; the static gates | [Test strategy](testing/test-strategy.md) |
| Why it is built this way: no write tools, derivative DB, Langfuse records, one group, no scope checks | [Design decisions in brief](concepts/design-decisions.md) |

## By task

- **Changing how skills are validated** → check items, then catalog app (how rejections surface), then skill lifecycle (what authors will experience).
- **Touching auth or Dex configuration** → auth, then design decisions (the three 2026-10-07 decisions), then deployment (overlay, proxy paths).
- **Changing the index or search** → PostgreSQL index, then catalog app (`STALE`/`UNAVAILABLE` semantics), then test strategy (the container tests to extend).
- **Adding a setting or a variable** → configuration first: the rule is that the registry has six settings; most additions belong to another layer.
- **Diagnosing a 503 or a degraded registry** → scheduler and operational surface (the reason table), then the page for the subsystem named in the reason.
- **Standing up a new environment** → deployment, then configuration §0 of `docs/configuration.md` for the minimal inputs.

## Conventions used in these pages

Identifiers, paths, commands and error codes are verbatim from the code. "Design says" points at `DESIGN.md`; "measured" points at `plans/pilot/r*.md`. Human-facing operating guides live in `docs/` (Korean) and are not duplicated here.
