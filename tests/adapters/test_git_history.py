"""얕은 클론은 은퇴 이름 검사를 통과로 돌리지 않는다(fail-closed) — CLI는 종료 2."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_catalog_cli.__main__ import app
from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.model import ContentError
from tests.conftest import CatalogRepo, commit_all, write_skill


def test_shallow_clone_fails_closed(tmp_path: Path, catalog_repo: CatalogRepo) -> None:
    repo = catalog_repo.path
    write_skill(repo, "third", "third skill")
    commit_all(repo, "third")
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow)], check=True)
    store = GitStore.local(shallow)
    with pytest.raises(ContentError):
        store.deleted_skill_names(store.resolve("HEAD"))
    r = CliRunner().invoke(app, ["check", str(shallow), "--rev", "HEAD", "--base", "HEAD"])
    assert r.exit_code == 2 and "shallow" in r.output
