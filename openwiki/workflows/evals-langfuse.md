---
type: workflow
title: Evals and records — Harbor tasks, Langfuse plugin, the CI evals job
description: How a skill's evals run and where their results live. Harbor tasks in Harbor's official shape (task.toml, instruction.md, environment image, tests/test.sh running pytest with a CTRF report, solution/solve.sh for the Oracle), the harbor-langfuse plugin that turns a run into a Langfuse dataset experiment with comparable metadata, the with/without-skill baseline pair, the runner's credentials, and the CI evals job that is one harness-catalog ci evals call per harness.
tags: [evals, harbor, langfuse, plugin, ci]
sources:
  - id: openwiki-source-eb717bf0b36ba13f5f7c2ecd
    resource: repo://.github/runner.env.example
  - id: openwiki-source-21f7c33015965f938339a839
    resource: repo://packages/cli/src/harness_catalog_cli/__main__.py
  - id: openwiki-source-6d7fdb64e59c26dbcd92f911
    resource: repo://packages/cli/src/harness_catalog_cli/ci.py
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-3ca18ab7d13260d3ae6cfe5d
    resource: repo://packages/cli/src/harness_catalog_cli/templates/gitlab/.gitlab-ci.yml
  - id: openwiki-source-d5d49c1505b52324284d6b60
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/pin-skill/evals/pin-project-scope/environment/Dockerfile
  - id: openwiki-source-043213c0700f2596a20bc1a9
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/pin-skill/evals/pin-project-scope/task.toml
  - id: openwiki-source-71f77beb2e80218e7e136bc5
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/pin-skill/evals/pin-project-scope/tests/test.sh
  - id: openwiki-source-62dbe81742a0232dcb36b0c3
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/write-skill/references/conventions.md
  - id: openwiki-source-5540575795be4e93471f051d
    resource: repo://packages/harbor-langfuse/src/harbor_langfuse/plugin.py
  - id: openwiki-source-8acd19e9e876c66d6a086c17
    resource: repo://packages/harbor-langfuse/src/harbor_langfuse/sink.py
  - id: openwiki-source-0c789906f696a5148c3e684c
    resource: repo://tests/plugin/test_plugin.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Evals and records

Evaluation never runs inside the registry. A skill carries its own cases under `evals/` as Harbor tasks; `harbor run` executes them in a sandbox with a chosen harness and model; the `harbor-langfuse` plugin turns each job into a Langfuse **dataset experiment**. The registry holds no evaluation data — Langfuse is the record, and humans compare runs in its UI.

## The shape of an eval case

Since 2026-10-10 every case follows the skeleton `harbor tasks init` generates, with one deliberate deviation (DESIGN §11; plans/skills.md D11). A case directory `skills/<name>/evals/<case>/` holds six files:

| File | Role |
|---|---|
| `task.toml` | schema 1.4; `[environment] skills_dir = "/skills"` so an injected skill lands where the harness looks; build, agent and verifier timeouts; a commented `[[environment.mcp_servers]]` block for cases that need the live registry |
| `instruction.md` | the task the harness is given — for a negative case, a task on which the skill must **not** trigger |
| `environment/Dockerfile` | `python:3.12-slim` plus git, with pytest and `pytest-json-ctrf` pre-installed, because the verifier runs without network |
| `tests/test.sh` | the verifier entry point: runs `python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py` in `/work` and writes `1` or `0` to `/logs/verifier/reward.txt` from the exit code |
| `tests/test_outputs.py` | all checking logic, as pytest assertions over the sandbox's state |
| `solution/solve.sh` | a self-contained reference solution for Harbor's Oracle agent; it cannot rely on the skill because Oracle accepts no `--skill` |

The official skeleton installs pytest with apt, curl and uvx on every trial; this project bakes them into the image instead. Everything else — the bash entry, pytest, the CTRF report, the reward from the exit code — is Harbor's. `write-skill`'s `scripts/scaffold.py` writes a positive and a negative case in exactly this shape, so an author only fills the TODOs, and `harbor run -a oracle -e docker` proves the pair before any model is involved (see [Test strategy](../testing/test-strategy.md)).

## What a run records

The plugin implements Harbor's job-plugin contract by duck typing (it does not import Harbor). Two hooks do the work:

- `on_job_start` — derives a `RunContext` from the job: the dataset name `<catalog>/<skill>` (the catalog name from `HARNESS_CATALOG_NAME`, default `catalog`; the skill from the evals directory's parent), the run name (Harbor's job name), metadata, and the cases (each case directory's `instruction.md`). It then makes sure the Langfuse dataset exists with one item per case (idempotent).
- `on_job_end` — converts every trial into a record (instruction, verifier output, reward, `passed` = reward ≥ 1.0, token counts, cost, exception) and writes the run through `run_experiment`, so Langfuse gets a trace, a run item and a boolean `passed` score per case in one call; then flushes.

The metadata is what makes runs comparable later:

| Key | Source | Why |
|---|---|---|
| `skill` | evals path | which skill |
| `sha` | `HARNESS_SKILL_REF` env | the skill version that was injected; Harbor rewrites the skill source to a cache path, so the caller must pass the ref (CI passes the commit SHA) |
| `scenario_sha` | `git rev-parse HEAD:./` of the evals dir | the version of the cases themselves |
| `harness`, `model` | the job's agent config | what ran the cases |
| `baseline` | `"true"` when no skill was injected | the "without the skill" control run |

A run with the skill and a run without it share the dataset and differ only in `baseline` and `sha`; if both pass, the model already does the job and the skill adds nothing; if only the with-skill run passes, the skill earned its place.

## Where the credentials come from

The real sink is built from the environment and fails fast if any of `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` or `LANGFUSE_HOST` is missing. On a developer machine they come from the shell; on the self-hosted runner from the runner's root `.env`, whose template (`.github/runner.env.example` in the code repository) also lists each harness's model credentials in the names Harbor's agent implementations read (`CLAUDE_CODE_OAUTH_TOKEN` + `CLAUDE_FORCE_OAUTH`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `CODEX_FORCE_AUTH_JSON`, `CURSOR_API_KEY`, `GEMINI_API_KEY`…). The file lives only on the runner machine; the repository keeps the example.

## Running locally

```sh
harbor run --path skills/<name>/evals --agent claude-code --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin   # with the skill
harbor run --path skills/<name>/evals --agent claude-code --env docker --plugin harbor_langfuse:LangfusePlugin                           # baseline
harbor run --path skills/<name>/evals --agent oracle --env docker                                                                       # verifier self-check, no model
```

`--path` points at a local task directory; `--skill` injects the skill; the plugin is loaded by import path. The plugin package is installed where Harbor runs (`uvx --with "harbor-langfuse @ git+…"`), never in the registry image.

## The CI evals job

The catalog repository's workflow (written by `harness-catalog init`) always contains an `evals` job, created only on a push to `main` when the repository variable `HARNESS_EVALS` is `true`. The job is wiring only: checkout with full depth, uv, the deploy-key credential step, and one line — `harness-catalog ci evals --agent <x>` — run from the pinned CLI tag on the `self-hosted, harness-catalog` runner. On GitHub the matrix comes straight from `fromJSON(vars.HARNESS_EVALS_AGENTS || '["claude-code", "codex"]')`, so the variable is a JSON array and the former `agents` splitting job is gone; GitLab cannot build a matrix from a variable, so its `parallel.matrix` lists the agents in the file.

Everything the job used to do in shell now happens inside `ci evals`, in the CLI's `ci.py`, under pytest:

1. **Credentials first.** `missing_credentials(agent, env)` applies the per-harness table — `claude-code` needs an OAuth token with `CLAUDE_FORCE_OAUTH=1` or an API key, `codex` an API key or `CODEX_FORCE_AUTH_JSON=1` with an `auth.json`, `cursor-cli` and `gemini-cli` their keys — and `missing_langfuse` requires the three Langfuse keys. A missing item prints what is needed and exits 1: switching evals on without credentials is a loud failure, not a silent skip.
2. **Base commit and changed skills.** The same base-commit rule the check job uses (the push's `before`, or the empty tree for a branch creation) yields the changed `skills/<name>` directories; if the base cannot be determined, exit 2.
3. **Two harbor jobs per changed skill with `evals/`**, in deterministic order: with `--skill ./skills/<name>` and without (the baseline). Each is `uvx --from harbor==0.24.0 --with "harbor-langfuse @ git+<code repo>@v<cli version>#subdirectory=packages/harbor-langfuse" harbor run … --plugin harbor_langfuse:LangfusePlugin`, so the plugin always comes from the same tag as the CLI. `HARNESS_SKILL_REF` is set to `HEAD` and `HARNESS_CATALOG_NAME` to the host's repository name unless already set.
4. All jobs run even if one fails; the command exits 1 with the failure count. `--dry-run` prints the harbor commands instead, which is how the plan is tested without Harbor.

The switch lives on the git host and the credentials on the runner so that neither the registry nor the catalog repository's files change when evals are turned on or off. See [CLI and CI](../architecture/cli-and-ci.md) for the base-commit rules and the credential step.

## Tests

`tests/plugin/test_plugin.py` drives both hooks with a Harbor-shaped job object and a recording sink: dataset creation with one item per case, run metadata including `sha` from the environment and a 40-character `scenario_sha`, per-trial records with multi-step cost summed, the flush, and the baseline run when no skill is injected (`baseline=true`, empty `sha`). `tests/cli/test_ci.py` covers the credential table, the two-jobs-per-skill plan, the harbor environment, and the exit codes of `ci evals`.

## Related

- [Skill lifecycle](skill-lifecycle.md) — where evals sit in the authoring procedure
- [CLI and CI](../architecture/cli-and-ci.md) — `ci base`, `ci check`, `ci evals` and gitleaks acquisition
- [Test strategy](../testing/test-strategy.md) — the Oracle self-check and the CI-logic tests
- [MCP server](../architecture/mcp-server.md) — the other Langfuse path: tool-call spans from the registry
