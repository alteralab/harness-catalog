"""release-notes 스킬이 있는 도구 changelog-diff를 **단계 절에서 이름으로** 엮었는지 — 도구를 복사하거나 새로 만들지 않고, 스킬에 scripts/를 두지 않고, evals 쌍이 실제 파일을 갖는지(Codex 2026-10-18: 문자열 하나·빈 디렉토리로는 통과하지 않는다)."""

from __future__ import annotations

import subprocess
import tomllib

BRANCH = "skill/release-notes"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def names_in(ref: str, top: str) -> set[str]:
    out = git("ls-tree", "--name-only", f"{ref}:{top}")
    return set(out.stdout.split()) if out.returncode == 0 else set()


def show(ref: str, path: str) -> str | None:
    out = git("show", f"{ref}:{path}")
    return out.stdout if out.returncode == 0 else None


def frontmatter(md: str) -> dict[str, str]:
    """SKILL.md 머리의 `---` 블록을 key: value로 읽는다(YAML 파서 없이 — 한 줄 스칼라만 쓴다는 팀 규약)."""
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for ln in lines[1:]:
        if ln.strip() == "---":
            return out
        key, sep, val = ln.partition(":")
        if sep:
            out[key.strip()] = val.strip()
    return {}


def section(md: str, heading: str) -> str:
    """`## <heading>`부터 다음 `## ` 전까지."""
    body: list[str] = []
    keep = False
    for ln in md.splitlines():
        if ln.startswith("## "):
            keep = ln[3:].strip() == heading
            continue
        if keep:
            body.append(ln)
    return "\n".join(body)


def eval_cases_are_real(ref: str, skill: str) -> list[str]:
    """evals/<case>/에 task.toml·instruction.md·tests/test.sh가 있고, 양성·no-trigger 둘 다 있는지. 틀린 점을 돌려준다."""
    cases = sorted(names_in(ref, f"skills/{skill}/evals"))
    problems: list[str] = []
    if len(cases) < 2 or not any(c.startswith("no-trigger-") for c in cases) or all(c.startswith("no-trigger-") for c in cases):
        problems.append(f"need a positive and a no-trigger case, got {cases}")
    for c in cases:
        for f in ("task.toml", "instruction.md", "tests/test.sh"):
            text = show(ref, f"skills/{skill}/evals/{c}/{f}")
            if not text or not text.strip():
                problems.append(f"{c}/{f} missing or empty")
        toml = show(ref, f"skills/{skill}/evals/{c}/task.toml") or ""
        try:
            tomllib.loads(toml)
        except tomllib.TOMLDecodeError as e:
            problems.append(f"{c}/task.toml not TOML: {e}")
    return problems


def test_branch_exists() -> None:
    assert git("rev-parse", "--verify", "-q", BRANCH).returncode == 0


def test_skill_calls_the_existing_tool_by_name_in_its_steps() -> None:
    md = show(BRANCH, "skills/release-notes/SKILL.md")
    assert md, "SKILL.md missing"
    fm = frontmatter(md)
    assert fm.get("name") == "release-notes" and len(fm.get("description", "")) >= 20, fm
    steps = section(md, "단계")
    assert "도구 `changelog-diff`" in steps, steps  # 호출은 단계 절에, 이름으로


def test_tool_is_neither_duplicated_nor_replaced() -> None:
    assert names_in(BRANCH, "tools") == {"scaffold", "changelog-diff"}
    assert git("diff", "--quiet", "main", BRANCH, "--", "tools/changelog-diff").returncode == 0


def test_skill_has_no_scripts_dir_and_a_real_evals_pair() -> None:
    assert git("cat-file", "-e", f"{BRANCH}:skills/release-notes/scripts").returncode != 0
    assert eval_cases_are_real(BRANCH, "release-notes") == []


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
