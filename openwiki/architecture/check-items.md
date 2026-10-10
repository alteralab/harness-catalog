---
type: concept
title: The ten check items — what check looks at, exit codes, base commit — rules for the repository and its skills
description: The ten checks that harness-catalog check (pre-commit hook, CI) and the registry's index build run through one shared function. What each item looks at, errors versus warnings, exit codes 0/1/2, the fail-closed secret scan when gitleaks is absent, and items 5 and 9 which need a base commit.
tags: [check, validation, gitleaks, skills, ci]
sources:
  - id: openwiki-source-21f7c33015965f938339a839
    resource: repo://packages/cli/src/harness_catalog_cli/__main__.py
  - id: openwiki-source-6d7fdb64e59c26dbcd92f911
    resource: repo://packages/cli/src/harness_catalog_cli/ci.py
  - id: openwiki-source-9cd44c598af54599c4da2c87
    resource: repo://packages/cli/src/harness_catalog_cli/gitleaks.py
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-849176cfe2a21dc2733885fb
    resource: repo://packages/core/src/harness_catalog_core/adapters/git.py
  - id: openwiki-source-44ccf004261a26e646e12099
    resource: repo://packages/core/src/harness_catalog_core/adapters/validate.py
  - id: openwiki-source-26ec5196a784179afea72f39
    resource: repo://packages/core/src/harness_catalog_core/check.py
  - id: openwiki-source-afe81887aa9e0e25a63c4164
    resource: repo://tests/cli/test_ci.py
  - id: openwiki-source-80a2cfb3c48998e688c559cb
    resource: repo://tests/cli/test_gitleaks.py
  - id: openwiki-source-50006f2346c4702d01ee9a4c
    resource: repo://tests/core/test_check_items.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# The ten check items

The knowledge of "what a skill is" lives in exactly one place: `check_commit` in `check.py`. The CLI's `harness-catalog check` (the author's pre-commit hook and the catalog repository's CI) and the registry's index build call the **same function**, so whatever passes before a commit also passes in the index after the merge. The function only judges; output is the caller's job.

## The items

| Item | Level | What it looks at | Result |
|---|---|---|---|
| 1 | repository | The marker `.harness-catalog` exists, is TOML and declares a supported `layout` (1); `skills/`, a CI workflow (`.github/workflows/` or `.gitlab-ci.yml`), `.pre-commit-config.yaml` and `README.md` exist | error |
| 2 | repository | Directly under `skills/` there are only directories (and `.gitkeep`), each with a `SKILL.md` | error |
| 3 | skill | `SKILL.md` passes the agentskills.io reference validator (`skills_ref`) and `name` equals the directory name | error |
| 4 | skill | gitleaks finds no secret in the skill directory | error |
| 5 | skill (history) | A name new since the base commit is not one that was retired (deleted) before | error |
| 6 | skill pair | The `metadata.replaced-by` target exists and is not itself replaced (no chains or cycles) | error |
| 7 | skill | At most 50 files, 1 MB per file, 5 MB in total, no symbolic links | error |
| 8 | skill | `metadata.requires-tools` is a space-separated list of `[a-z0-9._+-]+` tokens | error |
| 9 | skill (history) | A skill present at the base commit was deleted while its last version lacked `replaced-by` | warning |
| 10 | skill pair | Two skills carry the same relative path under `scripts/` with different contents | warning |

Repository-level items (1, 2) have an empty `Finding.skill`; in the registry they become readiness failures (`not_a_catalog`, `layout_mismatch`, …). A skill-level error excludes only that skill from the index. Warnings (9, 10) neither affect the exit code nor exclude anything.

## Exit codes and checker failure

The CLI ends in one of three ways.

- **0** — no errors (warnings are allowed).
- **1** — at least one error, printed one per line as `error: item N: <skill>: <reason>`.
- **2** — the checker itself failed (`checker_failed`). This is neither a pass nor a violation; no judgement was made.

The two sources of checker failure are `ValidatorFailure` (gitleaks failing to run, or `SKILL.md` unreadable) and `ContentError` (the repository could not be read). Secret scanning is **fail-closed**: without gitleaks, item 4 is not skipped — the whole run fails. In the registry this becomes a `checker_failed:…` degradation that keeps serving the previous version. The point is never to mistake "could not judge" for "passed".

Since 2026-10-10 the CLI no longer expects the operator or the CI workflow to install gitleaks. `_run_check` calls `ensure_gitleaks()` first: a `gitleaks` found on `PATH` is used only if `gitleaks version` reports the pinned 8.30.1; otherwise the CLI downloads the pinned release for the platform, verifies its SHA-256 against checksums compiled into `gitleaks.py`, installs it atomically into `~/.cache/harness-catalog/gitleaks-8.30.1/` with a sidecar hash, and reuses it while the hash still matches. Any failure to obtain a trustworthy binary — no network, checksum mismatch, malformed archive, unsupported platform — is `GitleaksUnavailable`, printed as `checker failed: …` with exit **2**. The registry image still installs gitleaks itself, so the download path is for author machines and CI runners.

## The base commit (`--base`)

Items 5 and 9 look at change, so they need a base commit; without one they are skipped. The pre-commit hook uses `--rev INDEX --base HEAD` (the staged tree against the last commit). CI no longer computes the base in shell: the workflow runs `harness-catalog ci check`, which derives it from the host's environment — the PR's merge-base with the target branch, or the pre-push commit (fetched from `origin` if the runner lacks it) — and refuses to guess when it cannot (exit 2) rather than silently narrowing to `HEAD~1`. A branch-creation push has no predecessor: the base is git's empty tree, every skill counts as changed, and `ci check` runs with `base=None`, so items 5 and 9 are skipped and the rest run. See [The CLI and catalog CI](cli-and-ci.md). The set of retired names is built from every `skills/*/SKILL.md` deletion in `main` history, so it is **fail-closed on a shallow clone**: instead of returning an empty set, `deleted_skill_names` raises `ContentError`. That is why the catalog CI template checks out with `fetch-depth: 0`.

Item 9 exports the base version's `SKILL.md` into a temporary directory and reads its frontmatter **with the parser**; it does not decide by the string "replaced-by" appearing in the body.

## Unit and order of checking

`check_commit` takes one commit and runs: repository structure → per skill `inspect_skill` (items 3, 4, 7, 8, on a temporary export of the skill directory where the validator and gitleaks run) → skill pairs (6, 10) → history (5, 9) if a base commit was given. A directory without `SKILL.md` is caught by item 2 and dropped from skill inspection, so it is not reported again as item 3.

`CheckReport.rejected_skills()` is the set of skill names with errors; the index build indexes everything else.

## Why those limits

Item 7's numbers (50 files, 1 MB, 5 MB) are upper bounds because the catalog returns a skill's **whole directory** through pin (`get_skill_archive`, capped separately at 20 MB of tar) and `get_skill_file`. Large data belongs outside the skill, fetched by a script. The symlink ban closes path-escape routes in export, archive and file reads.

## Tests

`tests/core/test_check_items.py` nails the item boundaries one at a time: a directory without `SKILL.md` is item 2, not 3; a repository-level violation makes the catalog not ready; item 9 reads frontmatter rather than body text. `tests/core/test_check.py` covers the remaining items against a fake repository. `tests/cli/test_check.py` covers the CLI's three exit codes, and `tests/cli/test_gitleaks.py` the acquisition path (PATH only on matching version, checksum verification and caching, mismatch and malformed archives fail closed, `check` exiting 2 when the binary is unavailable).

## Related

- [Catalog app](catalog-app.md) — where the check runs in the build and how `checker_failed`/`rejected` surface
- [Skill lifecycle](../workflows/skill-lifecycle.md) — when an author meets these rules (hook, CI) and the `replaced-by` procedure
- [The CLI and catalog CI](cli-and-ci.md) — `ci check`, the base-commit rules and the gitleaks acquisition
