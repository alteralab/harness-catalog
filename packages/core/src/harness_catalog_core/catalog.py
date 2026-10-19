"""카탈로그: 조립과 읽기. 목록·검색·본문·파일·도구·tar 명세를 돌려준다. git도 DB도 모른다(포트만).

재구축 상태 기계와 벡터 캐시는 `indexing.py`, tar 발급·캐시·퇴거는 `archives.py` 로 떼었다(DESIGN §11 2026-10-20 "코드 정리") —
공개 메서드와 그 뜻은 그대로다. 읽기 경로는 잠금을 잡지 않는다: `_ready_live()` 가 `Indexer.live` 한 참조(스냅샷 + 검색 색인 둘)를 읽고,
그 참조는 재구축이 자기 잠금 안에서 통째로 바꾼다.
"""

from __future__ import annotations

import base64
import json
from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple, TypeVar, cast

from .archive_token import KINDS
from .archives import ARCHIVE_RETENTION_SECONDS, MAX_ARCHIVE_BYTES, ArchiveCache
from .indexing import Indexer, inspect_tree
from .model import (
    CatalogError,
    ErrorCode,
    FileContent,
    ListResult,
    SkillBody,
    SkillEntry,
    SkillFile,
    SkillListing,
    Status,
    ToolBody,
    ToolEntry,
    ToolListing,
    ToolListResult,
)
from .toolbox import SERVER_FILE, TOOL_FILE

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from .archive_token import ArchiveKind
    from .model import ArchiveInfo, IndexSnapshot
    from .ports import ContentStore, Embedder, FactStore, SkillValidator
    from .search import SearchIndex

MAX_QUERY_CHARS = 2000
MAX_NAME_CHARS = 64
MAX_PATH_CHARS = 1024
MAX_FILE_BYTES = 1_000_000
DEFAULT_LIMIT = 10
MAX_LIMIT = 20
# 레코드 종류의 단수 이름(오류 문구) — 스킬·도구는 뿌리 이름만 다르다
RECORD_WORD: Mapping[str, str] = MappingProxyType({"skills": "skill", "tools": "tool"})

_Record = TypeVar("_Record", SkillEntry, ToolEntry)


class Limits(NamedTuple):
    query_chars: int = MAX_QUERY_CHARS
    file_bytes: int = MAX_FILE_BYTES
    max_limit: int = MAX_LIMIT
    archive_bytes: int = MAX_ARCHIVE_BYTES


class Catalog:
    """앱. 메서드는 동기이고 호출자가 스레드로 감싼다. 스냅샷 참조 교체가 유일한 상태 변경이다."""

    def __init__(self, store: ContentStore, validator: SkillValidator, facts: FactStore, *, workdir: Path, limits: Limits = Limits(), embedder: Embedder | None = None) -> None:
        self._store = store
        self._validator = validator
        self._embedder = embedder  # None 이면 BM25 만(§11 2026-10-19 검색 0.8.0)
        self._workdir = workdir
        self._limits = limits
        self._index = Indexer(store, validator, facts, workdir=workdir, embedder=embedder)  # 재구축 상태 기계 + 벡터 캐시(indexing.py)
        self._archives = ArchiveCache(store, workdir=workdir, max_bytes=limits.archive_bytes)  # tar 발급·캐시·퇴거(archives.py)

    # ---- For operating ----
    def status(self) -> Status:
        return self._index.status()

    # ---- For maintaining the catalog ----
    def rebuild(self, *, accept_rewind: bool = False) -> Status:
        """한 주기의 재구축. 돌려주는 상태는 status() 와 같은 것(임베딩 사유 포함)."""
        self._index.rebuild(accept_rewind=accept_rewind)
        return self.status()

    # ---- For consuming skills ----
    def _ready_snapshot(self) -> IndexSnapshot:
        snap = self._index.snapshot
        if snap is None:
            raise CatalogError(ErrorCode.NOT_FOUND, "index not built yet")
        return snap

    def _limit(self, query: str, limit: int | None) -> int:
        if len(query) > self._limits.query_chars:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"query longer than {self._limits.query_chars} chars")
        n = DEFAULT_LIMIT if limit is None else limit
        if n < 1 or n > self._limits.max_limit:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"limit must be 1..{self._limits.max_limit}")
        return n

    def _ready_live(self) -> tuple[IndexSnapshot, dict[str, SearchIndex]]:
        """스냅샷과 검색 색인 둘을 **한 참조로** 읽는다 — 잠금 없이, 재구축이 통째로 바꾼 그 참조 하나를."""
        live = self._index.live
        if live is None:
            raise CatalogError(ErrorCode.NOT_FOUND, "index not built yet")
        return live

    def _ranked(self, query: str, n: int, index: SearchIndex | None) -> tuple[str, ...]:
        """메모리 색인의 순위(§11 2026-10-19 검색 0.8.0): 벡터가 있고 임베딩 서비스가 답하면 BM25 + dense 볼록 결합, 아니면 BM25 만.
        질의 임베딩이 실패하면 그 호출은 BM25 로 깎고 상태에 embedding_unavailable 을 올린다(돌아오면 내린다; 색인·세대는 그대로)."""
        if index is None:
            return ()
        qv: list[float] | None = None
        if index.dense and self._embedder is not None:
            got = self._embedder.embed([query])
            qv = got[0] if got else None
            self._index.embedding_ok = qv is not None
        return index.search(query, qv, n)

    def _hits(self, query: str, limit: int | None, index: SearchIndex | None, records: Sequence[_Record]) -> tuple[_Record, ...]:
        """한도 검사 → 순위 → 그 이름의 항목. 스킬·도구는 넘기는 색인과 항목 종류만 다르다 — 이름만 다른 쌍이라 한 함수로 접었다(§11 2026-10-20)."""
        n = self._limit(query, limit)
        by_name = {r.name: r for r in records}
        return tuple(by_name[name] for name in self._ranked(query, n, index) if name in by_name)[:n]

    def search_skills(self, query: str, limit: int | None = None) -> ListResult:
        snap, indexes = self._ready_live()
        hits = self._hits(query, limit, indexes.get("skills"), snap.entries)
        return ListResult(tuple(SkillListing.of(e) for e in hits), snap.fetched_at)

    def _version(self, root: ArchiveKind, name: str, current_tree: str, current_commit: str, sha: str | None) -> tuple[str, str]:
        """(읽을 tree, 그 판의 커밋). sha가 없거나 현재 판이면 현재, 아니면 이력에서 찾는다(D6)."""
        if sha is None or sha == current_tree:
            return current_tree, current_commit
        commit = self._store.resolve_version(name, sha, self._ready_snapshot().commit_sha, root)
        if commit is None:
            raise CatalogError(ErrorCode.UNKNOWN_VERSION, f"{name!r} has no version {sha}")
        return sha, commit

    @staticmethod
    def _check_name(name: str) -> None:
        if len(name) > MAX_NAME_CHARS or not name:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"name must be 1..{MAX_NAME_CHARS} chars")

    def _resolve(self, root: ArchiveKind, name: str, sha: str | None) -> tuple[SkillEntry | ToolEntry, str, str]:
        """(현재 항목, 읽을 tree, 그 판의 커밋). 스킬·도구는 찾는 뿌리와 오류 문구의 낱말만 달라 한 함수로 접었다(§11 2026-10-20)."""
        self._check_name(name)
        snap = self._ready_snapshot()
        entry = snap.get(name) if root == "skills" else snap.get_tool(name)
        if entry is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{RECORD_WORD[root]} {name!r} not found")
        tree, commit = self._version(root, name, entry.tree_sha, entry.commit_sha, sha)
        return entry, tree, commit

    def get_skill(self, name: str, sha: str | None = None) -> SkillBody:
        """SKILL.md 본문과 파일 목록(§11 2026-10-18: load_skill → get_skill. 파일 하나는 get_skill_file, tar 명세는 get_skill_archive가 같은 도구의 path·archive 분기)."""
        entry, tree, commit = self._resolve("skills", name, sha)
        body = self._store.read_blob(tree, "SKILL.md")
        if body is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: SKILL.md missing in {tree}")
        files = tuple(SkillFile(e.path, e.size) for e in self._store.list_tree(tree) if e.kind != "tree")
        metadata: Mapping[str, str] = entry.metadata
        if tree != entry.tree_sha:
            props = inspect_tree(self._store, self._validator, tree, name, self._workdir).properties
            metadata = props.metadata if props is not None else MappingProxyType({})
        return SkillBody(name, body.decode("utf-8", errors="replace"), tree, commit, metadata, files, self._ready_snapshot().fetched_at)

    # ---- For consuming tools (toolbox, DESIGN §11 2026-10-11) ----
    def search_tools(self, query: str, limit: int | None = None) -> ToolListResult:
        snap, indexes = self._ready_live()
        hits = self._hits(query, limit, indexes.get("tools"), snap.tools)
        return ToolListResult(tuple(ToolListing.of(t) for t in hits), snap.fetched_at)

    def get_tool(self, name: str, sha: str | None = None) -> ToolBody:
        """tool.json 전체와 판·커밋·파일 목록. kind=mcp면 그 커밋의 server.json을 함께(레지스트리는 발견까지 — 서버를 부르지 않는다)."""
        _, tree, commit = self._resolve("tools", name, sha)
        spec = self._tool_spec(name, tree)
        files = tuple(SkillFile(e.path, e.size) for e in self._store.list_tree(tree) if e.kind != "tree")
        return ToolBody(name, MappingProxyType(spec), tree, commit, files, self._server_record(commit, spec), self._ready_snapshot().fetched_at)

    def _tool_spec(self, name: str, tree: str) -> dict[str, object]:
        """그 판의 tool.json 을 객체로. 검사 11이 거부했어야 하는 모양(없음·JSON 아님·객체 아님)은 not_found 로 막는다 — 방어."""
        raw = self._store.read_blob(tree, TOOL_FILE)
        if raw is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: {TOOL_FILE} missing in {tree}")
        try:
            loaded: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: {TOOL_FILE} in {tree} is not valid JSON ({e})") from e
        if not isinstance(loaded, dict):
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: {TOOL_FILE} in {tree} is not an object")
        return cast("dict[str, object]", loaded)

    def _server_record(self, commit: str, spec: Mapping[str, object]) -> Mapping[str, object] | None:
        """kind=mcp가 참조하는 그 커밋의 server.json. 아니거나 읽히지 않으면 None — 발견은 tool.json 만으로도 된다."""
        runtime = spec.get("runtime")
        if not isinstance(runtime, dict):
            return None
        rt = cast("Mapping[str, object]", runtime)
        server_name = rt.get("server")
        if rt.get("kind") != "mcp" or not isinstance(server_name, str) or not server_name:
            return None
        raw = self._store.read_blob(commit, f"mcp-servers/{server_name}/{SERVER_FILE}")
        if raw is None:
            return None
        try:
            loaded: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return MappingProxyType(cast("dict[str, object]", loaded)) if isinstance(loaded, dict) else None

    # ---- Archives (skills and script tools) ----
    def get_skill_archive(self, name: str, sha: str | None = None) -> ArchiveInfo:
        return self.get_archive("skills", name, sha)

    def get_tool_archive(self, name: str, sha: str | None = None) -> ArchiveInfo:
        return self.get_archive("tools", name, sha)

    def get_archive(self, kind: ArchiveKind, name: str, sha: str | None = None) -> ArchiveInfo:
        """한 판의 tar 명세. 이름→판을 풀어 캐시(archives.py)에 발급을 맡긴다 — 인증·서명·전송은 서버 어댑터의 몫."""
        if kind not in KINDS:
            raise CatalogError(ErrorCode.NOT_FOUND, f"unknown archive kind {kind!r}")
        entry, tree, commit = self._resolve(kind, name, sha)
        return self._archives.issue(kind, entry.name, tree, commit)

    def evict_archives(self, *, now: float | None = None, retention_seconds: int = ARCHIVE_RETENTION_SECONDS) -> int:
        """마지막 발급 뒤 보존 시간을 넘은 캐시 tar를 지운다(스케줄러가 주기마다, 기동 때는 retention 0으로 전부). 지운 파일 수."""
        return self._archives.evict(now=now, retention_seconds=retention_seconds)

    def get_skill_file(self, name: str, path: str, sha: str | None = None) -> FileContent:
        _, tree, _ = self._resolve("skills", name, sha)
        self._check_path(path)
        entry = next((e for e in self._store.list_tree(tree) if e.path == path), None)
        if entry is None or entry.kind == "tree":
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: file {path!r} not found")
        if entry.kind == "link":
            raise CatalogError(ErrorCode.PATH_REJECTED, f"{path!r} is a symbolic link")
        if entry.size > self._limits.file_bytes:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"{path!r} is {entry.size} bytes > {self._limits.file_bytes}")
        data = self._store.read_blob(tree, path)
        if data is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: file {path!r} not found")
        try:
            return FileContent(path, entry.size, tree, entry.sha, data.decode("utf-8"), None)
        except UnicodeDecodeError:
            return FileContent(path, entry.size, tree, entry.sha, None, base64.b64encode(data).decode("ascii"))

    @staticmethod
    def _check_path(path: str) -> None:
        if not path or len(path) > MAX_PATH_CHARS:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"path must be 1..{MAX_PATH_CHARS} chars")
        parts = path.split("/")
        if path.startswith("/") or "\\" in path or "\0" in path or any(p in ("", ".", "..") for p in parts):
            raise CatalogError(ErrorCode.PATH_REJECTED, f"path {path!r} rejected")
