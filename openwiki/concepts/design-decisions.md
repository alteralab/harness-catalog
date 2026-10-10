---
type: concept
title: Design decisions in brief — why it is built this way
description: The decisions behind harness-catalog that the code does not explain by itself, each with its rationale and a pointer to where it was decided. No write tools; publication is a git merge; the registry reads with a read-only deploy key; the database is a regenerable derivative; usage and evaluation records live in Langfuse; exactly six settings; one group decides reading; scopes are advertised but never checked; machine accounts are ordinary LDAP users. DESIGN.md §11 (Korean) is the source of truth.
tags: [design, decisions, rationale, governance, security]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-ca9eabc24825e6ff0edc2967
    resource: repo://DESIGN.md
  - id: openwiki-source-0c106052b3286e779bed85e7
    resource: repo://docker-compose.dev.yml
  - id: openwiki-source-25d12f036b20f342206d65a2
    resource: repo://packages/cli/src/harness_catalog_cli/templates/README.md
  - id: openwiki-source-759953adeee8d15c68d2bcc7
    resource: repo://plans/distribution.md
  - id: openwiki-source-8c4be7d2e9ca328d5223d216
    resource: repo://plans/pilot/r1.md
  - id: openwiki-source-940b962d295a02dd154267b4
    resource: repo://plans/pilot/r3.md
  - id: openwiki-source-a59342c4ef8f8cf143556b08
    resource: repo://plans/service.md
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Design decisions in brief

This page is a guide, not the record. The record is `DESIGN.md` — its body is the current contract and §11 is the dated ledger of every reversal, Codex adversarial review and user decision, written in Korean. When a page in this wiki says "because", it is summarising one of the entries below; when you need the full argument, read the cited section.

## Publication is a merge; the registry has no write tools

Earlier drafts had `publish_skill` and `certify_skill` tools and editor/admin roles inside the registry. v3.3 removed all of them: a skill is published, updated, retired or replaced by a branch → PR → merge into `main` of the catalog repository, and the person who merges is the certifier. The registry only fetches `main`, checks it and indexes it (DESIGN §11, "v3.3"; §2 "쓰기는 레지스트리를 지나지 않는다"). Consequences visible in code: the four MCP tools are all reads; `authz.py` has no write decision; the deploy key is read-only.

**Why:** write authorisation already exists on the git host, with review, history and blame for free. A second authorisation surface in the registry would duplicate it and widen the attack surface. The rule "the knowledge of what a skill is lives in one place" is served by `check_commit` being the single implementation for hooks, CI and the index.

## Branch protection is a discipline, not a requirement

`main` protection was dropped from the v3.0 requirements (DESIGN §11, 2026-09-26) so that the catalog works on any git host and plan. The catalog README states the rule — no direct push, no force push — and the registry defends itself instead: a rewound `main` is refused by the generation rule until an operator accepts it.

## The database never copies the source of truth

The one boundary rule for persistence: PostgreSQL holds nothing but an index derived from `main` (DESIGN §2 "경계 규칙"). There is no authoritative fact in the database, hence no backup (the backup cron was removed in v3.0) and no migration of content. The in-memory snapshot is the served version; the database is for ranked search and for remembering the last indexed generation. This is why a lost database only degrades the registry and why `replace_index` can be an all-or-nothing `DELETE` + `INSERT`.

## Usage and evaluation records live in Langfuse

v3.4 removed `eval_result`/`record_eval` and v3.5 removed `usage_record` and its retention setting `USAGE_RETENTION_DAYS` (DESIGN §11, 2026-09-27). Tool calls are OpenTelemetry spans exported to Langfuse with `langfuse.user.id` and skill attributes; evaluation runs are Langfuse dataset experiments written by the `harbor-langfuse` plugin. The registry never reads Langfuse.

**Why:** the team already runs Langfuse; inventing a second store for the same facts would mean inventing retention, dashboards and comparison views that Langfuse already has. It also keeps the registry's settings at six.

## Exactly six settings

Five required (catalog repository URL, deploy key, OIDC issuer, public URL, PostgreSQL connection) and one with a default (fetch interval, 60 s). The design's rule is that a setting exists only when the operator genuinely knows a better value than the project does (DESIGN §2.1 "운영자가 아는 것"). The fetch interval qualifies because it trades git-host load against publication latency. Observability variables are not settings: they are the OTel SDK's standard environment variables, read by the SDK.

## Reading requires a group; there is only one role

Reading is permitted by membership in `harness-readers` and nothing else (DESIGN §11, 2026-09-26 "읽기도 그룹 소속을 요구한다"; 2026-10-07 the group name). The intended operator discipline is that the catalog repository's read list and the LDAP group are the same set of people. There is no editor or admin role in the registry because every write lives on the git host.

## Machine accounts are ordinary LDAP users; `aud` comes from a scope; scopes are never checked

Three decisions were taken together on 2026-10-07 after measuring Dex v2.45.1 (DESIGN §11 last section; measurements in `plans/pilot/r1.md`):

1. **Unattended readers are LDAP machine accounts using the password grant** of a confidential client (`ci-runner`). Dex has no `client_credentials` grant, so a service-principal concept would have required another issuer; a machine account in `harness-readers` needs no new concept at all.
2. **The registry URL reaches `aud` through Dex's cross-client scope.** Dex ignores the `resource` parameter and sets `aud` to the client id, unless the client requests `audience:server:client_id:<url>` for a registered trusted peer. The registry therefore advertises that scope in its RFC 9728 metadata; a harness that requests the advertised scopes verbatim — which Claude Code does, as measured in `plans/pilot/r3.md` — gets the right audience without knowing why.
3. **Scopes are not checked from tokens.** Dex tokens carry no `scope` claim and reject custom scopes such as `skills:read`. The verifier therefore grants the required scope list to every valid token and authorisation is by group alone. Scopes remain a request vocabulary, not a permission unit.

## Pre-registered client ids instead of dynamic registration

Dex does not implement dynamic client registration. The pilot measured that Claude Code then needs `"oauth": {"clientId": "claude-code"}` in its MCP configuration (`plans/pilot/r3.md`), so the design accepts "two lines to register" (URL plus client id) rather than adopting an issuer that supports DCR.

## The index never moves backwards

A fetched commit that is not a descendant of the indexed one is treated as a rewind and refused; the served version is kept and `main_rewound` is reported until an operator runs `reindex --accept-rewind` (plans/service.md decisions on generation checks). The same rule is enforced inside the database transaction, so two registries cannot race each other into an older generation.

## Fail closed where a wrong "pass" would be worse than an outage

Secret scanning without gitleaks is a checker failure, not a skip; retired-name detection on a shallow clone is an error, not an empty set; a `merge-base` that cannot answer is an error, not "not an ancestor". In each case the registry keeps serving the previous version and reports the condition instead of guessing.

## Secrets are files, generated on the host

Production compose passes every secret as a Docker secret file (`*_FILE`), generated or copied by `scripts/make-secrets.sh` on the operations host, never pasted into chat or committed (plans/distribution.md D10). The development compose is the documented exception that passes secrets as environment variables.

## Related

- [System overview](../architecture/overview.md) — where each decision shows up in the structure
- [Authentication and authorization](../architecture/auth.md) — the three 2026-10-07 decisions in mechanism form
- [PostgreSQL index](../architecture/index-store.md) — the derivative-database rule in code
