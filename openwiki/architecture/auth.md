---
type: architecture
title: Authentication and authorization — Dex OIDC, token verification, harness-readers
description: How a browser login or a machine-account password grant becomes a token, how the registry verifies that token, and how a tool call is permitted. RFC 9728 metadata, the cross-client audience scope, why authorization reads only the groups claim, and the one HTTP surface (the archive route) that uses a signed header token instead of the bearer token.
tags: [auth, oidc, dex, authorization, mcp]
sources:
  - id: openwiki-source-7c9225e4499c7ccc6aa8d617
    resource: repo://docker/dex/config.yaml
  - id: openwiki-source-4c3d8a546415236d84f8e962
    resource: repo://docker/synology-ldap/dex/config.yaml
  - id: openwiki-source-c0344b993152580b36b61511
    resource: repo://packages/core/src/harness_catalog_core/authz.py
  - id: openwiki-source-34f586c6418c2d86d226045c
    resource: repo://packages/core/src/harness_catalog_core/model.py
  - id: openwiki-source-8aa357739fb26e383f0c1e84
    resource: repo://packages/server/src/harness_catalog_server/adapters/oidc.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-480437ca124a00d81b6ec34c
    resource: repo://packages/server/src/harness_catalog_server/driving/archive_route.py
  - id: openwiki-source-836ee40979dc18fe52db3779
    resource: repo://packages/server/src/harness_catalog_server/driving/mcp_tools.py
  - id: openwiki-source-07001c8aaf0ae69f7d18b731
    resource: repo://scripts/dev-token.sh
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Authentication and authorization

The registry never decides **who** someone is. Dex, in front of it, wraps the team directory (LDAP) as an OIDC issuer and mints tokens; the registry only verifies a token's signature, issuer and audience, then decides permission from **one group**. Human sessions and unattended loops obtain tokens from the same issuer through different grants and call the same tools.

## Flow

1. A harness calling `/mcp` without a token receives a 401 challenge whose `resource_metadata` header points at the RFC 9728 protected-resource document (`/.well-known/oauth-protected-resource/mcp`). The MCP SDK produces that document from `AuthSettings`; registry code only supplies the issuer, the public URL and the three required scopes.
2. The harness fetches discovery from the metadata's `authorization_servers` (the Dex issuer), requests `scopes_supported` **verbatim**, and opens a browser login (PKCE). Dex does not support dynamic client registration, so each harness must carry a pre-registered client id (`claude-code`, `codex`, `cursor`) in its configuration.
3. Unattended principals use an LDAP machine account with the password grant of the confidential client `ci-runner`. `scripts/dev-token.sh` is the reference for that call.
4. For every call that carries a token, `JwtTokenVerifier` verifies it, then the tool adapter builds a principal from the claims and asks `authorize` for a decision.
5. One HTTP surface deliberately sits outside this flow: `GET /mcp/archive/<id>/<tree>.tar` accepts no bearer token. It is reached only with the short-lived HMAC token that the authorized tool `get_skill_archive` minted, carried in the `X-Harness-Archive-Token` header; a missing or bad token is an empty 403, not a 401 challenge. The route is registered before the MCP mount so the MCP SDK's auth middleware never sees it. See [Archive download](archive-download.md).

## Required scopes and audience

By default a Dex token's `aud` is the client id that requested it. For the registry URL to appear in `aud`, the client must request Dex's cross-client scope `audience:server:client_id:<registry public URL>`, and that URL must be registered in Dex as a public client that lists the harness clients as `trustedPeers`. Hence the registry advertises three scopes: `openid`, `groups` and that audience scope (`required_scopes`). The essential point is that a harness only has to request what is advertised for `aud` to come out right.

The `groups` scope carries LDAP groups into the token. In the quickstart's static user set only `dev` belongs to `harness-readers`; `outsider` has no groups, which demonstrates the boundary: login succeeds, tool calls are refused.

## Token verification

`JwtTokenVerifier` verifies signatures with the JWKS found through the issuer's discovery document. The checks are: signature algorithm RS256 or ES256, `iss` equal to the configured issuer, `aud` containing the registry public URL, presence of `exp` and `sub`, with clock leeway. JWKS keys are cached for one hour and an unknown `kid` triggers an immediate refetch. Decoding runs in a worker thread so the event loop is not blocked.

On success the verifier returns the SDK's `AccessToken`, whose `scopes` are set to the **required scope list regardless of the token's content**. Dex tokens carry no `scope` claim and reject arbitrary scopes such as `skills:read` with `invalid_scope`, so scopes are a means of advertisement and request, not a unit of permission. Permission is decided by authorization below.

The issuer and the public URL must be seen as byte-identical strings by Dex and by the registry. That is why compose derives the Dex values from the two registry settings and why the settings reject a trailing slash.

## Authorization

`authz.py` is two pure functions. `principal_from_claims` extracts `sub`, `groups` and the client id (`azp`, or a string `aud`) into a `Principal`; `authorize` takes the tool name and the principal and returns a decision. The rule is a single one: if `groups` contains `harness-readers`, all five read tools (`list_skills`, `search_skills`, `load_skill`, `get_skill_file`, `get_skill_archive`) are allowed; otherwise the call is refused with `not_a_member`. Humans and machine accounts are not distinguished; a machine account placed in the same group is a reader. An unknown tool name yields `not_found`.

The tool adapter's `_principal` runs these two in order on every call and turns a refusal into an error tool result (`isError`). The principal's `sub` is recorded as the span attribute `langfuse.user.id`.

Authorization is one group because the only boundary for reading is "the team". Keeping the catalog repository's read list and the LDAP group identical is the operator's job; there is no write authorization in the registry at all, because writing is the git host's repository permission.

## Dex-side configuration

- Static clients: three public ones (`claude-code`, `codex`, `cursor`, with empty redirect URIs so loopback is allowed), one confidential (`ci-runner`), and the audience client (id = registry public URL, `trustedPeers` = the other four).
- `passwordConnector` is on, enabling the password grant. This is a deliberate choice made knowing it also opens that grant to public clients.
- Access tokens live one hour; refresh tokens expire after 30 days unused.
- The team LDAP variant (`docker/synology-ldap/dex/config.yaml`, mounted by the production overlay `docker/synology-ldap/compose.override.yml`; it lived under `examples/` until 2026-10-10) swaps in a `type: ldap` connector. Because users may lack `mail`, `emailAttr` is `uid`, and groups are resolved through a `member` attribute holding user DNs. Dex's local users log in by email; the LDAP variant logs in by `uid`.

## Failure modes

| Situation | Result |
|---|---|
| No token, bad signature, `iss`/`aud` mismatch, expired | 401. `verify_token` returns `None` and the SDK issues the challenge |
| Valid token but no `harness-readers` | Tool result with `isError`, code `not_a_member` — including `get_skill_archive`, so a non-reader never obtains a download token |
| Archive route without a valid header token | Empty 403 (no `WWW-Authenticate`); tokens expire after five minutes and all die when the registry restarts |
| Harness configuration lacks a client id | Dex has no DCR, so the login flow never starts |
| Proxy does not expose `/.well-known/oauth-protected-resource` | The 401's `resource_metadata` is a 404 and the harness stalls |
| Public URL with trailing slash | The registry refuses to start, to prevent Dex and the registry from diverging |

## Related

- [MCP server](mcp-server.md) — the five tools and their response/error shapes
- [Archive download](archive-download.md) — the signed header token and the route that bypasses the bearer check
- [Deployment](../operations/deployment.md) — proxy paths, the Dex overlay, secret files
- [Design decisions in brief](../concepts/design-decisions.md) — rationale for the machine account, the audience scope and the absence of scope checks
