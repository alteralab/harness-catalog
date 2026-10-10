---
type: testing
title: Test strategy — fakes, testcontainers, fake issuer, CI-logic and archive suites, gates
description: What each test suite proves and with which doubles. One fake per port for the application, a temp-dir repository for the git adapter (including byte-deterministic archives), a PostgreSQL container, a fake OIDC issuer around a real server process (including the archive descriptor and download), typer runners for the CLI including the CI logic, gitleaks acquisition and the scaffold script, Harbor's Oracle for the shipped evals, and the static gates run by pre-commit and CI.
tags: [testing, pytest, testcontainers, fake-issuer, pyright, gates]
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-4d1645cb6317345817452838
    resource: repo://.pre-commit-config.yaml
  - id: openwiki-source-77c13e3620ded188cdf006fb
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/pin-skill/evals/pin-project-scope/solution/solve.sh
  - id: openwiki-source-61af20cd94b72635f491927e
    resource: repo://plans/skills.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-6ef6c6646b1605cce25a7f69
    resource: repo://tests/adapters/test_git.py
  - id: openwiki-source-29be958e8697accdf8fe919d
    resource: repo://tests/adapters/test_pg.py
  - id: openwiki-source-afe81887aa9e0e25a63c4164
    resource: repo://tests/cli/test_ci.py
  - id: openwiki-source-80a2cfb3c48998e688c559cb
    resource: repo://tests/cli/test_gitleaks.py
  - id: openwiki-source-07ac5d099591df90a057dfc7
    resource: repo://tests/cli/test_scaffold.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-a11a11c2e4e310150c06f0d0
    resource: repo://tests/core/fakes.py
  - id: openwiki-source-fa359de63e5c65ce0a41fbf1
    resource: repo://tests/core/test_archive_token.py
  - id: openwiki-source-373cc192d3e934375abc9e1f
    resource: repo://tests/core/test_archive.py
  - id: openwiki-source-ef613a68c4cecbb1abcfb8a8
    resource: repo://tests/core/test_catalog.py
  - id: openwiki-source-78f2b724faf3f0ce8eb57880
    resource: repo://tests/http/fake_issuer.py
  - id: openwiki-source-64993ac7d19db2729fe1e640
    resource: repo://tests/http/test_server.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Test strategy

The hexagonal split is what makes the suite cheap: the application is tested without git, a database or a network, and each adapter is tested against the real thing it wraps. The suite is 106 tests and runs in about a minute, most of which is the PostgreSQL container; without Docker, deselecting the `pg` marker still runs 97 of them.

## Layers and what proves them

| Layer | Suite | Doubles | Real |
|---|---|---|---|
| Application (`Catalog`, checks, authorisation, archive cache) | `tests/core/` | `FakeStore` (an in-memory git that can also write a tar), `FakeValidator`, `MemoryFacts` — one class per port; an injectable clock for the archive signer | nothing external |
| Git adapter | `tests/adapters/test_git*.py` | — | a repository built in a temp dir by the `catalog_repo` fixture |
| PostgreSQL adapter | `tests/adapters/test_pg.py` (marker `pg`) | an injectable clock for the breaker | a `postgres:17` container from testcontainers, migrations applied |
| HTTP surface | `tests/http/` (needs a free port, no Docker) | `FakeIssuer`: a local HTTP server serving OIDC discovery and a JWKS, minting RS256 tokens with chosen `sub`, `aud`, `groups`, `exp` | the server as a **subprocess** (`python -m harness_catalog_server serve`) on a free port, reading a `file://` catalog |
| CLI | `tests/cli/` | fake `which`/download callables for gitleaks; a recording runner for harbor | `check`, `init`, `config`, `ci base/check/evals` through typer's runner against real repositories; `scaffold.py` run as a script |
| Harbor plugin | `tests/plugin/` | a recording sink | the plugin's job lifecycle with a Harbor-shaped job object |
| Telemetry | `tests/test_telemetry.py` | — | the OTel SDK provider, no network |
| Shipped evals | not pytest: `harbor run -a oracle -e docker` | — | each eval's `solution/solve.sh` against its own verifier image |

### Fakes mirror the ports exactly

`tests/core/fakes.py` implements the three protocols with the smallest behaviour that still exercises the app: `FakeStore` holds skills as `{name: {path: bytes}}`, computes deterministic tree hashes, answers ancestry and version questions, and since the archive feature also implements `archive_skill` — it writes a real tar of the skill's files and honours `max_bytes`, so the cache, size-cap and corrupt-sidecar branches of `Catalog.get_skill_archive` run without git; `FakeValidator` can be told which names to reject; `MemoryFacts` can be switched to "unavailable" to simulate a lost database. Because the app only knows the protocols, these doubles are sufficient to reach every branch of the status machine — rewind refusal, `accept_rewind`, degraded-not-unready, same-commit resync — in milliseconds.

### The archive download is tested at every layer

- `tests/core/test_archive_token.py` pins the signer: mint-then-verify inside the TTL, rejection of a tampered signature, another skill or tree, a far-future expiry and malformed tokens, and that a different key (a restart) invalidates everything.
- `tests/core/test_archive.py` covers the cache: a second call reuses the tar and its sidecar, a corrupt or oversized cached file is rebuilt, concurrent mints agree on the bytes that are served, errors (unknown skill, too large) surface as the right exceptions, and eviction deletes only files whose last issue time is past the retention.
- `tests/adapters/test_git.py::test_archive_skill_is_deterministic_capped_and_clean` proves the git adapter produces identical bytes for the same tree on repeated calls, enforces the cap while writing, and leaves no partial file behind.
- `tests/http/test_server.py::test_archive_descriptor_then_download_without_bearer` goes through the real process: a reader calls the tool, downloads the URI with only the header token (no bearer), checks size and sha256 against the descriptor, and sees an empty 403 without the token.

### The CI logic is unit-tested because it left the YAML

`tests/cli/test_ci.py` fixes the base-commit rules that used to be shell in the workflow templates: merge-base for a pull request, the event's `before` for a push, the empty tree for a branch creation (so the root commit's skills are checked), fetching an unreachable `before` from origin once, and failing closed when a pull request has no remote ref or when a CI marker is present without the host's variables. It also covers changed-skill discovery, the per-harness credential table, the two-jobs-per-skill evals plan, the harbor environment, and the exit codes of `ci evals` and `ci check` through the typer runner. `tests/cli/test_gitleaks.py` covers acquisition: a `PATH` binary is used only when its version matches, a download is checksum-verified and cached with a sidecar, a checksum mismatch or malformed archive is "unavailable" rather than a traceback, and `check` exits 2 when gitleaks cannot be obtained. `tests/cli/test_scaffold.py` runs `write-skill`'s `scripts/scaffold.py` as a script and checks that it creates a skill with its Harbor-shaped eval pair, is idempotent, and rejects a bad name or a missing description.

### The fixture repository

`conftest.catalog_repo` builds a valid catalog in a temporary directory: marker, `skills/`, a CI workflow, a pre-commit config, a README and two skills (one with scripts and references, one plain), committed on `main`. Adapter, CLI and HTTP suites all start from it, so "valid repository" means the same thing everywhere.

### Why the HTTP tests spawn a process

The MCP SDK's auth middleware, the lifespan, the scheduler, the archive route and uvicorn all need to be exercised as deployed. The fixture starts the server with the six `HC__*` settings pointing at the fixture repository, the fake issuer and an unused database URL, polls `/readyz` until 200, and then speaks real HTTP: the 401 challenge, the protected-resource document and its exact `scopes_supported`, each read tool as a reader, wrong-audience and expired tokens, a non-member, a machine account, and the archive descriptor followed by the download. No Dex is involved; the issuer is the fake. A second suite exports spans to an in-memory exporter and asserts the attribute set.

### Why the database tests use a container

Generated columns, GIN indexes, `pg_advisory_xact_lock` and `FOR UPDATE` cannot be faked meaningfully. The container fixture applies the real migration and the tests cover the schema contract, ranking, the breaker (with a fake clock), unreachable-database-as-value, the all-or-nothing concurrent first build, and the disabled-until-migrated gate. On macOS Docker Desktop the suite sets `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` itself.

### The shipped evals are verified with Harbor's Oracle

The evals under the two base skills are not run by pytest. Each carries `solution/solve.sh`, and `harbor run -a oracle -e docker` executes that script inside the eval's own environment image and then the verifier, so the task text, the image and the pytest verifier are proven consistent without calling a model. The Oracle agent accepts no `--skill`, which is why every `solve.sh` is self-contained.

## Static gates

Every commit runs, through pre-commit, the altera-rules gates pinned at a tag: `altera-rules-declared` (the declared rule surfaces match what is installed), `altera-ruff` with `--config pyproject.toml` (the project's `[tool.ruff]` table extends the shared base, and the hook refuses a config that does not), `altera-ast-grep` and `altera-shellcheck`. `pyright` runs in strict mode over `packages`, `tests` and `tools` and must report zero errors. CI repeats pyright and pytest on every PR; the rule gates run in CI only when a token for the private rules repository is present, otherwise they are skipped with a warning and the local hook remains the only gate.

## Conventions worth knowing

- anyio tests run on the asyncio backend only (`anyio_backend` fixture).
- The marker `pg` names the suite that needs Docker. A marker `http` is declared in `pyproject.toml` for the server suite, but no test currently carries it, so `tests/http/` runs in the default selection.
- Tests never read `~/.gitconfig` behaviour by accident: the registry-mode `GitStore` uses its own global config, and the CLI tests run with real repositories in temp dirs.
- Tests that depend on the package version (the CLI's `--version`) read it from the installed package metadata rather than hard-coding it, after a hard-coded value broke the suite on the first release bump.

## Related

- [Catalog app](../architecture/catalog-app.md) — the status machine the core tests enumerate
- [PostgreSQL index](../architecture/index-store.md) — the behaviours the container tests pin
- [Archive download](../architecture/archive-download.md) — what the four archive suites together guarantee
- [CLI and CI](../architecture/cli-and-ci.md) — the base-commit and gitleaks rules under test
- [Evals and records](../workflows/evals-langfuse.md) — the Harbor task shape the Oracle check exercises
