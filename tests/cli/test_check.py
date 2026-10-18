"""CLI check: 종료 코드 0/1/2와 항목 번호 출력."""

from __future__ import annotations

from typer.testing import CliRunner

from harness_catalog_cli.__main__ import app
from tests.conftest import CatalogRepo, git

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


def test_version_flag() -> None:
    r = runner.invoke(app, ["--version"])
    from importlib.metadata import version

    assert r.exit_code == 0 and r.output.strip() == version("harness-catalog-cli")  # 판은 pyproject가 정본이다(lockstep)


def test_check_reports_tool_and_server_findings(catalog_repo: CatalogRepo) -> None:
    """검사 11·12: 깨진 tool.json·server.json은 'item N: tool|server <name>:'으로 출력되고 종료 코드 1."""
    import json

    repo = catalog_repo.path
    (repo / "tools" / "bad-tool").mkdir()
    (repo / "tools" / "bad-tool" / "tool.json").write_text(json.dumps({"name": "bad-tool", "description": "x", "inputSchema": {"type": "object"}, "runtime": {"kind": "mcp", "server": "nowhere", "tool": "t"}}))
    (repo / "mcp-servers" / "bad-server").mkdir()
    (repo / "mcp-servers" / "bad-server" / "server.json").write_text(json.dumps({"name": "other", "version": "1"}))
    git(repo, "add", "-A")
    r = runner.invoke(app, ["check", str(repo)])
    assert r.exit_code == 1, r.output
    assert "error: item 11: tool bad-tool: runtime.server 'nowhere' not found" in r.output
    assert "error: item 12: server bad-server:" in r.output and "must be 'bad-server'" in r.output
    assert "yt-subs" not in r.output and "subs-fetch" not in r.output  # 멀쩡한 레코드는 조용하다
