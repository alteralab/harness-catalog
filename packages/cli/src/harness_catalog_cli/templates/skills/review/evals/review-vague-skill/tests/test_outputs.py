"""심사 뒤 고친 판이 브랜치에 있는지 — 심은 위반 넷(A1 막연한 description, B2 두 단계 참조, C4 시간 문장, D2 이유 없는 scripts/)이 모두 해소되고 main은 그대로. 링크 변형(<…>·제목·#·?)과 주석 속 낱말로는 통과하지 않는다(Codex 2026-10-18)."""

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
        if len(run) >= 3:
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


def fixed_refs() -> list[str]:
    refs = [r for r in git("for-each-ref", "--format=%(refname:short)").stdout.split() if r != "main"]
    return [r for r in refs if git("diff", "--quiet", "main", r, "--", "skills/yt-subs").returncode != 0]


def test_a_branch_changed_the_skill() -> None:
    assert fixed_refs(), "no branch changed skills/yt-subs"


def test_a1_description_is_specific_third_person_and_about_subtitles() -> None:
    md = show(fixed_refs()[0], "skills/yt-subs/SKILL.md") or ""
    desc = frontmatter(md).get("description", "")
    assert desc != "Helps with videos." and len(desc) >= 40 and "자막" in desc, desc
    assert "I can" not in desc and "You can" not in desc


def test_b2_references_are_one_level_deep() -> None:
    ref = fixed_refs()[0]
    for name in names_in(ref, "skills/yt-subs/references"):
        text = strip_markup(show(ref, f"skills/yt-subs/references/{name}") or "")
        assert not [t for t in md_links(text) if t.endswith(".md")], (name, md_links(text))


def test_c4_no_time_bound_sentence() -> None:
    assert "2025년 8월" not in strip_markup(show(fixed_refs()[0], "skills/yt-subs/SKILL.md") or "")


def test_d2_scripts_removed_or_justified_as_session_only() -> None:
    ref = fixed_refs()[0]
    if git("cat-file", "-e", f"{ref}:skills/yt-subs/scripts").returncode == 0:
        assert "세션 전용" in strip_markup(show(ref, "skills/yt-subs/SKILL.md") or "")  # conventions §1: 왜 세션 전용인지 한 줄


def test_name_kept_and_main_untouched() -> None:
    assert frontmatter(show(fixed_refs()[0], "skills/yt-subs/SKILL.md") or "").get("name") == "yt-subs"
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
