"""pin 양성: 프로젝트 범위에 내려받았는가 — PINNED 한 줄(이름 sha40 시각), SKILL.md, .claude/skills 링크, 임시 디렉토리 없음."""

import re
from pathlib import Path

SKILL = Path("/work/.agents/skills/yt-subs")
# ast-grep-ignore: regex-on-structure — 어휘: PINNED 한 줄은 고정 형식(이름·40자 hex·ISO 8601 UTC)의 정규 언어다
PINNED_LINE = re.compile(r"^yt-subs [0-9a-f]{40} [0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def test_pinned_is_one_well_formed_line() -> None:
    lines = (SKILL / "PINNED").read_text().splitlines()
    assert len(lines) == 1
    assert PINNED_LINE.match(lines[0]), lines[0]


def test_skill_body_and_claude_link() -> None:
    assert (SKILL / "SKILL.md").is_file()
    assert Path("/work/.claude/skills/yt-subs").is_symlink()


def test_no_leftover_tmp_dir() -> None:
    assert not Path("/work/.agents/skills/.yt-subs.pin-tmp").exists()
