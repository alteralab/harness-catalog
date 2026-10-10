"""CLI check: 종료 코드 0/1/2와 항목 번호 출력."""

from __future__ import annotations

from typer.testing import CliRunner

from harness_catalog_cli.__main__ import app
from tests.conftest import CatalogRepo, commit_all, git, write_skill

runner = CliRunner()


def test_check_passes_on_fixture(catalog_repo: CatalogRepo) -> None:
    r = runner.invoke(app, ["check", str(catalog_repo.path), "--rev", "HEAD"])
    assert r.exit_code == 0, r.output


def test_check_reports_violation_and_staged_tree(catalog_repo: CatalogRepo) -> None:
    repo = catalog_repo.path
    bad = repo / "skills" / "Bad_Name"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: Bad_Name\ndescription: x\n---\n")
    git(repo, "add", "-A")
    r = runner.invoke(app, ["check", str(repo)])  # 기본 --rev INDEX: 스테이징된 트리
    assert r.exit_code == 1 and "item 3" in r.output and "Bad_Name" in r.output
    r_head = runner.invoke(app, ["check", str(repo), "--rev", "HEAD"])
    assert r_head.exit_code == 0


def test_check_name_reuse_against_base(catalog_repo: CatalogRepo) -> None:
    repo = catalog_repo.path
    base = catalog_repo.head
    (repo / "skills" / "pin-skill" / "SKILL.md").unlink()
    (repo / "skills" / "pin-skill").rmdir()
    retired = commit_all(repo, "retire pin-skill without replaced-by")
    r = runner.invoke(app, ["check", str(repo), "--rev", "HEAD", "--base", base])
    assert r.exit_code == 0 and "warning: item 9" in r.output
    write_skill(repo, "pin-skill", "reused name")
    commit_all(repo, "reuse name")
    r2 = runner.invoke(app, ["check", str(repo), "--rev", "HEAD", "--base", retired])
    assert r2.exit_code == 1 and "item 5" in r2.output


def test_version_flag() -> None:
    r = runner.invoke(app, ["--version"])
    from importlib.metadata import version

    assert r.exit_code == 0 and r.output.strip() == version("harness-catalog-cli")  # 판은 pyproject가 정본이다(lockstep)
