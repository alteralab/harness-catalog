---
type: workflow
title: Skill lifecycle — repository contract, publishing, updating, retiring
description: What a catalog repository must contain and how harness-catalog init writes it once; why a branch, a PR and a merge into main are the only publication mechanism; how a skill is updated, retired or replaced and why a retired name can never return; how the templates pin the CLI version; and the two meta-skills (write-skill, pin-skill) that encode the procedures for agents.
tags: [skills, catalog-repository, init, publishing, replaced-by, templates]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-f9693b6e1ce4d2e0751b245f
    resource: repo://packages/cli/src/harness_catalog_cli/init.py
  - id: openwiki-source-4699297db335c68f3a06c37b
    resource: repo://packages/cli/src/harness_catalog_cli/templates/.pre-commit-config.yaml
  - id: openwiki-source-2fd28969aab5f590c3aecdcf
    resource: repo://packages/cli/src/harness_catalog_cli/templates/github/check.yml
  - id: openwiki-source-25d12f036b20f342206d65a2
    resource: repo://packages/cli/src/harness_catalog_cli/templates/README.md
  - id: openwiki-source-85a76422b73202924b7addfe
    resource: repo://packages/core/src/harness_catalog_core/catalog.py
  - id: openwiki-source-26ec5196a784179afea72f39
    resource: repo://packages/core/src/harness_catalog_core/check.py
  - id: openwiki-source-6e7a57fd98eb0a612451cf3c
    resource: repo://skills/pin-skill/SKILL.md
  - id: openwiki-source-d46c4dde101d421509b48b03
    resource: repo://skills/write-skill/SKILL.md
  - id: openwiki-source-73ccfe658017834ce601c998
    resource: repo://tests/cli/test_init.py
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# Skill lifecycle

A skill is a directory `skills/<name>/` in the catalog repository, and every state change in its life — creation, update, retirement, replacement — is a commit on `main` made through a pull request. The registry never writes; it observes `main`. This page follows a skill from the empty repository to its retirement.

## The repository contract

A catalog repository needs six things: the marker file `.harness-catalog` declaring `layout = 1`; a `skills/` directory (kept in git by `.gitkeep`); a CI workflow that runs `harness-catalog check` on every PR and push to `main` (plus the optional evals job); a pre-commit configuration that runs the same check before each commit; a README for team members; and the **discipline** of never pushing to or force-pushing `main`. The first five are files and the [check items](../architecture/check-items.md) 1 and 2 verify them; the sixth is not enforced by the registry but defended by it — a rewound `main` is refused until an operator accepts it.

## `harness-catalog init` writes the files once

`init <repo-url>` clones the repository with the operator's own git credentials, detects the host from the URL (GitHub or GitLab; `--host` overrides), checks out `main` — creating it on an unborn repository, refusing a repository that has commits but no `main` — writes only the files that are missing, commits as `harness-catalog init (cli <ref>)` and pushes to `main`. Running it twice changes nothing. If the marker exists but declares another layout, it stops rather than mixing layouts.

The workflow and the pre-commit configuration carry the CLI version: `init` substitutes the placeholder `v<판>` with its own package version and **verifies that this tag exists** in the code repository, refusing to write an unpublished pin unless `--pin <ref>` is given explicitly. The pre-commit hook installs `harness-catalog-core` and `-cli` from that tag; the CI workflow runs the CLI from the same tag with `uvx`. Raising the pin later is an edit to those two files in the catalog repository.

## Writing a new skill

The `write-skill` meta-skill encodes the team procedure for an agent, and `docs/authoring.md` the same for a person:

1. Search first (`search_skills`): if a skill already does the job, update it instead of adding a near-duplicate.
2. Choose a name — 1 to 64 characters of lowercase letters, digits and hyphens, unique across the catalog, never one that was retired.
3. From an up-to-date `main`, branch `skill/<name>` and write `skills/<name>/SKILL.md`; put deterministic work (computation, conversion, lookups) in `scripts/` run through `uv run --script`, judgement in the prose; declare system tools both in `compatibility` (for people) and `metadata.requires-tools` (for machines).
4. Add at least one pair of Harbor eval cases: one the skill must solve, one it must **not** trigger on.
5. Run `harness-catalog check` (the hook will again at commit, CI again on the PR), then the evals with and without the skill, recording both runs in Langfuse.
6. Open the PR. A person merges; the merger is the certifier. The registry indexes the new skill on its next fetch, and `list_skills` shows it with its tree `sha`.

The description deserves the most care: it is the only signal an agent has when deciding whether to load the skill, hosts may truncate it, and the eval pair exists to catch both missed and spurious triggers.

## Updating

An update is the same directory changed on a branch and merged. The tree `sha` changes; nothing else does. Older versions remain readable through `load_skill(id, sha=…)` because the registry resolves a tree hash through `main` history, so a harness that pinned a version keeps working and can detect the newer one.

## Pinning on the consumer side

`pin-skill` is the mirror image for readers: it downloads a skill's whole directory into the harness's skill folder (`.agents/skills/<name>/` for a project, `~/.agents/skills/<name>/` for a user, with `.claude/skills/<name>` as a symlink so every harness sees one copy), fetching every file at **one** `sha`, assembling it in a temporary directory, comparing the file set with `load_skill`'s list, and renaming into place atomically. A `PINNED` line records name, `sha` and time; "is there a newer version?" is answered by comparing that `sha` with `list_skills`. There is no server-side download tool — only the user's session can write to the user's machine.

## Retiring and replacing

Retirement is a PR that deletes the directory. Replacement is two PRs: first add `metadata.replaced-by: <new-name>` to the old skill so search results point readers onward (`replaced_by`), then delete it. The checks enforce the shape — the target must exist and must not itself be replaced (no chains), and deleting without `replaced-by` is a warning.

A retired name can **never** be reused (check item 5). The reason is on the consumer side: someone's `PINNED` file may still name it, and "the skill disappeared" must stay distinguishable from "a different skill took the name". The registry derives the retired set from the full history of `main`, which is why the catalog CI checks out with full depth.

## Related

- [The ten check items](../architecture/check-items.md) — what the hook and CI enforce at each step
- [Evals and records](evals-langfuse.md) — the with/without runs and where they are recorded
- [Deployment](../operations/deployment.md) — the deploy key and CI read credentials the repository needs
