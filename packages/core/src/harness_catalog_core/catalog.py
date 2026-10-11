"""카탈로그: main을 검사해 인덱스를 짓고, 목록·검색·본문·파일·도구를 돌려준다. git도 DB도 모른다(포트만)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple, cast

from .archive_token import DEFAULT_TTL_SECONDS, KINDS, LEEWAY_SECONDS, ArchiveKind
from .catalog_file import MARKER_PATH, MarkerError, parse_marker
from .check import check_commit, structure_findings
from .model import (
    ArchiveInfo,
    ArchiveTooLarge,
    SUPPORTED_LAYOUT,
    CatalogError,
    ContentError,
    ErrorCode,
    FileContent,
    IndexOutcome,
    IndexSnapshot,
    ListResult,
    ReadyReason,
    SkillBody,
    SkillEntry,
    SkillFile,
    SkillListing,
    SkillReport,
    Status,
    ToolBody,
    ToolEntry,
    ToolListing,
    ToolListResult,
)
from .ports import ContentStore, FactStore, SkillValidator
from .toolbox import SERVER_FILE, TOOL_FILE, parse_tool

MAX_QUERY_CHARS = 2000
MAX_NAME_CHARS = 64
MAX_PATH_CHARS = 1024
MAX_FILE_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 20_000_000  # 한 판의 tar 상한(실제 바이트). 넘으면 input_limit
# 캐시 tar 보존: 토큰 수명 + 검증 여유 + 60초. 그 뒤로는 어떤 토큰도 유효하지 않으므로 지워도 안전하다(필요하면 같은 바이트로 다시 만든다)
ARCHIVE_RETENTION_SECONDS = DEFAULT_TTL_SECONDS + LEEWAY_SECONDS + 60
# 캐시 사이드카의 형식 판. 생성 규칙(mtime·umask·속성 고정)이나 캐시 경로 규칙이 바뀌면 올린다 — 옛 규칙으로 만든 캐시는 적중하지 않는다
ARCHIVE_FORMAT_VERSION = "v3"
DEFAULT_LIMIT = 10
MAX_LIMIT = 20


class Limits(NamedTuple):
    query_chars: int = MAX_QUERY_CHARS
    file_bytes: int = MAX_FILE_BYTES
    max_limit: int = MAX_LIMIT
    archive_bytes: int = MAX_ARCHIVE_BYTES


def _now() -> datetime:
    return datetime.now(UTC)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return float("inf")


def _size_and_sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 16):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


class Catalog:
    """앱. 메서드는 동기이고 호출자가 스레드로 감싼다. 스냅샷 참조 교체가 유일한 상태 변경이다."""

    def __init__(self, store: ContentStore, validator: SkillValidator, facts: FactStore, *, workdir: Path, limits: Limits = Limits()) -> None:
        self._store = store
        self._validator = validator
        self._facts = facts
        self._workdir = workdir
        self._limits = limits
        self._snapshot: IndexSnapshot | None = None
        self._status = Status(ready=False)
        self._db_synced = False  # 마지막 스냅샷이 사실 저장소에도 반영됐는가 — 검색 순위를 DB에 맡기는 조건
        self._lock = threading.Lock()
        self._archive_lock = threading.Lock()  # 캐시 tar의 확인·생성·해시를 직렬화한다(동시 발급이 서로의 명세를 깨지 않게)

    # ---- For operating ----
    def status(self) -> Status:
        return self._status

    # ---- For maintaining the catalog ----
    def rebuild(self, *, accept_rewind: bool = False) -> Status:
        """fetch → 구조 검사 → 세대 검사 → 검사 열 → 스냅샷 교체. 구조가 깨지면 이전 스냅샷을 유지하고 unready.

        뒤로 가지 않는다: 새 커밋이 이전 커밋의 자손이 아니면(main 되감기) 아무것도 바꾸지 않고 degraded에 main_rewound.
        accept_rewind=True(운영 명령)면 그 검사를 건너뛴다.
        """
        with self._lock:
            try:
                commit = self._store.fetch()
            except ContentError as e:
                # 사유의 원문은 degraded에 남긴다(운영자가 /readyz만 보고도 git 오류를 읽게)
                detail = (f"{e.reason}:{e.detail[:300]}",)
                self._status = Status(ready=self._snapshot is not None, reasons=(e.reason,), degraded=detail + tuple(d for d in self._status.degraded if not d.startswith(("repo_unreachable:", "no_main_branch:"))),
                                      commit_sha=self._status.commit_sha, fetched_at=self._status.fetched_at, built_at=self._status.built_at)
                return self._status
            fetched_at = _now()
            reasons, details = self._structure_reasons(commit)
            if reasons:
                # 저장소 구조가 깨졌다: 빌드 전체가 실패하고 /readyz는 503 (이전 스냅샷은 들고 있되 준비됨은 아니다)
                self._status = Status(ready=False, reasons=reasons, degraded=details, commit_sha=commit, fetched_at=fetched_at)
                return self._status
            if self._snapshot is not None and self._snapshot.commit_sha == commit:
                return self._resync(commit, fetched_at, accept_rewind)
            base = self._snapshot.commit_sha if self._snapshot else self._facts.current_commit()
            if base is not None and not accept_rewind and not self._store.is_ancestor(base, commit):
                return self._rewound(base, fetched_at)
            if accept_rewind:
                base = None  # 되감기를 받아들이면 옛 기준 커밋은 이력에 없을 수 있다 — 항목 5·9는 이번 빌드에서 건너뛴다
            try:
                return self._build(commit, base, fetched_at, accept_rewind, write_facts=True)
            except Exception as e:  # noqa: BLE001 — 장기 실행 루프: 어느 예외든 인덱스는 이전 판으로 남고 다음 주기에 다시 시도한다(상태에 기록)
                # 빌드 실패: 인덱스는 이전 판으로 남고 다음 주기에 다시 시도한다
                self._status = Status(ready=self._snapshot is not None, degraded=(f"rebuild_failed:{e}",),
                                      commit_sha=self._status.commit_sha, fetched_at=fetched_at, built_at=self._status.built_at)
                return self._status

    def _resync(self, commit: str, fetched_at: datetime, accept_rewind: bool) -> Status:
        """같은 커밋: 빌드는 건너뛰되, 지난번 DB 반영이 실패했으면 그 스냅샷으로 다시 시도한다."""
        snap = self._snapshot
        assert snap is not None
        degraded = tuple(d for d in self._status.degraded if d not in ("db_unavailable", "main_rewound"))
        if not self._db_synced:
            outcome = self._facts.replace_index(snap, lambda stored: accept_rewind or self._store.is_ancestor(stored, commit))
            self._db_synced = outcome is IndexOutcome.REPLACED
            if outcome is IndexOutcome.UNAVAILABLE:
                degraded += ("db_unavailable",)
            elif outcome is IndexOutcome.STALE:
                # DB가 더 앞서 있다(또는 이 메모리 판이 되감긴 판이다): 숨기지 않고 적는다
                degraded += ("main_rewound",)
        self._status = Status(ready=True, degraded=degraded, commit_sha=commit, fetched_at=fetched_at, built_at=snap.built_at, rejected=snap.rejected)
        return self._status

    def _rewound(self, base: str, fetched_at: datetime) -> Status:
        """main이 base의 자손이 아니다: 아무것도 앞으로 가지 않는다. 메모리가 비어 있으면(재기동) base 세대를 git에서 다시 지어 읽기를 잇는다."""
        if self._snapshot is None:
            try:
                self._build(base, None, fetched_at, accept_rewind=True, write_facts=False)  # DB에는 이미 base 세대가 있다
            except Exception as e:  # noqa: BLE001 — base 세대를 못 지으면 unready로 남고 사유만 적는다
                self._status = Status(ready=False, degraded=("main_rewound", f"rebuild_failed:{e}"), commit_sha=None, fetched_at=fetched_at)
                return self._status
        snap = self._snapshot
        self._status = Status(ready=snap is not None, degraded=("main_rewound",), commit_sha=base, fetched_at=fetched_at,
                              built_at=snap.built_at if snap else None, rejected=snap.rejected if snap else ())
        return self._status

    def _build(self, commit: str, base: str | None, fetched_at: datetime, accept_rewind: bool, *, write_facts: bool) -> Status:
        report = check_commit(self._store, self._validator, commit, base=base, workdir=self._workdir)
        if report.checker_failed:
            self._status = Status(ready=self._snapshot is not None, degraded=(f"checker_failed:{report.checker_failed}",),
                                  commit_sha=self._status.commit_sha, fetched_at=fetched_at, built_at=self._status.built_at)
            return self._status
        rejected_names = report.rejected_skills()
        entries: list[SkillEntry] = []
        for tree in self._store.list_trees(commit, "skills"):
            if tree.name in rejected_names:
                continue
            props = self._inspect_tree(tree.tree_sha, tree.name).properties
            if props is None:
                continue
            entries.append(SkillEntry(tree.name, props.description, props.compatibility, props.metadata, tree.tree_sha, tree.commit_sha))
        rejected_tools = report.rejected_tools()
        tools: list[ToolEntry] = []
        for tree in self._store.list_trees(commit, "tools"):
            if tree.name in rejected_tools:
                continue
            raw = self._store.read_blob(tree.tree_sha, TOOL_FILE)
            spec, _ = parse_tool(raw) if raw is not None else (None, [])
            if spec is None:
                continue  # 검사 11이 거부했어야 하는 것 — 방어
            server = spec.runtime.server if spec.runtime.kind == "mcp" else None
            tools.append(ToolEntry(tree.name, spec.description, spec.runtime.kind, server, spec.metadata, tree.tree_sha, tree.commit_sha))
        rejected = tuple(sorted({(f.skill, f"{f.item}: {f.reason}") for f in report.errors if f.skill}))
        repo_findings: tuple[str, ...] = ()  # 저장소 수준 위반은 _structure_reasons가 먼저 잡아 빌드를 막는다
        snapshot = IndexSnapshot(tuple(sorted(entries, key=lambda e: e.name)), commit, _now(), fetched_at, rejected, tuple(sorted(tools, key=lambda t: t.name)))
        def is_descendant(stored: str) -> bool:
            return accept_rewind or self._store.is_ancestor(stored, commit)

        outcome = self._facts.replace_index(snapshot, is_descendant) if write_facts else IndexOutcome.REPLACED
        if outcome is IndexOutcome.STALE:
            # DB가 더 앞서 있거나 되감겼다: 메모리도 바꾸지 않는다(뒤로 가지 않는다)
            self._status = Status(ready=self._snapshot is not None, degraded=repo_findings + ("main_rewound",), commit_sha=self._status.commit_sha,
                                  fetched_at=fetched_at, built_at=self._status.built_at, rejected=self._status.rejected)
            return self._status
        self._snapshot = snapshot
        self._db_synced = outcome is IndexOutcome.REPLACED
        degraded = repo_findings + (("db_unavailable",) if outcome is IndexOutcome.UNAVAILABLE else ())
        self._status = Status(ready=True, degraded=degraded, commit_sha=commit, fetched_at=fetched_at, built_at=snapshot.built_at, rejected=rejected)
        return self._status

    def _structure_reasons(self, commit: str) -> tuple[tuple[ReadyReason, ...], tuple[str, ...]]:
        """표지 → 배치. 표지가 없거나 깨졌으면 not_a_catalog, layout 값이 다르면 unsupported_layout, 구조 항목(1·2·11·12) 위반은 layout_mismatch."""
        marker = self._store.read_blob(commit, MARKER_PATH)
        if marker is None:
            return (ReadyReason.NOT_A_CATALOG,), ()
        try:
            layout = parse_marker(marker.decode("utf-8", errors="replace")).layout
        except MarkerError as e:
            return (ReadyReason.NOT_A_CATALOG,), (f"marker: {e}",)
        if layout != SUPPORTED_LAYOUT:
            return (ReadyReason.UNSUPPORTED_LAYOUT,), ()
        violations = tuple(f"check:{f.item}:{f.reason}" for f in structure_findings(self._store, commit) if not f.warning)
        if violations:
            return (ReadyReason.LAYOUT_MISMATCH,), violations
        return (), ()

    def _inspect_tree(self, tree_sha: str, name: str) -> SkillReport:
        with tempfile.TemporaryDirectory(dir=self._workdir, prefix="read.") as tmp:
            dest = Path(tmp) / name  # 스펙 검증기가 디렉토리명 = name을 본다
            dest.mkdir()
            self._store.export_tree(tree_sha, dest)
            return self._validator.inspect(dest)

    # ---- For consuming skills ----
    def _ready_snapshot(self) -> IndexSnapshot:
        snap = self._snapshot
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

    def _ranked(self, query: str, n: int, kind: str) -> tuple[str, ...] | None:
        """DB 순위는 마지막 스냅샷이 DB에 반영됐을 때만 쓴다 — 아니면 복구된 DB의 구판 순위를 쓰게 된다(Codex 설계 리뷰 2026-10-11)."""
        return self._facts.search(query, n, kind) if self._db_synced else None

    def search_skills(self, query: str, limit: int | None = None) -> ListResult:
        snap = self._ready_snapshot()
        n = self._limit(query, limit)
        ranked = self._ranked(query, n, "skills")
        if ranked is not None:
            by_name = {e.name: e for e in snap.entries}
            hits = [by_name[name] for name in ranked if name in by_name]
        else:
            tokens = [t for t in query.lower().split() if t]
            hits = [e for e in snap.entries if all(t in e.search_text for t in tokens)] if tokens else []
        return ListResult(tuple(SkillListing.of(e) for e in hits[:n]), snap.fetched_at)

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

    def _resolve(self, name: str, sha: str | None) -> tuple[SkillEntry, str, str]:
        """(현재 스킬 항목, 읽을 tree, 그 판의 커밋)."""
        self._check_name(name)
        entry = self._ready_snapshot().get(name)
        if entry is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"skill {name!r} not found")
        tree, commit = self._version("skills", name, entry.tree_sha, entry.commit_sha, sha)
        return entry, tree, commit

    def _resolve_tool(self, name: str, sha: str | None) -> tuple[ToolEntry, str, str]:
        self._check_name(name)
        entry = self._ready_snapshot().get_tool(name)
        if entry is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"tool {name!r} not found")
        tree, commit = self._version("tools", name, entry.tree_sha, entry.commit_sha, sha)
        return entry, tree, commit

    def load_skill(self, name: str, sha: str | None = None) -> SkillBody:
        entry, tree, commit = self._resolve(name, sha)
        body = self._store.read_blob(tree, "SKILL.md")
        if body is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: SKILL.md missing in {tree}")
        files = tuple(SkillFile(e.path, e.size) for e in self._store.list_tree(tree) if e.kind != "tree")
        metadata: Mapping[str, str] = entry.metadata
        if tree != entry.tree_sha:
            props = self._inspect_tree(tree, name).properties
            metadata = props.metadata if props is not None else MappingProxyType({})
        return SkillBody(name, body.decode("utf-8", errors="replace"), tree, commit, metadata, files, self._ready_snapshot().fetched_at)

    # ---- For consuming tools (toolbox, DESIGN §11 2026-10-11) ----
    def search_tools(self, query: str, limit: int | None = None) -> ToolListResult:
        snap = self._ready_snapshot()
        n = self._limit(query, limit)
        ranked = self._ranked(query, n, "tools")
        if ranked is not None:
            by_name = {t.name: t for t in snap.tools}
            hits = [by_name[name] for name in ranked if name in by_name]
        else:
            tokens = [t for t in query.lower().split() if t]
            hits = [t for t in snap.tools if all(tok in t.search_text for tok in tokens)] if tokens else []
        return ToolListResult(tuple(ToolListing.of(t) for t in hits[:n]), snap.fetched_at)

    def get_tool(self, name: str, sha: str | None = None) -> ToolBody:
        """tool.json 전체와 판·커밋·파일 목록. kind=mcp면 그 커밋의 server.json을 함께(레지스트리는 발견까지 — 서버를 부르지 않는다)."""
        _, tree, commit = self._resolve_tool(name, sha)
        raw = self._store.read_blob(tree, TOOL_FILE)
        if raw is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: {TOOL_FILE} missing in {tree}")
        try:
            loaded: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: {TOOL_FILE} in {tree} is not valid JSON ({e})") from e
        if not isinstance(loaded, dict):
            raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: {TOOL_FILE} in {tree} is not an object")
        spec = cast("dict[str, object]", loaded)
        files = tuple(SkillFile(e.path, e.size) for e in self._store.list_tree(tree) if e.kind != "tree")
        server: Mapping[str, object] | None = None
        runtime = spec.get("runtime")
        if isinstance(runtime, dict):
            rt = cast("Mapping[str, object]", runtime)
            server_name = rt.get("server")
            if rt.get("kind") == "mcp" and isinstance(server_name, str) and server_name:
                raw_server = self._store.read_blob(commit, f"mcp-servers/{server_name}/{SERVER_FILE}")
                if raw_server is not None:
                    try:
                        loaded_server: object = json.loads(raw_server.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        loaded_server = None
                    if isinstance(loaded_server, dict):
                        server = MappingProxyType(cast("dict[str, object]", loaded_server))
        return ToolBody(name, MappingProxyType(spec), tree, commit, files, server, self._ready_snapshot().fetched_at)

    # ---- Archives (skills and script tools) ----
    def get_skill_archive(self, name: str, sha: str | None = None) -> ArchiveInfo:
        return self.get_archive("skills", name, sha)

    def get_tool_archive(self, name: str, sha: str | None = None) -> ArchiveInfo:
        return self.get_archive("tools", name, sha)

    def get_archive(self, kind: ArchiveKind, name: str, sha: str | None = None) -> ArchiveInfo:
        """한 판의 tar를 작업 디렉토리 캐시(`archives/<kind>/<tree>.<commit>.tar` + `.sha256` 사이드카)에 만들어(있고 온전하면 재사용) 경로·크기·sha256을 돌려준다.

        같은 커밋·트리는 언제 만들어도 같은 바이트(어댑터가 mtime을 커밋 시각으로 고정)라 캐시가 없어지면 다시 만들어도 명세의 sha256이 맞는다.
        캐시 키에 종류와 커밋이 들어가 스킬·도구나 같은 트리의 다른 커밋이 충돌하지 않는다(Codex 설계 리뷰 2026-10-11).
        발급마다 파일 mtime을 갱신해 evict_archives가 "마지막 발급 뒤 보존 시간" 기준으로 지운다. 인증·서명·전송은 서버 어댑터의 몫.
        """
        if kind not in KINDS:
            raise CatalogError(ErrorCode.NOT_FOUND, f"unknown archive kind {kind!r}")
        if kind == "skills":
            skill, tree, commit = self._resolve(name, sha)
            entry_name = skill.name
        else:
            tool, tree, commit = self._resolve_tool(name, sha)
            entry_name = tool.name
        archives = self._workdir / "archives" / kind
        dest = archives / f"{tree}.{commit}.tar"
        side = archives / f"{tree}.{commit}.tar.sha256"
        with self._archive_lock:
            info = self._cached_archive(kind, entry_name, tree, commit, dest, side)
            if info is None:
                try:
                    self._store.archive_tree(commit, kind, entry_name, dest, max_bytes=self._limits.archive_bytes)
                except ArchiveTooLarge as e:
                    raise CatalogError(ErrorCode.INPUT_LIMIT, f"{name!r} version {tree} is larger than {e.max_bytes} bytes as a tar") from e
                except ContentError as e:
                    raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: cannot archive {tree}: {e.detail}") from e
                size, digest = _size_and_sha256(dest)
                side.write_text(f"{ARCHIVE_FORMAT_VERSION} {digest}\n")
                info = ArchiveInfo(entry_name, tree, commit, dest, size, digest, kind)
            os.utime(dest, None)
            return info

    def _cached_archive(self, kind: str, name: str, tree: str, commit: str, dest: Path, side: Path) -> ArchiveInfo | None:
        """캐시 적중 조건: 파일과 사이드카가 있고, 크기가 상한 안이고, sha256이 사이드카와 같다. 아니면 None(다시 만든다)."""
        if not (dest.is_file() and side.is_file()):
            return None
        if dest.stat().st_size > self._limits.archive_bytes:
            return None
        try:
            version, _, recorded = side.read_text().strip().partition(" ")
        except OSError:
            return None
        if version != ARCHIVE_FORMAT_VERSION:
            return None
        size, digest = _size_and_sha256(dest)
        if digest != recorded:
            return None
        return ArchiveInfo(name, tree, commit, dest, size, digest, kind)

    def evict_archives(self, *, now: float | None = None, retention_seconds: int = ARCHIVE_RETENTION_SECONDS) -> int:
        """마지막 발급(mtime) 뒤 retention_seconds를 넘은 캐시 tar와 사이드카를 지운다(종류별 하위 디렉토리 전부). 스케줄러가 주기마다 부르고, 기동 때는 retention 0으로 전부 지운다. 지운 파일 수를 돌려준다."""
        archives = self._workdir / "archives"
        if not archives.is_dir():
            return 0
        cutoff = (time.time() if now is None else now) - retention_seconds
        removed = 0
        candidates = [tar for tar in archives.rglob("*.tar") if _mtime(tar) <= cutoff]  # 훑기는 lock 밖에서
        for tar in candidates:
            with self._archive_lock:  # 발급이 방금 mtime을 갱신했을 수 있으니 lock 안에서 다시 보고 지운다
                try:
                    if tar.stat().st_mtime <= cutoff:
                        tar.unlink()
                        Path(str(tar) + ".sha256").unlink(missing_ok=True)
                        removed += 1
                except OSError:
                    pass
        return removed

    def get_skill_file(self, name: str, path: str, sha: str | None = None) -> FileContent:
        _, tree, _ = self._resolve(name, sha)
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
