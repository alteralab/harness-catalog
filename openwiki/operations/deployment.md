---
type: operations
title: Deployment — the three compose files, secret files, proxy, LDAP overlay, image
description: How the registry is stood up. What differs between the production, development and quickstart compose files and what each assumes; the eight secret files and the script that makes them; the three proxy paths and why the third one matters; the Synology LDAP overlay with its hairpin mapping; how the image is built and tagged by CI, and why the quickstart shares a network namespace between registry and Dex.
tags: [deployment, compose, docker, secrets, proxy, ldap, ci]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-715dace563ef484b6e8bd1e2
    resource: repo://.dockerignore
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-0c106052b3286e779bed85e7
    resource: repo://docker-compose.dev.yml
  - id: openwiki-source-0b052d8b887a85484c366e21
    resource: repo://docker-compose.quickstart.yml
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
  - id: openwiki-source-64093b456f7feddb796be511
    resource: repo://docker/postgres/init.sh
  - id: openwiki-source-8dce026a7a38d31fea2197ea
    resource: repo://docker/quickstart/seed-catalog.sh
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-b8a89fa75bcbf4f5a743e336
    resource: repo://examples/synology-ldap/docker-compose.override.yml
  - id: openwiki-source-79e93d315437d87506a6b03f
    resource: repo://scripts/make-secrets.sh
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Deployment

The deliverable is one container image plus compose files; the design keeps a single host, a few seconds of downtime on upgrade, and no backups, because everything in the database is regenerable from `main`. Three compose files cover three situations and they do not overlap in purpose.

## Three compose files

| File | Purpose | Registry runs | Secrets | Catalog | Who edits anything |
|---|---|---|---|---|---|
| `docker-compose.yml` | Production: `registry`, `postgres`, `dex` behind a reverse proxy | in a container from `REGISTRY_IMAGE` | Docker secret files under `SECRETS_DIR` | the real git repository over the deploy key | operator fills `.env` and secret files |
| `docker-compose.dev.yml` | Development: `postgres` and `dex` only, ports bound to `127.0.0.1` | on the host (`uv run harness-catalog-server serve`) against the same `.env` | plain environment variables (the documented exception) | anything, including `file://` | developer fills `.env` with random secrets |
| `docker-compose.quickstart.yml` | Evaluation: everything in containers, no file to edit | in a container built from the checkout | public default values | a bare repository **seeded from this repository's `skills/`** | nobody; every variable has a default |

Dependencies are explicit: `registry` waits for `postgres` and `dex` to be healthy; the quickstart's `registry` additionally waits for `catalog-init` to complete successfully. Health checks are the services' own: `psql` probes that both databases and the `pg_trgm` extension exist, Dex's `/healthz/ready`, and the registry's `/healthz`.

## Secret files

Production passes every secret as a file mounted under `/run/secrets`. `scripts/make-secrets.sh <dir> [deploy_key]` creates the directory with mode 700 and, idempotently, eight files: four random values (`postgres_password`, `hc_db_password`, `dex_db_password`, `dex_ci_runner_secret`), the deploy key copied from the second argument (or empty, which only works for `file://` catalogs), `database_url` assembled from `hc_db_password`, and two empty placeholders that are only meaningful with a feature switched on — `otlp_headers` for Langfuse and `ldap_bind_pw` for the LDAP overlay. Existing files are never overwritten, so re-running the script after adding a key is safe. Rotation means replacing a file and restarting only the container that reads it.

The PostgreSQL init script reads `*_FILE` or plain variables to create the two roles and databases on first start; the SQL itself lives outside `initdb.d` so the entrypoint does not run it twice.

## The proxy and its three paths

TLS termination and routing are the proxy's job (the team uses `tailscale serve`). Three paths must be forwarded: `/mcp` and `/.well-known/oauth-protected-resource` to the registry, `/dex` to Dex. The second path is the one people forget: a harness's first contact is a 401 whose `resource_metadata` points there, and if the proxy returns 404 the login flow never starts. The registry's `HC__PUBLIC_URL` is the proxy-facing URL; it is also the token audience, so it must match what Dex is told.

## The Synology LDAP overlay

`examples/synology-ldap/docker-compose.override.yml` is layered on top of production (or development) compose. It swaps Dex's config for the LDAP connector variant, adds the `ldap_bind_pw` secret and the `LDAP_*` variables (defaults point at the team NAS over LDAPS 636 with certificate verification skipped), and adds an `extra_hosts` entry on the registry that maps the public hostname to the host's Tailscale IP. That last mapping is the **hairpin**: the registry must reach the issuer at its public name to fetch discovery and JWKS, but from inside the container that name would otherwise resolve to an address the proxy does not serve.

## Image and tags

The image is multi-stage: a builder installs only the server package from `pyproject.toml`, `uv.lock` and `packages/` with uv; the runtime stage is `python:3.12-slim` with `git`, `openssh-client` and the `gitleaks` binary, running as a non-root user whose home is the work directory. CI builds it on a self-hosted runner after every push to `main` (tag = short commit SHA) and on every `v*` tag (tag = the version), pushes to GHCR, and prunes untagged and old SHA versions while keeping version tags. Because the runner is the operations host, production can use the freshly built image without a pull.

Everything outside the Dockerfile's inputs is excluded from the build context by `.dockerignore` — tests, docs, plans, compose files, and the developer tooling (`node_modules/`, `graft/`, `.claude/`, `package.json`).

## Why the quickstart shares a network namespace

OIDC needs one issuer URL that is valid both for the browser on the host and for the registry inside Docker. Production solves this with the public hostname and the hairpin; the quickstart has no proxy, so it puts the registry in Dex's network namespace (`network_mode: service:dex`). Both then see `http://localhost:5556/dex`, and Dex's service publishes both ports (5556 and 8000) to the host. A `welcome` container that shares the same namespace prints the URLs, the demo users and the exact `claude mcp add` command once the registry is healthy.

The seed container builds the catalog from this repository's `skills/` and the CLI's templates into a bare repository on a named volume, substituting the CLI version into the template pins, and exits; the registry fetches it over `file://`. The seed is idempotent, so restarting the stack keeps the data; `down -v` resets it.

## Related

- [Configuration](configuration.md) — which variables each file reads and the minimal set an operator types
- [Scheduler and operational surface](../architecture/scheduler-and-ops.md) — what `/readyz` reports after `up`
- [Authentication and authorization](../architecture/auth.md) — the Dex clients and the LDAP connector
