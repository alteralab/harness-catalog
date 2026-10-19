"""config docs: 생성 구역(표식 사이)만 바뀌고 손으로 쓴 본문은 남는다."""

from __future__ import annotations

from harness_catalog_cli.config import GENERATED_BEGIN, GENERATED_END, merge_docs, render_docs


def test_fresh_file_has_title_and_table() -> None:
    out = merge_docs(None, render_docs())
    assert out.startswith("# 설정값")
    assert out.count("| `HC__") == 8
    assert GENERATED_BEGIN in out and GENERATED_END in out


def test_merge_keeps_hand_written_sections() -> None:
    existing = f"# 설정값\n\n머리말\n\n## 1. 레지스트리\n\n{GENERATED_BEGIN}\n\n| 옛 표 |\n\n{GENERATED_END}\n\n## 2. 관측\n\n손으로 쓴 절\n"
    out = merge_docs(existing, render_docs())
    assert "머리말" in out and "## 2. 관측" in out and "손으로 쓴 절" in out
    assert "| 옛 표 |" not in out
    assert out.count("| `HC__") == 8
    assert merge_docs(out, render_docs()) == out  # 멱등
