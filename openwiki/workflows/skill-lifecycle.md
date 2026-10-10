---
type: workflow
title: Skill lifecycle — repository contract, init, writing, updating, pinning, retiring
description: A skill's life from the empty catalog repository to retirement. The repository contract and the files harness-catalog init writes once (including the two base skills), how write-skill scaffolds a skill and its Harbor eval pair with a deterministic script, how a change becomes a version, how pin-skill downloads one tar through get_skill_archive and installs it atomically, and why a retired name is never reused.
tags: [skills, catalog-repository, init, publishing, replaced-by, templates]
sources:
  - id: openwiki-source-8dce026a7a38d31fea2197ea
    resource: repo://docker/quickstart/seed-catalog.sh
  - id: openwiki-source-f9693b6e1ce4d2e0751b245f
    resource: repo://packages/cli/src/harness_catalog_cli/init.py
  - id: openwiki-source-4699297db335c68f3a06c37b
    resource: repo://packages/cli/src/harness_catalog_cli/templates/.pre-commit-config.yaml
  - id: openwiki-source-4ffa2c5cdbf87521a2f1016c
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/actions/code-repo-credentials/action.yml
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-25d12f036b20f342206d65a2
    resource: repo://packages/cli/src/harness_catalog_cli/templates/README.md
  - id: openwiki-source-e38edc0a0c8956c81d346427
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/pin-skill/SKILL.md
  - id: openwiki-source-840e0efbbf6279095f6037f0
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/write-skill/scripts/scaffold.py
  - id: openwiki-source-66877d544cf0f1f4801b2e92
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/write-skill/SKILL.md
  - id: openwiki-source-85a76422b73202924b7addfe
    resource: repo://packages/core/src/harness_catalog_core/catalog.py
  - id: openwiki-source-26ec5196a784179afea72f39
    resource: repo://packages/core/src/harness_catalog_core/check.py
  - id: openwiki-source-759953adeee8d15c68d2bcc7
    resource: repo://plans/distribution.md
  - id: openwiki-source-73ccfe658017834ce601c998
    resource: repo://tests/cli/test_init.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
---

# Skill lifecycle

A skill is a directory `skills/<name>/` in the catalog repository, and every state change in its life — creation, update, retirement, replacement — is a commit on `main` made through a pull request. The registry never writes; it observes `main`. This page follows a skill from the empty repository to its retirement.

## The repository contract

A catalog repository needs six things: the marker file `.harness-catalog` declaring `layout = 1`; a `skills/` directory containing only skill directories (each with a `SKILL.md`; a `.gitkeep` is tolerated); a CI workflow that runs `harness-catalog ci check` on every PR and push to `main` (plus the optional evals job); a pre-commit configuration that runs the same check before each commit; a README for team members; and the **discipline** of never pushing to or force-pushing `main`. The first five are files and the [check items](../architecture/check-items.md) 1 and 2 verify them; the sixth is not enforced by the registry but defended by it — a rewound `main` is refused until an operator accepts it.

## `harness-catalog init` writes the files once

`init <repo-url>` clones the repository with the operator's own git credentials, detects the host from the URL (GitHub or GitLab; `--host` overrides), checks out `main` — creating it on an unborn repository, refusing a repository that has commits but no `main` — writes only the files that are missing, commits as `harness-catalog init (cli <ref>)` and pushes to `main`. Running it twice changes nothing. If the marker exists but declares another layout, it stops rather than mixing layouts.

Since 2026-10-10 the file set is complete from the first commit (DESIGN §11; plans/distribution.md D14 revised): the marker, README, pre-commit configuration, the host's workflow — on GitHub `.github/workflows/check.yml` together with the local composite action `.github/actions/code-repo-credentials/action.yml` that it uses, on GitLab `.gitlab-ci.yml` — and **the two base skills** `skills/pin-skill/` and `skills/write-skill/` with all their files, read straight from the CLI package's `templates/skills/`. There is no `.gitkeep` and no "first PR": a new catalog answers `search_skills` for both skills as soon as the registry fetches it. Because `init` writes only missing files, a later change to either base skill still reaches an existing catalog by an ordinary PR, and `check` treats them like any other skill. The quickstart seeds its demo catalog from the same package directory, so there is exactly one copy of the skill sources.

The workflow and the pre-commit configuration carry the CLI version: `init` substitutes the placeholder `v<판>` with its own package version and **verifies that this tag exists** in the code repository, refusing to write an unpublished pin unless `--pin <ref>` is given explicitly. The pre-commit hook installs `harness-catalog-core` and `-cli` from that tag and runs `harness-catalog check --rev INDEX --base HEAD`; the CI workflow runs `harness-catalog ci check` from the same tag with `uvx`, after a credential step that hands the job a read-only deploy key for the code repository while it is private. Raising the pin later is an edit to those two files in the catalog repository. The workflow itself contains no logic — base commit, changed skills and gitleaks live in the CLI (see [CLI and CI](../architecture/cli-and-ci.md)).

## Writing a new skill

The `write-skill` meta-skill encodes the team procedure for an agent, and `docs/authoring.md` the same for a person:

1. Search first (`search_skills`): if a skill already does the job, update it instead of adding a near-duplicate.
2. Choose a name — 1 to 64 characters of lowercase letters, digits and hyphens, unique across the catalog, never one that was retired.
3. From an up-to-date `main`, branch `skill/<name>` and run the deterministic scaffold: `uv run --script skills/write-skill/scripts/scaffold.py <name> --description "<one sentence>" [--positive <case>] [--negative <case>] [--script <x.py>]`. The script (PEP 723, no dependencies, idempotent — it never touches an existing file) writes `SKILL.md` with its frontmatter and section headings, an optional `scripts/<x.py>` with the PEP 723 header and the exit-code convention (2 input error, 3 target missing, 4 tool missing), and one positive and one negative eval case in Harbor's six-file shape. It owns the boilerplate — schema 1.4, `skills_dir`, timeouts, the `no-trigger-` prefix, the verifier skeleton — so the agent fills only the TODOs: the description, the body (when to use, steps, failure table), script bodies, task text, pytest assertions and the Oracle solution.
4. Pass the checklist in `references/conventions.md`: deterministic work (computation, conversion, lookups) in scripts run through `uv run --script`, judgement in the prose; system tools declared both in `compatibility` (for people) and `metadata.requires-tools` (for machines).
5. Fill the eval pair — one task the skill must solve, one it must **not** trigger on — and run it without a model first: `harbor run -p skills/<name>/evals -a oracle -e docker` must give reward 1 on every case, which proves the task, the image and the pytest verifier agree.
6. Review the description: the core use and the trigger words belong in the first sentence, because hosts may truncate it and it is the only signal an agent has when deciding whether to load the skill.
7. Run `harness-catalog check` (the hook will again at commit, CI again on the PR), then the evals with and without the skill, recording both runs in Langfuse.
8. Report to the user and **stop**. Only when told to does the agent commit, push and open the PR; a person merges, and the merger is the certifier. The registry indexes the new skill on its next fetch, and `list_skills` shows it with its tree `sha`.

## Updating

An update is the same directory changed on a branch and merged. The tree `sha` changes; nothing else does. Older versions remain readable through `load_skill(id, sha=…)` because the registry resolves a tree hash through `main` history, so a harness that pinned a version keeps working and can detect the newer one.

## Pinning on the consumer side

`pin-skill` is the mirror image for readers: it installs a skill's whole directory into the harness's skill folder (`.agents/skills/<name>/` for a project, `~/.agents/skills/<name>/` for a user, with `.claude/skills/<name>` as a symlink so every harness sees one copy). Since 2026-10-11 the bytes never pass through the model:

1. `load_skill(<name>)` gives the current `sha`, `commit` and file list; every later call names that same `sha`, so a `main` that moves mid-download cannot mix versions.
2. `get_skill_archive(<name>, sha=…)` returns a download descriptor — `uri`, a `headers` map holding a five-minute `X-Harness-Archive-Token`, `size`, `sha256`, `digest` — instead of file contents.
3. In the shell, `curl -fsS -H "X-Harness-Archive-Token: …" -o <tmp>.tar "<uri>"`, then the size and sha256 are compared with the descriptor (a mismatch deletes the file and stops), then `tar -xf` into a temporary directory `.<name>.pin-tmp/` beside the target. A 403 means the token expired or the registry restarted; the descriptor is re-minted **once**.
4. The extracted file set is compared with the list from step 1 — sha256 guards the transfer, this comparison guards the version — and a `PINNED` line (`<name> <sha> <ISO 8601 UTC>`) is written into the temporary directory.
5. The temporary directory is renamed into place in one step (an existing copy is moved aside first and restored if the rename fails), and the `.claude/skills/<name>` symlink is created unless a real directory already sits there.

"Is there a newer version?" is answered by comparing `PINNED`'s `sha` with `list_skills` across both scopes. There is still no server-side write and no CLI — the registry only hands out bytes, and the user's session writes to the user's machine. `get_skill_file` remains for reading one file inside a loop. See [Archive download](../architecture/archive-download.md) for the route, the token and the cache.

## Retiring and replacing

Retirement is a PR that deletes the directory. Replacement is two PRs: first add `metadata.replaced-by: <new-name>` to the old skill so search results point readers onward (`replaced_by`), then delete it. The checks enforce the shape — the target must exist and must not itself be replaced (no chains), and deleting without `replaced-by` is a warning.

A retired name can **never** be reused (check item 5). The reason is on the consumer side: someone's `PINNED` file may still name it, and "the skill disappeared" must stay distinguishable from "a different skill took the name". The registry derives the retired set from the full history of `main`, which is why the catalog CI checks out with full depth — and why `ci check` on a branch-creation push, which has no prior history, skips items 5 and 9 explicitly instead of guessing.

## Related

- [The ten check items](../architecture/check-items.md) — what the hook and CI enforce at each step
- [CLI and CI](../architecture/cli-and-ci.md) — `init`, `ci check` and the credential step the workflow uses
- [Evals and records](evals-langfuse.md) — the Harbor-shaped cases, the Oracle self-check and the with/without runs
- [Archive download](../architecture/archive-download.md) — the tool and route behind `pin-skill`
- [Deployment](../operations/deployment.md) — the deploy key the registry needs to read the catalog
