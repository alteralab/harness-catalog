"""기본 도구 scaffold(templates/tools/scaffold) — stdin JSON → 뼈대 파일, stdout JSON. 템플릿 패키지 데이터라 모듈이 아니므로 파일을 그대로 실행한다."""

import json
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

import jsonschema

from harness_catalog_core.toolbox import parse_server, parse_tool, tool_json_schema

TEMPLATES = Path(__file__).resolve().parents[2] / "packages/cli/src/harness_catalog_cli/templates"
SKILLS = TEMPLATES / "skills"
SCAFFOLD = TEMPLATES / "tools/scaffold/scripts/scaffold.py"
TOOL_JSON = TEMPLATES / "tools/scaffold/tool.json"


def run(cwd: Path, payload: Mapping[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCAFFOLD)], cwd=cwd, input=json.dumps(payload), capture_output=True, text=True, check=False)


def created(proc: subprocess.CompletedProcess[str]) -> list[str]:
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    jsonschema.validate(out, json.loads(TOOL_JSON.read_text())["outputSchema"])
    return list(out["created"])


def test_shipped_tool_json_is_valid() -> None:
    raw = TOOL_JSON.read_bytes()
    spec, errors = parse_tool(raw)
    assert errors == [] and spec is not None and spec.runtime.kind == "script" and spec.outputSchema is not None
    jsonschema.validate(json.loads(raw), tool_json_schema())


def test_skill_with_tool_then_idempotent(tmp_path: Path) -> None:
    first = run(tmp_path, {"kind": "skill", "name": "demo-skill", "description": "데모. '데모 돌려줘'.", "positive": "runs-demo", "negative": "explain", "tools": ["demo-run"]})
    files = created(first)
    d = tmp_path / "skills" / "demo-skill"
    assert (d / "SKILL.md").read_text().startswith("---\nname: demo-skill\ndescription: 데모.")
    assert "도구 `demo-run`을 `{\"TODO\": …}`로 부른다" in (d / "SKILL.md").read_text() and not (d / "scripts").exists()  # 코드는 도구로, 스킬에 scripts/는 없다
    assert "metadata" not in (d / "SKILL.md").read_text().split("---")[1]  # frontmatter는 name·description뿐
    for case in ("runs-demo", "no-trigger-explain"):  # 음성 이름에 no-trigger- 접두가 붙는다
        for f in ("task.toml", "instruction.md", "environment/Dockerfile", "tests/test.sh", "tests/test_outputs.py", "solution/solve.sh"):
            assert (d / "evals" / case / f).is_file(), f"{case}/{f}"
        cfg = tomllib.loads((d / "evals" / case / "task.toml").read_text())
        assert cfg["schema_version"] == "1.4" and cfg["environment"]["skills_dir"] == "/skills" and cfg["verifier"]["environment_mode"] == "shared"
    spec, errors = parse_tool((tmp_path / "tools/demo-run/tool.json").read_bytes())
    assert errors == [] and spec is not None and spec.runtime.kind == "script" and (tmp_path / "tools/demo-run/scripts/main.py").exists()
    assert len(files) == 13 + 2
    second = run(tmp_path, {"kind": "skill", "name": "demo-skill", "description": "x", "positive": "runs-demo", "negative": "explain", "tools": ["demo-run"]})
    assert created(second) == [] and (d / "SKILL.md").read_text().startswith("---\nname: demo-skill\ndescription: 데모.")  # 있는 파일은 건드리지 않는다


def test_skill_composes_existing_tools_and_scaffolds_missing_ones(tmp_path: Path) -> None:
    """있는 도구는 tool.json을 읽어 호출 줄을 적고(건드리지 않음), 없는 도구는 뼈대를 함께 만든다 — 두 방향이 한 인자(2026-10-18)."""
    existing = tmp_path / "tools" / "changelog-diff"
    existing.mkdir(parents=True)
    existing.joinpath("tool.json").write_text(json.dumps({
        "name": "changelog-diff", "description": "Group commits between two tags by kind. Not for a single commit.",
        "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "from": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["from", "to"]},
        "outputSchema": {"type": "object", "properties": {"groups": {"type": "object"}, "count": {"type": "integer"}}},
        "runtime": {"kind": "script", "path": "scripts/diff.py", "command": ["uv", "run", "--script", "scripts/diff.py"]}}))
    before = existing.joinpath("tool.json").read_text()
    res = run(tmp_path, {"kind": "skill", "name": "release-notes", "description": "릴리스 노트.", "tools": ["changelog-diff", "git-tags"]})
    files = created(res)
    assert "tools/git-tags/tool.json" in files and "tools/git-tags/scripts/main.py" in files and not any(f.startswith("tools/changelog-diff/") for f in files)
    assert existing.joinpath("tool.json").read_text() == before
    body = (tmp_path / "skills/release-notes/SKILL.md").read_text()
    assert '   - 도구 `changelog-diff`을 `{"from": …, "to": …, "limit": …}`로 부른다 — Group commits between two tags by kind. 결과: `groups`, `count`' in body  # required 먼저, 설명 첫 문장, 결과 키
    assert '   - 도구 `git-tags`을 `{"TODO": …}`로 부른다 — TODO' in body
    assert body.index("`changelog-diff`") < body.index("`git-tags`") < body.index("2. TODO 사람 승인")
    assert any("tools/git-tags/tool.json" in t for t in json.loads(res.stdout)["todo"]) and not any("changelog-diff" in t for t in json.loads(res.stdout)["todo"])
    bad = run(tmp_path, {"kind": "skill", "name": "x", "description": "x", "tools": "changelog-diff"})
    assert bad.returncode == 2 and "tools must be a list" in bad.stderr


def test_script_tool_skeleton_is_valid_and_runs_abi(tmp_path: Path) -> None:
    first = run(tmp_path, {"kind": "tool", "name": "subs-fetch", "description": "Fetch subtitles. 자막.", "script": "fetch.py"})
    assert created(first) == ["tools/subs-fetch/tool.json", "tools/subs-fetch/scripts/fetch.py"]
    raw = (tmp_path / "tools/subs-fetch/tool.json").read_bytes()
    spec, errors = parse_tool(raw)  # 검사 11의 파서 — 뼈대 그대로가 모양 규칙을 지킨다(내용은 TODO)
    assert errors == [] and spec is not None and spec.schema_url == "../../schemas/tool.schema.json" and spec.runtime.kind == "script" and "metadata" not in json.loads(raw)
    jsonschema.validate(json.loads(raw), tool_json_schema())
    script = tmp_path / "tools/subs-fetch/scripts/fetch.py"
    assert script.read_text().startswith("# /// script") and "uv run --script scripts/fetch.py" in script.read_text()
    ok = subprocess.run([sys.executable, str(script)], input='{"url": "x"}', capture_output=True, text=True, check=False)
    result = json.loads(ok.stdout)  # stdout은 JSON 객체 하나만
    assert ok.returncode == 0 and result["received"] == ["url"]
    jsonschema.validate(result, json.loads(raw)["outputSchema"])
    bad = subprocess.run([sys.executable, str(script)], input="[]", capture_output=True, text=True, check=False)
    assert bad.returncode != 0 and bad.stderr.strip() and bad.stdout == ""  # 실패면 stdout에 부분 결과를 두지 않는다
    assert created(run(tmp_path, {"kind": "tool", "name": "subs-fetch", "description": "x", "script": "fetch.py"})) == []


def test_mcp_tool_skeleton_makes_server_record_once(tmp_path: Path) -> None:
    first = run(tmp_path, {"kind": "tool", "name": "graft-ask", "description": "Ask the code graph.", "runtime": "mcp", "server": "graft", "mcp_tool": "graft_find_code"})
    assert created(first) == ["tools/graft-ask/tool.json", "mcp-servers/graft/server.json"]
    spec, errors = parse_tool((tmp_path / "tools/graft-ask/tool.json").read_bytes())
    assert errors == [] and spec is not None and spec.runtime.kind == "mcp"
    server, s_errors = parse_server((tmp_path / "mcp-servers/graft/server.json").read_bytes(), "graft")
    assert server is not None and s_errors == []
    again = run(tmp_path, {"kind": "tool", "name": "graft-trace", "description": "Trace calls.", "runtime": "mcp", "server": "graft", "mcp_tool": "graft_trace_calls"})
    assert created(again) == ["tools/graft-trace/tool.json"]  # 서버 레코드는 한 번만


def test_rejects_bad_inputs(tmp_path: Path) -> None:
    for payload in ({"kind": "skill", "name": "Bad_Name", "description": "x"}, {"kind": "tool", "name": "ok", "description": "x", "script": "dir/a.py"},
                    {"kind": "tool", "name": "ok", "description": "x", "runtime": "mcp", "server": "graft"}, {"kind": "http", "name": "ok", "description": "x"}, {"kind": "skill", "name": "ok"}):
        assert run(tmp_path, payload).returncode == 2, payload
    assert subprocess.run([sys.executable, str(SCAFFOLD)], cwd=tmp_path, input="[]", capture_output=True, text=True, check=False).returncode == 2
    assert not (tmp_path / "skills").exists() and not (tmp_path / "tools").exists() and not (tmp_path / "mcp-servers").exists()


def _scaffold_constants() -> dict[str, str]:
    """스크립트 소스를 실행해 템플릿 상수를 읽는다(__main__ 가드가 있어 부작용 없음). import 경로를 쓰지 않는 이유: 패키지 데이터 안에 __pycache__가 생기면 init이 .pyc를 텍스트로 읽는다(실측)."""
    ns: dict[str, object] = {"__name__": "scaffold_constants"}
    exec(compile(SCAFFOLD.read_text(), str(SCAFFOLD), "exec"), ns)  # noqa: S102 — 저장소 안의 고정 파일, 입력 없음
    return {"head": str(ns["DOCKERFILE_HEAD"]), "test_sh": str(ns["TEST_SH"])}


def test_shipped_base_evals_match_scaffold() -> None:
    """실린 기본 스킬 둘(pin·write)의 evals 여섯 케이스는 scaffold가 만드는 것과 같은 Dockerfile 머리·test.sh·공유 검증기 선언을 가진다 — 문면은 한 곳(scaffold.py)이 소유한다."""
    k = _scaffold_constants()
    cases = sorted(SKILLS.glob("*/evals/*"))
    assert len(cases) == 6 and sorted({c.parents[1].name for c in cases}) == ["pin", "write"]
    for case in cases:
        dockerfile = (case / "environment/Dockerfile").read_text()
        assert dockerfile.startswith(k["head"]), f"{case}: Dockerfile 머리가 scaffold.py DOCKERFILE_HEAD와 다르다"
        assert (case / "tests/test.sh").read_text() == k["test_sh"], f"{case}: test.sh가 scaffold.py TEST_SH와 다르다"
        cfg = tomllib.loads((case / "task.toml").read_text())
        assert cfg["verifier"]["environment_mode"] == "shared" and cfg["environment"]["skills_dir"] == "/skills", case
