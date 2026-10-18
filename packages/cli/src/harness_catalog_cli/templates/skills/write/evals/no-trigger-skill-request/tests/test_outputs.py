"""write 음성(도구): 스킬 요청에 tools/ 디렉토리를 만들지 않는다 — 어느 ref에도, 작업 트리에도."""

import subprocess
from pathlib import Path


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def test_no_tools_dir_in_any_ref() -> None:
    refs = git("for-each-ref", "--format=%(refname:short)").stdout.split()
    for ref in [*refs, "HEAD"]:
        assert git("cat-file", "-e", f"{ref}:tools").returncode != 0, ref


def test_no_tools_dir_in_worktree() -> None:
    assert not Path("/work/catalog/tools").exists()
