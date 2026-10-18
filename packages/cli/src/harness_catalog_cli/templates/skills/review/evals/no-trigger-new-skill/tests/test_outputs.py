"""새 스킬 요청에 review가 끼어들지 않았는지 — yt-subs는 어느 ref에서도 그대로이고 review/ 브랜치가 없다."""

from __future__ import annotations

import subprocess


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def test_yt_subs_untouched_on_every_ref() -> None:
    for ref in [*git("for-each-ref", "--format=%(refname:short)").stdout.split(), "HEAD"]:
        assert git("diff", "--quiet", "main", ref, "--", "skills/yt-subs").returncode == 0, ref


def test_no_review_branch() -> None:
    assert not [r for r in git("for-each-ref", "--format=%(refname:short)").stdout.split() if r.startswith("review/")]
