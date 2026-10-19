from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import CatalogError, ErrorCode, ReadyReason

from .fakes import FakeEmbedder, FakeStore, FakeValidator, MemoryFacts

if TYPE_CHECKING:
    from pathlib import Path

SKILL_A = {"SKILL.md": b"---\nname: alpha\ndescription: first skill about youtube\nmetadata:\n  requires-tools: \"yt-dlp\"\n---\nbody A\n", "scripts/run.py": b"print(1)\n"}
SKILL_B = {"SKILL.md": b"---\nname: beta\ndescription: second skill\n---\nbody B\n", "data.bin": bytes([0, 255, 1, 2])}


def make(tmp_path: Path, skills: dict[str, dict[str, bytes]] | None = None, **kw: object) -> tuple[Catalog, FakeStore, MemoryFacts]:
    store = FakeStore(skills if skills is not None else {"alpha": SKILL_A, "beta": SKILL_B}, **kw)  # type: ignore[arg-type]
    facts = MemoryFacts()
    return Catalog(store, FakeValidator(), facts, workdir=tmp_path), store, facts


def test_rebuild_then_list_and_search(tmp_path: Path) -> None:
    cat, store, facts = make(tmp_path)
    status = cat.rebuild()
    assert status.ready and not status.reasons and status.commit_sha == store.commit
    hits = cat.search_skills("skill").skills
    assert sorted(s.name for s in hits) == ["alpha", "beta"]  # 전체 목록 도구는 없다 — 공통 낱말로 둘을 본다(순서는 BM25 점수: 짧은 설명이 앞)
    assert {s.name: s.has_scripts for s in hits} == {"alpha": True, "beta": False}
    assert [s.name for s in cat.search_skills("youtube").skills] == ["alpha"]
    assert len(cat.search_skills("skill", limit=1).skills) == 1
    assert cat.search_skills("nothing-matches").skills == ()
    assert "embedding_unavailable" in status.degraded  # 임베더 없음(HC__EMBED_URL 비면) 도 설계대로 degraded — 운영자가 /readyz 로 설정 누락을 본다
    assert len(facts.snapshots) == 1


def test_not_ready_before_rebuild(tmp_path: Path) -> None:
    cat, _, _ = make(tmp_path)
    with pytest.raises(CatalogError) as e:
        cat.search_skills("skill")
    assert e.value.code is ErrorCode.NOT_FOUND


def test_structure_reasons(tmp_path: Path) -> None:
    cat, _, _ = make(tmp_path, marker=None)
    assert cat.rebuild().reasons == (ReadyReason.NOT_A_CATALOG,)
    cat, _, _ = make(tmp_path, marker=b"layout = 2\n")
    assert cat.rebuild().reasons == (ReadyReason.UNSUPPORTED_LAYOUT,)
    cat, _, _ = make(tmp_path, {}, marker=b"layout = 1\n")
    assert cat.rebuild().reasons == (ReadyReason.LAYOUT_MISMATCH,)


def test_rejected_skill_is_excluded_and_reported(tmp_path: Path) -> None:
    leaky = {"SKILL.md": b"---\nname: leaky\ndescription: has a secret\n---\n", "notes.txt": b"token=SECRET\n"}
    cat, _, _ = make(tmp_path, {"alpha": SKILL_A, "leaky": leaky})
    status = cat.rebuild()
    assert status.ready
    assert [n for n, _ in status.rejected] == ["leaky"]
    assert [s.name for s in cat.search_skills("skill").skills] == ["alpha"]


def test_get_skill_and_file(tmp_path: Path) -> None:
    cat, store, _ = make(tmp_path)
    cat.rebuild()
    body = cat.get_skill("alpha")
    assert body.sha == store.tree_of("alpha") and "body A" in body.body and body.has_scripts
    assert sorted(f.path for f in body.files) == ["SKILL.md", "scripts/run.py"]
    f = cat.get_skill_file("alpha", "scripts/run.py")
    assert f.text == "print(1)\n" and f.base64 is None
    b = cat.get_skill_file("beta", "data.bin")
    assert b.text is None and b.base64 == "AP8BAg=="


def test_unknown_version_and_history(tmp_path: Path) -> None:
    cat, _, _ = make(tmp_path)
    cat.rebuild()
    with pytest.raises(CatalogError) as e:
        cat.get_skill("alpha", sha="f" * 40)
    assert e.value.code is ErrorCode.UNKNOWN_VERSION
    with pytest.raises(CatalogError) as e2:
        cat.get_skill("nope")
    assert e2.value.code is ErrorCode.NOT_FOUND


@pytest.mark.parametrize("path", ["../x", "/etc/passwd", "a/../b", "", "a\\b", "scripts/./run.py"])
def test_path_rejected(tmp_path: Path, path: str) -> None:
    cat, _, _ = make(tmp_path)
    cat.rebuild()
    with pytest.raises(CatalogError) as e:
        cat.get_skill_file("alpha", path)
    assert e.value.code in (ErrorCode.PATH_REJECTED, ErrorCode.INPUT_LIMIT)


def test_symlink_and_size_limits(tmp_path: Path) -> None:
    skills = {"alpha": {**SKILL_A, "link.lnk": b"x"}}
    store = FakeStore(skills)
    cat = Catalog(store, FakeValidator(), MemoryFacts(), workdir=tmp_path)
    status = cat.rebuild()
    assert ("alpha", "7: link.lnk: symbolic link") in status.rejected


def test_input_limits(tmp_path: Path) -> None:
    cat, _, _ = make(tmp_path)
    cat.rebuild()
    with pytest.raises(CatalogError) as e:
        cat.search_skills("x" * 2001)
    assert e.value.code is ErrorCode.INPUT_LIMIT
    with pytest.raises(CatalogError):
        cat.search_skills("x", limit=21)


def test_db_unavailable_is_degraded_not_unready(tmp_path: Path) -> None:
    store = FakeStore({"alpha": SKILL_A})
    cat = Catalog(store, FakeValidator(), MemoryFacts(available=False), workdir=tmp_path)
    status = cat.rebuild()
    assert status.ready and "db_unavailable" in status.degraded
    assert [s.name for s in cat.search_skills("youtube").skills] == ["alpha"]


def test_rewind_is_refused_unless_accepted(tmp_path: Path) -> None:
    cat, store, facts = make(tmp_path)
    cat.rebuild()
    first = store.commit
    store.commit = "d" * 40  # 자손 관계를 등록하지 않았다 = 되감기
    status = cat.rebuild()
    assert status.ready and "main_rewound" in status.degraded and status.commit_sha == first and len(facts.snapshots) == 1
    store.ancestors.add((first, "d" * 40))
    assert cat.rebuild().commit_sha == "d" * 40
    store.commit = "e" * 40
    assert cat.rebuild(accept_rewind=True).commit_sha == "e" * 40 and len(facts.snapshots) == 3


def test_same_commit_skips_rebuild(tmp_path: Path) -> None:
    cat, store, facts = make(tmp_path)
    cat.rebuild()
    cat.rebuild()
    assert store.fetch_calls == 2 and len(facts.snapshots) == 1


def test_accept_rewind_builds_unrelated_commit(tmp_path: Path) -> None:
    """되감기 수용: 새 커밋이 옛 커밋의 자손이 아니어도 빌드된다(검사는 이력을 보지 않는다)."""
    store = FakeStore({"alpha": SKILL_A})
    facts = MemoryFacts()
    Catalog(store, FakeValidator(), facts, workdir=tmp_path).rebuild()
    store.commit = "g" * 40
    fresh = Catalog(store, FakeValidator(), facts, workdir=tmp_path)
    status = fresh.rebuild(accept_rewind=True)
    assert status.ready and status.commit_sha == "g" * 40 and status.degraded == ("embedding_unavailable",) and facts.current_commit() == "g" * 40


def test_db_unavailable_then_resync_on_same_commit(tmp_path: Path) -> None:
    """DB가 죽었다 살아나면 같은 커밋이어도 다음 주기에 다시 반영한다."""
    store = FakeStore({"alpha": SKILL_A})
    facts = MemoryFacts(available=False)
    cat = Catalog(store, FakeValidator(), facts, workdir=tmp_path)
    assert "db_unavailable" in cat.rebuild().degraded and facts.snapshots == []
    facts.available = True
    status = cat.rebuild()
    assert "db_unavailable" not in status.degraded and len(facts.snapshots) == 1 and facts.snapshots[0].commit_sha == store.commit


def test_first_start_uses_db_commit_as_base(tmp_path: Path) -> None:
    """재기동: 메모리는 비었지만 DB에 커밋이 있으면 그것이 세대·이력 검사의 기준이다. 되감기면 base 세대를 git에서 지어 읽기를 잇는다."""
    store = FakeStore({"alpha": SKILL_A})
    facts = MemoryFacts()
    Catalog(store, FakeValidator(), facts, workdir=tmp_path).rebuild()  # 이전 프로세스가 DB에 c…c를 남겼다
    assert facts.current_commit() == store.commit
    fresh = Catalog(store, FakeValidator(), facts, workdir=tmp_path)
    old = store.commit
    store.commit = "r" * 40  # 자손 아님 = 되감기
    status = fresh.rebuild()
    assert status.ready and "main_rewound" in status.degraded and status.commit_sha == old
    assert [s.name for s in fresh.search_skills("skill").skills] == ["alpha"] and len(facts.snapshots) == 1


# ---- 검색 0.8.0(§11 2026-10-19): dense + BM25 볼록 결합, 벡터 재사용, 임베딩 서비스 장애 ----

SKILL_SUBS = {"SKILL.md": "---\nname: yt-subs\ndescription: youtube 자막을 추출한다\n---\nbody\n".encode()}
SKILL_COMMITS = {"SKILL.md": "---\nname: git-log\ndescription: git 커밋을 정리한다\n---\nbody\n".encode()}


def _make_dense(tmp_path: Path, embedder: FakeEmbedder, facts: MemoryFacts | None = None) -> tuple[Catalog, FakeStore, MemoryFacts]:
    store = FakeStore({"yt-subs": SKILL_SUBS, "git-log": SKILL_COMMITS})  # type: ignore[arg-type]
    facts = facts or MemoryFacts()
    return Catalog(store, FakeValidator(), facts, workdir=tmp_path, embedder=embedder), store, facts


def test_dense_rescues_synonym_query_and_vectors_are_persisted(tmp_path: Path) -> None:
    emb = FakeEmbedder()
    cat, _, facts = _make_dense(tmp_path, emb)
    status = cat.rebuild()
    assert status.ready and "embedding_unavailable" not in status.degraded
    assert emb.calls and len(emb.calls[0]) == 2  # 문서 둘을 한 번에 임베딩
    assert [s.name for s in cat.search_skills("캡션 가져와").skills][0] == "yt-subs"  # BM25 로는 0 — 벡터가 살린다
    assert [s.name for s in cat.search_skills("자막").skills][0] == "yt-subs"
    snap = facts.snapshots[-1]
    assert snap.embedding_generation == "fake-model/doc1" and len(snap.embeddings) == 2


def test_rebuild_reuses_vectors_for_unchanged_trees(tmp_path: Path) -> None:
    emb = FakeEmbedder()
    cat, store, _ = _make_dense(tmp_path, emb)
    cat.rebuild()
    doc_calls = len(emb.calls)
    store.commit = store.commit + "1" if not store.commit.endswith("1") else store.commit + "2"  # 같은 트리, 새 커밋
    cat.rebuild(accept_rewind=True)
    assert len(emb.calls) == doc_calls  # tree sha 가 같으니 다시 임베딩하지 않는다


def test_restart_loads_vectors_from_facts_instead_of_embedding_again(tmp_path: Path) -> None:
    first = FakeEmbedder()
    cat, _, facts = _make_dense(tmp_path, first)
    cat.rebuild()
    second = FakeEmbedder()
    cat2, _, _ = _make_dense(tmp_path, second, facts)  # 재기동: 같은 사실 저장소
    cat2.rebuild(accept_rewind=True)
    assert second.calls == [] or all(c == [] for c in second.calls)  # 저장된 벡터를 읽어 썼다
    assert [s.name for s in cat2.search_skills("캡션").skills][0] == "yt-subs"


def test_embedder_down_degrades_to_bm25(tmp_path: Path) -> None:
    emb = FakeEmbedder(available=False)
    cat, _, facts = _make_dense(tmp_path, emb)
    status = cat.rebuild()
    assert status.ready and "embedding_unavailable" in status.degraded
    assert [s.name for s in cat.search_skills("자막").skills] == ["yt-subs"]  # BM25 는 산다
    assert cat.search_skills("캡션").skills == ()  # dense 없이는 동의어를 못 잡는다 — 정직하게 비어 있다
    assert facts.snapshots[-1].embedding_generation is None


def test_embedder_outage_keeps_stored_vectors_and_recovers(tmp_path: Path) -> None:
    """임베더가 잠시 죽은 사이의 재구축: dense 는 끄되(BM25 만) 이미 있던 벡터는 사실 저장소에 남긴다. 돌아오면 빠진 것만 임베딩한다."""
    emb = FakeEmbedder()
    cat, store, facts = _make_dense(tmp_path, emb)
    cat.rebuild()
    store.skills["pdf-merge"] = {"SKILL.md": "---\nname: pdf-merge\ndescription: PDF 를 합친다\n---\nbody\n".encode()}
    store.commit = "d" * 40
    emb.available = False
    status = cat.rebuild(accept_rewind=True)
    assert status.ready and "embedding_unavailable" in status.degraded
    assert cat.search_skills("캡션").skills == ()  # 이번 판은 BM25 만
    snap = facts.snapshots[-1]
    assert snap.embedding_generation == "fake-model/doc1" and len(snap.embeddings) == 2  # 옛 둘의 벡터는 지워지지 않았다
    emb.available = True
    store.commit = "e" * 40
    status = cat.rebuild(accept_rewind=True)
    assert "embedding_unavailable" not in status.degraded
    assert len(emb.calls[-1]) == 1  # pdf-merge 하나만 임베딩
    assert [s.name for s in cat.search_skills("캡션").skills][0] == "yt-subs"


def test_embedder_recovers_on_same_commit(tmp_path: Path) -> None:
    """Codex 2026-10-19 #1: 같은 main 에서 다음 주기의 rebuild 가 임베딩을 다시 시도한다(_resync 로 빠지지 않는다)."""
    emb = FakeEmbedder(available=False)
    cat, _, _ = _make_dense(tmp_path, emb)
    assert "embedding_unavailable" in cat.rebuild().degraded
    emb.available = True
    status = cat.rebuild()  # 커밋 그대로
    assert "embedding_unavailable" not in status.degraded
    assert [s.name for s in cat.search_skills("캡션").skills][0] == "yt-subs"
    calls = len(emb.calls)
    assert "embedding_unavailable" not in cat.rebuild().degraded and len(emb.calls) == calls  # 온전하면 같은 커밋은 다시 임베딩하지 않는다


def test_query_time_embedder_outage_is_visible_in_status(tmp_path: Path) -> None:
    """Codex 2026-10-19 #7: 색인은 있는데 질의 임베딩만 실패하면 그 호출은 BM25, 상태는 embedding_unavailable — 돌아오면 내려간다."""
    emb = FakeEmbedder()
    cat, _, _ = _make_dense(tmp_path, emb)
    cat.rebuild()
    emb.available = False
    assert [s.name for s in cat.search_skills("자막").skills] == ["yt-subs"]
    assert "embedding_unavailable" in cat.status().degraded
    emb.available = True
    assert [s.name for s in cat.search_skills("캡션").skills][0] == "yt-subs"
    assert "embedding_unavailable" not in cat.status().degraded
