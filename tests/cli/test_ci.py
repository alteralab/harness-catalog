"""CI 논리(ci.py): 기준 커밋·바뀐 스킬·자격·harbor 호출. 워크플로 YAML에서 CLI로 옮긴 것이 이 테스트의 대상이다."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from harness_catalog_cli import ci
from harness_catalog_cli.__main__ import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, rel: str, text: str, msg: str) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    repo = tmp_path / "catalog"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    shas = [commit(repo, "README.md", "a", "c1"), commit(repo, "skills/a/SKILL.md", "a", "c2"), commit(repo, "skills/b/SKILL.md", "b", "c3")]
    return repo, shas


def test_base_commit_github_pull_request_is_merge_base(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/main", "main")  # 러너의 checkout은 origin/main을 안다
    git(repo, "checkout", "-q", "-b", "skill/x")
    commit(repo, "skills/x/SKILL.md", "x", "c4")
    run = ci.git_runner(repo)
    assert ci.base_commit({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_REF": "main"}, run) == shas[2]


def test_base_commit_push_uses_event_before(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path)
    run = ci.git_runner(repo)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": shas[0]}))
    assert ci.base_commit({"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event)}, run) == shas[0]
    event.write_text(json.dumps({"before": ci.ZERO_SHA}))  # 브랜치 생성(첫 push) → 빈 트리: 루트 커밋의 변경까지 전부
    created = ci.base_commit({"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event)}, run)
    assert created == ci.EMPTY_TREE and ci.is_branch_creation(created, run) and not ci.is_branch_creation(shas[0], run)
    assert not ci.is_branch_creation("4b825dc6" + "0" * 32, run)  # 앞자리만 같은 id는 빈 트리가 아니다
    assert ci.changed_skill_dirs(run, created) == ("skills/a", "skills/b")
    event.write_text("not json")
    assert ci.base_commit({"GITHUB_EVENT_PATH": str(event)}, run) == shas[1]  # CI 표지 없이 이벤트만 깨졌으면 로컬 규칙
    with pytest.raises(ci.CIError):
        ci.base_commit({"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event)}, run)  # CI 안에서는 폴백 금지
    with pytest.raises(ci.CIError):
        ci.base_commit({"GITLAB_CI": "true"}, run)
    event.write_text(json.dumps({"before": "deadbeef" * 5}))  # 닿을 수 없는 before(이력 재작성) → 좁히지 않고 실패
    with pytest.raises(ci.CIError):
        ci.base_commit({"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event)}, run)


def test_base_commit_pull_request_without_remote_ref_fails_closed(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    with pytest.raises(ci.CIError):
        ci.base_commit({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_REF": "main"}, ci.git_runner(repo))


def test_base_commit_gitlab_and_fallbacks(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path)
    run = ci.git_runner(repo)
    assert ci.base_commit({"CI_MERGE_REQUEST_DIFF_BASE_SHA": shas[0]}, run) == shas[0]
    assert ci.base_commit({"CI_COMMIT_BEFORE_SHA": shas[1]}, run) == shas[1]
    with pytest.raises(ci.CIError):
        ci.base_commit({"CI_COMMIT_BEFORE_SHA": "deadbeef" * 5}, run)  # 모르는 커밋은 실패(이전 YAML은 조용히 HEAD~1)
    assert ci.base_commit({"CI_COMMIT_BEFORE_SHA": ci.ZERO_SHA}, run) == ci.EMPTY_TREE
    assert ci.base_commit({}, run) == shas[1]
    single = tmp_path / "single"
    single.mkdir()
    git(single, "init", "-q", "-b", "main")
    only = commit(single, "README.md", "a", "c1")
    assert ci.base_commit({}, ci.git_runner(single)) == only  # 첫 커밋이면 HEAD


def test_branch_creation_diff_includes_root_commit(tmp_path: Path) -> None:
    # init의 첫 push: 커밋 하나(루트)에 스킬이 들어 있고 before는 0 → 빈 트리 기준이라 루트의 스킬도 '바뀐 것'이다
    single = tmp_path / "single"
    single.mkdir()
    git(single, "init", "-q", "-b", "main")
    (single / "skills" / "s").mkdir(parents=True)
    (single / "skills" / "s" / "SKILL.md").write_text("s")
    commit(single, "README.md", "a", "root")
    run = ci.git_runner(single)
    base = ci.base_commit({"CI_COMMIT_BEFORE_SHA": ci.ZERO_SHA}, run)
    assert base == ci.EMPTY_TREE and ci.changed_skill_dirs(run, base) == ("skills/s",)


def test_base_commit_fetches_unreachable_before_from_origin(tmp_path: Path) -> None:
    upstream, shas = make_repo(tmp_path)
    git(upstream, "config", "uploadpack.allowReachableSHA1InWant", "true")  # 보통 저장소를 원격으로 쓴다. GitHub가 허용하는 것과 같은 동작
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{upstream}", str(clone)], check=True, capture_output=True)
    run = ci.git_runner(clone)
    assert not ci.commit_exists(run, shas[0])  # 얕은 클론에는 없다
    assert ci.base_commit({"CI_COMMIT_BEFORE_SHA": shas[0]}, run) == shas[0]  # fetch로 살려 낸다
    assert ci.commit_exists(run, shas[0])


def test_changed_skill_dirs(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path)
    commit(repo, "skills/a/scripts/x.py", "1", "c4")
    commit(repo, "docs/x.md", "1", "c5")
    run = ci.git_runner(repo)
    assert ci.changed_skill_dirs(run, shas[0]) == ("skills/a", "skills/b")
    assert ci.changed_skill_dirs(run, shas[2]) == ("skills/a",)
    assert ci.changed_skill_dirs(run, "HEAD") == ()
    with pytest.raises(ci.CIError):
        ci.changed_skill_dirs(run, "deadbeef" * 5)  # git 실패는 '변경 없음'이 아니다


def test_missing_credentials_table(tmp_path: Path) -> None:
    assert ci.missing_credentials("claude-code", {}) == "claude-code: CLAUDE_CODE_OAUTH_TOKEN+CLAUDE_FORCE_OAUTH=1 또는 ANTHROPIC_API_KEY"
    assert ci.missing_credentials("claude-code", {"CLAUDE_CODE_OAUTH_TOKEN": "t"}) is not None  # FORCE_OAUTH 없이는 부족
    assert ci.missing_credentials("claude-code", {"CLAUDE_CODE_OAUTH_TOKEN": "t", "CLAUDE_FORCE_OAUTH": "1"}) is None
    assert ci.missing_credentials("claude-code", {"ANTHROPIC_API_KEY": "k"}) is None
    auth = tmp_path / "auth.json"
    assert ci.missing_credentials("codex", {"CODEX_FORCE_AUTH_JSON": "1", "CODEX_AUTH_JSON_PATH": str(auth)}) is not None
    auth.write_text("{}")
    assert ci.missing_credentials("codex", {"CODEX_FORCE_AUTH_JSON": "1", "CODEX_AUTH_JSON_PATH": str(auth)}) is None
    assert ci.missing_credentials("codex", {"OPENAI_API_KEY": "k"}) is None
    assert ci.missing_credentials("cursor-cli", {}) == "cursor-cli: CURSOR_API_KEY"
    assert ci.missing_credentials("gemini-cli", {"GEMINI_FORCE_OAUTH": "1"}) is None
    assert ci.missing_credentials("aider", {}) is not None and "unknown agent" in (ci.missing_credentials("aider", {}) or "")
    assert ci.missing_langfuse({"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b"}) == "Langfuse keys missing: LANGFUSE_HOST"
    assert ci.missing_langfuse({"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b", "LANGFUSE_HOST": "h"}) is None


def test_evals_plan_two_jobs_per_skill_with_evals(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "skills" / "a" / "evals" / "c1").mkdir(parents=True)
    plan = ci.evals_plan(repo, ("skills/a", "skills/b"), "claude-code", cli_version="0.1.0", code_repo_url="https://example.com/code")
    assert len(plan) == 2  # b에는 evals/가 없다
    with_skill, baseline = plan
    assert with_skill[:3] == ("uvx", "--from", f"harbor=={ci.HARBOR_VERSION}")
    assert "harbor-langfuse @ git+https://example.com/code@v0.1.0#subdirectory=packages/harbor-langfuse" in with_skill
    assert ("--path", "skills/a/evals") == tuple(with_skill[with_skill.index("--path") : with_skill.index("--path") + 2])
    assert with_skill[-2:] == ("--skill", "./skills/a") and "--skill" not in baseline
    assert baseline.index("--plugin") > 0 and baseline[baseline.index("--plugin") + 1] == "harbor_langfuse:LangfusePlugin"


def test_evals_plan_oracle_is_one_job_without_skill_or_langfuse(tmp_path: Path) -> None:
    """CI 기본(2026-10-18): Oracle 은 스킬 주입도 플러그인도 자격도 없이 잡 하나."""
    repo, _ = make_repo(tmp_path)
    (repo / "skills" / "a" / "evals" / "c1").mkdir(parents=True)
    plan = ci.evals_plan(repo, ("skills/a", "skills/b"), ci.ORACLE, cli_version="0.1.0", code_repo_url="https://example.com/code")
    assert len(plan) == 1
    (job,) = plan
    assert job == ("uvx", "--from", f"harbor=={ci.HARBOR_VERSION}", "harbor", "run", "--path", "skills/a/evals", "--agent", "oracle", "--env", "docker")
    assert "--skill" not in job and "--plugin" not in job and "--with" not in job


def test_harbor_env_fills_skill_ref_and_catalog_name(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path)
    run = ci.git_runner(repo)
    env = ci.harbor_env({"GITHUB_REPOSITORY": "alteralab/catalog", "PATH": "/bin"}, run, repo)
    assert env[ci.SKILL_REF_ENV] == shas[2] and env[ci.CATALOG_NAME_ENV] == "catalog" and env["PATH"] == "/bin"
    env2 = ci.harbor_env({ci.SKILL_REF_ENV: "abc", "CI_PROJECT_NAME": "cat2"}, run, repo)
    assert env2[ci.SKILL_REF_ENV] == "abc" and env2[ci.CATALOG_NAME_ENV] == "cat2"
    assert ci.harbor_env({}, run, repo)[ci.CATALOG_NAME_ENV] == "catalog"  # 디렉토리 이름


def test_run_plan_runs_all_and_counts_failures(tmp_path: Path) -> None:
    seen: list[tuple[list[str], Path, str]] = []

    def execute(argv: list[str], cwd: Path, env: object) -> int:
        seen.append((argv, cwd, str(env.__class__.__name__)))
        return 1 if "fail" in argv else 0

    logs: list[str] = []
    plan = (("harbor", "ok"), ("harbor", "fail"), ("harbor", "ok2"))
    assert ci.run_plan(plan, tmp_path, {"A": "1"}, execute=execute, log=logs.append) == 1
    assert [a for a, _, _ in seen] == [list(p) for p in plan] and all(c == tmp_path for _, c, _ in seen)  # 실패해도 끝까지 돈다
    assert logs == ["$ harbor ok", "$ harbor fail", "$ harbor ok2"]


def test_cli_ci_evals_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, shas = make_repo(tmp_path)
    (repo / "skills" / "a" / "evals" / "c").mkdir(parents=True)
    runner = CliRunner()
    for k in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_FORCE_OAUTH", "ANTHROPIC_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "CI_COMMIT_BEFORE_SHA", "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "CI_MERGE_REQUEST_DIFF_BASE_SHA"):
        monkeypatch.delenv(k, raising=False)
    r = runner.invoke(app, ["evals", "--agent", "claude-code", str(repo)])
    assert r.exit_code == 1 and "CLAUDE_CODE_OAUTH_TOKEN" in r.output  # 자격 없음
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for k, v in {"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b", "LANGFUSE_HOST": "h"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CI_COMMIT_BEFORE_SHA", "deadbeef" * 5)
    r = runner.invoke(app, ["evals", "--agent", "claude-code", str(repo)])
    assert r.exit_code == 2 and "not reachable" in r.output  # 기준을 못 정하면 2
    monkeypatch.setenv("CI_COMMIT_BEFORE_SHA", shas[0])
    r = runner.invoke(app, ["evals", "--agent", "claude-code", "--dry-run", str(repo)])
    assert r.exit_code == 0 and "harbor jobs: 2" in r.output and r.output.count("$ uvx") == 2 and "--skill ./skills/a" in r.output
    for k in ("ANTHROPIC_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(k, raising=False)
    r = runner.invoke(app, ["evals", "--dry-run", str(repo)])  # 기본 oracle: 자격 없이도 돈다, 잡 하나
    assert r.exit_code == 0 and "harbor jobs: 1" in r.output and "--agent oracle" in r.output and "--skill" not in r.output and "--plugin" not in r.output
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for k, v in {"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b", "LANGFUSE_HOST": "h"}.items():
        monkeypatch.setenv(k, v)
    calls: list[list[str]] = []

    def fake_run_plan(plan: tuple[tuple[str, ...], ...], cwd: Path, env: object, **_: object) -> int:  # noqa: ARG001 — 픽스처·콜백 시그니처가 요구하는 인자
        calls.extend(list(p) for p in plan)
        return 1

    monkeypatch.setattr(ci, "run_plan", fake_run_plan)
    r = runner.invoke(app, ["evals", "--agent", "claude-code", str(repo)])
    assert r.exit_code == 1 and len(calls) == 2 and "1 harbor job(s) failed" in r.output
    monkeypatch.setenv("CI_COMMIT_BEFORE_SHA", shas[2])  # HEAD 자신이 기준이면 바뀐 스킬 없음 → 아무것도 안 하고 0
    r = runner.invoke(app, ["evals", "--agent", "claude-code", str(repo)])
    assert r.exit_code == 0 and "(none)" in r.output
