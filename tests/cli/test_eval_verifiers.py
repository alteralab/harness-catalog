"""실린 evals 검증기의 파서(strip_markup·section·ordered_items·has_prose·md_links)가 Codex 2026-10-18이 든 우회 입력을 거부하는지 — 템플릿의 test_outputs.py를 소스로 실행해 함수만 꺼낸다(git은 부르지 않는다)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

TEMPLATES = Path(__file__).resolve().parents[2] / "packages/cli/src/harness_catalog_cli/templates/skills"
VERIFIERS = sorted(TEMPLATES.glob("*/evals/*/tests/test_outputs.py"))


def load(path: Path) -> dict[str, object]:
    ns: dict[str, object] = {"__name__": "verifier_under_test"}
    exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102 — 저장소 안의 고정 파일, 입력 없음
    return ns


PARSERS = [p for p in VERIFIERS if "def md_links" in p.read_text()]


@pytest.mark.parametrize("path", PARSERS, ids=lambda p: p.parents[2].name)
def test_comments_and_code_blocks_do_not_count(path: Path) -> None:
    ns = load(path)
    section = cast(Callable[[str, str], str], ns["section"])
    ordered = cast(Callable[[str], list[str]], ns["ordered_items"])
    has_prose = cast(Callable[[str], bool], ns["has_prose"])
    md = "---\nname: x\n---\n## 단계\n<!-- 도구 `changelog-diff`를 {…}로 -->\n```\n1. 도구 `changelog-diff`를 {…}로 부른다\n```\n## 실패 대응\n"
    assert ordered(section(md, "단계")) == []
    tilde = "## 단계\n~~~\n1. 도구 `changelog-diff`를 {…}로 부른다\n~~~\n\n    2. 들여쓰기 코드 블록의 단계\n"
    assert ordered(section(tilde, "단계")) == []  # Codex 3차: ~~~ 펜스와 4칸 들여쓰기
    assert not has_prose("~~~\n자막을 뽑아 요약한다\n~~~\n") and not has_prose("\n    자막을 뽑아 요약한다\n")
    mixed = "## 단계\n~~~\n~~~```\n1. 위장 단계\n~~~\n"  # Codex 4차: 혼합 펜스는 닫힘이 아니다
    assert ordered(section(mixed, "단계")) == []
    # CommonMark 4.5: 여는 펜스는 info string을 가질 수 있다(백틱 펜스의 info string에는 백틱이 못 온다) — ```python도 ~~~```도 여는 펜스다. 닫는 펜스만 info string이 없다.
    info_opens = "## 단계\n```python\n1. 코드 속 단계\n```\n~~~```\n1. 틸드 펜스 속 단계\n~~~\n1. 진짜 단계\n"
    assert ordered(section(info_opens, "단계")) == ["진짜 단계"]
    mixed_rev = "## 단계\n```\n```~~~\n1. 위장 단계\n```\n1. 진짜 단계\n"
    assert ordered(section(mixed_rev, "단계")) == ["진짜 단계"]
    nested_fence = "## 단계\n````\n```\n1. 안쪽\n```\n````\n1. 바깥 단계\n"
    assert ordered(section(nested_fence, "단계")) == ["바깥 단계"]
    good = "## 단계\n1. 도구 `changelog-diff`를 `{\"from\": …}`로 부른다\n2. 고른다\n"
    assert len(ordered(section(good, "단계"))) == 2
    assert not has_prose("<!-- 자막 요약 노트 -->\n# only a comment\n") and has_prose("자막을 뽑아 요약한다\n")


@pytest.mark.parametrize("path", PARSERS, ids=lambda p: p.parents[2].name)
def test_link_variants_are_normalized(path: Path) -> None:
    md_links = cast(Callable[[str], list[str]], load(path)["md_links"])
    text = "[a](nested.md#section) [b](<nested two.md>) [c](nested.md \"title\") [d](x.md?v=1) [e](https://x/y.html)"
    assert [t for t in md_links(text) if t.endswith(".md")] == ["nested.md", "nested two.md", "nested.md", "x.md"]
