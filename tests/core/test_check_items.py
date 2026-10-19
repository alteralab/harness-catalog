"""검사 항목 번호 보장: 리뷰가 짚은 표본들(항목 2, 저장소 수준 위반의 준비 상태)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness_catalog_core.catalog import Catalog
from harness_catalog_core.check import check_commit
from harness_catalog_core.model import ReadyReason

from .fakes import FakeStore, FakeValidator, MemoryFacts

if TYPE_CHECKING:
    from pathlib import Path

GOOD = {"SKILL.md": b"---\nname: good\ndescription: fine\n---\nbody\n"}


def test_item2_skill_md_missing_is_item_2_not_3(tmp_path: Path) -> None:
    store = FakeStore({"good": GOOD, "empty": {"notes.txt": b"no skill md"}})
    report = check_commit(store, FakeValidator(), store.commit, workdir=tmp_path)
    assert [(f.item, f.skill) for f in report.errors] == [(2, "empty")]


def test_repo_level_violation_makes_catalog_unready(tmp_path: Path) -> None:
    store = FakeStore({"good": GOOD}, extra_top=(".pre-commit-config.yaml", "README.md"))  # CI 워크플로 없음
    cat = Catalog(store, FakeValidator(), MemoryFacts(), workdir=tmp_path)
    status = cat.rebuild()
    assert not status.ready and status.reasons == (ReadyReason.LAYOUT_MISMATCH,)
    assert any(d.startswith("check:1:CI workflow missing") for d in status.degraded)
