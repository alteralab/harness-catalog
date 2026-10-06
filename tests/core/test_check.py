from __future__ import annotations

from harness_catalog_core.check import drift_findings, replaced_by_findings, requires_tools_findings


def test_requires_tools_tokens() -> None:
    assert requires_tools_findings("s", None) == []
    assert requires_tools_findings("s", "yt-dlp uv python3.12") == []
    bad = requires_tools_findings("s", "Yt-Dlp uv;rm")
    assert [f.item for f in bad] == [8, 8]


def test_replaced_by_chain_and_missing() -> None:
    f = replaced_by_findings({"a": "b", "b": "c", "c": None, "d": "zzz"})
    assert {(x.skill, x.item) for x in f} == {("a", 6), ("d", 6)}
    assert replaced_by_findings({"a": "c", "c": None}) == []


def test_drift_warning() -> None:
    f = drift_findings({"a": {"common.py": "1" * 40}, "b": {"common.py": "2" * 40}, "c": {"common.py": "1" * 40}})
    assert len(f) == 1 and f[0].warning and f[0].skill == "b" and f[0].item == 10
