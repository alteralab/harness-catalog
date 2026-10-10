---
type: testing
title: Test strategy — fake adapters, testcontainers, fake issuer, gates
description: Which layer each test suite measures and how it isolates it. Core tests drive the application through fake adapters with no clock; adapter tests use a real git repository and a throwaway PostgreSQL from testcontainers; HTTP tests run the real server process against a fake OIDC issuer; CLI tests run the commands end to end; pyright strict and the altera-rules gates run before every commit and in CI.
tags: [testing, pytest, testcontainers, fake-issuer, pyright, gates]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-4d1645cb6317345817452838
    resource: repo://.pre-commit-config.yaml
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-29be958e8697accdf8fe919d
    resource: repo://tests/adapters/test_pg.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-a11a11c2e4e310150c06f0d0
    resource: repo://tests/core/fakes.py
  - id: openwiki-source-ef613a68c4cecbb1abcfb8a8
    resource: repo://tests/core/test_catalog.py
  - id: openwiki-source-78f2b724faf3f0ce8eb57880
    resource: repo://tests/http/fake_issuer.py
  - id: openwiki-source-64993ac7d19db2729fe1e640
    resource: repo://tests/http/test_server.py
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Test strategy

The hexagonal split is what makes the suite cheap: the application is tested without git, a database or a network, and each adapter is tested against the real thing it wraps. There are 72 tests and they run in about a minute, most of which is the PostgreSQL container.

## Layers and what proves them

| Layer | Suite | Doubles | Real |
|---|---|---|---|
| Application (`Catalog`, checks, authorisation) | `tests/core/` | `FakeStore` (an in-memory git), `FakeValidator`, `MemoryFacts` — one class per port | nothing external; no clock |
| Git adapter | `tests/adapters/test_git*.py` | — | a repository built in a temp dir by the `catalog_repo` fixture |
| PostgreSQL adapter | `tests/adapters/test_pg.py` (marker `pg`) | an injectable clock for the breaker | a `postgres:17` container from testcontainers, migrations applied |
| HTTP surface | `tests/http/` (marker `http`) | `FakeIssuer`: a local HTTP server serving OIDC discovery and a JWKS, minting RS256 tokens with chosen `sub`, `aud`, `groups`, `exp` | the server as a **subprocess** (`python -m harness_catalog_server serve`) on a free port, reading a `file://` catalog |
| CLI | `tests/cli/` | — | `check`, `init`, `config` through typer's runner against real repositories |
| Harbor plugin | `tests/plugin/` | a recording sink | the plugin's job lifecycle with a Harbor-shaped job object |
| Telemetry | `tests/test_telemetry.py` | — | the OTel SDK provider, no network |

### Fakes mirror the ports exactly

`tests/core/fakes.py` implements the three protocols with the smallest behaviour that still exercises the app: `FakeStore` holds skills as `{name: {path: bytes}}`, computes deterministic tree hashes, and answers ancestry and version questions; `FakeValidator` can be told which names to reject; `MemoryFacts` can be switched to "unavailable" to simulate a lost database. Because the app only knows the protocols, these doubles are sufficient to reach every branch of the status machine — rewind refusal, `accept_rewind`, degraded-not-unready, same-commit resync — in milliseconds.

### The fixture repository

`conftest.catalog_repo` builds a valid catalog in a temporary directory: marker, `skills/`, a CI workflow, a pre-commit config, a README and two skills (one with scripts and references, one plain), committed on `main`. Adapter, CLI and HTTP suites all start from it, so "valid repository" means the same thing everywhere.

### Why the HTTP tests spawn a process

The MCP SDK's auth middleware, the lifespan, the scheduler and uvicorn all need to be exercised as deployed. The fixture starts the server with the six `HC__*` settings pointing at the fixture repository, the fake issuer and an unused database URL, polls `/readyz` until 200, and then speaks real HTTP: the 401 challenge, the protected-resource document and its exact `scopes_supported`, each tool as a reader, wrong-audience and expired tokens, a non-member, and a machine account. No Dex is involved; the issuer is the fake. A second suite exports spans to an in-memory exporter and asserts the attribute set.

### Why the database tests use a container

Generated columns, GIN indexes, `pg_advisory_xact_lock` and `FOR UPDATE` cannot be faked meaningfully. The container fixture applies the real migration and the tests cover the schema contract, ranking, the breaker (with a fake clock), unreachable-database-as-value, the all-or-nothing concurrent first build, and the disabled-until-migrated gate. On macOS Docker Desktop the suite sets `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` itself.

## Static gates

Every commit runs, through pre-commit, the altera-rules gates pinned at a tag: `altera-rules-declared` (the declared rule surfaces match what is installed), `altera-ruff`, `altera-ast-grep` and `altera-shellcheck`. `pyright` runs in strict mode over `packages`, `tests` and `tools` and must report zero errors. CI repeats pyright and pytest on every PR; the rule gates run in CI only when a token for the private rules repository is present, otherwise they are skipped with a warning and the local hook remains the only gate.

## Conventions worth knowing

- anyio tests run on the asyncio backend only (`anyio_backend` fixture).
- Markers `pg` and `http` name the suites that need Docker or a free port; everything else runs anywhere.
- Tests never read `~/.gitconfig` behaviour by accident: the registry-mode `GitStore` uses its own global config, and the CLI tests run with real repositories in temp dirs.

## Related

- [Catalog app](../architecture/catalog-app.md) — the status machine the core tests enumerate
- [PostgreSQL index](../architecture/index-store.md) — the behaviours the container tests pin
