---
type: architecture
title: Archive download — get_skill_archive, the signed token and the tar route
description: How a whole skill version reaches a consumer without passing through the model. The fifth MCP tool returns a download descriptor (uri, header token, size, sha256); the route /mcp/archive/<id>/<tree>.tar verifies a five-minute HMAC token and serves a cached, byte-deterministic tar; how the cache is built, validated, evicted, and how pin-skill consumes it.
tags: [architecture, mcp, download, security, cache]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-10T16:35:35.587Z
sources:
  - id: openwiki-source-ca9eabc24825e6ff0edc2967
    resource: repo://DESIGN.md
  - id: openwiki-source-e38edc0a0c8956c81d346427
    resource: repo://packages/cli/src/harness_catalog_cli/templates/skills/pin-skill/SKILL.md
  - id: openwiki-source-849176cfe2a21dc2733885fb
    resource: repo://packages/core/src/harness_catalog_core/adapters/git.py
  - id: openwiki-source-1884c12f086a87c542e8ca3d
    resource: repo://packages/core/src/harness_catalog_core/archive_token.py
  - id: openwiki-source-c0344b993152580b36b61511
    resource: repo://packages/core/src/harness_catalog_core/authz.py
  - id: openwiki-source-85a76422b73202924b7addfe
    resource: repo://packages/core/src/harness_catalog_core/catalog.py
  - id: openwiki-source-1f1c56c0a37e25e90d4d34d5
    resource: repo://packages/server/src/harness_catalog_server/bootstrap.py
  - id: openwiki-source-480437ca124a00d81b6ec34c
    resource: repo://packages/server/src/harness_catalog_server/driving/archive_route.py
  - id: openwiki-source-836ee40979dc18fe52db3779
    resource: repo://packages/server/src/harness_catalog_server/driving/mcp_tools.py
  - id: openwiki-source-4599c74d95f98ca664b58c4a
    resource: repo://packages/server/src/harness_catalog_server/driving/scheduler.py
  - id: openwiki-source-6ef6c6646b1605cce25a7f69
    resource: repo://tests/adapters/test_git.py
  - id: openwiki-source-373cc192d3e934375abc9e1f
    resource: repo://tests/core/test_archive.py
  - id: openwiki-source-64993ac7d19db2729fe1e640
    resource: repo://tests/http/test_server.py
generated: { by: "claude-code", at: "2026-10-10T16:35:35.587Z" }
---

# Archive download

Until 2026-10-11 the only way to copy a skill directory to a consumer's machine was `load_skill` plus one `get_skill_file` call per file, with the agent writing each file itself. Every byte therefore crossed the model twice (as a tool result and again as the argument of a write call), and a fifteen-file skill took about thirty model turns. The decision recorded in `DESIGN.md` §11 (2026-10-11) replaces that with the pattern every comparable system uses (Databricks UC `ug skills add`, Codex `skill-installer`, Vercel `npx skills`, Claude Code plugin sources, Anthropic's Skills API zip endpoint, and the MCP community's "presigned URL" guidance that SEP-2631 is standardizing): the registry hands out a **download descriptor**, and the agent's shell fetches the bytes out of band.

The feature is split across the usual layers:

| Layer | Piece | Responsibility |
|---|---|---|
| core | `archive_token.ArchiveSigner` | mint and verify the HMAC token |
| core | `Catalog.get_skill_archive`, `Catalog.evict_archives` | build/validate/reuse the cached tar, describe it, age it out |
| core port + git adapter | `ContentStore.archive_skill` / `GitStore.archive_skill` | produce one deterministic tar from a commit |
| server | tool `get_skill_archive` in `ToolBindings` | authorize, mint, return the descriptor |
| server | route `GET /mcp/archive/{name}/{tree}.tar` | verify the header token, serve the cache file |
| server | bootstrap and scheduler | process-lifetime key, startup wipe, periodic eviction |

## The descriptor

`get_skill_archive(id, sha?)` is authorized exactly like the other read tools — `READ_TOOLS` in `authz.py` now lists five names, and the `harness-readers` group rule is unchanged. The tool resolves the version with the same `_resolve` used by `load_skill` (so `sha` omitted means the current `main` version and an unknown `sha` is `unknown_version`), asks the app for the archive, mints a token and returns:

```json
{"id": "...", "sha": "<tree>", "commit": "...",
 "uri": "<public_url>/archive/<id>/<tree>.tar", "method": "GET",
 "headers": {"X-Harness-Archive-Token": "v1.<exp>.<sig>"},
 "expires_at": "...", "mimeType": "application/x-tar",
 "size": 12345, "sha256": "...", "digest": "git-tree:<tree>"}
```

The shape follows SEP-2631's download descriptor (uri, mimeType, size, digest, expiry) so a later move to the protocol-native `files/authorizeDownload` is a rename, not a redesign. Only this one line enters the model's context; the bytes never do.

Because `public_url` ends in `/mcp` (that is what the proxy exposes and what the token audience is), the URI is `.../mcp/archive/...` and the route is registered at that path — the `tailscale serve --set-path /mcp` mapping passes sub-paths through, so no proxy change was needed (verified on the production host). The route is a plain Starlette `Route` placed **before** `Mount("/", mcp_app)`; if it were after, the MCP app would answer every `/mcp/...` request with its 401 challenge.

## The token

`ArchiveSigner` holds a key of at least 32 bytes and a TTL (default 300 s). `mint(name, tree)` returns `v1.<exp>.<base64url(HMAC-SHA256(key, "v1:<name>:<tree>:<exp>"))>` where `exp` is a Unix time; `verify(name, tree, token)` checks, in order, the canonical forms of name and tree, the exact token grammar, the expiry window `now < exp ≤ now + ttl + 60` (so a token with a far-future `exp` is rejected even if its signature is valid), and finally the signature with `hmac.compare_digest`. Every failure is the same `False`; the route turns it into an **empty 403** with no `WWW-Authenticate` header, so an attacker cannot tell a bad signature from an unknown tree.

Three consequences of the design, each traceable to the sources consulted when it was made:

- **The credential travels in a header, not in the URL.** RFC 9110 §17.9 says URIs are made to be shared and are logged by servers, proxies and user agents; the first design review found that uvicorn's default access log and the proxy would have recorded a query-string signature. The URL now contains only the skill name and the tree SHA.
- **The expiry is inside the signed payload.** Taken from the webhook-signature discipline (timestamp inside the HMAC prevents extending the window); replay inside the window is allowed because the download is an idempotent read.
- **The key lives only in the process.** `bootstrap` creates it with `secrets.token_bytes(32)` and never persists it: no new setting (the "six settings" rule holds), and a restart is a rotation. The documented trade-off is a single-replica assumption — two replicas would mint tokens the other cannot verify — and that every token dies on restart, which pin-skill handles by re-requesting the descriptor once on a 403.

## Building the tar deterministically

`GitStore.archive_skill(commit, name, dest, max_bytes)` runs `git archive --format=tar --mtime=@<commit time> --end-of-options <commit>:skills/<name>` with `-c tar.umask=0022 -c core.attributesfile=/dev/null`. The `--mtime` flag (git ≥ 2.42; the image ships 2.47) is what makes the output reproducible: the code review measured that archiving the bare tree-ish `<commit>:skills/<name>` stamps entries with the *generation* time, so two archives of the same version two seconds apart had different SHA-256s. Pinning the mtime to the commit time, the umask and the attributes file removes every environment-dependent byte, which is why the descriptor's `sha256` stays valid even if the cache is rebuilt later.

The adapter streams stdout to a `mkstemp` file in the destination directory while counting bytes; exceeding `max_bytes` kills the child and raises `ArchiveTooLarge`, stderr goes to a temporary file rather than a pipe (no deadlock when git is chatty), any exceptional exit kills and reaps the child, and only a complete file is `os.replace`d into place. The adapter test archives the same version twice and asserts identical hashes and that every member's mtime equals the commit time.

## The cache and its lifetime

`Catalog.get_skill_archive` keeps `workdir/archives/<tree>.tar` plus a sidecar `<tree>.tar.sha256` whose first token is the cache format version (`v2`). Under a dedicated `_archive_lock` it either reuses the cache — only if the file and sidecar exist, the size is within `Limits.archive_bytes` (20 MB), the sidecar's version matches and the recomputed SHA-256 matches — or rebuilds it and rewrites the sidecar. Every issue touches the file's mtime, so the mtime is "time of last descriptor".

Eviction is time-based and never happens in the request path. `evict_archives()` deletes files whose mtime is older than `ARCHIVE_RETENTION_SECONDS` (TTL + leeway + 60 s = 7 minutes): after that no token for the file can still verify, so deleting it cannot strand a valid download, and a straggler would simply trigger a byte-identical rebuild. The scheduler calls it at the top of every fetch tick (every `HC__FETCH_INTERVAL_SECONDS`, 60 s by default), and `bootstrap` calls it with retention 0 right after creating the signer, since the new key already invalidated every outstanding token. The scan happens outside the lock; only the recheck-and-unlink of each candidate is serialized against issuance. Disk usage is therefore bounded by "distinct versions requested in the last seven minutes × ≤ 20 MB", and the registry's `clone` volume does not accumulate archives across restarts.

## Serving

The route reads `name` and `tree` from the path, verifies the header, then asks the app for the archive in a worker thread; `not_found`/`unknown_version` become 404, `input_limit` 413, and any other `CatalogError` is re-raised so an unexpected code surfaces as a 500 instead of a misleading 404. The response is a `FileResponse` (exact `Content-Length`, nothing held in memory) with `Cache-Control: private, no-store` and the tar's SHA-256 echoed in `X-Harness-Archive-Sha256`.

## How pin-skill uses it

Steps 5–7 of `pin-skill/SKILL.md` are now: `load_skill` for the version and file list; `get_skill_archive(name, sha)` for the descriptor; in the shell, `curl -fsS -H "X-Harness-Archive-Token: ..." -o <tmp>.tar "<uri>"`, compare size and SHA-256 with the descriptor, then `tar -xf` into the temporary directory; finally compare the extracted file set with the `load_skill` list before writing `PINNED` and renaming atomically. The SHA-256 guards the transfer, the file-set comparison guards the version, and a 403 is retried once with a fresh descriptor. `get_skill_file` remains for the loop's single-file reads.

## Tests

- `tests/core/test_archive_token.py`: mint/verify inside the window, rejection of tampering, other target, expiry extension, far-future expiry, malformed tokens, non-canonical names, and a different key (restart).
- `tests/core/test_archive.py`: cache reuse with sidecar, rebuild on corrupt or oversized cache or old format version, eight concurrent issues agreeing with the served bytes, eviction by last-issue time and retention 0.
- `tests/adapters/test_git.py`: byte-identical archives, member mtimes equal to the commit time, cap, bad name, bad commit, no temp leftovers.
- `tests/http/test_server.py`: against a real uvicorn and fake issuer — descriptor, download with only the header, file set equal to `load_skill.files`, size/sha256/headers, empty 403 for no token, tampered token and another tree, replay within TTL allowed, `not_a_member`, `unknown_version`.

## Related

- [MCP server](mcp-server.md) — the other four tools and the shared error vocabulary
- [Catalog app](catalog-app.md) — `_resolve`, limits, the snapshot the tool reads
- [GitStore](git-content-store.md) — the git adapter the archive is produced by
- [Scheduler and operational surface](scheduler-and-ops.md) — the tick that evicts
- [Skill lifecycle](../workflows/skill-lifecycle.md) — pinning from the consumer's side
- [Authentication and authorization](auth.md) — why this route is the one surface without a bearer token
