---
type: architecture
title: Catalog app — snapshot, rebuild, read paths, archive cache — fetch, check, index, and the status machine
description: How the Catalog app fetches main, runs the checks and builds the index snapshot; the ready/degraded status and its reason codes; the generation rule that refuses a rewound main and accept_rewind; resolving a past version by sha; limits on the read paths.
tags: [catalog, index, rebuild, readiness, rewind, hexagonal]
sources:
  - id: openwiki-source-85a76422b73202924b7addfe
    resource: repo://packages/core/src/harness_catalog_core/catalog.py
  - id: openwiki-source-34f586c6418c2d86d226045c
    resource: repo://packages/core/src/harness_catalog_core/model.py
  - id: openwiki-source-373cc192d3e934375abc9e1f
    resource: repo://tests/core/test_archive.py
  - id: openwiki-source-ef613a68c4cecbb1abcfb8a8
    resource: repo://tests/core/test_catalog.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Catalog app

`Catalog` is the **application** of the hexagonal structure. It knows neither git nor PostgreSQL, only the three ports (`ContentStore`, `SkillValidator`, `FactStore`). It does two things: periodically fetch `main`, check it and build an index snapshot (`rebuild`), and answer reads from that snapshot (`list_skills`, `search_skills`, `load_skill`, `get_skill_file`, `get_skill_archive`). The scheduler drives the former (and, since 2026-10-11, the archive-cache eviction), the MCP tool adapter and the archive route the latter.

## One snapshot, replaced wholesale

The index is a single immutable `IndexSnapshot`: the entries, their commit, the build and fetch timestamps, and the list of rejected skills. A build replaces it as a whole. The in-memory copy is always "the served version"; PostgreSQL is a replica of it for search. Without a database the registry serves from memory, and when the database returns it re-synchronises from the same commit. The design principle "the DB never copies the source of truth; derived data is regenerated" is this code.

## The rebuild flow

1. **Fetch.** `ContentStore.fetch` returns the `main` commit. On failure the reason (`repo_unreachable`, `no_main_branch`) goes into `reasons` and the raw git error into `degraded`, so `/readyz` alone shows what git said. If a snapshot already exists, `ready` stays true.
2. **Structure check.** The marker file `.harness-catalog` and its `layout`, the required files and the `skills/` layout are inspected. A repository-level violation sets `ready=false` with `not_a_catalog`, `unsupported_layout` or `layout_mismatch` and stops the build.
3. **Same commit: resync only.** If the commit equals the previous one, skills are not re-checked; only the database synchronisation is retried (`_resync`). A database that went away and came back takes this path.
4. **Generation check.** If the new commit is not a descendant of the previous one, `main` was rewound. The default is to **change nothing** and record `main_rewound` in `degraded` (`_rewound`). The served version stays.
5. **Build.** `check_commit` runs the ten check items. If the checker itself fails (gitleaks missing, for example) the status is only degraded with `checker_failed:…` and the previous snapshot is kept. Skills with errors are excluded from the index and listed in `rejected` as `(name, "item: reason")`; the remaining skills' properties are read and the snapshot built.
6. **Database replacement.** `FactStore.replace_index` receives the snapshot and a predicate "is the stored commit an ancestor of the new one". `REPLACED` means in sync; `UNAVAILABLE` keeps the in-memory change and marks `db_unavailable`; `STALE` means the database is ahead or was rewound, and then **even the in-memory snapshot is left unchanged** (never go backwards).

On first start the commit stored in the database is used as the base. Restarting the registry therefore never steps behind a generation the database already holds.

## Accepting a rewind

When `main` was rewound on purpose (a force push, say), the operator runs `reindex --accept-rewind`. `accept_rewind=True` skips the generation check and builds even if the base commit is no longer in history. After accepting a rewind the serving process is restarted so its in-memory copy follows the new `main`. The command is a separate entry point, independent of the scheduler.

## What `Status` means

| Field | Meaning |
|---|---|
| `ready` | Whether a snapshot exists to serve. `false` before the first successful build |
| `reasons` | Why `ready=false`: `repo_unreachable`, `no_main_branch`, `not_a_catalog`, `unsupported_layout`, `layout_mismatch` |
| `degraded` | Ready but not whole: `db_unavailable`, `main_rewound`, `checker_failed:…`, `rebuild_failed:…`, raw git errors |
| `commit_sha`, `fetched_at`, `built_at` | The served version and its timestamps |
| `rejected` | Skills excluded from the index and why |

`/readyz` renders `ready` as 200/503 and the rest as the body. The scheduler counts only `reasons`, `checker_failed` and `rebuild_failed` as failures for backoff; rejected skills and a lost database are not failures.

## Read paths and limits

Every read starts from `_ready_snapshot`; without a snapshot it is `not_found` ("index not built yet").

- `search_skills` rejects a query over 2,000 characters or a `limit` outside 1..20 (default 10) with `input_limit`. Ranking comes from `FactStore.search`; without a database a plain containment search over the snapshot stands in.
- `load_skill(name, sha)` and `get_skill_file(name, path, sha)` enforce a 64-character name; an unknown name is `not_found`. When `sha` (the skill directory's tree hash) is given, `ContentStore.resolve_version` finds the commit in `main` history whose tree matches. If none does, the result is `unknown_version`. This is what makes a pinned old version readable at any time.
- A file that is a symbolic link is `path_rejected`; over 1 MB is `input_limit`; paths are capped at 1,024 characters. Text comes back as `text`, binary as `base64`.
- `get_skill_archive(name, sha)` resolves the version the same way and returns an `ArchiveInfo` (name, tree, commit, cache path, size, sha256) for a tar of the whole version. The tar is built by `ContentStore.archive_skill` into `workdir/archives/<tree>.tar` and reused while a `v2 <sha256>` sidecar validates it; a tar larger than 20 MB is `input_limit`. The build, validation and hashing are serialized under a separate `_archive_lock`, independent of the snapshot lock, and every issue touches the file's mtime. Signing and HTTP delivery are not the app's concern — see [Archive download](archive-download.md).

The four limits (`query_chars`, `file_bytes`, `max_limit`, `archive_bytes`) are injected through `Limits`, so tests substitute small values.

## The archive cache

`evict_archives(now, retention_seconds)` is the one maintenance path besides `rebuild`: it deletes cached tars (and their sidecars) whose mtime is older than the retention, which defaults to the token TTL plus leeway plus 60 seconds (7 minutes) — the point after which no download token for the file can still verify. Candidates are scanned outside the lock and re-checked under it before unlinking, so an issue that just refreshed a file's mtime wins. The scheduler calls it every tick; bootstrap calls it with retention 0 at startup. Because the tar bytes are deterministic (the adapter pins the archive mtime to the commit time), an evicted version is simply rebuilt byte-identically on the next request.

## Invariants

- The served version never moves backwards. A rewind is accepted only by an explicit operator command.
- A checker failure never produces a new version, by the same principle that makes secret scanning fail-closed.
- A repository-level violation means not ready; a skill-level violation means that skill is excluded. One bad skill does not take the catalog down.
- The app never drives a clock. `rebuild` and `evict_archives` are functions (`evict_archives` takes `now` as a parameter); the scheduler sets the cadence; tests call the functions without a clock.

## Tests

`tests/core/test_catalog.py` drives the app through fake adapters: the not-ready state, structure reasons, exclusion and reporting of rejected skills, past-version resolution and `unknown_version`, path/size/input limits, a lost database as degraded rather than unready, rewind refusal and `accept_rewind`, skipping a rebuild on the same commit, and using the database commit as the base on first start, each as one test. `tests/core/test_archive.py` covers the archive cache: creation and reuse with the sidecar, `not_found`/`unknown_version`/`input_limit`, rebuild on a corrupt, oversized or old-format cache, eight concurrent issues agreeing with the served bytes, and eviction by last-issue time.

## Related

- [The ten check items](check-items.md) — the rules run during the build step
- [GitStore](git-content-store.md) — fetch, ancestor check and history resolution
- [PostgreSQL index](index-store.md) — the `replace_index` transaction and `STALE`/`UNAVAILABLE`
- [Scheduler and operational surface](scheduler-and-ops.md) — cadence, backoff, `/readyz`, `reindex`
- [Archive download](archive-download.md) — the token, the route and pin-skill on top of `get_skill_archive`
