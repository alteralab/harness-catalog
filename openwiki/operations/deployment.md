---
type: operations
title: Deployment — compose files under docker/, secret files, proxy, LDAP overlay, image
description: How the registry is stood up. The docker/ layout and what differs between the production, development and quickstart compose files; the eight secret files under SECRETS_DIR and the script that makes them; the three proxy paths and why the archive route needs no fourth; the production-only Synology LDAP overlay with its hairpin mapping; how the image is built and tagged by CI; and why the quickstart shares a network namespace between registry and Dex.
tags: [deployment, compose, docker, secrets, proxy, ldap, ci]
sources:
  - id: openwiki-source-715dace563ef484b6e8bd1e2
    resource: repo://.dockerignore
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-ca9eabc24825e6ff0edc2967
    resource: repo://DESIGN.md
  - id: openwiki-source-b79e0281d1b09a8b2bfd2a06
    resource: repo://docker/compose.dev.yml
  - id: openwiki-source-bf2f07ac78709d005a9f28b9
    resource: repo://docker/compose.quickstart.yml
  - id: openwiki-source-8cb90064a9a682740da2974b
    resource: repo://docker/compose.yml
  - id: openwiki-source-64093b456f7feddb796be511
    resource: repo://docker/postgres/init.sh
  - id: openwiki-source-8dce026a7a38d31fea2197ea
    resource: repo://docker/quickstart/seed-catalog.sh
  - id: openwiki-source-a3ac6f697d6a74a34e4ae655
    resource: repo://docker/synology-ldap/compose.override.yml
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-d1a506dbe5374546142e2cfd
    resource: repo://docs/operations.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-480437ca124a00d81b6ec34c
    resource: repo://packages/server/src/harness_catalog_server/driving/archive_route.py
  - id: openwiki-source-79e93d315437d87506a6b03f
    resource: repo://scripts/make-secrets.sh
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Deployment

The deliverable is one container image plus compose files; the design keeps a single host, a few seconds of downtime on upgrade, and no backups, because everything in the database is regenerable from `main`. Three compose files cover three situations and they do not overlap in purpose.

## Everything compose-related lives under `docker/`

Since 2026-10-10 the compose files, `.env.example`, the Dex configurations, the PostgreSQL init scripts, the quickstart seed and the LDAP overlay all live under `docker/`; the Dockerfile and `.dockerignore` stay at the repository root because the build context is the root. Compose resolves `.env` and relative paths from the compose file's directory, which has three practical consequences:

- the operator's file is `docker/.env`, copied from `docker/.env.example`;
- `SECRETS_DIR` defaults to `../secrets`, the `secrets/` directory at the repository root that `scripts/make-secrets.sh secrets` creates (the first production deployment with `./secrets` failed because that path meant `docker/secrets`);
- every command carries the file name: `docker compose -f docker/compose.yml up -d`, with `-f docker/synology-ldap/compose.override.yml` added for the team's LDAP.

The production and development files pin `name: harness-catalog`. Without it Compose would derive the project name from the new directory, `docker`, and the existing `harness-catalog_pgdata` and `harness-catalog_clone` volumes would be orphaned. The quickstart is deliberately a separate project, `harness-catalog-quickstart`, so it never touches those volumes.

## Three compose files

| File | Purpose | Registry runs | Secrets | Catalog | Who edits anything |
|---|---|---|---|---|---|
| `docker/compose.yml` | Production: `registry`, `postgres`, `dex` behind a reverse proxy | in a container from `REGISTRY_IMAGE` | Docker secret files under `SECRETS_DIR` | the real git repository over the deploy key | operator fills `docker/.env` and secret files |
| `docker/compose.dev.yml` | Development: `postgres` and `dex` only, ports bound to `127.0.0.1` | on the host (`make serve` sources `docker/.env` and runs `uv run harness-catalog-server serve`) | plain environment variables (the documented exception) | anything, including `file://` | developer fills `docker/.env` with random secrets |
| `docker/compose.quickstart.yml` | Evaluation: everything in containers, no file to edit | in a container built from the checkout (`build: ..`) | public default values | a bare repository **seeded from the CLI template's two base skills** | nobody; every variable has a default |

Dependencies are explicit: `registry` waits for `postgres` and `dex` to be healthy; the quickstart's `registry` additionally waits for `catalog-init` to complete successfully. Health checks are the services' own: `psql` probes that both databases and the `pg_trgm` extension exist, Dex's `/healthz/ready`, and the registry's `/healthz` (the quickstart probes `/readyz` so the welcome banner appears only once the seeded catalog is indexed).

## Secret files

Production passes every secret as a file mounted under `/run/secrets`. `scripts/make-secrets.sh <dir> [deploy_key]` creates the directory with mode 700 and, idempotently, eight files: four random values (`postgres_password`, `hc_db_password`, `dex_db_password`, `dex_ci_runner_secret`), the deploy key copied from the second argument (or empty, which only works for `file://` catalogs), `database_url` assembled from `hc_db_password`, and two empty placeholders that are only meaningful with a feature switched on — `otlp_headers` for Langfuse and `ldap_bind_pw` for the LDAP overlay. Existing files are never overwritten, so re-running the script after adding a key is safe. Rotation means replacing a file and restarting only the container that reads it. The production compose declares seven of the eight (`ldap_bind_pw` is declared by the overlay), each as `${SECRETS_DIR:-../secrets}/<name>`, so a missing file fails `up` immediately rather than at first use.

The PostgreSQL init script reads `*_FILE` or plain variables to create the two roles and databases on first start; the SQL itself lives outside `initdb.d` so the entrypoint does not run it twice.

## The proxy and its three paths

TLS termination and routing are the proxy's job (the team uses `tailscale serve`). Three paths must be forwarded: `/mcp` and `/.well-known/oauth-protected-resource` to the registry, `/dex` to Dex. The second path is the one people forget: a harness's first contact is a 401 whose `resource_metadata` points there, and if the proxy returns 404 the login flow never starts. The registry's `HC__PUBLIC_URL` is the proxy-facing URL; it is also the token audience, so it must match what Dex is told.

The archive download route added on 2026-10-11 needs no fourth mapping: it is registered at `/mcp/archive/<id>/<tree>.tar`, under the `/mcp` prefix the proxy already forwards, and `tailscale serve --set-path /mcp` passes subpaths through. This was verified on the operations host after the deployment, where the route answered 403 for a missing token both locally and through the proxy. See [Archive download](../architecture/archive-download.md).

## The Synology LDAP overlay

`docker/synology-ldap/compose.override.yml` is layered on top of the **production** compose only. It swaps Dex's config for the LDAP connector variant, adds the `ldap_bind_pw` secret and the `LDAP_*` variables (defaults point at the team NAS over LDAPS 636 with certificate verification skipped), and adds an `extra_hosts` entry on the registry that maps the public hostname to the host's Tailscale IP. That last mapping is the **hairpin**: the registry must reach the issuer at its public name to fetch discovery and JWKS, but from inside the container that name would otherwise resolve to an address the proxy does not serve. The overlay cannot be combined with the development compose: that file has no `registry` service, so the hairpin block makes `config` fail (measured 2026-10-10); development uses Dex's static users instead.

## Image and tags

The image is multi-stage: a builder installs only the server package from `pyproject.toml`, `uv.lock` and `packages/` with uv; the runtime stage is `python:3.12-slim` with `git`, `ca-certificates`, `openssh-client` and the `gitleaks` binary copied from the pinned gitleaks image, running as a non-root user whose home is the work directory. The runtime's git must be 2.42 or newer because the archive route relies on `git archive --mtime` for byte-deterministic tars; the current base image ships 2.47. CI builds the image on a self-hosted runner after every push to `main` (tag = short commit SHA) and on every `v*` tag (tag = the version), pushes to GHCR, and prunes untagged and old SHA versions while keeping version tags. Because the runner is the operations host, production can use the freshly built image without a pull; the operator sets `REGISTRY_IMAGE` in `docker/.env` to the short SHA of the released commit.

Everything outside the Dockerfile's inputs is excluded from the build context by `.dockerignore` — tests, docs, plans, the whole `docker/` directory, `secrets/`, `openwiki/`, Markdown, and the developer tooling (`node_modules/`, `graft/`, `.claude/`, `package.json`, `Makefile`, `.github/`).

## Why the quickstart shares a network namespace

OIDC needs one issuer URL that is valid both for the browser on the host and for the registry inside Docker. Production solves this with the public hostname and the hairpin; the quickstart has no proxy, so it puts the registry in Dex's network namespace (`network_mode: service:dex`). Both then see `http://localhost:5556/dex`, and Dex's service publishes both ports (5556 and 8000) to the host. A `welcome` container that shares the same namespace prints the URLs, the demo users, the machine-account example and the exact `claude mcp add` command once the registry is healthy.

The `catalog-init` container seeds the catalog from the CLI package's template directory — the marker file, the two base skills `pin-skill` and `write-skill`, README, pre-commit configuration, the GitHub workflow and its credentials action — into a bare repository on a named volume, substituting the CLI package version into the template pins, and exits; the registry fetches it over `file://`. This is the same source `harness-catalog init` writes, so the quickstart shows exactly what a new catalog repository looks like. The seed is idempotent, so restarting the stack keeps the data; `down -v` resets it. A `docker/.env` left over from development is honoured by the quickstart because the two files share a directory and variable names.

## Related

- [Configuration](configuration.md) — which variables each file reads and the minimal set an operator types
- [Scheduler and operational surface](../architecture/scheduler-and-ops.md) — what `/readyz` reports after `up`
- [Authentication and authorization](../architecture/auth.md) — the Dex clients and the LDAP connector
- [Archive download](../architecture/archive-download.md) — the route that rides the existing `/mcp` proxy mapping
- [Design decisions](../concepts/design-decisions.md) — why compose moved to `docker/` and `examples/` went away
