from __future__ import annotations

from pathlib import Path

import pytest

from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import CatalogError, ContentError, ErrorCode, ReadyReason

from .fakes import FakeStore, FakeValidator, MemoryFacts

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
    assert [s.name for s in cat.list_skills().skills] == ["alpha", "beta"]
    assert cat.list_skills().skills[0].requires_tools == ("yt-dlp",)
    assert [s.name for s in cat.search_skills("youtube").skills] == ["alpha"]
    assert [s.name for s in cat.search_skills("skill", limit=1).skills] == ["alpha"]
    assert cat.search_skills("nothing-matches").skills == ()
    assert len(facts.snapshots) == 1


def test_not_ready_before_rebuild(tmp_path: Path) -> None:
    cat, _, _ = make(tmp_path)
    with pytest.raises(CatalogError) as e:
        cat.list_skills()
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
    assert [s.name for s in cat.list_skills().skills] == ["alpha"]


def test_load_skill_and_file(tmp_path: Path) -> None:
    cat, store, _ = make(tmp_path)
    cat.rebuild()
    body = cat.load_skill("alpha")
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
        cat.load_skill("alpha", sha="f" * 40)
    assert e.value.code is ErrorCode.UNKNOWN_VERSION
    with pytest.raises(CatalogError) as e2:
        cat.load_skill("nope")
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


def test_accept_rewind_drops_missing_base(tmp_path: Path) -> None:
    """되감기 수용: 옛 기준 커밋이 이력에 없어도(deleted_skill_names가 실패해도) 빌드된다."""
    store = FakeStore({"alpha": SKILL_A})
    facts = MemoryFacts()
    Catalog(store, FakeValidator(), facts, workdir=tmp_path).rebuild()
    gone = store.commit
    store.commit = "g" * 40

    def boom(_commit: str) -> frozenset[str]:
        raise ContentError(ReadyReason.REPO_UNREACHABLE, f"bad object {gone}")

    store.deleted_skill_names = boom  # type: ignore[method-assign]
    fresh = Catalog(store, FakeValidator(), facts, workdir=tmp_path)
    status = fresh.rebuild(accept_rewind=True)
    assert status.ready and status.commit_sha == "g" * 40 and not status.degraded and facts.current_commit() == "g" * 40


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
    assert [s.name for s in fresh.list_skills().skills] == ["alpha"] and len(facts.snapshots) == 1
