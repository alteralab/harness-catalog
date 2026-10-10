---
type: architecture
title: PostgreSQL index — schema, transaction, breaker, migrations
description: The FactStore adapter on PostgreSQL. One index table plus one state row, all derived from main; the search query; the build transaction with its advisory lock and ancestor check; the half-open circuit breaker that lets the registry keep serving from memory while the database is down; the migration task that runs at startup with backoff and gates database access until applied.
tags: [postgresql, index, fact-store, breaker, migrations, search]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-a461033ed5771c09838cd6c8
    resource: repo://packages/server/src/harness_catalog_server/adapters/pg.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-4599c74d95f98ca664b58c4a
    resource: repo://packages/server/src/harness_catalog_server/driving/scheduler.py
  - id: openwiki-source-7d3b07754d7565d39d61f1cc
    resource: repo://packages/server/src/harness_catalog_server/migrate.py
  - id: openwiki-source-0790dc08bc2a47935ac3b259
    resource: repo://packages/server/src/harness_catalog_server/migrations/0001_schema.sql
  - id: openwiki-source-29be958e8697accdf8fe919d
    resource: repo://tests/adapters/test_pg.py
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# PostgreSQL index

`PgFactStore` is the `FactStore` adapter. It holds nothing authoritative: the index table and the state row are a projection of the in-memory snapshot that the [catalog app](catalog-app.md) builds from `main`, and they can be rebuilt at any time. The database exists for ranked search and for remembering which generation of `main` was last indexed across restarts.

## Schema

Two tables, created by the single migration `0001_schema.sql`:

- `skill_index` — one row per indexed skill: `name` (primary key, 64 chars), `description`, `compatibility`, `metadata` (jsonb), `tree_sha`, `commit_sha`, `indexed_at`. Four **generated** columns derive from `metadata`: `replaced_by` and `requires_tools` (an array split on spaces), plus `search_text` and a `tsvector` `search` built from name, description and all metadata values. GIN indexes cover the `tsvector`, a trigram index on `search_text` (`pg_trgm`) and the `requires_tools` array.
- `index_state` — a single row (`id = 1` enforced by a check constraint) with the `commit_sha` and `indexed_at` of the current generation.

The generated-column and index DDL is the contract string from the design document; `tests/adapters/test_pg.py` reads the live catalog back and compares the expressions, so a drift between document and migration fails a test.

## Replacing the index: one transaction

`replace_index(snapshot, is_descendant)` does everything in one transaction:

1. Take a transaction-scoped advisory lock (`pg_advisory_xact_lock` on a fixed key). On the very first build there is no row to lock, so this lock is what serialises two registries starting at once.
2. `SELECT … FOR UPDATE` the state row. If a stored commit exists, differs from the snapshot's commit and is **not** an ancestor of it (the predicate is supplied by the app, which asks git), return `STALE` without touching anything.
3. `DELETE FROM skill_index`, insert every entry, and upsert the state row.

The outcome is one of three values: `REPLACED`, `STALE`, or `UNAVAILABLE` when the pool times out or the driver raises. `UNAVAILABLE` is never an exception: the adapter logs, records a breaker failure and returns the value, and the app keeps serving from memory with `db_unavailable` in `degraded`. A concurrent-first-build test asserts the all-or-nothing property.

## Search

`search(query, limit)` returns skill names ranked by full-text rank (`plainto_tsquery` on the `simple` configuration), then trigram similarity, then name. Three predicates are OR-ed so that a query matches by full-text, by trigram similarity, or by a case-insensitive `ILIKE` with the query's words joined by wildcards. The query text is passed as a parameter, never interpolated. When the database is unavailable the method returns `None` and the app falls back to a containment search over the in-memory snapshot.

## Circuit breaker

Every database call is gated by a `Breaker` with three states. Three consecutive failures open it for 30 seconds; while open, calls return `UNAVAILABLE`/`None` immediately without touching the pool. When the open period ends the breaker is **half-open**: exactly one probe is let through; success closes it, failure re-opens it for another period. The clock is injectable, so the state machine is tested without sleeping. Statement timeout is 5 s and the pool holds 1–4 connections, so a stalled database bounds latency instead of hanging the fetch loop.

## Migrations and the enable gate

Migrations are applied with yoyo from the package's `migrations/` directory, under yoyo's own lock, and the function returns the number applied. At startup the server launches a dedicated task that calls `migrate()` and retries on failure with exponential backoff from 5 s up to 5 min; it runs independently of the fetch loop, so a database that comes up late never delays serving. Until the migration task reports success the store is **disabled**: every call returns `UNAVAILABLE`/`None` (a test asserts this), and the scheduler waits at most 10 s for that signal before starting the first build, because the database is not a readiness condition.

## Failure behaviour

| Condition | Adapter | App-level effect |
|---|---|---|
| Database unreachable or pool timeout | `UNAVAILABLE` / `None`, breaker failure | Serve from memory, `degraded: db_unavailable`; resync on a later cycle |
| Breaker open | Immediate `UNAVAILABLE` / `None` | Same, without load on the database |
| Stored commit newer or unrelated | `STALE` | In-memory snapshot also left unchanged (`main_rewound`) |
| Migration not yet applied | Disabled: `UNAVAILABLE` / `None` | Serve from memory until `enable()` |

## Tests

`tests/adapters/test_pg.py` runs against a throwaway PostgreSQL from testcontainers: the schema contract, generation checks and search ranking, breaker opening and the half-open probe (with a fake clock), unreachable database as a value rather than an exception, the all-or-nothing concurrent first build, the DDL contract match, and the disabled-until-migrated gate.

## Related

- [Catalog app](catalog-app.md) — how `REPLACED`/`STALE`/`UNAVAILABLE` drive the status machine
- [Scheduler and operational surface](scheduler-and-ops.md) — the migration task and the 10-second wait before the first build
