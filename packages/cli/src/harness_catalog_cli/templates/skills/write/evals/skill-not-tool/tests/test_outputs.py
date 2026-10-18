"""스킬을 만들라는 요청에 스킬을 만들었는지 — 새 스킬이 브랜치에 생겼고, 도구는 환경에 있던 scaffold뿐이다."""

from __future__ import annotations

import subprocess


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def names_in(ref: str, top: str) -> set[str]:
    out = git("ls-tree", "--name-only", f"{ref}:{top}")
    return set(out.stdout.split()) if out.returncode == 0 else set()


def refs() -> list[str]:
    return [*git("for-each-ref", "--format=%(refname:short)").stdout.split(), "HEAD"]


def test_a_new_skill_with_skill_md_exists_on_some_ref() -> None:
    found: list[tuple[str, str]] = []
    for ref in refs():
        for name in names_in(ref, "skills") - {"yt-subs"}:
            if git("cat-file", "-e", f"{ref}:skills/{name}/SKILL.md").returncode == 0:
                found.append((ref, name))
    assert found, "no new skill with SKILL.md on any ref"


def test_no_new_tool_on_any_ref_or_in_worktree() -> None:
    for ref in refs():
        assert names_in(ref, "tools") <= {"scaffold"}, (ref, names_in(ref, "tools"))


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
