"""스킬을 만들라는 요청에 **절차가 있는 스킬**을 만들었는지 — 새 스킬 하나가 브랜치에 있고(이름·설명·순서 단계·evals 쌍, scripts/ 없음), 도구는 환경에 있던 scaffold뿐이다. 빈 SKILL.md·주석만 있는 절차·주석만 있는 eval 파일로는 통과하지 않는다(Codex 2026-10-18)."""

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


def strip_markup(text: str) -> str:
    """HTML 주석(<!-- -->)과 펜스 코드 블록(```)을 지운다 — 주석·코드 안의 낱말은 절차가 아니다(Codex 2026-10-18)."""
    out: list[str] = []
    rest = text
    while "<!--" in rest:
        before, _, rest = rest.partition("<!--")
        out.append(before)
        _, _, rest = rest.partition("-->")
    out.append(rest)
    joined = "".join(out)
    kept: list[str] = []
    fence = ""  # 열린 펜스(``` 또는 ~~~, 같은 글자·같거나 긴 길이로 닫힌다)
    prev_blank = True
    for ln in joined.splitlines():
        s = ln.strip()
        ch = s[0] if s and s[0] in "`~" else ""
        run = s[: len(s) - len(s.lstrip(ch))] if ch else ""  # 한 글자의 반복만 펜스다 — ~~~``` 는 펜스가 아니다(Codex 4차)
        if fence:
            if run and run[0] == fence[0] and len(run) >= len(fence) and s == run:
                fence = ""
            continue
        if len(run) >= 3 and not (ch == "`" and "`" in s[len(run):]):  # 백틱 펜스의 info string에는 백틱이 못 온다(CommonMark 4.5)
            fence = run
            continue
        if prev_blank and (ln.startswith("    ") or ln.startswith("\t")) and s:
            continue  # 들여쓰기 코드 블록(빈 줄 뒤 4칸·탭)
        prev_blank = not s
        kept.append(ln)
    return "\n".join(kept)


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
    """`## <heading>`부터 다음 `## ` 전까지, 주석·코드 블록을 뺀 본문."""
    body: list[str] = []
    keep = False
    for ln in strip_markup(md).splitlines():
        if ln.startswith("## "):
            keep = ln[3:].strip() == heading
            continue
        if keep:
            body.append(ln)
    return "\n".join(body)


def ordered_items(text: str) -> list[str]:
    """`1. …` 꼴의 순서 항목 줄들."""
    items: list[str] = []
    for ln in text.splitlines():
        head, dot, rest = ln.strip().partition(". ")
        if dot and head.isdigit() and rest.strip():
            items.append(rest.strip())
    return items


def has_prose(text: str) -> bool:
    """주석·공백·셸 주석줄을 뺀 글자가 있는가."""
    lines = [ln for ln in strip_markup(text).splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return any(any(ch.isalnum() for ch in ln) for ln in lines)


def eval_cases_are_real(ref: str, skill: str) -> list[str]:
    """evals/<case>/에 task.toml(TOML)·instruction.md(산문)·tests/test.sh(shebang + 검증 명령)가 있고 양성·no-trigger 둘 다 있는지. 틀린 점을 돌려준다."""
    cases = sorted(names_in(ref, f"skills/{skill}/evals"))
    problems: list[str] = []
    if len(cases) < 2 or not any(c.startswith("no-trigger-") for c in cases) or all(c.startswith("no-trigger-") for c in cases):
        problems.append(f"need a positive and a no-trigger case, got {cases}")
    for c in cases:
        toml = show(ref, f"skills/{skill}/evals/{c}/task.toml") or ""
        try:
            tomllib.loads(toml)
        except tomllib.TOMLDecodeError as e:
            problems.append(f"{c}/task.toml not TOML: {e}")
        if not has_prose(show(ref, f"skills/{skill}/evals/{c}/instruction.md") or ""):
            problems.append(f"{c}/instruction.md has no prose")
        sh = show(ref, f"skills/{skill}/evals/{c}/tests/test.sh") or ""
        if not sh.startswith("#!") or not ("pytest" in sh or "reward.txt" in sh):
            problems.append(f"{c}/tests/test.sh is not a runnable verifier")
    return problems


def md_links(text: str) -> list[str]:
    """마크다운 링크의 대상 경로 — `](` 뒤를 읽어 `<…>`·제목(" ")·#fragment·?query를 벗긴다(정규식 없이)."""
    out: list[str] = []
    rest = text
    while "](" in rest:
        _, _, rest = rest.partition("](")
        raw, _, rest = rest.partition(")")
        dest = raw.strip()
        if dest.startswith("<") and ">" in dest:
            dest = dest[1 : dest.index(">")]
        else:
            dest = dest.split()[0] if dest.split() else ""
        dest = dest.partition("#")[0].partition("?")[0]
        out.append(dest)
    return out


def refs() -> list[str]:
    return [*git("for-each-ref", "--format=%(refname:short)").stdout.split(), "HEAD"]


def new_skill_on(ref: str) -> str | None:
    new = names_in(ref, "skills") - names_in("main", "skills")  # 기준은 main(기본 스킬 셋 + yt-subs)
    return next(iter(new)) if len(new) == 1 else None


def the_ref() -> tuple[str, str]:
    found = [(r, n) for r in refs() if (n := new_skill_on(r))]
    assert found, "no ref with exactly one new skill"
    return found[0]


def test_new_skill_has_name_description_and_ordered_steps_about_the_task() -> None:
    ref, name = the_ref()
    md = show(ref, f"skills/{name}/SKILL.md")
    assert md, "SKILL.md missing"
    fm = frontmatter(md)
    assert fm.get("name") == name and len(fm.get("description", "")) >= 20, fm
    steps = ordered_items(section(md, "단계"))
    assert len(steps) >= 2, steps
    plain = strip_markup(md)
    assert "자막" in plain and "요약" in plain and "노트" in plain  # 과제: 자막을 뽑고 요약해서 노트에 붙이는 순서


def test_new_skill_has_a_real_evals_pair_and_no_scripts() -> None:
    ref, name = the_ref()
    assert eval_cases_are_real(ref, name) == []
    assert git("cat-file", "-e", f"{ref}:skills/{name}/scripts").returncode != 0  # 공용 기본형


def test_no_new_tool_on_any_ref() -> None:
    for ref in refs():
        assert names_in(ref, "tools") <= names_in("main", "tools"), (ref, names_in(ref, "tools"))


def test_main_untouched() -> None:
    assert git("rev-parse", "main").stdout.strip() == open("/work/main.sha").read().strip()  # noqa: PTH123, SIM115
