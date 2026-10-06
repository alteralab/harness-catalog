"""카탈로그: main을 검사해 인덱스를 짓고, 목록·검색·본문·파일을 돌려준다. git도 DB도 모른다(포트만)."""

from __future__ import annotations

import base64
import tempfile
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple

from .catalog_file import MARKER_PATH, MarkerError, parse_marker
from .check import check_commit, structure_findings
from .model import (
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
)
from .ports import ContentStore, FactStore, SkillValidator

MAX_QUERY_CHARS = 2000
MAX_NAME_CHARS = 64
MAX_PATH_CHARS = 1024
MAX_FILE_BYTES = 1_000_000
DEFAULT_LIMIT = 10
MAX_LIMIT = 20


class Limits(NamedTuple):
    query_chars: int = MAX_QUERY_CHARS
    file_bytes: int = MAX_FILE_BYTES
    max_limit: int = MAX_LIMIT


def _now() -> datetime:
    return datetime.now(UTC)


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
        self._lock = threading.Lock()

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
                self._status = Status(ready=self._snapshot is not None, reasons=(e.reason,), degraded=self._status.degraded,
                                      commit_sha=self._status.commit_sha, fetched_at=self._status.fetched_at, built_at=self._status.built_at)
                return self._status
            fetched_at = _now()
            reasons, details = self._structure_reasons(commit)
            if reasons:
                # 저장소 구조가 깨졌다: 빌드 전체가 실패하고 /readyz는 503 (이전 스냅샷은 들고 있되 준비됨은 아니다)
                self._status = Status(ready=False, reasons=reasons, degraded=details, commit_sha=commit, fetched_at=fetched_at)
                return self._status
            if self._snapshot is not None and self._snapshot.commit_sha == commit:
                self._status = Status(ready=True, degraded=self._status.degraded, commit_sha=commit, fetched_at=fetched_at,
                                      built_at=self._snapshot.built_at, rejected=self._snapshot.rejected)
                return self._status
            base = self._snapshot.commit_sha if self._snapshot else None
            if base is not None and not accept_rewind and not self._store.is_ancestor(base, commit):
                self._status = Status(ready=True, degraded=("main_rewound",), commit_sha=base, fetched_at=fetched_at, built_at=self._snapshot.built_at if self._snapshot else None,
                                      rejected=self._snapshot.rejected if self._snapshot else ())
                return self._status
            try:
                return self._build(commit, base, fetched_at, accept_rewind)
            except Exception as e:  # noqa: BLE001 — 장기 실행 루프: 어느 예외든 인덱스는 이전 판으로 남고 다음 주기에 다시 시도한다(상태에 기록)
                # 빌드 실패: 인덱스는 이전 판으로 남고 다음 주기에 다시 시도한다
                self._status = Status(ready=self._snapshot is not None, degraded=(f"rebuild_failed:{e}",),
                                      commit_sha=self._status.commit_sha, fetched_at=fetched_at, built_at=self._status.built_at)
                return self._status

    def _build(self, commit: str, base: str | None, fetched_at: datetime, accept_rewind: bool) -> Status:
        report = check_commit(self._store, self._validator, commit, base=base, workdir=self._workdir)
        if report.checker_failed:
            self._status = Status(ready=self._snapshot is not None, degraded=(f"checker_failed:{report.checker_failed}",),
                                  commit_sha=self._status.commit_sha, fetched_at=fetched_at, built_at=self._status.built_at)
            return self._status
        rejected_names = report.rejected_skills()
        entries: list[SkillEntry] = []
        for tree in self._store.list_skill_trees(commit):
            if tree.name in rejected_names:
                continue
            props = self._inspect_tree(tree.tree_sha, tree.name).properties
            if props is None:
                continue
            entries.append(SkillEntry(tree.name, props.description, props.compatibility, props.metadata, tree.tree_sha, tree.commit_sha))
        rejected = tuple(sorted({(f.skill, f"{f.item}: {f.reason}") for f in report.errors if f.skill}))
        repo_findings: tuple[str, ...] = ()  # 저장소 수준 위반은 _structure_reasons가 먼저 잡아 빌드를 막는다
        snapshot = IndexSnapshot(tuple(sorted(entries, key=lambda e: e.name)), commit, _now(), fetched_at, rejected)
        def is_descendant(stored: str) -> bool:
            return accept_rewind or self._store.is_ancestor(stored, commit)

        outcome = self._facts.replace_index(snapshot, is_descendant)
        if outcome is IndexOutcome.STALE:
            # DB가 더 앞서 있거나 되감겼다: 메모리도 바꾸지 않는다(뒤로 가지 않는다)
            self._status = Status(ready=self._snapshot is not None, degraded=repo_findings + ("main_rewound",), commit_sha=self._status.commit_sha,
                                  fetched_at=fetched_at, built_at=self._status.built_at, rejected=self._status.rejected)
            return self._status
        self._snapshot = snapshot
        degraded = repo_findings + (("db_unavailable",) if outcome is IndexOutcome.UNAVAILABLE else ())
        self._status = Status(ready=True, degraded=degraded, commit_sha=commit, fetched_at=fetched_at, built_at=snapshot.built_at, rejected=rejected)
        return self._status

    def _structure_reasons(self, commit: str) -> tuple[tuple[ReadyReason, ...], tuple[str, ...]]:
        """표지 → 배치. 표지가 없거나 깨졌으면 not_a_catalog, layout 값이 다르면 unsupported_layout, 항목 1·2 위반은 layout_mismatch."""
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

    def list_skills(self) -> ListResult:
        snap = self._ready_snapshot()
        return ListResult(tuple(SkillListing.of(e) for e in snap.entries), snap.fetched_at)

    def search_skills(self, query: str, limit: int | None = None) -> ListResult:
        snap = self._ready_snapshot()
        if len(query) > self._limits.query_chars:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"query longer than {self._limits.query_chars} chars")
        n = DEFAULT_LIMIT if limit is None else limit
        if n < 1 or n > self._limits.max_limit:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"limit must be 1..{self._limits.max_limit}")
        ranked = self._facts.search(query, n)
        if ranked is not None:
            by_name = {e.name: e for e in snap.entries}
            hits = [by_name[name] for name in ranked if name in by_name]
        else:
            tokens = [t for t in query.lower().split() if t]
            hits = [e for e in snap.entries if all(t in e.search_text for t in tokens)] if tokens else []
        return ListResult(tuple(SkillListing.of(e) for e in hits[:n]), snap.fetched_at)

    def _resolve(self, name: str, sha: str | None) -> tuple[SkillEntry, str, str]:
        """(현재 항목, 읽을 tree, 그 판의 커밋)."""
        if len(name) > MAX_NAME_CHARS or not name:
            raise CatalogError(ErrorCode.INPUT_LIMIT, f"name must be 1..{MAX_NAME_CHARS} chars")
        snap = self._ready_snapshot()
        entry = snap.get(name)
        if entry is None:
            raise CatalogError(ErrorCode.NOT_FOUND, f"skill {name!r} not found")
        if sha is None or sha == entry.tree_sha:
            return entry, entry.tree_sha, entry.commit_sha
        commit = self._store.resolve_version(name, sha, snap.commit_sha)
        if commit is None:
            raise CatalogError(ErrorCode.UNKNOWN_VERSION, f"{name!r} has no version {sha}")
        return entry, sha, commit

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
