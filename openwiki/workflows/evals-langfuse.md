---
type: workflow
title: Evals and records — Harbor evals and the harbor-langfuse plugin
description: How a skill's evaluation cases are run with Harbor and recorded in Langfuse as dataset experiments. The dataset and run naming, the metadata that makes with-skill and baseline runs comparable (skill, sha, scenario_sha, harness, model, baseline), the environment variables the plugin reads, and how the catalog CI's optional evals job is switched on and refuses to run without credentials.
tags: [evals, harbor, langfuse, plugin, ci]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-98336a47be0a931c50a9e553
    resource: repo://docs/runner.env.example
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-5540575795be4e93471f051d
    resource: repo://packages/harbor-langfuse/src/harbor_langfuse/plugin.py
  - id: openwiki-source-8acd19e9e876c66d6a086c17
    resource: repo://packages/harbor-langfuse/src/harbor_langfuse/sink.py
  - id: openwiki-source-0c789906f696a5148c3e684c
    resource: repo://tests/plugin/test_plugin.py
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Evals and records

Evaluation never runs inside the registry. A skill carries its own cases under `evals/` as Harbor tasks; `harbor run` executes them in a sandbox with a chosen harness and model; the `harbor-langfuse` plugin turns each job into a Langfuse **dataset experiment**. The registry holds no evaluation data — Langfuse is the record, and humans compare runs in its UI.

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

The real sink is built from the environment and fails fast if any of `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` or `LANGFUSE_HOST` is missing. On a developer machine they come from the shell; on the self-hosted runner from the runner's root `.env`, whose template (`docs/runner.env.example`) also lists each harness's model credentials in the names Harbor's agent implementations read (`CLAUDE_CODE_OAUTH_TOKEN` + `CLAUDE_FORCE_OAUTH`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `CODEX_FORCE_AUTH_JSON`, `CURSOR_API_KEY`, `GEMINI_API_KEY`…).

## Running locally

```sh
harbor run --path skills/<name>/evals --agent claude-code --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin   # with the skill
harbor run --path skills/<name>/evals --agent claude-code --env docker --plugin harbor_langfuse:LangfusePlugin                           # baseline
```

`--path` points at a local task directory; `--skill` injects the skill; the plugin is loaded by import path. The plugin package is installed where Harbor runs (`uvx --with harbor-langfuse @ git+…`), never in the registry image.

## The CI evals job

The catalog repository's workflow (written by `harness-catalog init`) always contains the evals jobs, but they are created only on a push to `main` when the repository variable `HARNESS_EVALS` is `true`. A small `agents` job turns the space-separated `HARNESS_EVALS_AGENTS` (default `claude-code codex`) into a JSON matrix, because workflow expressions cannot split strings. The `evals` job then, per harness:

1. **Checks credentials first** and fails naming the missing variable — `claude-code` needs an OAuth token with `CLAUDE_FORCE_OAUTH=1` or an API key, `codex` an API key or `CODEX_FORCE_AUTH_JSON=1` with an `auth.json`, and every harness needs the three Langfuse keys. Switching evals on without credentials is a loud failure, not a silent skip.
2. Computes the skills changed by the push (the same base commit the check job used).
3. For each changed skill that has `evals/`, runs `harbor run` twice (with and without the skill) with `HARNESS_SKILL_REF` set to the pushed commit and `HARNESS_CATALOG_NAME` to the repository name.

The switch lives on the git host and the credentials on the runner so that neither the registry nor the catalog repository's files change when evals are turned on or off.

## Tests

`tests/plugin/test_plugin.py` drives both hooks with a Harbor-shaped job object and a recording sink: dataset creation with one item per case, run metadata including `sha` from the environment and a 40-character `scenario_sha`, per-trial records with multi-step cost summed, the flush, and the baseline run when no skill is injected (`baseline=true`, empty `sha`).

## Related

- [Skill lifecycle](skill-lifecycle.md) — where evals sit in the authoring procedure
- [MCP server](../architecture/mcp-server.md) — the other Langfuse path: tool-call spans from the registry
