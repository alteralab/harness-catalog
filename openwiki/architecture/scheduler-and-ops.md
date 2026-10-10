---
type: architecture
title: Scheduler and operational surface — fetch loop, archive eviction, /healthz, /readyz
description: How the registry process starts and stops, how the fetch loop paces itself with exponential backoff and evicts expired archive tars each tick, what the two operational routes report and which reason codes an operator will see, and the reindex --accept-rewind command for an intentionally rewound main.
tags: [scheduler, operations, readiness, backoff, reindex, lifespan]
sources:
  - id: openwiki-source-85a76422b73202924b7addfe
    resource: repo://packages/core/src/harness_catalog_core/catalog.py
  - id: openwiki-source-f426b79a4adacbf83e4356b3
    resource: repo://packages/server/src/harness_catalog_server/__main__.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-84243c2775db291b35a77ac2
    resource: repo://packages/server/src/harness_catalog_server/driving/ops.py
  - id: openwiki-source-4599c74d95f98ca664b58c4a
    resource: repo://packages/server/src/harness_catalog_server/driving/scheduler.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Scheduler and operational surface

The registry is one process with three driving adapters besides the MCP tools: a startup/shutdown lifespan, a fetch loop, and two HTTP routes for orchestration. None of them contains catalog logic; they call `Catalog.rebuild()`, `Catalog.evict_archives()` and `Catalog.status()` and translate the results into timing and HTTP status codes.

## Startup and shutdown

`harness-catalog-server serve` reads the six settings (exiting with code 2 and pydantic's message if any is missing or invalid), configures tracing if an OTLP endpoint is present, builds the app through `bootstrap` — which also creates the process-lifetime archive-signing key and empties the archive cache, since no token minted before the restart can verify any more — and hands the ASGI application to uvicorn (`--host`, `--port`, `--workdir`, `--log-level`).

The Starlette lifespan does, in order: open the PostgreSQL pool; enter the MCP app's own lifespan; start a task group with two tasks — the **migration task** and the **scheduler**; yield to serve requests; on shutdown set the stop event, wait for both tasks to end, then close the pool and the git store (which deletes the deploy key file). Because the task group is awaited before the pool closes, no task is left mid-query at exit.

The migration task applies pending migrations and, on success, enables the fact store and sets a `db_ready` event. On failure it retries with backoff from 5 s doubling to a 5 min cap. The scheduler waits for `db_ready` for at most 10 s before its first build; after that it proceeds regardless, because the database is not a readiness condition — the registry serves from memory until the database is usable.

## The fetch loop

Each iteration first calls `catalog.evict_archives()` and then `catalog.rebuild()`, both in a worker thread, then sleeps `interval × backoff` seconds (interval from `HC__FETCH_INTERVAL_SECONDS`, default 60) or until the stop event fires. The backoff factor is a pure function: doubled on failure up to 16, reset to 1 on success. "Failure" is defined narrowly — a fetch failure (`reasons` non-empty) or a build failure (`checker_failed:…` or `rebuild_failed:…` in `degraded`). Rejected skills and a lost database are **not** failures, so they never slow the loop. An unexpected exception from `rebuild` is logged and counted as a failure; the loop never dies. Every iteration that returned reasons, degradations or rejections is logged with the current backoff factor.

The practical effect: a healthy catalog is polled every minute; an unreachable git host is polled at 2, 4, 8 and then 16 minutes until it returns, at which point the cadence snaps back to one minute.

The eviction call is the registry's only housekeeping besides the index: it deletes cached archive tars whose last issue (file mtime) is older than the download token's lifetime plus leeway plus a minute, so the `clone` volume never accumulates them and a file is removed only once no token for it can still verify. Eviction failures do not affect the backoff; the call is cheap (a directory scan) and runs before the fetch so a slow git host does not delay it. See [Archive download](archive-download.md).

## `/healthz` and `/readyz`

- `/healthz` always returns 200 `{"status": "ok"}` while the process is up. Orchestrators use it for liveness; the compose healthcheck polls it.
- `/readyz` returns the catalog `Status` as JSON and uses the HTTP code to say whether the registry can serve: **200** when a snapshot exists, **503** otherwise. The body carries `ready`, `reasons`, `degraded`, `commit`, `fetched_at`, `built_at` and `rejected` (as `{skill, reason}` objects).

Reading the body:

| Field | Values | What to do |
|---|---|---|
| `reasons` | `repo_unreachable`, `no_main_branch`, `not_a_catalog`, `unsupported_layout`, `layout_mismatch` | Fix the repository URL/key, run `harness-catalog init`, or fix the marker file; the raw git error is in `degraded` |
| `degraded` | `db_unavailable`, `main_rewound`, `checker_failed:…`, `rebuild_failed:…` | Serving continues from memory; investigate the database, accept the rewind, or fix the checker (e.g. gitleaks) |
| `rejected` | per-skill `item: reason` | Authors fix the skill; nothing else is affected |

Readiness is deliberately about the catalog, not the database: a registry with a working snapshot and a dead PostgreSQL is **ready** (search falls back to in-memory containment) and only degraded.

## `reindex --accept-rewind`

When `main` was rewound on purpose, the scheduler refuses to follow it (`main_rewound`) because the served index never moves backwards. The operator runs:

```sh
harness-catalog-server reindex --accept-rewind
```

The command applies migrations, builds a catalog with the same settings, opens and enables the fact store, calls `rebuild(accept_rewind=True)`, prints the resulting status and exits 0 only if the catalog is ready and no longer rewound. It writes the new generation to PostgreSQL; the serving process must then be restarted so its in-memory copy follows. Without `--accept-rewind` the same command is a plain one-shot rebuild that respects the generation rule.

## Related

- [Catalog app](catalog-app.md) — the status machine these adapters expose
- [PostgreSQL index](index-store.md) — the migration task's counterpart and the enable gate
- [Deployment](../operations/deployment.md) — the compose healthcheck and the runbook for 503 reasons
- [Archive download](archive-download.md) — what the per-tick eviction cleans up and why the retention is seven minutes
