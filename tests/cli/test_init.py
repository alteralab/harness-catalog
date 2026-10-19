"""init: 빈 bare 저장소를 세우고 두 번째 실행은 변경 0. 호스트 판별. 표지 layout 불일치는 종료 1."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from harness_catalog_cli.__main__ import app
from harness_catalog_cli.init import InitError, detect_host, init_repository
from harness_catalog_core.toolbox import tool_json_schema
from typer.testing import CliRunner

from tests.conftest import git

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def bare(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(repo)], check=True)
    return repo


def listing(remote: Path) -> set[str]:
    return set(git(remote, "ls-tree", "-r", "--name-only", "main").split())


def test_detect_host() -> None:
    assert detect_host("https://github.com/alteralab/catalog.git") == "github"
    assert detect_host("git@github.com:alteralab/catalog.git") == "github"
    assert detect_host("https://gitlab.example.com/team/catalog") == "gitlab"
    for bad in ("https://bitbucket.org/x/y", "https://evilgithub.example/x/y", "https://notgitlab.example/x/y", "https://github.evil.com/x/y"):
        with pytest.raises(InitError):
            detect_host(bad)


def test_init_refuses_repo_without_main(tmp_path: Path) -> None:
    remote = bare(tmp_path, "nomain.git")
    work = tmp_path / "w"
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)
    git(work, "checkout", "-q", "-b", "develop")
    (work / "x").write_text("x")
    git(work, "add", "-A")
    subprocess.run(["git", "-C", str(work), "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", "x"], check=True)
    git(work, "push", "-q", "origin", "develop")
    git(remote, "symbolic-ref", "HEAD", "refs/heads/develop")
    with pytest.raises(InitError, match="no 'main' branch"):
        init_repository(str(remote), pin="x", host="github")


def test_init_twice_is_idempotent(tmp_path: Path) -> None:
    remote = bare(tmp_path, "catalog.git")
    first = init_repository(str(remote), pin="deadbeef", host="gitlab")  # 로컬 경로는 호스트가 없다
    base = {".harness-catalog", "README.md", ".pre-commit-config.yaml", ".gitignore", ".gitlab-ci.yml", "schemas/tool.schema.json", ".mcp.json"}  # 스키마는 core ToolSpec의 산출물, .mcp.json은 toolbox 항목(§11 2026-10-18)
    skills = {w for w in first.written if w.startswith(("skills/", "tools/"))}
    assert set(first.written) - skills == base
    # 기본 스킬 셋이 init과 함께 들어간다(DESIGN §11 2026-10-10·2026-10-11). .gitkeep은 더 쓰지 않는다
    assert {"skills/pin/SKILL.md", "skills/write/SKILL.md", "skills/review/SKILL.md", "tools/scaffold/tool.json", "tools/scaffold/scripts/scaffold.py"} <= skills and "skills/.gitkeep" not in skills
    assert all(w.startswith(("skills/pin/", "skills/write/", "skills/review/", "tools/scaffold/")) for w in skills)
    schema = json.loads(git(remote, "show", "main:schemas/tool.schema.json"))
    assert schema == tool_json_schema() and schema["additionalProperties"] is False and "$schema" in schema["properties"]
    assert listing(remote) == set(first.written)
    second = init_repository(str(remote), pin="deadbeef", host="gitlab")
    assert second.written == ()
    assert git(remote, "rev-list", "--count", "main") == "1"
    pre = git(remote, "show", "main:.pre-commit-config.yaml")
    assert "@vdeadbeef#subdirectory=packages/cli" in pre and "<판>" not in pre


def test_init_github_url_gets_actions_workflow(tmp_path: Path) -> None:
    remote = bare(tmp_path, "gh.git")
    r = init_repository(str(remote), pin="1.2.3", host="github")
    assert ".github/workflows/check.yml" in r.written and ".gitlab-ci.yml" not in r.written
    assert ".github/actions/code-repo-credentials/action.yml" in r.written  # 자격 주입은 로컬 composite action 하나(check·evals 잡이 공유)
    wf = git(remote, "show", "main:.github/workflows/check.yml")
    assert "@v1.2.3#subdirectory=packages/cli" in wf and "harness-catalog evals" in wf and "HARNESS_EVALS" not in wf  # CI evals 는 Oracle, 켜는 변수 없음(2026-10-18)


def test_init_stops_on_layout_mismatch(tmp_path: Path) -> None:
    remote = bare(tmp_path, "old.git")
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)
    git(work, "checkout", "-q", "-b", "main")
    (work / ".harness-catalog").write_text("layout = 2\n")
    git(work, "add", "-A")
    subprocess.run(["git", "-C", str(work), "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", "old layout"], check=True)
    git(work, "push", "-q", "origin", "main")
    r = runner.invoke(app, ["init", str(remote), "--pin", "x", "--host", "github"])
    assert r.exit_code == 1 and "layout 2" in r.output


def test_config_list_and_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HC__OIDC_ISSUER", "http://issuer")
    monkeypatch.setenv("HC__GIT_DEPLOY_KEY", "secret-pem")
    monkeypatch.delenv("HC__CATALOG_REPO_URL", raising=False)
    r = runner.invoke(app, ["config", "list"])
    assert r.exit_code == 0
    assert "HC__OIDC_ISSUER                  env      http://issuer" in r.output
    assert "********" in r.output and "secret-pem" not in r.output
    assert "HC__CATALOG_REPO_URL             missing" in r.output
    assert "HC__FETCH_INTERVAL_SECONDS       default  60" in r.output
    d = runner.invoke(app, ["config", "docs", "--out-dir", str(tmp_path / "docs")])
    assert d.exit_code == 0 and (tmp_path / "docs" / "configuration.md").read_text().count("| `HC__") == 8
    assert "HC__PUBLIC_URL=" in d.output


def test_init_refresh_rewrites_stale_schema_only(tmp_path: Path) -> None:
    """--refresh: 생성 스키마가 낡았으면 그 파일만 다시 쓰고 커밋한다. 그 밖은 여전히 없는 것만."""
    remote = bare(tmp_path, "catalog.git")
    init_repository(str(remote), pin="deadbeef", host="gitlab")
    work = tmp_path / "w"
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)
    (work / "schemas" / "tool.schema.json").write_text("{}\n")
    (work / "README.md").write_text("edited by the team\n")
    git(work, "add", "-A")
    subprocess.run(["git", "-C", str(work), "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", "stale"], check=True)
    git(work, "push", "-q", "origin", "main")
    assert init_repository(str(remote), pin="deadbeef", host="gitlab").written == ()  # refresh 없이는 변경 0
    refreshed = init_repository(str(remote), pin="deadbeef", host="gitlab", refresh=True)
    assert refreshed.written == ("schemas/tool.schema.json",)
    assert json.loads(git(remote, "show", "main:schemas/tool.schema.json")) == tool_json_schema()
    assert git(remote, "show", "main:README.md").strip() == "edited by the team"  # 사람이 고친 파일은 건드리지 않는다
    assert json.loads(git(remote, "show", "main:.mcp.json"))["mcpServers"]["toolbox"]["args"] == ["toolbox", "./tools"]
