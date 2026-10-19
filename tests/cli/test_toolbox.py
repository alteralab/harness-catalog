"""hc toolbox: tools/*/tool.json → MCP 도구. 로드·검증·실행·결과 모양, 그리고 stdio 끝에서 끝(실제 서브프로세스로 띄워 MCP 클라이언트로 부른다)."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest
from harness_catalog_cli import toolbox

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT = """# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
import json, sys
args = json.load(sys.stdin)
if args.get("fail"):
    print("boom", file=sys.stderr)
    sys.exit(3)
if args.get("garbage"):
    print("not json")
    sys.exit(0)
print(json.dumps({"echo": args["text"], "n": len(args["text"])}))
"""


def write_tool(root: Path, name: str, *, output_schema: bool = True, command: list[str] | None = None, kind: str = "script") -> Path:
    d = root / name
    (d / "scripts").mkdir(parents=True)
    (d / "scripts" / "run.py").write_text(SCRIPT)
    spec: dict[str, object] = {
        "name": name, "description": f"{name} echoes text",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "fail": {"type": "boolean"}, "garbage": {"type": "boolean"}}, "required": ["text"], "additionalProperties": False},
        "runtime": {"kind": kind, "path": "scripts/run.py", "command": command or [sys.executable, "scripts/run.py"]} if kind == "script" else {"kind": "mcp", "server": "x", "tool": "y"},
    }
    if output_schema:
        spec["outputSchema"] = {"type": "object", "properties": {"echo": {"type": "string"}, "n": {"type": "integer"}}, "required": ["echo", "n"]}
    (d / "tool.json").write_text(json.dumps(spec))
    return d


def test_load_skips_broken_and_mcp(tmp_path: Path) -> None:
    write_tool(tmp_path, "echo")
    write_tool(tmp_path, "remote", kind="mcp")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "tool.json").write_text("{not json")
    (tmp_path / "noentry").mkdir()
    (tmp_path / "noentry" / "tool.json").write_text(json.dumps({"name": "noentry", "description": "d", "inputSchema": {"type": "object"}, "runtime": {"kind": "script", "path": "scripts/x.py", "command": ["python", "scripts/x.py"]}}))
    tools, skipped = toolbox.load_tools(tmp_path)
    assert list(tools) == ["echo"] and len(tools["echo"].entry_sha256) == 64
    assert sorted(s.split(":")[0] for s in skipped) == ["broken", "noentry", "remote"]
    assert [t.name for t in toolbox.mcp_tools(tools)] == ["echo"] and toolbox.mcp_tools(tools)[0].output_schema is not None


def test_call_validates_input_runs_and_validates_output(tmp_path: Path) -> None:
    write_tool(tmp_path, "echo")
    tools, _ = toolbox.load_tools(tmp_path)
    tool = tools["echo"]
    ok = toolbox.call(tool, {"text": "hi"})
    assert not ok.is_error and ok.structured_content == {"echo": "hi", "n": 2} and json.loads(ok.content[0].text) == {"echo": "hi", "n": 2}  # type: ignore[union-attr]
    bad_input = toolbox.call(tool, {"nope": 1})
    assert bad_input.is_error and "input rejected" in bad_input.content[0].text  # type: ignore[union-attr]
    failed = toolbox.call(tool, {"text": "x", "fail": True})
    assert failed.is_error and "exit 3" in failed.content[0].text and "boom" in failed.content[0].text  # type: ignore[union-attr]
    garbage = toolbox.call(tool, {"text": "x", "garbage": True})
    assert garbage.is_error and "not JSON" in garbage.content[0].text  # type: ignore[union-attr]  # fail-closed


def test_text_tool_without_output_schema_and_hash_pin(tmp_path: Path) -> None:
    d = write_tool(tmp_path, "plain", output_schema=False)
    tools, _ = toolbox.load_tools(tmp_path)
    res = toolbox.call(tools["plain"], {"text": "ab"})
    assert not res.is_error and res.structured_content is None and '"echo": "ab"' in res.content[0].text  # type: ignore[union-attr]
    (d / "scripts" / "run.py").write_text(SCRIPT + "\n# changed\n")  # 실행물이 바뀌면 재시작 전까지 거부(해시 고정)
    changed = toolbox.call(tools["plain"], {"text": "ab"})
    assert changed.is_error and "hash pinned" in changed.content[0].text  # type: ignore[union-attr]


def test_timeout_is_an_error_not_a_hang(tmp_path: Path) -> None:
    d = tmp_path / "slow"
    (d / "scripts").mkdir(parents=True)
    (d / "scripts" / "run.py").write_text("import time; time.sleep(5)\n")
    (d / "tool.json").write_text(json.dumps({"name": "slow", "description": "d", "inputSchema": {"type": "object"}, "runtime": {"kind": "script", "path": "scripts/run.py", "command": [sys.executable, "scripts/run.py"]}}))
    tools, _ = toolbox.load_tools(tmp_path)
    res = toolbox.call(tools["slow"], {}, timeout=0.5)
    assert res.is_error and "timeout" in res.content[0].text  # type: ignore[union-attr]


def test_output_flood_is_killed_at_the_cap(tmp_path: Path) -> None:
    """Codex 2026-10-18 high: 상한은 돌면서 집행한다 — 10 MB를 쏟는 도구는 1 MB에서 끊기고 오류가 되며 메모리에 다 쌓이지 않는다."""
    d = tmp_path / "flood"
    (d / "scripts").mkdir(parents=True)
    (d / "scripts" / "run.py").write_text("import sys\nfor _ in range(200):\n    sys.stdout.write('x' * 50_000)\n    sys.stdout.flush()\n")
    (d / "tool.json").write_text(json.dumps({"name": "flood", "description": "d", "inputSchema": {"type": "object"}, "runtime": {"kind": "script", "path": "scripts/run.py", "command": [sys.executable, "scripts/run.py"]}}))
    tools, _ = toolbox.load_tools(tmp_path)
    outcome = toolbox.run_tool(tools["flood"], {}, timeout=30)
    assert outcome.truncated and outcome.exit_code != 0 and len(outcome.stdout) <= toolbox.MAX_OUTPUT_BYTES and "exceeded" in outcome.stderr
    res = toolbox.call(tools["flood"], {})
    assert res.is_error


def test_grandchild_holding_the_pipe_is_killed_with_the_group(tmp_path: Path) -> None:
    """Codex 2026-10-18 2차 high: 도구가 띄운 자식이 파이프를 물고 있어도 그룹째 끝나고 reader가 회수된다."""
    import os
    import time

    d = tmp_path / "spawner"
    (d / "scripts").mkdir(parents=True)
    (d / "scripts" / "run.py").write_text(
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"  # stdout/stderr 파이프를 상속한 손자
        "print(child.pid, file=sys.stderr, flush=True)\n"
        "time.sleep(60)\n"
    )
    (d / "tool.json").write_text(json.dumps({"name": "spawner", "description": "d", "inputSchema": {"type": "object"}, "runtime": {"kind": "script", "path": "scripts/run.py", "command": [sys.executable, "scripts/run.py"]}}))
    tools, _ = toolbox.load_tools(tmp_path)
    started = time.monotonic()
    outcome = toolbox.run_tool(tools["spawner"], {}, timeout=1.0)
    assert outcome.exit_code is None and time.monotonic() - started < 15  # 시간 초과로 끝났고 reader에 묶이지 않았다
    child_pid = int(outcome.stderr.split()[0])
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("grandchild survived the group kill")


@pytest.mark.anyio
async def test_stdio_end_to_end(tmp_path: Path) -> None:
    """`hc toolbox <dir>`를 실제 프로세스로 띄워 MCP 클라이언트로 tools/list·tools/call. 세션·루프가 보는 모양 그대로."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    write_tool(tmp_path, "echo")
    params = StdioServerParameters(command=sys.executable, args=["-m", "harness_catalog_cli", "toolbox", str(tmp_path)])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        assert [t.name for t in listed.tools] == ["echo"] and listed.tools[0].input_schema["required"] == ["text"]
        res = await session.call_tool("echo", {"text": "hey"})
        assert not res.is_error and res.structured_content == {"echo": "hey", "n": 3}
        err = await session.call_tool("echo", {"text": "x", "fail": True})
        assert err.is_error
