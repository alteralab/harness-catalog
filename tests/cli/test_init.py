"""init: 빈 bare 저장소를 세우고 두 번째 실행은 변경 0. 호스트 판별. 표지 layout 불일치는 종료 1."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_catalog_cli.__main__ import app
from harness_catalog_cli.init import InitError, detect_host, init_repository
from tests.conftest import git

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
    with pytest.raises(InitError):
        detect_host("https://bitbucket.org/x/y")


def test_init_twice_is_idempotent(tmp_path: Path) -> None:
    remote = bare(tmp_path, "catalog.git")
    first = init_repository(str(remote), pin="deadbeef", host="gitlab")  # 로컬 경로는 호스트가 없다
    assert set(first.written) == {".harness-catalog", "skills/.gitkeep", "README.md", ".pre-commit-config.yaml", ".gitlab-ci.yml"}
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
    wf = git(remote, "show", "main:.github/workflows/check.yml")
    assert "@v1.2.3#subdirectory=packages/cli" in wf and "HARNESS_EVALS" in wf


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
    assert d.exit_code == 0 and (tmp_path / "docs" / "configuration.md").read_text().count("| `HC__") == 6
    assert "HC__PUBLIC_URL=" in d.output
