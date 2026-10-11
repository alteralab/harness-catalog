"""write-tool 양성: 브랜치 tool/subs-fetch에 tool.json(계약 모양)과 runtime.path가 가리키는 스크립트가 있고 main은 그대로다."""

import json
import subprocess
from typing import Any

BRANCH = "tool/subs-fetch"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", "/work/catalog", *args], capture_output=True, text=True, check=False)


def spec() -> dict[str, Any]:
    out = git("show", f"{BRANCH}:tools/subs-fetch/tool.json")
    assert out.returncode == 0, out.stderr
    data: dict[str, Any] = json.loads(out.stdout)
    return data


def test_branch_exists() -> None:
    assert git("rev-parse", "--verify", "-q", BRANCH).returncode == 0


def test_tool_json_shape() -> None:
    s = spec()
    assert s["name"] == "subs-fetch" and s["description"]
    assert s["inputSchema"]["type"] == "object"
    rt = s["runtime"]
    assert rt["kind"] == "script" and rt["command"].count(rt["path"]) == 1
    assert set(s) <= {"$schema", "name", "description", "inputSchema", "runtime", "metadata"}


def test_script_exists_at_runtime_path() -> None:
    path = spec()["runtime"]["path"]
    assert git("cat-file", "-e", f"{BRANCH}:tools/subs-fetch/{path}").returncode == 0


def test_no_skill_was_made_instead() -> None:
    assert git("cat-file", "-e", f"{BRANCH}:skills/subs-fetch").returncode != 0


def test_main_untouched() -> None:
    assert git("rev-list", "--count", "main").stdout.strip() == "1"
