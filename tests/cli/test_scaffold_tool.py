"""write-tool의 scripts/scaffold.py — 결정적 뼈대 스크립트와 `harness-catalog schema tool`. 템플릿 패키지 데이터라 모듈이 아니므로 파일을 그대로 실행한다."""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
from typer.testing import CliRunner

from harness_catalog_cli.__main__ import app
from harness_catalog_core.toolbox import parse_server, parse_tool, tool_json_schema

SKILLS = Path(__file__).resolve().parents[2] / "packages/cli/src/harness_catalog_cli/templates/skills"
SCAFFOLD = SKILLS / "write-tool/scripts/scaffold_tool.py"


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCAFFOLD), *args], cwd=cwd, capture_output=True, text=True, check=False)


def test_script_tool_skeleton_is_valid_and_idempotent(tmp_path: Path) -> None:
    first = run(tmp_path, "subs-fetch", "--description", "Fetch subtitles. 자막.", "--kind", "script", "--script", "fetch.py")
    assert first.returncode == 0, first.stderr
    assert first.stdout.split() == ["tools/subs-fetch/tool.json", "tools/subs-fetch/scripts/fetch.py"]
    raw = (tmp_path / "tools/subs-fetch/tool.json").read_bytes()
    spec, errors = parse_tool(raw)  # 검사 11의 파서 — 뼈대 그대로가 모양 규칙을 지킨다(내용은 TODO)
    assert errors == [] and spec is not None and spec.schema_url == "../../schemas/tool.schema.json" and spec.runtime.kind == "script"
    jsonschema.validate(json.loads(raw), tool_json_schema())  # 편집기가 보는 스키마에도 맞는다
    script = (tmp_path / "tools/subs-fetch/scripts/fetch.py").read_text()
    assert script.startswith("# /// script") and "uv run --script scripts/fetch.py" in script
    # ABI: stdin JSON 객체 → stdout, 0; 객체가 아니면 0이 아닌 코드와 stderr 사유
    ok = subprocess.run([sys.executable, str(tmp_path / "tools/subs-fetch/scripts/fetch.py")], input='{"url": "x"}', capture_output=True, text=True, check=False)
    result = json.loads(ok.stdout)  # stdout은 JSON 객체 하나만(§11 2026-10-12 보정)
    assert ok.returncode == 0 and result["received"] == ["url"]
    jsonschema.validate(result, json.loads(raw)["outputSchema"])  # 뼈대 스크립트의 출력이 뼈대 outputSchema에 맞는다
    bad = subprocess.run([sys.executable, str(tmp_path / "tools/subs-fetch/scripts/fetch.py")], input="[]", capture_output=True, text=True, check=False)
    assert bad.returncode != 0 and bad.stderr.strip() and bad.stdout == ""  # 실패면 stdout에 부분 결과를 두지 않는다
    second = run(tmp_path, "subs-fetch", "--description", "x", "--kind", "script", "--script", "fetch.py")
    assert second.returncode == 0 and second.stdout == ""  # 있는 파일은 건드리지 않는다


def test_mcp_tool_skeleton_makes_server_record_once(tmp_path: Path) -> None:
    first = run(tmp_path, "graft-ask", "--description", "Ask the code graph.", "--kind", "mcp", "--server", "graft", "--tool", "graft_find_code")
    assert first.returncode == 0, first.stderr
    assert first.stdout.split() == ["tools/graft-ask/tool.json", "mcp-servers/graft/server.json"]
    spec, errors = parse_tool((tmp_path / "tools/graft-ask/tool.json").read_bytes())
    assert errors == [] and spec is not None and spec.runtime.kind == "mcp"
    server, s_errors = parse_server((tmp_path / "mcp-servers/graft/server.json").read_bytes(), "graft")
    assert server is not None and s_errors == []  # 골격은 모양 규칙을 지킨다 — version·identifier는 TODO 문자열
    again = run(tmp_path, "graft-trace", "--description", "Trace calls.", "--kind", "mcp", "--server", "graft", "--tool", "graft_trace_calls")
    assert again.stdout.split() == ["tools/graft-trace/tool.json"]  # 서버 레코드는 한 번만


def test_rejects_bad_inputs(tmp_path: Path) -> None:
    assert run(tmp_path, "Bad_Name", "--description", "x", "--kind", "script", "--script", "a.py").returncode == 2
    assert run(tmp_path, "ok", "--description", "x", "--kind", "script").returncode == 2  # --script 없음
    assert run(tmp_path, "ok", "--description", "x", "--kind", "script", "--script", "dir/a.py").returncode == 2
    assert run(tmp_path, "ok", "--description", "x", "--kind", "mcp", "--server", "graft").returncode == 2  # --tool 없음
    assert run(tmp_path, "ok", "--description", "x", "--kind", "http").returncode == 2
    assert not (tmp_path / "tools").exists() and not (tmp_path / "mcp-servers").exists()


def test_cli_schema_tool_prints_the_same_schema() -> None:
    r = CliRunner().invoke(app, ["schema", "tool"])
    assert r.exit_code == 0 and json.loads(r.stdout) == tool_json_schema()
    assert CliRunner().invoke(app, ["schema", "server"]).exit_code == 2
