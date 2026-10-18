"""release-notes 스킬이 있는 도구 changelog-diff를 **단계의 순서 항목에서 이름과 입력으로** 엮었는지 — 도구를 복사하거나 새로 만들지 않고, 스킬에 scripts/를 두지 않고, evals 쌍이 실제 파일을 갖는지. 주석·코드 블록 속 이름으로는 통과하지 않는다(Codex 2026-10-18)."""

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
        run = s[: len(s) - len(s.lstrip("`~"))]
        if fence:
            if run and run[0] == fence[0] and len(run) >= len(fence) and s == run:
                fence = ""
            continue
        if len(run) >= 3 and (run.startswith("```") or run.startswith("~~~")):
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


def test_branch_exists() -> None:
    assert git("rev-parse", "--verify", "-q", BRANCH).returncode == 0


def test_skill_calls_the_existing_tool_by_name_in_an_ordered_step() -> None:
    md = show(BRANCH, "skills/release-notes/SKILL.md")
    assert md, "SKILL.md missing"
    fm = frontmatter(md)
    assert fm.get("name") == "release-notes" and len(fm.get("description", "")) >= 20, fm
    calls = [s for s in ordered_items(section(md, "단계")) if "도구 `changelog-diff`" in s and "{" in s]
    assert calls, "no ordered step that calls the tool by name with an input object"


def test_tool_is_neither_duplicated_nor_replaced() -> None:
    assert names_in(BRANCH, "tools") == {"scaffold", "changelog-diff"}
    assert git("diff", "--quiet", "main", BRANCH, "--", "tools/changelog-diff").returncode == 0


def test_skill_has_no_scripts_dir_and_a_real_evals_pair() -> None:
    assert git("cat-file", "-e", f"{BRANCH}:skills/release-notes/scripts").returncode != 0
    assert eval_cases_are_real(BRANCH, "release-notes") == []


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
