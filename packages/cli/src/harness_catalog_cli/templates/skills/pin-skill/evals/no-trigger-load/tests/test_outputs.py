"""pin-skill 음성: 세션에 잠깐 넣는 요청(load_skill)에는 내려받지 않는다 — 디렉토리도 PINNED도 없어야 한다."""

from pathlib import Path


def test_nothing_was_downloaded() -> None:
    for p in (Path("/work/.agents/skills/yt-subs"), Path("/work/.claude/skills/yt-subs"), Path.home() / ".agents/skills/yt-subs"):
        assert not p.exists(), p
