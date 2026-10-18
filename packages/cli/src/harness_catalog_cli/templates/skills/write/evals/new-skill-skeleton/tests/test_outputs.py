"""write 양성(스킬): 브랜치 skill/hello-greeting에 SKILL.md와 evals 쌍(no-trigger-* 포함)이 있고 main은 그대로다."""

import subprocess

BRANCH = "skill/hello-greeting"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def test_branch_exists() -> None:
    assert git("rev-parse", "--verify", "-q", BRANCH).returncode == 0


def test_skill_md_declares_name() -> None:
    out = git("show", f"{BRANCH}:skills/hello-greeting/SKILL.md")
    assert out.returncode == 0
    assert "name: hello-greeting" in out.stdout.splitlines()


def test_evals_pair_with_negative_case() -> None:
    cases = git("ls-tree", "--name-only", f"{BRANCH}:skills/hello-greeting/evals").stdout.split()
    assert len(cases) >= 2, cases
    assert any(c.startswith("no-trigger-") for c in cases), cases


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
