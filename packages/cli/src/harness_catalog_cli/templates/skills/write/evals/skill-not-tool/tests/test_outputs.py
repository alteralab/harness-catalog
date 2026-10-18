"""스킬을 만들라는 요청에 **절차가 있는 스킬**을 만들었는지 — 새 스킬 하나가 브랜치에 있고(이름·설명·단계·evals 쌍, scripts/ 없음), 도구는 환경에 있던 scaffold뿐이다. 빈 SKILL.md 하나로는 통과하지 않는다(Codex 2026-10-18)."""

from __future__ import annotations

import subprocess
import tomllib


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


def refs() -> list[str]:
    return [*git("for-each-ref", "--format=%(refname:short)").stdout.split(), "HEAD"]


def new_skill_on(ref: str) -> str | None:
    new = names_in(ref, "skills") - {"yt-subs"}
    return next(iter(new)) if len(new) == 1 else None


def the_ref() -> tuple[str, str]:
    found = [(r, n) for r in refs() if (n := new_skill_on(r))]
    assert found, "no ref with exactly one new skill"
    return found[0]


def test_new_skill_has_name_description_and_a_procedure_about_the_task() -> None:
    ref, name = the_ref()
    md = show(ref, f"skills/{name}/SKILL.md")
    assert md, "SKILL.md missing"
    fm = frontmatter(md)
    assert fm.get("name") == name and len(fm.get("description", "")) >= 20, fm
    steps = section(md, "단계")
    assert steps.strip(), "no 단계 section"
    assert "자막" in md and "요약" in md and "노트" in md  # 과제: 자막을 뽑고 요약해서 노트에 붙이는 순서


def test_new_skill_has_a_real_evals_pair_and_no_scripts() -> None:
    ref, name = the_ref()
    assert eval_cases_are_real(ref, name) == []
    assert git("cat-file", "-e", f"{ref}:skills/{name}/scripts").returncode != 0  # 공용 기본형


def test_no_new_tool_on_any_ref() -> None:
    for ref in refs():
        assert names_in(ref, "tools") <= {"scaffold"}, (ref, names_in(ref, "tools"))


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
