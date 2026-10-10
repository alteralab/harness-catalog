---
type: operations
title: Configuration — the six HC__ settings, _FILE secrets, observability variables
description: How the registry is configured and why the surface is small. The six HC__ settings and their validation (including trailing-slash rejection), the *_FILE secret source used by Docker secrets, how compose derives Dex's issuer and audience from the same two settings, why the OTel variables are not settings, and how the configuration reference keeps a generated region inside a hand-written document.
tags: [configuration, settings, secrets, env, otel, compose]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-5f5b95b3d6a215fa02ceb945
    resource: repo://.env.example
  - id: openwiki-source-0c106052b3286e779bed85e7
    resource: repo://docker-compose.dev.yml
  - id: openwiki-source-0b052d8b887a85484c366e21
    resource: repo://docker-compose.quickstart.yml
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
  - id: openwiki-source-f9a97df6afb4dd8c285f0b2c
    resource: repo://docs/configuration.md
  - id: openwiki-source-37c3c9f4a0365c33199e11c0
    resource: repo://packages/cli/src/harness_catalog_cli/config.py
  - id: openwiki-source-1f7212efc41fd797b2b123e9
    resource: repo://packages/core/src/harness_catalog_core/settings.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-894244c6a8d53cceecd9b6cf
    resource: repo://packages/server/src/harness_catalog_server/telemetry.py
  - id: openwiki-source-9ed8710f6e966a268201a49f
    resource: repo://tests/cli/test_config_docs.py
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Configuration

The registry's configuration is deliberately a single, small list. Everything else an operator sees in `.env.example` or `docs/configuration.md` belongs to another layer — compose, Dex, observability, CI — and the reference document is organised by those layers so that "what must I fill in" is answered before "what exists".

## The six settings

`Settings` (pydantic-settings) reads environment variables with the prefix `HC__`:

| Variable | Required | Meaning |
|---|---|---|
| `HC__CATALOG_REPO_URL` | yes | Catalog git repository URL; fetched with the deploy key, never pushed |
| `HC__GIT_DEPLOY_KEY` | yes | Private key of the read-only deploy key (PEM). Empty string for a local `file://` repository |
| `HC__OIDC_ISSUER` | yes | OIDC issuer URL: the token `iss` and where discovery/JWKS are fetched |
| `HC__PUBLIC_URL` | yes | The registry's public URL = token audience = RFC 9728 `resource` |
| `HC__DATABASE_URL` | yes | PostgreSQL connection string |
| `HC__FETCH_INTERVAL_SECONDS` | no (60) | Fetch cadence; must be ≥ 1 |

A missing or invalid required value stops `serve` with exit code 2 and pydantic's message naming the field. Secrets (`git_deploy_key`, `database_url`) are `SecretStr`, so they are masked in `config list` output and in reprs.

**Trailing slashes are rejected** on `HC__OIDC_ISSUER` and `HC__PUBLIC_URL` by a `before` validator. The reason is not aesthetics: Dex receives the same two strings as its issuer and audience client id, and the registry strips a trailing slash internally while Dex does not, so `…/mcp/` and `…/mcp` would silently split the audience between the two services. Refusing the input makes the mismatch impossible instead of unlikely.

## Secrets from files: the `_FILE` source

A custom settings source reads `HC__<NAME>_FILE=<path>` and uses the file's content (trailing newline stripped) as the value. It sits after the plain environment in the precedence order, so an explicit `HC__X` wins over `HC__X_FILE`. Production compose uses this for the two secrets (`/run/secrets/git_deploy_key`, `/run/secrets/database_url`) and never puts them in the environment; the development compose, by documented exception, passes them as variables.

## One source for Dex's issuer and audience

Dex needs the issuer URL and the registry URL too (the latter as the id of the audience client). All three compose files pass `DEX_ISSUER` and `HC_PUBLIC_URL` to the Dex container **from** `HC__OIDC_ISSUER` and `HC__PUBLIC_URL`; the operator never types them twice and `.env.example` has no separate Dex entries for them. Together with the trailing-slash validator this closes the class of "works in the registry, fails in Dex" misconfigurations.

## Observability variables are not settings

`OTEL_EXPORTER_OTLP_ENDPOINT`, `_HEADERS`, `_PROTOCOL` and `OTEL_SERVICE_NAME` are the OpenTelemetry SDK's standard variables. The registry only checks whether an endpoint is present to decide whether to install a tracer provider; the exporter reads the rest itself. Production compose supplies the Langfuse `Authorization` header through a secret file (`OTEL_EXPORTER_OTLP_HEADERS_FILE` → `/run/secrets/otlp_headers`) because the header embeds the project keys; an empty file means "no headers". Keeping these out of `Settings` keeps the registry's contract at six values and lets the same variables work for any OTLP backend.

## Where the other variables live

| Layer | Examples | Where they are set |
|---|---|---|
| Compose (production) | `REGISTRY_IMAGE`, `REGISTRY_PORT`, `DEX_PORT`, `SECRETS_DIR` | `.env` beside `docker-compose.yml` |
| Compose (development) | `POSTGRES_PASSWORD`, `HC_DB_PASSWORD`, `DEX_DB_PASSWORD`, `DEX_CI_RUNNER_SECRET`, `POSTGRES_PORT` | `.env`; random values generated by the operator |
| Compose (quickstart) | the same names, all defaulted to public values | nothing to set; a stray `.env` in the directory overrides the defaults |
| Dex / LDAP | `LDAP_HOST`, `LDAP_BIND_DN`, `LDAP_BIND_PW(_FILE)`, `LDAP_USER_BASE_DN`, `LDAP_GROUP_BASE_DN`, `LDAP_INSECURE_*`, hairpin `HC_PUBLIC_HOSTNAME`/`HC_HOST_TAILSCALE_IP` | `.env` with the Synology overlay; the bind password as a secret file |
| Catalog CI and runner | `HARNESS_EVALS`, `HARNESS_EVALS_AGENTS`, `HARNESS_CATALOG_DEPLOY_KEY`/`READ_TOKEN`, runner `.env` credentials | git host variables/secrets and the self-hosted runner |

`docs/configuration.md` §0 lists what an operator actually types for a production install: four values in `.env`, one deploy-key file, and the LDAP, hairpin and Langfuse items only when those features are in use.

## The generated region of the reference

`harness-catalog config docs` regenerates only the table between two HTML comment markers in `docs/configuration.md`; everything outside is hand-written and preserved (`merge_docs`). The table is rendered from `Settings.model_fields`, so a new field cannot be added without the reference changing, and a test proves that regeneration is idempotent and keeps surrounding sections. `config list` prints each setting's effective value and its origin (`env`, `file`, `default`, `missing`) without starting the server.

## Related

- [Deployment](deployment.md) — the compose files and secret files that carry these values
- [MCP server](../architecture/mcp-server.md) — what the OTel variables switch on
- [Authentication and authorization](../architecture/auth.md) — why issuer and public URL must match Dex byte for byte
