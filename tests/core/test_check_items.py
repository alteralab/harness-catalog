"""검사 열의 항목 번호 보장: 리뷰가 짚은 표본들(항목 2·5·9, 저장소 수준 위반의 준비 상태)."""

from __future__ import annotations

from pathlib import Path

from harness_catalog_core.catalog import Catalog
from harness_catalog_core.check import check_commit
from harness_catalog_core.model import ReadyReason

from .fakes import FakeStore, FakeValidator, MemoryFacts

GOOD = {"SKILL.md": b"---\nname: good\ndescription: fine\n---\nbody\n"}


def test_item2_skill_md_missing_is_item_2_not_3(tmp_path: Path) -> None:
    store = FakeStore({"good": GOOD, "empty": {"notes.txt": b"no skill md"}})
    report = check_commit(store, FakeValidator(), store.commit, base=None, workdir=tmp_path)
    assert [(f.item, f.skill) for f in report.errors] == [(2, "empty")]


def test_repo_level_violation_makes_catalog_unready(tmp_path: Path) -> None:
    store = FakeStore({"good": GOOD}, extra_top=(".pre-commit-config.yaml", "README.md"))  # CI 워크플로 없음
    cat = Catalog(store, FakeValidator(), MemoryFacts(), workdir=tmp_path)
    status = cat.rebuild()
    assert not status.ready and status.reasons == (ReadyReason.LAYOUT_MISMATCH,)
    assert any(d.startswith("check:1:CI workflow missing") for d in status.degraded)


def test_item9_reads_frontmatter_not_body_text(tmp_path: Path) -> None:
    """본문에 'replaced-by'라는 낱말만 있는 기준판 → 경고는 남는다; metadata에 있으면 경고 없음."""
    mention = {"SKILL.md": b"---\nname: old\ndescription: says replaced-by in the body only\n---\nreplaced-by nothing\n"}
    proper = {"SKILL.md": b"---\nname: old2\ndescription: retired properly\nmetadata:\n  replaced-by: \"good\"\n---\n"}
    base_store = FakeStore({"good": GOOD, "old": mention, "old2": proper})
    now_store = FakeStore({"good": GOOD})
    now_store.commit = "n" * 40

    class Both(FakeStore):
        """기준 커밋이면 base_store, 아니면 now_store로 답한다."""

        def list_skill_trees(self, commit: str):  # noqa: ANN202
            return base_store.list_skill_trees(commit) if commit == base_store.commit else now_store.list_skill_trees(commit)

        def export_tree(self, tree_sha: str, dest: Path) -> None:
            base_store.export_tree(tree_sha, dest)
            now_store.export_tree(tree_sha, dest)

    store = Both({"good": GOOD})
    store.commit = now_store.commit
    report = check_commit(store, FakeValidator(), store.commit, base=base_store.commit, workdir=tmp_path)
    warnings = [(f.item, f.skill) for f in report.findings if f.warning]
    assert warnings == [(9, "old")]
