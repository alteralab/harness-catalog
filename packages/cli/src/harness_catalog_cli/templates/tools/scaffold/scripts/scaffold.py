# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""scaffold — 새 스킬 또는 도구의 뼈대를 결정적으로 만든다(카탈로그의 기본 도구, DESIGN §11 2026-10-18).

실행 ABI(tool-contract): stdin으로 tool.json의 inputSchema에 맞는 JSON 객체 하나, stdout으로 outputSchema의 JSON 객체 하나({"created": [...], "todo": [...]}), 종료 0.
입력이 틀리면 종료 2와 stderr 사유. 있는 파일은 건드리지 않는다(멱등). 판단은 여기 없다 — 내용(설명·과제 문장·검증 조건·절차·inputSchema 필드)은 에이전트가 TODO 자리에 쓴다.

kind=skill: skills/<name>/SKILL.md + evals 양성·음성 한 쌍(Harbor 태스크 여섯 파일씩). `tools`(이름 목록)는 스킬이 이름으로 엮는 결정적 부분이다 — 이미 tools/<x>/가 있으면
  그 tool.json(description·inputSchema·outputSchema)을 읽어 SKILL.md 단계에 호출 줄을 적고, 없으면 tools/<x>/(script 런타임)를 함께 만든다. 두 방향(있는 도구를 엮기, 새 도구 만들기)이 한 인자다.
  기본형은 세션·루프 공용 스킬이라 코드는 처음부터 도구다. skills/<name>/scripts/는 만들지 않는다(세션 전용 예외는 저자가 손으로, 이유 한 줄과 함께).
kind=tool: tools/<name>/tool.json + runtime=script면 scripts/<script>(ABI 골격), runtime=mcp면 없을 때 mcp-servers/<server>/server.json 골격.
검증기의 인터페이스와 보고 형식은 `harbor tasks init`의 공식 뼈대를 따른다 — tests/test.sh가 pytest로 tests/test_outputs.py를 돌려 CTRF 보고와 reward 0/1을 쓴다.
이미지는 python:3.12-slim + git + uv + pytest 미리 설치(검증 중 PyPI 내려받기 없음) + /skills + WORKDIR /work. 검증기는 공유 모드.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple, cast

# ast-grep-ignore: regex-on-structure — 어휘: 카탈로그 name 문법은 문자집합과 길이만 보는 정규 언어다(중첩 구조 아님)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# ast-grep-ignore: regex-on-structure — 어휘: scripts/ 아래 파일 이름 하나(.py)
SCRIPT_RE = re.compile(r"^[A-Za-z0-9_.-]+\.py$")
SCHEMA_REL = "../../schemas/tool.schema.json"
SERVER_SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"

SKILL_MD = """---
name: {name}
description: {description}
---

# {name}

TODO 한 문단: 무엇을 하는가, 결과는 어디에 남는가.

## 언제 쓰는가

- 쓴다: TODO 사용자가 실제로 말하는 문장 둘셋.
- 쓰지 않는다: TODO 비슷하지만 이 스킬이 아닌 상황 하나.

## 단계

1. TODO 판단은 여기 문장으로. 결정적인 일은 도구를 이름으로 부른다.
{tool_lines}2. TODO 사람 승인 전까지는 되돌릴 수 있는 일만 한다 — 그 줄에 오면 루프는 멈춘다(needs_human).

## 실패 대응

| 상황 | 대응 |
|---|---|
| TODO | TODO |
"""

TOOL_SCRIPT_PY = '''# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""TODO 한 줄: 무엇을 받아 무엇을 돌려주는가.

실행 ABI(tool-contract): 호출자(toolbox)가 `{command}`를 argv 그대로 실행한다(셸 없음, cwd = 이 도구의 디렉토리).
입력은 tool.json의 inputSchema에 맞는 JSON 객체 하나가 stdin으로 온다. 결과는 stdout에 outputSchema에 맞는 JSON 객체 **하나만**(로그·진행 표시는 stderr). 종료 0 = 결과를 냈다, 0 아님 = 실행 실패(사유는 stderr, stdout 비움).
통과·불통과 같은 판정은 결과 객체의 필드로 말한다 — 종료 1로 말하지 않는다. 권고 코드: 2 입력 오류 · 3 대상 없음 · 4 시스템 도구 없음(설치 안내 한 줄을 stderr에).
의존성은 이 파일 안에만 적는다: 파이썬 패키지는 위 PEP 723 머리, 바이너리는 없을 때 종료 4.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        raw: object = json.load(sys.stdin)
    except ValueError as e:
        print(f"input is not JSON: {{e}}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print("input must be a JSON object", file=sys.stderr)
        return 2
    args: dict[str, object] = raw  # type: ignore[assignment]
    # TODO inputSchema의 required 키가 다 있는지 확인한다. 없으면 어느 키가 왜 틀렸는지 stderr에 적고 2.
    # TODO 일을 한다. 결과는 outputSchema의 필드로.
    print(json.dumps({{"summary": "TODO 사람이 읽을 한 줄", "received": sorted(args)}}, ensure_ascii=False))  # outputSchema와 함께 바꾼다
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

TASK_TOML = """schema_version = "1.4"

[metadata]
description = "{description}"

[environment]
build_timeout_sec = 600.0
skills_dir = "/skills"
# 라이브 소비(레지스트리 MCP)가 필요하면: [[environment.mcp_servers]] name = "harness-catalog" url = "<REGISTRY_URL>"

[agent]
timeout_sec = 600.0

[verifier]
timeout_sec = 120.0
environment_mode = "shared"   # 검증기가 에이전트 컨테이너의 끝 상태를 직접 본다. 분리 모드(separate)면 artifacts 선언과 tests/Dockerfile이 필요하다
"""

INSTRUCTION_MD = "TODO 사용자가 실제로 할 한 문장. 과제의 입력과 끝 상태가 드러나게.\n"

DOCKERFILE_HEAD = """FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
# uv는 도구 스크립트 규약(`uv run --script`) 때문에 있어야 한다. 검증 도구(pytest·pytest-json-ctrf)는 Harbor 0.24 뼈대와 같은 판을 미리 넣는다 —
# 검증 중 PyPI 내려받기를 없애 검증 예산과 결정성을 지키기 위해서다(Harbor PR #2596, Terminal-Bench check-verifier-tooling-baked). network_mode는 기본 public이라 네트워크가 없는 것은 아니다.
# PyPI에서 받는다: GHCR의 uv 이미지(COPY --from)는 self-hosted 러너에서 pull denied가 난 적이 있다(루트 Dockerfile과 같은 이유).
RUN pip install --no-cache-dir uv==0.11.8 pytest==8.4.1 pytest-json-ctrf==0.3.5 && uv --version
RUN pip install --no-cache-dir --index-url https://ds923plus.tail2f9fe3.ts.net:8443/repository/pypi-public/simple/ harness-catalog-cli==<판>   # hc: toolbox(MCP)·pin·init. 팀 Nexus(tailnet) — 이미지는 tailnet 안에서 굽는다
RUN mkdir -p /skills   # task.toml의 skills_dir. Harbor가 주입 때 만들기도 하지만 문서("이미지에 있게 하라")를 따른다
WORKDIR /work
"""
# 실린 기본 스킬 둘의 evals Dockerfile도 이 머리로 시작한다(tests/cli/test_scaffold.py가 검사) — 과제의 시작 상태만 그 뒤에 더한다.
DOCKERFILE = DOCKERFILE_HEAD + "# TODO 과제의 시작 상태(파일·저장소)를 여기서 만든다\n"

TEST_SH = """#!/bin/bash
# Harbor 공식 뼈대(harbor tasks init)와 같은 검증기 진입점: /tests/test_outputs.py를 pytest로 돌려 종료 코드로 reward 0/1을 쓴다.
# pytest·pytest-json-ctrf는 environment/Dockerfile이 미리 넣는다(검증 중 PyPI 내려받기 없음 — 공식 뼈대는 검증 때 설치한다). CTRF 보고는 /logs/verifier/ctrf.json.
set -u
mkdir -p /logs/verifier
cd /work || exit 1
if python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""

TEST_OUTPUTS_PY = '''"""{description} — 끝 상태를 검사하는 pytest. {condition}"""

from pathlib import Path


def test_outputs() -> None:
    assert Path("/work/TODO").exists()  # TODO 끝 상태를 검사하는 단언으로 바꾼다
'''

SOLVE_SH = """#!/bin/sh
# Oracle: 검증기가 참으로 보는 끝 상태를 직접 만든다. 먼저 `harbor run -p skills/{name}/evals -a oracle -e docker`로 reward 1을 확인한다.
set -eu
{body}
"""


class Input(Exception):
    """입력 오류(종료 2)."""


def put(path: Path, text: str, created: list[str], root: Path) -> None:
    """없는 파일만 쓴다 — 배타적 생성(O_EXCL)이라 검사와 쓰기 사이에 남이 만든 파일도 덮어쓰지 않고, created에는 실제로 만든 것만 남는다(롤백이 그것만 지운다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        return
    created.append(path.relative_to(root).as_posix())


def case_files(case_dir: Path, name: str, description: str, condition: str, solve_body: str, created: list[str], root: Path) -> None:
    put(case_dir / "task.toml", TASK_TOML.format(description=description), created, root)
    put(case_dir / "instruction.md", INSTRUCTION_MD, created, root)
    put(case_dir / "environment" / "Dockerfile", DOCKERFILE, created, root)
    put(case_dir / "tests" / "test.sh", TEST_SH, created, root)
    put(case_dir / "tests" / "test_outputs.py", TEST_OUTPUTS_PY.format(description=description, condition=condition), created, root)
    put(case_dir / "solution" / "solve.sh", SOLVE_SH.format(name=name, body=solve_body), created, root)


def tool_json(name: str, description: str, runtime: dict[str, object]) -> str:
    spec: dict[str, object] = {
        "$schema": SCHEMA_REL,
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {"TODO": {"type": "string", "description": "TODO 인자마다 한 줄 — 검색 색인이 설명을 본다"}},
            "required": ["TODO"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "TODO 사람이 읽을 한 줄. 판정이 있으면 passed 같은 필드를 더한다 — 종료 코드로 말하지 않는다"},
                "received": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        "runtime": runtime,
    }
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def server_json(server: str) -> str:
    spec: dict[str, object] = {
        "$schema": SERVER_SCHEMA_URL,
        "name": server,
        "version": "TODO 서버의 판(예: 0.1.0)",
        "description": "TODO 이 서버가 무엇을 내는가 한 줄",
        "packages": [{"registryType": "npm", "identifier": "TODO 패키지 식별자(예: @scope/name)", "version": "TODO", "runtimeHint": "npx", "transport": {"type": "stdio"}}],
    }
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def scaffold_tool(root: Path, name: str, description: str, runtime: str, script: str, server: str | None, mcp_tool: str | None, created: list[str]) -> list[str]:
    tool_dir = root / "tools" / name
    if (root / "skills" / name).exists():
        raise Input(f"name {name!r} is already a skill (skills/{name}/) — names are unique across skills and tools")
    if runtime == "script":
        if not SCRIPT_RE.match(script):
            raise Input(f"script must be a file name like main.py, not {script!r}")
        path = f"scripts/{script}"
        command = ["uv", "run", "--script", path]
        put(tool_dir / "tool.json", tool_json(name, description, {"kind": "script", "path": path, "command": command}), created, root)
        put(tool_dir / path, TOOL_SCRIPT_PY.format(command=" ".join(command)), created, root)
        return [f"tools/{name}/tool.json: inputSchema.properties·required, outputSchema 필드, description의 '쓰지 말 상황' 한 줄", f"tools/{name}/{path}: 본문(stdin JSON → 일 → stdout JSON)과 PEP 723 dependencies"]
    if not server or not mcp_tool:
        raise Input("runtime=mcp needs server and mcp_tool")
    if not NAME_RE.match(server):
        raise Input(f"server must match {NAME_RE.pattern}: {server!r}")
    put(tool_dir / "tool.json", tool_json(name, description, {"kind": "mcp", "server": server, "tool": mcp_tool}), created, root)
    put(root / "mcp-servers" / server / "server.json", server_json(server), created, root)
    return [f"tools/{name}/tool.json: inputSchema·outputSchema를 그 서버의 도구 정의와 맞춘다", f"mcp-servers/{server}/server.json: version과 packages 또는 remotes(시크릿 값은 적지 않는다)"]


class ToolShape(NamedTuple):
    """호출 줄에 필요한 만큼의 tool.json 모양 — read_tool_spec이 검증해 만든다."""

    description: str
    input_keys: list[str]  # required 먼저
    output_keys: list[str] | None  # None = outputSchema 없음(텍스트 도구)


def _object_schema(value: object, what: str) -> tuple[dict[str, object], list[str]]:
    """`{"type": "object", "properties": {...}, "required": [...]}` 모양인지 보고 (properties, required)를 돌려준다."""
    if not isinstance(value, dict):
        raise Input(f"{what} must be an object schema with properties")
    schema = cast(dict[str, object], value)
    props_raw, required_raw = schema.get("properties", {}), schema.get("required", [])
    if schema.get("type") != "object" or not isinstance(props_raw, dict) or not isinstance(required_raw, list):
        raise Input(f"{what} must be an object schema with properties")
    props = cast(dict[str, object], props_raw)
    required = [str(k) for k in cast(list[object], required_raw)]
    if any(k not in props for k in required):
        raise Input(f"{what}.required must list keys of properties")
    return props, required


def read_tool_spec(root: Path, tool: str) -> ToolShape:
    """tools/<tool>/tool.json을 읽어 호출 줄에 필요한 모양만 검증한다(전체 계약은 hc check 항목 11). 틀리면 Input — 쓰기 전에."""
    path = root / "tools" / tool / "tool.json"
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Input(f"tools/{tool}/tool.json unreadable: {e}") from e
    if not isinstance(raw, dict):
        raise Input(f"tools/{tool}/tool.json: not an object with name {tool!r}")
    spec = cast(dict[str, object], raw)
    if spec.get("name") != tool:
        raise Input(f"tools/{tool}/tool.json: not an object with name {tool!r}")
    props, required = _object_schema(spec.get("inputSchema"), f"tools/{tool}/tool.json: inputSchema")
    out = spec.get("outputSchema")
    output_keys = None
    if out is not None:
        try:
            output_keys = list(_object_schema(out, "outputSchema")[0])
        except Input as e:
            raise Input(f"tools/{tool}/tool.json: {e} (omit it for a text tool)") from e
    return ToolShape(str(spec.get("description", "")), required + [k for k in props if k not in required], output_keys)


def tool_line(tool: str, shape: ToolShape) -> str:
    """SKILL.md 단계에 들어갈 호출 줄 하나 — 설명 첫 문장, 입력 키는 required 먼저, 결과 키(outputSchema 없으면 텍스트 도구)."""
    args = ", ".join(f'"{k}": …' for k in shape.input_keys) or "…"
    out_keys = shape.output_keys or []
    desc = shape.description.split(". ")[0].strip().rstrip(".") or "TODO"
    result = f" 결과: `{'`, `'.join(out_keys)}`" if out_keys else " 결과: 사람이 읽을 텍스트"
    return f"   - 도구 `{tool}`을 `{{{args}}}`로 부른다 — {desc}.{result}\n"


def plan_tools(root: Path, skill: str, tools: list[str]) -> tuple[list[str], list[str]]:
    """스킬이 엮는 도구 목록을 검증하고 (새로 만들 이름들, SKILL.md 호출 줄들)을 돌려준다. 파일은 쓰지 않는다."""
    missing: list[str] = []
    lines: list[str] = []
    for tool in tools:
        if not NAME_RE.match(tool):
            raise Input(f"tools[] must match {NAME_RE.pattern}: {tool!r}")
        if (root / "tools" / tool / "tool.json").exists():
            shape = read_tool_spec(root, tool)
        else:
            if tool == skill or (root / "skills" / tool).exists():
                raise Input(f"tool {tool!r} would collide with a skill of the same name — names are unique across skills and tools")
            missing.append(tool)
            shape = ToolShape("TODO", ["TODO"], ["summary", "received"])  # tool_json 뼈대와 같은 모양
        lines.append(tool_line(tool, shape))
    return missing, lines


def scaffold_skill(root: Path, name: str, description: str, positive: str, negative: str, tools: list[str], created: list[str]) -> list[str]:
    neg = negative if negative.startswith("no-trigger-") else f"no-trigger-{negative}"
    d = root / "skills" / name
    # 1) 검증과 호출 줄을 전부 메모리에서 — 어느 하나라도 틀리면 아무것도 쓰지 않는다
    if (root / "tools" / name).exists():
        raise Input(f"name {name!r} is already a tool (tools/{name}/) — names are unique across skills and tools")
    missing, lines = plan_tools(root, name, tools)
    skill_md = d / "SKILL.md"
    if skill_md.exists():  # 재실행: 있는 본문은 건드리지 않으므로, 본문이 모르는 도구를 새로 만들어 고아로 두지 않는다
        body = skill_md.read_text(encoding="utf-8")
        unlinked = [t for t in tools if f"도구 `{t}`" not in body]
        if unlinked:
            raise Input(f"skills/{name}/SKILL.md exists and does not call {', '.join(unlinked)} — add the call line by hand, then scaffold the tool with kind=tool")
    # 2) 쓰기
    put(skill_md, SKILL_MD.format(name=name, description=description, tool_lines="".join(lines)), created, root)
    case_files(d / "evals" / positive, name, "TODO 써야 하는 과제 한 줄", "TODO 스킬이 만들어야 하는 결과(파일·상태)가 있어야 1", "cd /work\n# TODO 끝 상태를 만든다", created, root)
    case_files(d / "evals" / neg, name, "TODO 쓰지 말아야 하는 과제 한 줄(비슷하지만 이 스킬이 아닌 상황)", "TODO 스킬이 발동했을 때 생길 흔적이 없어야 1", "exit 0  # 음성 케이스 — 아무것도 하지 않는 것이 정답", created, root)
    todo = [f"skills/{name}/SKILL.md: 본문 세 절(언제 쓰는가·단계·실패 대응)", f"skills/{name}/evals/{positive}·{neg}: instruction.md, tests/test_outputs.py의 단언, solution/solve.sh"]
    for tool in missing:
        todo += scaffold_tool(root, tool, f"TODO {name} 스킬이 부르는 결정적 연산 한 줄", "script", "main.py", None, None, created)
    return todo


def main() -> int:
    try:
        raw: object = json.load(sys.stdin)
    except ValueError as e:
        print(f"input is not JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print("input must be a JSON object", file=sys.stderr)
        return 2
    args: dict[str, object] = raw  # type: ignore[assignment]
    root = Path(str(args.get("root", ".")))
    created: list[str] = []
    try:
        kind, name, description = str(args.get("kind", "")), str(args.get("name", "")), str(args.get("description", ""))
        if kind not in ("skill", "tool"):
            raise Input("kind must be skill or tool")
        if not NAME_RE.match(name):
            raise Input(f"name must match {NAME_RE.pattern}: {name!r}")
        if not description:
            raise Input("description is required")
        if kind == "skill":
            tools_raw = args.get("tools", [])
            if not isinstance(tools_raw, list) or not all(isinstance(t, str) for t in cast(list[object], tools_raw)):
                raise Input("tools must be a list of tool names")
            tools = list(dict.fromkeys(cast(list[str], tools_raw)))
            todo = scaffold_skill(root, name, description, str(args.get("positive", "basic")), str(args.get("negative", "basic")), tools, created)
        else:
            server, mcp_tool = args.get("server"), args.get("mcp_tool")
            todo = scaffold_tool(root, name, description, str(args.get("runtime", "script")), str(args.get("script", "main.py")), str(server) if server else None, str(mcp_tool) if mcp_tool else None, created)
    except Input as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:  # 쓰기 도중 실패 — 이번 호출이 만든 파일만 되돌린다(있던 파일은 put이 건드리지 않았다)
        rollback(root, created)
        print(f"write failed, rolled back {len(created)} new file(s): {e}", file=sys.stderr)
        return 1
    print(json.dumps({"created": created, "todo": todo}, ensure_ascii=False))
    return 0


def rollback(root: Path, created: list[str]) -> None:
    for rel in reversed(created):
        path = root / rel
        try:
            path.unlink()
        except OSError:
            continue
        parent = path.parent
        while parent != root and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


if __name__ == "__main__":
    raise SystemExit(main())
