"""write 음성(스킬): 기존 스킬의 한 줄 수정에 새 skills/* 디렉토리를 만들지 않는다 — 어느 ref에도, 작업 트리에도."""

import subprocess
from pathlib import Path


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def skills_in(ref: str) -> set[str]:
    out = git("ls-tree", "--name-only", f"{ref}:skills")
    return set(out.stdout.split()) if out.returncode == 0 else set()


def test_no_new_skill_in_any_ref() -> None:
    refs = git("for-each-ref", "--format=%(refname:short)").stdout.split()
    for ref in [*refs, "HEAD"]:
        assert skills_in(ref) <= {"yt-subs"}, (ref, skills_in(ref))


def test_no_new_skill_in_worktree() -> None:
    assert {p.name for p in Path("/work/catalog/skills").iterdir() if p.is_dir()} <= {"yt-subs"}
