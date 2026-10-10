---
type: architecture
title: The CLI and catalog CI — check, init, config, ci base/check/evals
description: The harness-catalog command surface after 2026-10-10. check acquires gitleaks itself; init writes the template, the two base skills and the credentials action; the ci subcommands hold every piece of logic the catalog workflows used to embed in shell — base-commit selection that fails closed in CI and uses the empty tree for a branch-creation push, changed-skill detection, per-harness credential checks and the harbor runs — so the GitHub and GitLab templates are wiring only.
tags: [cli, ci, github-actions, gitlab-ci, gitleaks, harbor]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
sources:
  - id: openwiki-source-21f7c33015965f938339a839
    resource: repo://packages/cli/src/harness_catalog_cli/__main__.py
  - id: openwiki-source-6d7fdb64e59c26dbcd92f911
    resource: repo://packages/cli/src/harness_catalog_cli/ci.py
  - id: openwiki-source-9cd44c598af54599c4da2c87
    resource: repo://packages/cli/src/harness_catalog_cli/gitleaks.py
  - id: openwiki-source-f9693b6e1ce4d2e0751b245f
    resource: repo://packages/cli/src/harness_catalog_cli/init.py
  - id: openwiki-source-4ffa2c5cdbf87521a2f1016c
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/actions/code-repo-credentials/action.yml
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-3ca18ab7d13260d3ae6cfe5d
    resource: repo://packages/cli/src/harness_catalog_cli/templates/gitlab/.gitlab-ci.yml
  - id: openwiki-source-759953adeee8d15c68d2bcc7
    resource: repo://plans/distribution.md
  - id: openwiki-source-afe81887aa9e0e25a63c4164
    resource: repo://tests/cli/test_ci.py
  - id: openwiki-source-80a2cfb3c48998e688c559cb
    resource: repo://tests/cli/test_gitleaks.py
  - id: openwiki-source-73ccfe658017834ce601c998
    resource: repo://tests/cli/test_init.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
---

# The CLI and catalog CI

`harness-catalog` is one Typer application (`packages/cli/src/harness_catalog_cli/__main__.py`) installed from the code repository at a pinned tag. Three audiences use it: authors through the pre-commit hook, operators through `init` and `config`, and the catalog repository's CI through the `ci` group. The design rule behind the 2026-10-10 restructuring (`DESIGN.md` §11, `plans/distribution.md` D24) is that **workflow YAML wires and the CLI decides**. The previous templates embedded about seventy lines of shell per host, duplicated across jobs and hosts, that no linter or test ever saw; and because `init` only writes files that do not exist, logic frozen into a catalog repository's YAML could never be upgraded. Logic in the CLI follows the `@v<tag>` pin instead.

## Commands

| Command | Who runs it | What it does |
|---|---|---|
| `check [root] [--base C] [--rev INDEX\|HEAD\|commit]` | pre-commit hook, humans | The ten check items on one tree; exit 0 / 1 (violations) / 2 (checker failed) |
| `init <repo-url> [--pin] [--host]` | operators, once per catalog | Clone, detect host, write the template files that are missing, commit, push |
| `config list` / `config docs` | operators, release | Effective settings with their source; regenerate `docs/configuration.md` and the `.env.example` block |
| `ci base [root]` | CI, debugging | Print the base commit the CI rules select |
| `ci check [root]` | catalog CI `check` job | `check --rev HEAD --base <ci base>`; skips history items on a branch-creation push |
| `ci evals --agent <name> [root] [--dry-run]` | catalog CI `evals` job | Credential checks, changed skills since base, two `harbor run`s per skill |

`--version` prints the package version, which is also what the templates pin and what `ci evals` uses to select the matching `harbor-langfuse` plugin.

## check and gitleaks

`_run_check` resolves the requested tree through `GitStore.local`, obtains a gitleaks binary with `ensure_gitleaks()`, runs `check_commit` and prints findings as `error|warning: item N: <skill>: <reason>`. Gitleaks acquisition is deliberate: a binary on `PATH` is used only if `gitleaks version` equals the pinned `8.30.1`; otherwise the release tarball for the platform is downloaded, its SHA-256 compared with the checksums compiled into `gitleaks.py`, the binary installed atomically into `~/.cache/harness-catalog/gitleaks-8.30.1/` next to a hash sidecar, and reused while the sidecar still matches. Any failure to obtain a trustworthy binary — unsupported platform, download error, checksum mismatch, malformed archive — raises `GitleaksUnavailable`, which `_run_check` turns into `checker failed: …` and exit 2. The workflow templates therefore install nothing; the registry image still ships its own gitleaks.

## init

`init_repository` clones the target with the operator's git credentials, detects GitHub or GitLab from the URL, and writes, through `write_missing`, every template file that is absent: the marker `.harness-catalog`, `README.md`, `.pre-commit-config.yaml`, the host's workflow (`.github/workflows/check.yml` plus `.github/actions/code-repo-credentials/action.yml`, or `.gitlab-ci.yml`), and — since the D14 revision of 2026-10-10 — the two base skills `skills/pin-skill/` and `skills/write-skill/` in full. `v<판>` placeholders become the CLI's own version so the catalog pins the tag it was created from. A second run writes nothing. The skills' single source of truth is the CLI package data under `templates/skills/`; the quickstart's seed script copies from the same place.

## The ci group

`ci.py` is pure logic with injectable git and subprocess runners, so every rule below is unit-tested.

**Base commit.** `base_commit(env, run)` implements the rules that items 5 and 9 need:

1. GitHub pull request (`GITHUB_EVENT_NAME=pull_request`): `git merge-base origin/<GITHUB_BASE_REF> HEAD`; if that fails (the checkout was shallow), `CIError`.
2. Otherwise the first available of `CI_MERGE_REQUEST_DIFF_BASE_SHA`, the `before` field of the GitHub event payload (`GITHUB_EVENT_PATH`), `CI_COMMIT_BEFORE_SHA`. A zero SHA means a branch-creation push and yields git's **empty tree**, so every file counts as changed. A SHA the runner does not have is fetched from `origin` once; if it is still missing the command refuses with `CIError` rather than narrowing the window.
3. If a CI marker (`GITHUB_ACTIONS`, `GITLAB_CI`) is set and no candidate was found — payload unreadable, variables missing — `CIError`. Only a local run without markers falls back to `HEAD~1` (or `HEAD` on a one-commit repository).

`ci check` maps `CIError` to exit 2, and when the base is the empty tree it runs `check` with `base=None` after printing that history items are skipped.

**Changed skills.** `changed_skill_dirs` is `git diff --name-only <base> HEAD -- skills` reduced to `skills/<name>` directories; a failing diff is `CIError`, never "nothing changed".

**Credentials.** `missing_credentials(agent, env)` encodes, per harness, the variables Harbor's agent implementations read: `claude-code` needs `CLAUDE_CODE_OAUTH_TOKEN` with `CLAUDE_FORCE_OAUTH=1` or `ANTHROPIC_API_KEY`; `codex` needs `OPENAI_API_KEY` or `CODEX_FORCE_AUTH_JSON=1` with an existing `auth.json`; `cursor-cli` needs `CURSOR_API_KEY`; `gemini-cli` needs `GEMINI_API_KEY` or `GEMINI_FORCE_OAUTH`; anything else is unknown. `missing_langfuse` requires the three Langfuse variables. `ci evals` exits 1 with the missing name before touching git.

**Harbor runs.** For each changed skill that has an `evals/` directory, `evals_plan` yields two commands — with `--skill ./skills/<name>` and without (the baseline) — each `uvx --from harbor==0.24.0 --with "harbor-langfuse @ git+<code repo>@v<cli version>#subdirectory=packages/harbor-langfuse" harbor run --path skills/<name>/evals --agent <agent> --env docker --plugin harbor_langfuse:LangfusePlugin`. `harbor_env` adds `HARNESS_SKILL_REF` (HEAD) and `HARNESS_CATALOG_NAME` (from `GITHUB_REPOSITORY`, `CI_PROJECT_NAME` or the directory name) for the plugin. `run_plan` runs every command even after a failure and the exit code is 1 if any failed; `--dry-run` prints the plan.

## What the templates still contain

The GitHub workflow has two jobs. `check` runs on pull requests and `main` pushes: checkout with `fetch-depth: 0` (history for item 5), `setup-uv`, the local composite action `./.github/actions/code-repo-credentials`, and one `uvx … harness-catalog ci check` line. `evals` runs on `main` pushes when the repository variable `HARNESS_EVALS` is `true`, on the `[self-hosted, harness-catalog]` runner, with `strategy.matrix.agent` taken from `fromJSON(vars.HARNESS_EVALS_AGENTS || '["claude-code", "codex"]')` — a JSON array, which removed the former shell job that split a space-separated string — and one `uvx … harness-catalog ci evals --agent "${{ matrix.agent }}"` line.

The only shell left is the credentials action: while the code repository is private, `uvx --from git+https://…` cannot fetch the CLI without a credential, and the CLI cannot install its own prerequisite. The action takes the deploy key from the secret `HARNESS_CATALOG_DEPLOY_KEY`, writes it to `$RUNNER_TEMP`, pins GitHub's host key, and exports `GIT_SSH_COMMAND` and a `url.<ssh>.insteadOf <https>` rewrite through `$GITHUB_ENV` so only this job's git sees them. If the secret is empty the action does nothing. The former personal-access-token path was dropped because such tokens cannot be created by API and expire. Publishing the code repository or the packages would make the action unnecessary.

The GitLab template mirrors this with a hidden job `.code-repo-credentials` whose `before_script` the two jobs `extends`; the `check` job additionally installs `git` and `openssh-client` because the `uv` slim image ships neither. GitLab cannot build a matrix from a variable, so its `evals` matrix is a literal list to edit.

## Tests

- `tests/cli/test_ci.py`: base-commit rules for GitHub PR, push `before`, zero SHA, GitLab variables, unreachable SHA recovered by fetch, fail-closed cases with CI markers, root-only repository; changed-skill detection; the credential table; the two-command plan; `harbor_env`; `run_plan` running everything and counting failures; the CLI's exit codes 1 (credentials), 2 (no base), 0 (nothing changed) and the dry run; `ci check` on a branch creation calling `_run_check(repo, None, "HEAD")`.
- `tests/cli/test_gitleaks.py`: PATH binary accepted only on matching version, download verified and cached, mismatch and malformed archive fail closed, `check` exits 2 when unavailable.
- `tests/cli/test_init.py`: idempotence, the two base skills written without `.gitkeep`, the credentials action written for GitHub, layout mismatch refused.

## Related

- [The ten check items](check-items.md) — what `check` and `ci check` judge
- [Skill lifecycle](../workflows/skill-lifecycle.md) — `init`, the hook and CI from the author's side
- [Evals and records](../workflows/evals-langfuse.md) — what the two harbor runs record
- [Test strategy](../testing/test-strategy.md) — how these suites are isolated
- [Design decisions in brief](../concepts/design-decisions.md) — why logic moved out of YAML
