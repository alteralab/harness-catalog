"""심사 뒤 고친 판이 브랜치에 있는지 — description이 막연하지 않고, 시간에 묶인 문장이 없고, 참조가 한 단계이고, main은 그대로."""

from __future__ import annotations

import subprocess


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def fixed_refs() -> list[str]:
    refs = [r for r in git("for-each-ref", "--format=%(refname:short)").stdout.split() if r != "main"]
    return [r for r in refs if git("diff", "--quiet", "main", r, "--", "skills/yt-subs/SKILL.md").returncode != 0]


def skill_md(ref: str) -> str:
    return git("show", f"{ref}:skills/yt-subs/SKILL.md").stdout


def test_a_branch_changed_the_skill() -> None:
    assert fixed_refs(), "no branch changed skills/yt-subs/SKILL.md"


def test_description_is_specific_and_in_third_person() -> None:
    ref = fixed_refs()[0]
    lines = [ln for ln in skill_md(ref).splitlines() if ln.startswith("description: ")]  # frontmatter 한 줄 — 구조가 아니라 접두사
    assert lines, "no description"
    desc = lines[0].removeprefix("description: ").strip()
    assert desc != "Helps with videos." and len(desc) >= 40, desc
    assert "I can" not in desc and "You can" not in desc


def test_no_time_bound_sentence_and_references_one_level_deep() -> None:
    ref = fixed_refs()[0]
    assert "2025년 8월" not in skill_md(ref)
    adv = git("show", f"{ref}:skills/yt-subs/references/advanced.md")
    if adv.returncode == 0:
        assert "details.md" not in adv.stdout  # 참조 파일이 또 참조하지 않는다


def test_name_kept_and_main_untouched() -> None:
    ref = fixed_refs()[0]
    assert "name: yt-subs" in skill_md(ref).splitlines()
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
