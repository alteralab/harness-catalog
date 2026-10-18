"""release-notes 스킬이 있는 도구 changelog-diff를 **이름으로** 엮었는지 — 도구를 복사하거나 새로 만들지 않고, 스킬에 scripts/를 두지 않고."""

from __future__ import annotations

import subprocess

BRANCH = "skill/release-notes"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def test_branch_exists() -> None:
    assert git("rev-parse", "--verify", "-q", BRANCH).returncode == 0


def test_skill_calls_the_existing_tool_by_name() -> None:
    out = git("show", f"{BRANCH}:skills/release-notes/SKILL.md")
    assert out.returncode == 0
    assert "name: release-notes" in out.stdout.splitlines()
    assert "`changelog-diff`" in out.stdout


def test_tool_is_neither_duplicated_nor_replaced() -> None:
    tools = set(git("ls-tree", "--name-only", f"{BRANCH}:tools").stdout.split())
    assert tools == {"scaffold", "changelog-diff"}, tools
    assert git("diff", "--quiet", "main", BRANCH, "--", "tools/changelog-diff").returncode == 0


def test_skill_has_no_scripts_dir() -> None:
    assert git("cat-file", "-e", f"{BRANCH}:skills/release-notes/scripts").returncode != 0


def test_evals_pair_with_negative_case() -> None:
    cases = git("ls-tree", "--name-only", f"{BRANCH}:skills/release-notes/evals").stdout.split()
    assert len(cases) >= 2 and any(c.startswith("no-trigger-") for c in cases), cases


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
