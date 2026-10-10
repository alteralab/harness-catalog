---
type: operations
title: Configuration — the six HC__ settings, _FILE secrets, observability variables
description: How the registry is configured and why the surface is small. The six HC__ settings and their validation (including trailing-slash rejection), the *_FILE secret source used by Docker secrets, where the compose files, docker/.env and the SECRETS_DIR secret files live, how compose passes Dex's issuer and audience from the same two settings, why the OTel variables are not settings, and how the configuration reference keeps a generated region inside a hand-written document.
tags: [configuration, settings, secrets, env, otel, compose]
sources:
  - id: openwiki-source-eb717bf0b36ba13f5f7c2ecd
    resource: repo://.github/runner.env.example
  - id: openwiki-source-2480eda4770a7db2844a2087
    resource: repo://docker/.env.example
  - id: openwiki-source-b79e0281d1b09a8b2bfd2a06
    resource: repo://docker/compose.dev.yml
  - id: openwiki-source-bf2f07ac78709d005a9f28b9
    resource: repo://docker/compose.quickstart.yml
  - id: openwiki-source-8cb90064a9a682740da2974b
    resource: repo://docker/compose.yml
  - id: openwiki-source-f9a97df6afb4dd8c285f0b2c
    resource: repo://docs/configuration.md
  - id: openwiki-source-37c3c9f4a0365c33199e11c0
    resource: repo://packages/cli/src/harness_catalog_cli/config.py
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-1f7212efc41fd797b2b123e9
    resource: repo://packages/core/src/harness_catalog_core/settings.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-894244c6a8d53cceecd9b6cf
    resource: repo://packages/server/src/harness_catalog_server/telemetry.py
  - id: openwiki-source-9ed8710f6e966a268201a49f
    resource: repo://tests/cli/test_config_docs.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Configuration

The registry's configuration is deliberately a single, small list. Everything else an operator sees in `docker/.env.example` or `docs/configuration.md` belongs to another layer — compose, Dex, observability, CI — and the reference document is organised by those layers so that "what must I fill in" is answered before "what exists".

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

A custom settings source reads `HC__<NAME>_FILE=<path>` and uses the file's content (trailing newline stripped) as the value. It sits after the plain environment in the precedence order, so an explicit `HC__X` wins over `HC__X_FILE`. Production compose (`docker/compose.yml`) uses this for the two secrets (`/run/secrets/git_deploy_key`, `/run/secrets/database_url`) and never puts them in the environment; the development compose, by documented exception, passes them as variables.

## One source for Dex's issuer and audience

Dex needs the issuer URL and the registry URL too (the latter as the id of the audience client). The production and development compose files pass `DEX_ISSUER` and `HC_PUBLIC_URL` to the Dex container **from** `HC__OIDC_ISSUER` and `HC__PUBLIC_URL` — required in production, defaulted to `http://localhost:5556/dex` and `http://localhost:8000/mcp` in development — so the operator never types them twice and `docker/.env.example` has no separate Dex entries for them. The quickstart compose takes no operator values at all: it writes the same two localhost URLs, built from `DEX_PORT` and `REGISTRY_PORT`, into both the Dex and the registry service, so the pair still cannot diverge. Together with the trailing-slash validator this closes the class of "works in the registry, fails in Dex" misconfigurations.

## Observability variables are not settings

`OTEL_EXPORTER_OTLP_ENDPOINT`, `_HEADERS`, `_PROTOCOL` and `OTEL_SERVICE_NAME` are the OpenTelemetry SDK's standard variables. The registry only checks whether an endpoint is present to decide whether to install a tracer provider; the exporter reads the rest itself. Production compose supplies the Langfuse `Authorization` header through a secret file (`OTEL_EXPORTER_OTLP_HEADERS_FILE` → `/run/secrets/otlp_headers`) because the header embeds the project keys; an empty file means "no headers". Keeping these out of `Settings` keeps the registry's contract at six values and lets the same variables work for any OTLP backend.

## Where the files live

Since 2026-10-10 the three compose files, `.env.example` and the Dex configuration live under `docker/`; only the Dockerfile and the build context stay at the repository root. Compose resolves `.env` and every relative path from the directory of the compose file, so:

- the operator's values go in `docker/.env` (`cp docker/.env.example docker/.env && chmod 600 docker/.env`), and all three compose files read that same file;
- `SECRETS_DIR` defaults to `../secrets`, which is `secrets/` at the repository root — the directory `scripts/make-secrets.sh secrets` creates; a value such as `./secrets` would wrongly point at `docker/secrets`;
- every command names the file, for example `docker compose -f docker/compose.yml up -d`, with the Synology overlay `-f docker/synology-ldap/compose.override.yml` appended for the team's LDAP;
- the production and development compose files pin the project name `harness-catalog` so the move did not rename the existing volumes, and the quickstart compose is its own project, `harness-catalog-quickstart`.

The self-hosted runner's environment sample moved from `docs/` to `.github/runner.env.example`; it is a template for the `.env` at the runner's root on the operations host, never for the repository.

## Where the other variables live

| Layer | Examples | Where they are set |
|---|---|---|
| Compose (production) | `REGISTRY_IMAGE`, `REGISTRY_PORT`, `DEX_PORT`, `SECRETS_DIR` | `docker/.env` beside `docker/compose.yml` |
| Compose (development) | `POSTGRES_PASSWORD`, `HC_DB_PASSWORD`, `DEX_DB_PASSWORD`, `DEX_CI_RUNNER_SECRET`, `POSTGRES_PORT` | `docker/.env`; random values generated by the operator |
| Compose (quickstart) | the same names, all defaulted to public values | nothing to set; a filled `docker/.env` from development overrides the defaults because the files share a directory |
| Dex / LDAP | `LDAP_HOST`, `LDAP_BIND_DN`, `LDAP_BIND_PW(_FILE)`, `LDAP_USER_BASE_DN`, `LDAP_GROUP_BASE_DN`, `LDAP_INSECURE_*`, hairpin `HC_PUBLIC_HOSTNAME`/`HC_HOST_TAILSCALE_IP` | `docker/.env` with the Synology overlay under `docker/synology-ldap/`; the bind password as the secret file `ldap_bind_pw` |
| Catalog CI and runner | `HARNESS_EVALS`, `HARNESS_EVALS_AGENTS` (a JSON array, default `["claude-code", "codex"]`), `HARNESS_CATALOG_DEPLOY_KEY`, runner `.env` credentials (`CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`, `LANGFUSE_*`) | git host variables/secrets and the self-hosted runner's `.env` (sample: `.github/runner.env.example`) |

The CI credential path is a single read-only deploy key; the earlier personal-access-token alternative was removed when the workflow logic moved into the CLI (see [CLI and CI](../architecture/cli-and-ci.md)).

`docs/configuration.md` §0 lists what an operator actually types for a production install: four values in `docker/.env`, one deploy-key file, and the LDAP, hairpin and Langfuse items only when those features are in use.

## The generated region of the reference

`harness-catalog config docs` regenerates only the table between two HTML comment markers in `docs/configuration.md`; everything outside is hand-written and preserved (`merge_docs`). The table is rendered from `Settings.model_fields`, so a new field cannot be added without the reference changing, and a test proves that regeneration is idempotent and keeps surrounding sections. `config list` prints each setting's effective value and its origin (`env`, `file`, `default`, `missing`) without starting the server.

## Related

- [Deployment](deployment.md) — the compose files and secret files that carry these values
- [CLI and CI](../architecture/cli-and-ci.md) — the catalog-side variables and the deploy-key credential step
- [MCP server](../architecture/mcp-server.md) — what the OTel variables switch on
- [Authentication and authorization](../architecture/auth.md) — why issuer and public URL must match Dex byte for byte
