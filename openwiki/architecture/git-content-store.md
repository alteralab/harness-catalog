---
type: architecture
title: GitStore — bare clone, fetch, deploy key, history resolution
description: How the ContentStore adapter obtains and reads the catalog repository. The two modes (registry with a bare clone and a read-only deploy key; CLI reading a working repository in place), why safe.directory is delivered through a private global git config, how a past version is found in main history, and where it fails closed.
tags: [git, content-store, adapter, deploy-key, history]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T11:24:40.987Z
sources:
  - id: openwiki-source-849176cfe2a21dc2733885fb
    resource: repo://packages/core/src/harness_catalog_core/adapters/git.py
  - id: openwiki-source-26ec5196a784179afea72f39
    resource: repo://packages/core/src/harness_catalog_core/check.py
  - id: openwiki-source-343c3014e84cd4cd16294a7d
    resource: repo://tests/adapters/test_git_history.py
  - id: openwiki-source-6ef6c6646b1605cce25a7f69
    resource: repo://tests/adapters/test_git.py
generated: { by: "claude-code", at: "2026-10-10T11:24:40.987Z" }
---

# GitStore

`GitStore` is the `ContentStore` adapter: everything the app knows about the repository arrives through it. It shells out to the `git` binary, never writes to the remote, and serialises every operation on one lock so that fetches and exports do not interleave.

## Two modes

| Mode | Construction | What it reads | Fetches? |
|---|---|---|---|
| Registry | `GitStore(workdir/clone, remote_url, deploy_key)` | A **bare** clone of the catalog repository, `main` tracked under `refs/remotes/origin/main` | Yes, on every `fetch()` |
| CLI | `GitStore.local(repo_root)` | The author's existing repository in place; `resolve("INDEX")` turns the staged tree into a tree object so pre-commit checks the exact content being committed | No |

`fetch()` in registry mode creates the bare clone on first use (`git clone --bare --no-tags`), then runs `git fetch --prune --no-tags origin +refs/heads/main:refs/remotes/origin/main` and returns the commit. A missing `main` is reported as `no_main_branch` (so `harness-catalog init` can be suggested), any other failure as `repo_unreachable` with git's stderr attached. In CLI mode `fetch()` simply resolves `HEAD`.

## Read-only access

The deploy key is passed in as text and written to `<workdir>/ssh/deploy_key` with mode `0600` in a `0700` directory; `GIT_SSH_COMMAND` points at it with `IdentitiesOnly=yes`, `StrictHostKeyChecking=accept-new` and `BatchMode=yes`. `close()` deletes the key file on shutdown. The key is registered on the git host as **read-only**, so even a compromised registry cannot push; the design treats the registry as a pure reader of `main`.

`GIT_TERMINAL_PROMPT=0` guarantees that git never waits for credentials interactively, and `GIT_DIR`/`GIT_WORK_TREE` from the environment are stripped so an operator's shell cannot redirect the adapter.

## Why `safe.directory` lives in a private global config

Git refuses to read a repository owned by another uid ("dubious ownership"). The quickstart mounts a bare repository seeded by a root container into the registry (uid 10001), so this case is real. `safe.directory` is only honoured from **protected** configuration scopes (system and global), and the `git-upload-pack` child spawned for a `file://` transport does not inherit `-c` or `GIT_CONFIG_COUNT` overrides. GitStore therefore writes `<workdir>/gitconfig` containing `[safe] directory = *` and points `GIT_CONFIG_GLOBAL` at it — but only in registry mode, so the CLI never shadows an author's own `~/.gitconfig`.

## Reading trees and files

- `list_skill_trees(commit)` lists the trees directly under `skills/` at that commit and, for each, the last commit that touched it (so an index entry knows its own commit).
- `read_blob(revision, path)` and `list_tree(tree_sha)` read without a checkout; `list_tree` reports blob sizes and marks symbolic links with kind `link`, which item 7 of the checks uses.
- `export_tree(tree_sha, dest)` extracts a tree with `git archive` into a temporary directory; this is where the validator and gitleaks run, and where pin-style exports come from. Extraction uses the tar `data` filter so archive entries cannot escape the destination.

## History: retired names and past versions

- `deleted_skill_names(commit)` walks `git log --diff-filter=D` for `skills/*/SKILL.md` to find every name that was ever retired. It first checks `rev-parse --is-shallow-repository`; on a shallow clone it raises `ContentError` rather than returning an empty set, because a partial history would silently allow a retired name to be reused.
- `resolve_version(name, tree_sha, head)` walks the commits that touched `skills/<name>` from `head` backwards and returns the first whose `skills/<name>` tree equals `tree_sha`. This is how `load_skill(id, sha=…)` serves an old version: the `sha` a harness pinned is a tree hash, and the commit that carried it is recovered from history.
- `is_ancestor(a, b)` wraps `git merge-base --is-ancestor`. Exit 0 and 1 are answers; any other exit (missing object, corruption) raises `ContentError` so that a damaged clone is never mistaken for a rewind.

## Failure behaviour

| Condition | Result |
|---|---|
| Remote unreachable, key rejected | `ContentError(repo_unreachable)` with git stderr; the catalog stays on its previous snapshot |
| Remote has no `main` (empty repository) | `ContentError(no_main_branch)` |
| Shallow clone when history is needed | `ContentError(repo_unreachable, "shallow clone…")`; the CLI exits 2 |
| `merge-base` cannot answer | `ContentError` rather than a false "rewound" verdict |
| Requested version not in history | `resolve_version` returns `None`, surfaced by the app as `unknown_version` |

## Tests

`tests/adapters/test_git.py` builds a real repository in a temporary directory and covers fetch/list/read/export, history and version resolution, and the unreachable and no-main cases; `tests/adapters/test_git_history.py` proves the shallow-clone fail-closed path both at the adapter and through the CLI (exit code 2 with "shallow" in the output).

## Related

- [Catalog app](catalog-app.md) — how fetch results, ancestor checks and version resolution are used
- [Deployment](../operations/deployment.md) — where the deploy key comes from and how the quickstart mounts a seeded bare repository
