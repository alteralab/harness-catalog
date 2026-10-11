# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""새 도구의 뼈대를 결정적으로 만든다 — tools/<name>/tool.json(과 kind: script면 ABI 골격 스크립트, kind: mcp면 없을 때 mcp-servers/<server>/server.json 골격).

호출(카탈로그 클론 루트에서):
  uv run --script scripts/scaffold_tool.py <name> --description "<한 문장>" --kind script --script <x.py> [--root .]
  uv run --script scripts/scaffold_tool.py <name> --description "<한 문장>" --kind mcp --server <server> --tool <tool> [--root .]
  name        1~64자, 소문자·숫자·하이픈. 디렉토리명이 된다. 스킬과 합쳐 전역 유일(검사 11이 본다).
  --kind      script | mcp (DESIGN D18의 닫힌 판별자)
  --script    kind=script: tools/<name>/scripts/<x.py>를 만들고 runtime.path·command에 넣는다
  --server    kind=mcp: mcp-servers/<server>의 이름. 없으면 server.json 골격도 만든다
  --tool      kind=mcp: 그 서버가 내는 도구 이름
있는 파일은 건드리지 않는다(멱등). 만든 파일을 한 줄씩 찍는다. 종료 코드: 0 성공 · 2 입력 오류.
판단은 여기 없다 — 내용(설명·inputSchema의 필드·스크립트 본문·server.json의 packages)은 에이전트가 TODO 자리에 쓴다.
tool.json의 $schema는 ../../schemas/tool.schema.json(harness-catalog init이 core ToolSpec에서 생성해 둔다; 낡았으면 `harness-catalog schema tool`로 다시 쓴다).
실행 ABI(D18): command는 셸 없는 argv, path는 그 원소 정확히 하나, cwd = 도구 디렉토리, 입력 = stdin의 JSON 객체 하나, 결과 = stdout(outputSchema를 선언하면 그 스키마의 JSON 객체 하나만), 종료 0 = 결과를 냈다·0 아님 = 실행 실패(사유는 stderr). 판정은 결과 객체의 필드로, 종료 코드로 하지 않는다(§11 2026-10-12 보정).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ast-grep-ignore: regex-on-structure — 어휘: 카탈로그 name 문법은 문자집합과 길이만 보는 정규 언어다(중첩 구조 아님)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SCHEMA_REL = "../../schemas/tool.schema.json"
SERVER_SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"

SCRIPT_PY = '''# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""TODO 한 줄: 무엇을 받아 무엇을 돌려주는가.

실행 ABI(카탈로그 D18): 호출자가 `{command}`를 argv 그대로 실행한다(셸 없음, cwd = 이 도구의 디렉토리).
입력은 tool.json의 inputSchema에 맞는 JSON 객체 하나가 stdin으로 온다. 결과는 stdout에 tool.json의 outputSchema에 맞는 JSON 객체 **하나만**(로그·진행 표시를 섞지 않는다). 종료 0 = 결과를 냈다, 0 아님 = 실행 실패(사유는 stderr, stdout 비움).
통과·불통과 같은 판정은 결과 객체의 필드로 말한다 — 종료 1로 말하지 않는다. 조용히 끝나지 않는다. 소비자가 종료 코드·stdout·stderr를 구분된 관측으로 모델에 되돌린다.
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
    # TODO inputSchema의 required 키가 다 있는지 확인한다. 없으면 사유를 stderr에 적고 2.
    # TODO 일을 한다. 결과는 stdout에 — 사람이 읽을 텍스트든 JSON 한 줄이든 tool.json의 description이 말한 대로.
    print(json.dumps({{"summary": "TODO 사람이 읽을 한 줄", "received": sorted(args)}}, ensure_ascii=False))  # outputSchema와 함께 바꾼다
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def put(path: Path, text: str, created: list[str]) -> None:
    """없는 파일만 쓴다."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    created.append(path.as_posix())


def tool_json(name: str, description: str, runtime: dict[str, object], requires_tools: str) -> str:
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
        "metadata": {"requires-tools": requires_tools} if requires_tools else {},
    }
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def server_json(server: str) -> str:
    spec: dict[str, object] = {
        "$schema": SERVER_SCHEMA_URL,
        "name": server,
        "version": "TODO 서버의 판(예: 0.1.0)",
        "description": "TODO 이 서버가 무엇을 내는가 한 줄",
        "packages": [
            {
                "registryType": "npm",
                "identifier": "TODO 패키지 식별자(예: @scope/name)",
                "version": "TODO",
                "runtimeHint": "npx",
                "transport": {"type": "stdio"},
            }
        ],
    }
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="scaffold_tool.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--description", required=True, help="무엇을 돌려주는지와 사용자가 실제로 말할 낱말이 든 한 문장")
    ap.add_argument("--kind", required=True, choices=("script", "mcp"))
    ap.add_argument("--script", default=None, help="kind=script: scripts/<x.py> 파일 이름")
    ap.add_argument("--server", default=None, help="kind=mcp: mcp-servers/<server>")
    ap.add_argument("--tool", default=None, help="kind=mcp: 그 서버가 내는 도구 이름")
    ap.add_argument("--root", default=".", help="카탈로그 클론 루트(기본 .)")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not NAME_RE.match(a.name):
        print(f"name은 1~64자 소문자·숫자·하이픈: {a.name}", file=sys.stderr)
        return 2
    root = Path(a.root)
    created: list[str] = []
    tool_dir = root / "tools" / a.name
    if a.kind == "script":
        if not a.script or "/" in a.script or not a.script.endswith(".py"):
            print("kind=script에는 --script <x.py>(파일 이름만, .py)가 필요하다", file=sys.stderr)
            return 2
        path = f"scripts/{a.script}"
        command = ["uv", "run", "--script", path]
        put(tool_dir / "tool.json", tool_json(a.name, a.description, {"kind": "script", "path": path, "command": command}, "uv"), created)
        put(tool_dir / path, SCRIPT_PY.format(command=" ".join(command)), created)
    else:
        if not a.server or not a.tool:
            print("kind=mcp에는 --server <server>와 --tool <tool>이 필요하다", file=sys.stderr)
            return 2
        if not NAME_RE.match(a.server):
            print(f"server는 1~64자 소문자·숫자·하이픈: {a.server}", file=sys.stderr)
            return 2
        put(tool_dir / "tool.json", tool_json(a.name, a.description, {"kind": "mcp", "server": a.server, "tool": a.tool}, ""), created)
        put(root / "mcp-servers" / a.server / "server.json", server_json(a.server), created)
    for c in created:
        print(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
