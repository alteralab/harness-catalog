---
type: concept
title: Design decisions in brief — why it is built this way
description: The decisions behind harness-catalog that the code does not explain by itself, each with its rationale and a pointer to where it was decided. No write tools; publication is a git merge; the registry reads with a read-only deploy key; the database is a regenerable derivative; usage and evaluation records live in Langfuse; exactly six settings; one group decides reading; scopes are advertised but never checked; machine accounts are ordinary LDAP users; compose files live under docker/; init seeds the two base skills; evals verifiers follow Harbor's official skeleton; CI workflows only wire the CLI; skill archives are downloaded out of band with a short-lived header token; the wiki is refreshed by a nightly batch. DESIGN.md §11 (Korean) is the source of truth.
tags: [design, decisions, rationale, governance, security]
sources:
  - id: openwiki-source-6d4b4e707b8d60b6ccfa3425
    resource: repo://.github/workflows/openwiki-update.yml
  - id: openwiki-source-ca9eabc24825e6ff0edc2967
    resource: repo://DESIGN.md
  - id: openwiki-source-b79e0281d1b09a8b2bfd2a06
    resource: repo://docker/compose.dev.yml
  - id: openwiki-source-bf2f07ac78709d005a9f28b9
    resource: repo://docker/compose.quickstart.yml
  - id: openwiki-source-8cb90064a9a682740da2974b
    resource: repo://docker/compose.yml
  - id: openwiki-source-21f7c33015965f938339a839
    resource: repo://packages/cli/src/harness_catalog_cli/__main__.py
  - id: openwiki-source-f9693b6e1ce4d2e0751b245f
    resource: repo://packages/cli/src/harness_catalog_cli/init.py
  - id: openwiki-source-25d12f036b20f342206d65a2
    resource: repo://packages/cli/src/harness_catalog_cli/templates/README.md
  - id: openwiki-source-1884c12f086a87c542e8ca3d
    resource: repo://packages/core/src/harness_catalog_core/archive_token.py
  - id: openwiki-source-c0344b993152580b36b61511
    resource: repo://packages/core/src/harness_catalog_core/authz.py
  - id: openwiki-source-759953adeee8d15c68d2bcc7
    resource: repo://plans/distribution.md
  - id: openwiki-source-8c4be7d2e9ca328d5223d216
    resource: repo://plans/pilot/r1.md
  - id: openwiki-source-940b962d295a02dd154267b4
    resource: repo://plans/pilot/r3.md
  - id: openwiki-source-a59342c4ef8f8cf143556b08
    resource: repo://plans/service.md
  - id: openwiki-source-61af20cd94b72635f491927e
    resource: repo://plans/skills.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Design decisions in brief

This page is a guide, not the record. The record is `DESIGN.md` — its body is the current contract and §11 is the dated ledger of every reversal, Codex adversarial review and user decision, written in Korean — together with the decision tables in `plans/service.md`, `plans/distribution.md` and `plans/skills.md`. When a page in this wiki says "because", it is summarising one of the entries below; when you need the full argument, read the cited section.

## Publication is a merge; the registry has no write tools

Earlier drafts had `publish_skill` and `certify_skill` tools and editor/admin roles inside the registry. v3.3 removed all of them: a skill is published, updated, retired or replaced by a branch → PR → merge into `main` of the catalog repository, and the person who merges is the certifier. The registry only fetches `main`, checks it and indexes it (DESIGN §11, "v3.3"; §2 "쓰기는 레지스트리를 지나지 않는다"). Consequences visible in code: the five MCP tools are all reads (`authz.py` lists them in one `READ_TOOLS` set and has no write decision); the deploy key is read-only.

**Why:** write authorisation already exists on the git host, with review, history and blame for free. A second authorisation surface in the registry would duplicate it and widen the attack surface. The rule "the knowledge of what a skill is lives in one place" is served by `check_commit` being the single implementation for hooks, CI and the index.

## Branch protection is a discipline, not a requirement

`main` protection was dropped from the v3.0 requirements (DESIGN §11, 2026-09-26) so that the catalog works on any git host and plan. The catalog README states the rule — no direct push, no force push — and the registry defends itself instead: a rewound `main` is refused by the generation rule until an operator accepts it.

## The database never copies the source of truth

The one boundary rule for persistence: PostgreSQL holds nothing but an index derived from `main` (DESIGN §2 "경계 규칙"). There is no authoritative fact in the database, hence no backup (the backup cron was removed in v3.0) and no migration of content. The in-memory snapshot is the served version; the database is for ranked search and for remembering the last indexed generation. This is why a lost database only degrades the registry and why `replace_index` can be an all-or-nothing `DELETE` + `INSERT`.

## Usage and evaluation records live in Langfuse

v3.4 removed `eval_result`/`record_eval` and v3.5 removed `usage_record` and its retention setting `USAGE_RETENTION_DAYS` (DESIGN §11, 2026-09-27). Tool calls are OpenTelemetry spans exported to Langfuse with `langfuse.user.id` and skill attributes; evaluation runs are Langfuse dataset experiments written by the `harbor-langfuse` plugin. The registry never reads Langfuse.

**Why:** the team already runs Langfuse; inventing a second store for the same facts would mean inventing retention, dashboards and comparison views that Langfuse already has. It also keeps the registry's settings at six.

## Exactly six settings

Five required (catalog repository URL, deploy key, OIDC issuer, public URL, PostgreSQL connection) and one with a default (fetch interval, 60 s). The design's rule is that a setting exists only when the operator genuinely knows a better value than the project does (DESIGN §2.1 "운영자가 아는 것"). The fetch interval qualifies because it trades git-host load against publication latency. Observability variables are not settings: they are the OTel SDK's standard environment variables, read by the SDK. The 2026-10-11 archive download deliberately added no setting — its token lifetime, size cap and retention are constants, and its signing key is generated at startup.

## Reading requires a group; there is only one role

Reading is permitted by membership in `harness-readers` and nothing else (DESIGN §11, 2026-09-26 "읽기도 그룹 소속을 요구한다"; 2026-10-07 the group name). The intended operator discipline is that the catalog repository's read list and the LDAP group are the same set of people. There is no editor or admin role in the registry because every write lives on the git host.

## Machine accounts are ordinary LDAP users; `aud` comes from a scope; scopes are never checked

Three decisions were taken together on 2026-10-07 after measuring Dex v2.45.1 (DESIGN §11; measurements in `plans/pilot/r1.md`):

1. **Unattended readers are LDAP machine accounts using the password grant** of a confidential client (`ci-runner`). Dex has no `client_credentials` grant, so a service-principal concept would have required another issuer; a machine account in `harness-readers` needs no new concept at all.
2. **The registry URL reaches `aud` through Dex's cross-client scope.** Dex ignores the `resource` parameter and sets `aud` to the client id, unless the client requests `audience:server:client_id:<url>` for a registered trusted peer. The registry therefore advertises that scope in its RFC 9728 metadata; a harness that requests the advertised scopes verbatim — which Claude Code does, as measured in `plans/pilot/r3.md` — gets the right audience without knowing why.
3. **Scopes are not checked from tokens.** Dex tokens carry no `scope` claim and reject custom scopes such as `skills:read`. The verifier therefore grants the required scope list to every valid token and authorisation is by group alone. Scopes remain a request vocabulary, not a permission unit.

## Pre-registered client ids instead of dynamic registration

Dex does not implement dynamic client registration. The pilot measured that Claude Code then needs `"oauth": {"clientId": "claude-code"}` in its MCP configuration (`plans/pilot/r3.md`), so the design accepts "two lines to register" (URL plus client id) rather than adopting an issuer that supports DCR.

## The index never moves backwards

A fetched commit that is not a descendant of the indexed one is treated as a rewind and refused; the served version is kept and `main_rewound` is reported until an operator runs `reindex --accept-rewind` (plans/service.md decisions on generation checks). The same rule is enforced inside the database transaction, so two registries cannot race each other into an older generation.

## Fail closed where a wrong "pass" would be worse than an outage

Secret scanning without gitleaks is a checker failure, not a skip; retired-name detection on a shallow clone is an error, not an empty set; a `merge-base` that cannot answer is an error, not "not an ancestor". In each case the registry keeps serving the previous version and reports the condition instead of guessing. The same rule reached the CLI on 2026-10-10: `harness-catalog ci check` refuses to guess a base commit when it runs under a CI marker without the host's event variables, and treats a missing gitleaks that cannot be fetched as exit code 2 rather than a pass.

## Secrets are files, generated on the host

Production compose passes every secret as a Docker secret file (`*_FILE`), generated or copied by `scripts/make-secrets.sh` on the operations host into the directory named by `SECRETS_DIR` in `docker/.env`, never pasted into chat or committed (plans/distribution.md D10). The development compose `docker/compose.dev.yml` is the documented exception that passes secrets as environment variables and binds PostgreSQL to the host loopback; its static Dex passwords are public values, which is why that file must never be exposed beyond 127.0.0.1.

## Compose files live under `docker/`; `examples/` is gone

On 2026-10-10 the user asked for the root to hold fewer tracked files. Two decisions followed (DESIGN §11, 2026-10-10):

- **The three compose files and `.env.example` moved to `docker/`**; the Dockerfile, `.dockerignore` and the build context stay at the root (plans/distribution.md D11). Of six surveyed open-source repositories, DataHub keeps compose under `docker/` while Dex, Langfuse and the MCP registry keep it at the root, so this is a choice of taste with a known price: relative paths, `.env` and the default secrets directory are now resolved from `docker/`, and every command carries `-f docker/compose.yml`. Both the production and the development compose pin `name: harness-catalog` so the Compose project name — previously the root directory name by default — and therefore the existing volume names survive the move. The quickstart compose is a separate project, `harness-catalog-quickstart`.
- **`examples/` was removed.** The catalog-repository template that was meant to live there must be written by `init`, so it became CLI package data; the remaining Synology LDAP overlay is not an example but the production configuration running on the operations host, so it is a compose support file at `docker/synology-ldap/`. The self-hosted runner's environment sample moved to `.github/runner.env.example`. Future variants get `docker/<variant>/`, and documentation points at them instead of an examples directory.

In the same clean-up the ruff configuration moved from a root `ruff.toml` into `pyproject.toml`: `[tool.ruff]` extends the shared `altera-rules` base and `[tool.ruff.lint.extend-per-file-ignores]` exempts only the two CLI entry points and the measurement tools from the no-print rule (plain `per-file-ignores` would silently replace the base's own exemptions).

## A new catalog is born with its two base skills

The earlier rule (plans/distribution.md D14, first version) was "an empty catalog plus a first PR carrying `pin-skill` and `write-skill`", and its real reason was copy count: the skill sources lived outside the CLI package, so `init` could only write them from a copy. On 2026-10-10 the user decided that a template-created catalog should start complete, and the sources moved into the CLI package as `templates/skills/`, where `init` reads them directly (DESIGN §11, 2026-10-10 "`init`이 기본 스킬 둘을 함께 쓴다"). `init` still writes only files that do not exist, so later changes to those skills reach a catalog by PR, and `check` runs on them like any other skill. The quickstart seed copies the same source, so there is still exactly one copy. The first real catalog, `alteralab/catalog`, predates this and received the skills through its PR #1.

## Evals verifiers follow Harbor's official skeleton

The first evals verifiers were shell conditionals that wrote `reward.txt` — they honoured Harbor's contract but did not look like what `harbor tasks init` generates, and they would not have stayed readable as conditions grew. On 2026-10-10 the user decided to adopt the official skeleton unchanged (DESIGN §11; plans/skills.md D11): a bash entry point `tests/test.sh` runs pytest on `tests/test_outputs.py`, pytest writes a CTRF report and its exit code becomes the reward, and all checking logic lives in pytest assertions. Each eval also carries `solution/solve.sh`, a self-contained reference solution that Harbor's Oracle agent runs so a task and its verifier can be confirmed without a model (Oracle accepts no `--skill`, so `solve.sh` cannot lean on the skill). The one deliberate deviation is that the environment image bakes pytest, the CTRF plugin and uv in, because the verifier has no network at check time. A deterministic Python scaffold in `write-skill` (`scripts/scaffold.py`, PEP 723, run with `uv run --script`) writes this five-file shape so that agents fill in only the TODOs (plans/skills.md D3, revised the same day).

## CI workflows wire; the CLI decides

The workflows that `init` writes for GitHub and GitLab used to embed about seventy lines of shell, copied four times. The user asked whether that was a good structure; the answer was no, for three reasons (plans/distribution.md D24; DESIGN §11, 2026-10-10): shell inside YAML is outside shellcheck, ruff and pytest; the same block was duplicated per host and per job; and because `init` never overwrites existing files, logic baked into YAML freezes forever in every catalog repository, whereas CLI logic follows a one-line version pin. Now the workflows do checkout, uv, credential injection and one call each to `harness-catalog ci check` and `harness-catalog ci evals --agent <x>`. Base-commit selection (merge-base for PRs, the pre-push commit for pushes, the empty tree for branch creation), changed-skill discovery, per-harness credential tables, the two harbor invocations and gitleaks acquisition with checksum verification live in the CLI's `ci.py` and `gitleaks.py`, covered by pytest. Only credential injection stays in YAML, because it is needed before the CLI can be installed; it is one local composite action on GitHub and one hidden job on GitLab, both using a single deploy-key path. `HARNESS_EVALS_AGENTS` became a JSON array, which removed the agents matrix job. See [CLI and CI](../architecture/cli-and-ci.md).

## Skill archives are downloaded out of band, with a header token and a process-lifetime key

Pinning a skill through `get_skill_file` meant every file's bytes passed through the model twice (tool result, then write call) — thirty turns for a fifteen-file skill. Every surveyed precedent (Databricks Unity Catalog skills, Codex's skill-installer, Vercel's `npx skills`, Claude Code plugin sources, the Anthropic Skills API's zip endpoint) installs outside the model, and the MCP community pattern and the SEP-2631 draft hand the client a download descriptor rather than bytes. On 2026-10-11 the user chose that shape (DESIGN §11, 2026-10-11; plans/service.md D17): a fifth read tool, `get_skill_archive`, returns `uri`, `headers`, `size`, `sha256` and `digest`, and `GET /mcp/archive/<id>/<tree>.tar` serves a cached tar after verifying only the header token. The decisions inside that decision:

- **The credential travels in a header, never in the URL** (RFC 9110 §17.9 — URIs are made to be shared and end up in uvicorn and proxy access logs). The token is an HMAC-SHA256 over name, tree and expiry, valid for five minutes with one minute of leeway; any failure is an empty 403.
- **Archives are byte-deterministic.** `git archive` of a tree-ish alone stamps the generation time into every header, so the same version produced different bytes each time (found in Codex review and measured). The registry pins `--mtime` to the commit time, the tar umask and the attributes file, so the descriptor's `sha256` stays valid even if the cache is wiped. A 20 MB cap is enforced while writing.
- **The signing key lives as long as the process.** It is random at startup, which assumes a single replica (distribution D1·D11); a restart is a rotation, old tokens get 403, and `pin-skill` re-mints once. Cached tars are evicted every scheduler tick once their last issue is older than the token lifetime plus leeway plus a minute, and wiped at startup because no earlier token can verify. No new setting was introduced.

`get_skill_file` remains for reading a single file inside a loop. See [Archive download](../architecture/archive-download.md).

## The wiki is refreshed by a nightly batch that skips when nothing changed

OpenWiki was first run from a Claude Code session, then on every push to `main`. Concurrent merges and per-push model cost made that wasteful, so the workflow now runs on a schedule (19:00 UTC, 04:00 KST) plus a manual `workflow_dispatch` with a `force` input. A detect step compares the wiki baseline (`gitHead` in `openwiki/.last-update.json`) with `HEAD` and, unless something outside `openwiki/**`, `AGENTS.md`, `CLAUDE.md` and the workflow file changed, ends the run without calling the model. The provider is Anthropic and the model id comes from the repository variable `OPENWIKI_MODEL_ID`, defaulting to `claude-opus-5`, so cost can be tuned without a commit. Running the update by hand from a clean `main` remains the documented fallback.

## Related

- [System overview](../architecture/overview.md) — where each decision shows up in the structure
- [Authentication and authorization](../architecture/auth.md) — the three 2026-10-07 decisions in mechanism form
- [PostgreSQL index](../architecture/index-store.md) — the derivative-database rule in code
- [Archive download](../architecture/archive-download.md) — the fifth tool and its route
- [CLI and CI](../architecture/cli-and-ci.md) — what moved out of the workflow YAML
- [Deployment](../operations/deployment.md) — the `docker/` layout in operation
- [Skill lifecycle](../workflows/skill-lifecycle.md) — seeding, scaffolding and the Harbor-shaped verifiers in use
