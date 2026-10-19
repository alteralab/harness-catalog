"""재구축: 한 주기의 상태 기계와 벡터 캐시. `catalog.py` 에서 떼었다(DESIGN §11 2026-10-20 "코드 정리").

떼어 낸 기준은 줄 수가 아니라 **변경 이유**다 — 여기 있는 것은 "main 을 어떤 조건에 받아들이는가"(구조·되감기·DB 세대)와
"어떤 벡터를 다시 임베딩하는가"의 규칙이고, 읽기 경로(검색·get·아카이브)는 그 결과를 쓸 뿐 규칙을 모른다.
`catalog.py` 는 조립과 읽기만 남고 재구축은 여기, tar 보존은 `archives.py` 다.

**분할 뒤에도 글자 그대로 지키는 셋**(plans/refactor.md R5-1 보존 계약):
 1. 잠금 하나(`Indexer._lock`)가 fetch → 구조 검사 → 빌드 → 교체를 통째로 감싼다. 범위도 소유자도 쪼개지 않았다.
 2. 바뀌는 상태는 `Indexer.live = (스냅샷, 검색 색인 둘)` 한 참조의 원자 교체뿐이다(옛 `Catalog._live` 와 같은 것) —
    동시 검색이 두 세대를 섞지 않게(Codex 2026-10-19 #3).
 3. 읽기 경로는 잠금 없이 그 한 참조를 읽는다(`Catalog._ready_live`).
"""

from __future__ import annotations

import tempfile
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .catalog_file import MARKER_PATH, MarkerError, parse_marker
from .check import check_commit, structure_findings
from .model import (
    SUPPORTED_LAYOUT,
    ContentError,
    IndexOutcome,
    IndexSnapshot,
    ReadyReason,
    SkillEntry,
    SkillReport,
    Status,
    ToolEntry,
)
from .search import SearchIndex, index_document
from .toolbox import TOOL_FILE, parse_tool

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .ports import ContentStore, Embedder, FactStore, SkillValidator

    VectorsByName = Mapping[str, tuple[float, ...]]
    Record = SkillEntry | ToolEntry
    Doc = tuple[tuple[str, str], str]  # ((name, tree_sha), 색인 문서)


def _now() -> datetime:
    return datetime.now(UTC)


def inspect_tree(store: ContentStore, validator: SkillValidator, tree_sha: str, name: str, workdir: Path) -> SkillReport:
    """트리 하나를 임시 디렉토리에 풀어 스펙 검증기에 보인다. 빌드(항목 전부)와 읽기(이력 판의 메타데이터)가 같이 쓴다."""
    with tempfile.TemporaryDirectory(dir=workdir, prefix="read.") as tmp:
        dest = Path(tmp) / name  # 스펙 검증기가 디렉토리명 = name을 본다
        dest.mkdir()
        store.export_tree(tree_sha, dest)
        return validator.inspect(dest)


def _index_for(records: Sequence[Record], vectors: VectorsByName | None) -> SearchIndex:
    """한 종류(스킬 또는 도구)의 검색 색인. vectors=None 은 이번 판에 dense 없음 — SearchIndex 가 BM25 만으로 돈다."""
    names = [r.name for r in records]
    docs = [index_document(r.name, r.description, r.metadata.values()) for r in records]
    return SearchIndex(names, docs, [vectors.get(n) for n in names] if vectors is not None else None)


class VectorCache:
    """현재 세대의 `(name, tree_sha) → 벡터`. 재구축 때 **바뀐 항목만** 임베딩한다.

    이름이 키에 드는 이유는 `ports.load_embeddings` 에 적혀 있다(색인 문서가 이름을 담는데 tree SHA 에는 이름이 없다).
    DB 의 저장분은 한 번만 읽고(재기동 뒤 재임베딩 회피), 은퇴한 판의 벡터는 버리며, 임베딩 서비스의 일시 장애에는
    이미 있는 벡터를 그대로 돌려준다 — 장애가 저장 벡터를 지우지 않게.
    """

    def __init__(self, embedder: Embedder, facts: FactStore) -> None:
        self._embedder = embedder
        self._facts = facts
        self._vectors: dict[tuple[str, str], tuple[float, ...]] = {}
        self._loaded = False  # DB 의 저장 벡터를 한 번 읽었는가

    @property
    def generation(self) -> str:
        return self._embedder.generation

    def discard(self) -> None:
        """저장된 벡터가 깨져 있었다(차원·NaN): 캐시를 버려 다음 빌드가 전부 다시 임베딩하게 한다."""
        self._vectors = {}

    def resolve(self, wanted: Sequence[Doc]) -> tuple[dict[str, tuple[float, ...]], bool]:
        """`(name → 벡터, dense 가 온전한가)`. 메모리 캐시 → DB 저장분(한 번) → 없는 것만 임베딩 서비스."""
        self._load_once()
        missing = [(key, doc) for key, doc in wanted if key not in self._vectors]
        ok = self._embed(missing)
        keep = {key for key, _ in wanted}
        self._vectors = {key: v for key, v in self._vectors.items() if key in keep}  # 은퇴한 판의 벡터는 버린다
        return {name: v for (name, _), v in self._vectors.items()}, ok

    def _load_once(self) -> None:
        stored = None if self._loaded else self._facts.load_embeddings(self.generation)
        if stored is not None:
            self._vectors.update(stored)
            self._loaded = True

    def _embed(self, missing: Sequence[Doc]) -> bool:
        """없는 것만 한 번에 임베딩한다. 실패면 False — 이번 판은 dense 없이(BM25 만) 가고 이미 있는 벡터는 남는다."""
        if not missing:
            return True
        got = self._embedder.embed([doc for _, doc in missing])
        if got is None or len(got) != len(missing):
            return False
        for (key, _), vec in zip(missing, got, strict=True):
            self._vectors[key] = tuple(vec)
        return True


class Indexer:
    """재구축 상태 기계. 한 주기의 fetch → 검사 → 빌드 → 교체와 그 결과(`live`·`status()`)를 들고 있다."""

    def __init__(self, store: ContentStore, validator: SkillValidator, facts: FactStore, *, workdir: Path, embedder: Embedder | None = None) -> None:
        self._store = store
        self._validator = validator
        self._facts = facts
        self._embedder = embedder  # None 이면 BM25 만(§11 2026-10-19 검색 0.8.0)
        self._workdir = workdir
        self._cache = VectorCache(embedder, facts) if embedder is not None else None
        self.live: tuple[IndexSnapshot, dict[str, SearchIndex]] | None = None  # (스냅샷, 검색 색인 둘) — 하나의 참조로 통째로 교체한다(동시 검색이 두 세대를 섞지 않게, Codex 2026-10-19 #3)
        self.embedding_ok = embedder is not None  # dense 가 온전한가 — 색인 때와 질의 때 둘 다 갱신하고 status() 가 embedding_unavailable 로 보인다
        self._status = Status(ready=False)
        self._db_synced = False  # 마지막 스냅샷이 사실 저장소에도 반영됐는가
        self._lock = threading.Lock()

    @property
    def snapshot(self) -> IndexSnapshot | None:
        return self.live[0] if self.live is not None else None

    def status(self) -> Status:
        """임베딩 사유는 상태 객체 밖에서 합친다: 색인 때 장애든 질의 때 장애든 지금 dense 가 온전하지 않으면 embedding_unavailable(설계 §11 2026-10-19)."""
        s = self._status
        if not self.embedding_ok and "embedding_unavailable" not in s.degraded:
            return replace(s, degraded=s.degraded + ("embedding_unavailable",))
        return s

    def rebuild(self, *, accept_rewind: bool = False) -> Status:
        """fetch → 구조 검사 → 세대 검사 → 검사 열 → 스냅샷 교체. 구조가 깨지면 이전 스냅샷을 유지하고 unready.

        뒤로 가지 않는다: 새 커밋이 이전 커밋의 자손이 아니면(main 되감기) 아무것도 바꾸지 않고 degraded에 main_rewound.
        accept_rewind=True(운영 명령)면 그 검사를 건너뛴다.
        """
        with self._lock:
            try:
                commit = self._store.fetch()
            except ContentError as e:
                return self._unreachable(e)
            fetched_at = _now()
            reasons, details = self._structure_reasons(commit)
            if reasons:
                # 저장소 구조가 깨졌다: 빌드 전체가 실패하고 /readyz는 503 (이전 스냅샷은 들고 있되 준비됨은 아니다)
                self._status = Status(ready=False, reasons=reasons, degraded=details, commit_sha=commit, fetched_at=fetched_at)
                return self._status
            if self._already_built(commit):
                return self._resync(commit, fetched_at, accept_rewind=accept_rewind)
            base = self._rewind_base(commit, accept_rewind=accept_rewind)
            if base is not None:
                return self._rewound(base, fetched_at)
            try:
                return self._build(commit, fetched_at, accept_rewind=accept_rewind, write_facts=True)
            except Exception as e:  # noqa: BLE001 — 장기 실행 루프: 어느 예외든 인덱스는 이전 판으로 남고 다음 주기에 다시 시도한다(상태에 기록)
                # 빌드 실패: 인덱스는 이전 판으로 남고 다음 주기에 다시 시도한다
                self._status = Status(ready=self.snapshot is not None, degraded=(f"rebuild_failed:{e}",),
                                      commit_sha=self._status.commit_sha, fetched_at=fetched_at, built_at=self._status.built_at)
                return self._status

    def _unreachable(self, e: ContentError) -> Status:
        """저장소를 읽지 못했다. 사유의 원문은 degraded에 남긴다(운영자가 /readyz만 보고도 git 오류를 읽게)."""
        detail = (f"{e.reason}:{e.detail[:300]}",)
        self._status = Status(ready=self.snapshot is not None, reasons=(e.reason,), degraded=detail + tuple(d for d in self._status.degraded if not d.startswith(("repo_unreachable:", "no_main_branch:"))),
                              commit_sha=self._status.commit_sha, fetched_at=self._status.fetched_at, built_at=self._status.built_at)
        return self._status

    def _already_built(self, commit: str) -> bool:
        """이 커밋은 이미 지었고 dense 도 온전하다 → 빌드를 건너뛴다. 임베딩이 빠져 있으면 전체 빌드로 다시 시도한다(Codex 2026-10-19 #1)."""
        snap = self.snapshot
        return snap is not None and snap.commit_sha == commit and (self.embedding_ok or self._embedder is None)

    def _rewind_base(self, commit: str, *, accept_rewind: bool) -> str | None:
        """되감기면 그 기준 커밋, 아니면 None. 기준은 메모리 스냅샷이고 비었으면(재기동) DB가 들고 있는 커밋이다."""
        if accept_rewind:
            return None
        snap = self.snapshot
        base = snap.commit_sha if snap else self._facts.current_commit()
        return base if base is not None and not self._store.is_ancestor(base, commit) else None

    def _resync(self, commit: str, fetched_at: datetime, *, accept_rewind: bool) -> Status:
        """같은 커밋: 빌드는 건너뛰되, 지난번 DB 반영이 실패했으면 그 스냅샷으로 다시 시도한다."""
        snap = self.snapshot
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
        if self.snapshot is None:
            try:
                self._build(base, fetched_at, accept_rewind=True, write_facts=False)  # DB에는 이미 base 세대가 있다
            except Exception as e:  # noqa: BLE001 — base 세대를 못 지으면 unready로 남고 사유만 적는다
                self._status = Status(ready=False, degraded=("main_rewound", f"rebuild_failed:{e}"), commit_sha=None, fetched_at=fetched_at)
                return self._status
        snap = self.snapshot
        self._status = Status(ready=snap is not None, degraded=("main_rewound",), commit_sha=base, fetched_at=fetched_at,
                              built_at=snap.built_at if snap else None, rejected=snap.rejected if snap else ())
        return self._status

    def _build(self, commit: str, fetched_at: datetime, *, accept_rewind: bool, write_facts: bool) -> Status:
        report = check_commit(self._store, self._validator, commit, workdir=self._workdir)
        if report.checker_failed:
            self._status = Status(ready=self.snapshot is not None, degraded=(f"checker_failed:{report.checker_failed}",),
                                  commit_sha=self._status.commit_sha, fetched_at=fetched_at, built_at=self._status.built_at)
            return self._status
        entries = self._skill_entries(commit, report.rejected_skills())
        tools = self._tool_entries(commit, report.rejected_tools())
        rejected = tuple(sorted({(f.skill, f"{f.item}: {f.reason}") for f in report.errors if f.skill}))
        repo_findings: tuple[str, ...] = ()  # 저장소 수준 위반은 _structure_reasons가 먼저 잡아 빌드를 막는다
        vectors, generation, embedding_ok = self._dense(entries, tools)
        snapshot = IndexSnapshot(tuple(entries), commit, _now(), fetched_at, rejected, tuple(tools),
                                 embeddings=vectors, embedding_generation=generation)
        def is_descendant(stored: str) -> bool:
            return accept_rewind or self._store.is_ancestor(stored, commit)

        outcome = self._facts.replace_index(snapshot, is_descendant) if write_facts else IndexOutcome.REPLACED
        if outcome is IndexOutcome.STALE:
            # DB가 더 앞서 있거나 되감겼다: 메모리도 바꾸지 않는다(뒤로 가지 않는다)
            self._status = Status(ready=self.snapshot is not None, degraded=repo_findings + ("main_rewound",), commit_sha=self._status.commit_sha,
                                  fetched_at=fetched_at, built_at=self._status.built_at, rejected=self._status.rejected)
            return self._status
        self.live = (snapshot, self._indexes(entries, tools, vectors if embedding_ok else None))
        self._db_synced = outcome is IndexOutcome.REPLACED
        degraded = repo_findings + (("db_unavailable",) if outcome is IndexOutcome.UNAVAILABLE else ())
        self._status = Status(ready=True, degraded=degraded, commit_sha=commit, fetched_at=fetched_at, built_at=snapshot.built_at, rejected=rejected)
        return self._status

    def _skill_entries(self, commit: str, rejected: frozenset[str]) -> list[SkillEntry]:
        """main 의 `skills/` 를 인덱스 항목으로. 거부된 것과 속성을 읽지 못한 것(검사 3이 거부했어야 하는 것)은 뺀다."""
        entries: list[SkillEntry] = []
        for tree in self._store.list_trees(commit, "skills"):
            if tree.name in rejected:
                continue
            props = inspect_tree(self._store, self._validator, tree.tree_sha, tree.name, self._workdir).properties
            if props is None:
                continue
            has_scripts = any(e.path.startswith("scripts/") and e.kind != "tree" for e in self._store.list_tree(tree.tree_sha))
            entries.append(SkillEntry(tree.name, props.description, props.compatibility, props.metadata, tree.tree_sha, tree.commit_sha, has_scripts))
        entries.sort(key=lambda e: e.name)
        return entries

    def _tool_entries(self, commit: str, rejected: frozenset[str]) -> list[ToolEntry]:
        """main 의 `tools/` 를 인덱스 항목으로. kind=mcp 면 참조 서버 이름을 함께 든다."""
        tools: list[ToolEntry] = []
        for tree in self._store.list_trees(commit, "tools"):
            if tree.name in rejected:
                continue
            raw = self._store.read_blob(tree.tree_sha, TOOL_FILE)
            spec, _ = parse_tool(raw) if raw is not None else (None, [])
            if spec is None:
                continue  # 검사 11이 거부했어야 하는 것 — 방어
            server = spec.runtime.server if spec.runtime.kind == "mcp" else None
            tools.append(ToolEntry(tree.name, spec.description, spec.runtime.kind, server, spec.metadata, tree.tree_sha, tree.commit_sha))
        tools.sort(key=lambda t: t.name)
        return tools

    def _dense(self, entries: Sequence[SkillEntry], tools: Sequence[ToolEntry]) -> tuple[VectorsByName, str | None, bool]:
        """`(name → 벡터, 그 벡터의 세대, dense 가 온전한가)`. 임베더가 없거나(HC__EMBED_URL 비면) 닿지 않으면 세 번째가 False —
        둘 다 embedding_unavailable 이다(설계 §11 2026-10-19). 한 스냅샷에 한 세대만이라 벡터가 비면 세대도 비운다."""
        if self._cache is None:
            self.embedding_ok = False
            return {}, None, False
        wanted: list[Doc] = [((r.name, r.tree_sha), index_document(r.name, r.description, r.metadata.values())) for r in (*entries, *tools)]
        vectors, ok = self._cache.resolve(wanted)
        self.embedding_ok = ok
        return vectors, (self._cache.generation if vectors else None), ok

    def _indexes(self, entries: Sequence[SkillEntry], tools: Sequence[ToolEntry], vectors: VectorsByName | None) -> dict[str, SearchIndex]:
        """검색 색인 둘. 벡터가 모두 있을 때만 dense(SearchIndex 가 하나라도 빠지거나 깨졌으면 BM25 만). vectors=None 은 이번 판에 dense 없음."""
        indexes = {"skills": _index_for(entries, vectors), "tools": _index_for(tools, vectors)}
        if vectors is not None and not all(ix.dense for ix in indexes.values() if ix.names):
            # 저장된 벡터가 깨져 있다(차원·NaN): 캐시를 버려 다음 빌드가 전부 다시 임베딩하게 하고 이번 판은 BM25 만
            if self._cache is not None:
                self._cache.discard()
            self.embedding_ok = False
        return indexes

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
