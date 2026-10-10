---
type: architecture
title: MCP server — the five tools, responses, errors, spans
description: The driving adapter that exposes the catalog over MCP Streamable HTTP. Inputs and response shapes of list_skills, search_skills, load_skill, get_skill_file and get_skill_archive; the error-code vocabulary; the fixed order of principal, app call and response; the per-call span attributes and how tracing is switched on.
tags: [mcp, tools, api, telemetry, otel]
sources:
  - id: openwiki-source-34f586c6418c2d86d226045c
    resource: repo://packages/core/src/harness_catalog_core/model.py
  - id: openwiki-source-f426b79a4adacbf83e4356b3
    resource: repo://packages/server/src/harness_catalog_server/__main__.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-836ee40979dc18fe52db3779
    resource: repo://packages/server/src/harness_catalog_server/driving/mcp_tools.py
  - id: openwiki-source-894244c6a8d53cceecd9b6cf
    resource: repo://packages/server/src/harness_catalog_server/telemetry.py
  - id: openwiki-source-64993ac7d19db2729fe1e640
    resource: repo://tests/http/test_server.py
  - id: openwiki-source-2554c5046bdb4ad47c33df1d
    resource: repo://tests/http/test_spans.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# MCP server

The MCP server is a thin driving adapter: for each of the five tools it authorises the caller, calls the [catalog app](catalog-app.md) in a worker thread, and converts the result or the error into a tool result. It adds nothing to the domain. The server is built with the MCP Python SDK's `MCPServer`, mounted at `/mcp` as a **stateless** Streamable HTTP app that answers with JSON responses, so each request is self-contained and a restart loses no session state. One sibling route lives next to it in the same Starlette app: `GET /mcp/archive/{name}/{tree}.tar`, registered **before** the MCP mount so the SDK's auth middleware never sees it; it is described in [Archive download](archive-download.md).

## The five tools

| Tool | Arguments | Returns |
|---|---|---|
| `list_skills` | none | `skills` (every published skill: `name`, `description`, `sha` (tree), `replaced_by`, `requires_tools`, `compatibility`) and `fetched_at` |
| `search_skills` | `query`, `limit` (1..20, default 10) | Same listing shape, ranked |
| `load_skill` | `id`, optional `sha` | `body` (SKILL.md), `sha`, `commit`, `metadata`, `files` (path/size/kind/sha), `has_scripts`, `fetched_at` |
| `get_skill_file` | `id`, `path`, optional `sha` | `path`, `size`, `sha` (tree), `blob`, and exactly one of `text` or `base64` |
| `get_skill_archive` | `id`, optional `sha` | A download descriptor: `uri` (`<public_url>/archive/<id>/<tree>.tar`), `method`, `headers` (the five-minute `X-Harness-Archive-Token`), `expires_at`, `mimeType`, `size`, `sha256`, `digest` (`git-tree:<tree>`). The bytes are fetched out of band; see [Archive download](archive-download.md) |

Every success is a `CallToolResult` whose single text content is the JSON payload and whose `structured_content` is the same mapping, so a host can read either. Tool descriptions are part of the registration and are what a harness sees in `tools/list`. `ToolBindings` is constructed with the catalog, the `ArchiveSigner` and the public URL; `build_server` registers the fifth tool only when a signer is supplied, which the production `bootstrap` always does.

## Errors

A refused or failed call is still a tool result, not a transport error: `is_error=True` with payload `{"code": …, "detail": …}`. The codes are the app's `ErrorCode` vocabulary:

| Code | Meaning |
|---|---|
| `not_a_member` | Token is valid but the principal is not in `harness-readers` |
| `not_found` | Unknown skill, file or tool; or the index has not been built yet |
| `unknown_version` | A `sha` that no commit in `main` history carries |
| `input_limit` | Query too long, `limit` out of range, name too long, file over 1 MB, or a version whose tar exceeds 20 MB |
| `path_rejected` | Path traversal or a symbolic link |

Transport-level 401 happens before any tool runs, when the token is missing or invalid; see [authentication and authorization](auth.md).

## Order of operations in a call

1. `_principal(tool)` reads the verified access token from the SDK context, builds a `Principal` from its claims, records `langfuse.user.id` on the current span, and runs `authorize`. A refusal returns immediately.
2. The app method runs via `anyio.to_thread.run_sync`, because the app is synchronous and may touch git or PostgreSQL.
3. `CatalogError` becomes an error result; any other exception propagates as a tool failure.
4. Result-specific span attributes are set and the payload is returned.

## Spans and tracing

The MCP SDK creates a server span per tool call (`tools/call <tool>`, with `gen_ai.tool.name`), and this adapter adds attributes to it:

| Attribute | Set by | Value |
|---|---|---|
| `langfuse.user.id` | every tool | the token subject |
| `harness_catalog.query` | `search_skills` | the query, printable characters only, truncated to 2,000 |
| `harness_catalog.result_count` | `list_skills`, `search_skills` | number of skills returned |
| `harness_catalog.skill`, `harness_catalog.sha` | `load_skill`, `get_skill_file`, `get_skill_archive` | the skill and the tree version served or described |

Spans leave the process only when tracing is configured. `configure_tracing()` runs at `serve` startup: if `OTEL_EXPORTER_OTLP_ENDPOINT` is set it installs a `TracerProvider` (service name from `OTEL_SERVICE_NAME`, default `harness-catalog`) with a batch OTLP/HTTP exporter; headers come from `OTEL_EXPORTER_OTLP_HEADERS_FILE` (a docker secret in production) when present, otherwise from the exporter's own environment variables. Without an endpoint there is no provider and every span is a no-op. This is the registry's usage record: pointed at Langfuse's OTLP endpoint, each tool call becomes a trace attributed to the user and the skill.

## Tests

`tests/http/test_server.py` starts a real `uvicorn` process with a fake issuer and checks `/healthz` and `/readyz`, the 401 challenge and the protected-resource metadata (including the exact `scopes_supported`), all five tools as a reader (for `get_skill_archive`: the descriptor, then the download with only the header token, the extracted file set equal to `load_skill`'s list, size and sha256, empty 403 without a token or with a tampered one, replay within the TTL, `not_a_member`, `unknown_version`), the `path_rejected` error, wrong-audience and expired tokens (401), a non-member (`not_a_member`), and a machine account reading by group. `tests/http/test_spans.py` exports spans to an in-memory exporter and asserts the attribute set above.

## Related

- [Authentication and authorization](auth.md) — what happens before a tool runs
- [Catalog app](catalog-app.md) — the semantics behind each tool and the limits that produce `input_limit`
- [Evals and records](../workflows/evals-langfuse.md) — the other path into Langfuse (evaluation results)
- [Archive download](archive-download.md) — the fifth tool's token, the route and the cache behind it
