"""`hc toolbox <dir>`: 디렉토리의 `*/tool.json`(kind: script)을 MCP 도구로 노출하는 stdio 서버 — 공구 걸이(DESIGN §11 2026-10-18).

레지스트리는 발견까지고 실행은 로컬이다. 이 어댑터가 그 실행기이고, 세션(pin이 `.mcp.json`에 등록)과 루프(조립기가 등록)가 같은 것을 쓴다.
호출 한 번 = inputSchema 검증 → 셸 없는 argv 서브프로세스(cwd 도구 디렉토리, stdin에 JSON 하나) → 종료 0의 stdout을 outputSchema로 검증해 structuredContent, ≠0은 isError.
안전 요건(Codex 2026-10-18): 실행물 해시 고정(로드 때 잰 sha256과 다르면 거부), 셸 없음, 경로 정규화(검사 11과 같은 규칙), 최소 환경, 시간 상한, 출력 상한을 돌면서 집행(넘치면 kill), 동시 호출 상한, 비 JSON fail-closed, 호출마다 stderr에 감사 로그 한 줄.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
import jsonschema
from mcp import types
from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server

from harness_catalog_core.toolbox import TOOL_FILE, ScriptRuntime, ToolSpec, parse_tool

SERVER_NAME = "toolbox"
log = logging.getLogger("harness_catalog.toolbox")  # stdout은 MCP 전송이라 로그는 전부 stderr
DEFAULT_TIMEOUT = 120.0
MAX_OUTPUT_BYTES = 1_000_000  # stdout·stderr 각각. 넘으면 자르고 표시한다(관측은 무제한 주입하지 않는다, §11 2026-10-12)
ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TZ", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "VIRTUAL_ENV")  # 최소 환경: 도구가 받는 것은 이것뿐


@dataclass(frozen=True)
class LoadedTool:
    spec: ToolSpec
    directory: Path
    runtime: ScriptRuntime
    entry_sha256: str  # runtime.path의 해시 — 호출마다 다시 재서 다르면 거부(해시 고정)


@dataclass(frozen=True)
class Outcome:
    exit_code: int | None  # None = 시간 초과
    stdout: str
    stderr: str
    truncated: bool
    seconds: float


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_tools(directory: Path) -> tuple[dict[str, LoadedTool], list[str]]:
    """`<dir>/*/tool.json`을 읽어 kind: script 도구만 싣는다. 깨진 레코드와 kind: mcp는 사유와 함께 건너뛴다(그 서버는 하네스가 따로 붙인다)."""
    tools: dict[str, LoadedTool] = {}
    skipped: list[str] = []
    if not directory.is_dir():
        return tools, [f"{directory}: not a directory"]
    for child in sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")):
        raw = child / TOOL_FILE
        if not raw.is_file():
            skipped.append(f"{child.name}: {TOOL_FILE} missing")
            continue
        spec, errors = parse_tool(raw.read_bytes())
        if spec is None or errors:
            skipped.append(f"{child.name}: " + "; ".join(errors or ["invalid"]))
            continue
        if spec.name != child.name:
            skipped.append(f"{child.name}: name {spec.name!r} != directory")
            continue
        if not isinstance(spec.runtime, ScriptRuntime):
            skipped.append(f"{child.name}: kind=mcp — attach its server in the harness config instead")
            continue
        entry = child / spec.runtime.path
        if not entry.is_file() or entry.is_symlink():
            skipped.append(f"{child.name}: runtime.path {spec.runtime.path!r} is not a regular file")
            continue
        tools[spec.name] = LoadedTool(spec, child.resolve(), spec.runtime, _sha256(entry))
    return tools, skipped


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in ENV_KEYS}


def _drain(stream: Any, sink: list[bytes], limit: int, overflow: list[bool]) -> None:
    """파이프를 읽어 상한까지만 모은다. 넘치면 표시하고 계속 비운다(버퍼를 무한정 쌓지 않는다 — Codex 2026-10-18)."""
    total = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            return
        if total < limit:
            take = chunk[: limit - total]
            sink.append(take)
        total += len(chunk)
        if total > limit:
            overflow[0] = True


def run_tool(tool: LoadedTool, arguments: Mapping[str, Any], *, timeout: float = DEFAULT_TIMEOUT) -> Outcome:
    """argv를 셸 없이 실행한다. 입력은 stdin의 JSON 객체 하나. stdout·stderr는 돌면서 상한까지만 모으고, 넘치면 프로세스를 끝낸다. 해시가 바뀐 실행물은 돌리지 않는다."""
    entry = tool.directory / tool.runtime.path
    if not entry.is_file() or _sha256(entry) != tool.entry_sha256:
        return Outcome(126, "", f"{tool.runtime.path}: changed since the toolbox started (hash pinned) — restart the toolbox", False, 0.0)
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 — argv 배열, shell=False; command는 검사 11이 본 tool.json의 것
            list(tool.runtime.command), cwd=tool.directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(),
        )
    except FileNotFoundError as e:
        return Outcome(127, "", f"{tool.runtime.command[0]}: not found ({e})", False, time.monotonic() - started)
    out_parts: list[bytes] = []
    err_parts: list[bytes] = []
    overflow = [False]
    assert proc.stdout is not None and proc.stderr is not None and proc.stdin is not None
    readers = [threading.Thread(target=_drain, args=(proc.stdout, out_parts, MAX_OUTPUT_BYTES, overflow), daemon=True),
               threading.Thread(target=_drain, args=(proc.stderr, err_parts, MAX_OUTPUT_BYTES, overflow), daemon=True)]
    for t in readers:
        t.start()
    try:
        proc.stdin.write(json.dumps(dict(arguments), ensure_ascii=False).encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass  # 입력을 안 읽고 끝난 프로세스
    timed_out = False
    deadline = started + timeout
    while proc.poll() is None:
        if overflow[0] or time.monotonic() > deadline:
            timed_out = time.monotonic() > deadline and not overflow[0]
            proc.kill()
            break
        time.sleep(0.02)
    proc.wait()
    for t in readers:
        t.join(timeout=5)
    out = b"".join(out_parts).decode("utf-8", errors="replace")
    err = b"".join(err_parts).decode("utf-8", errors="replace")
    seconds = time.monotonic() - started
    if timed_out:
        return Outcome(None, out, err + f"\n[toolbox] timed out after {timeout:g}s", True, seconds)
    if overflow[0]:
        return Outcome(proc.returncode if proc.returncode not in (None, 0) else 1, out, err + f"\n[toolbox] output exceeded {MAX_OUTPUT_BYTES} bytes; process killed", True, seconds)
    return Outcome(proc.returncode, out, err, False, seconds)


def _text(s: str) -> list[types.ContentBlock]:
    return [types.TextContent(type="text", text=s)]


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=_text(message), is_error=True)


def call(tool: LoadedTool, arguments: Mapping[str, Any] | None, *, timeout: float = DEFAULT_TIMEOUT) -> types.CallToolResult:
    """호출 하나의 결과를 MCP 모양으로. outputSchema가 있으면 stdout은 그 스키마의 JSON 객체 하나여야 한다(아니면 오류 — fail-closed)."""
    args: Mapping[str, Any] = arguments or {}
    try:
        jsonschema.validate(dict(args), tool.spec.inputSchema, cls=jsonschema.Draft202012Validator)
    except jsonschema.ValidationError as e:
        return _error(f"input rejected: {e.message} (at {'/'.join(str(p) for p in e.absolute_path) or '<root>'})")
    outcome = run_tool(tool, args, timeout=timeout)
    _audit(tool, outcome)
    if outcome.exit_code != 0:
        code = "timeout" if outcome.exit_code is None else f"exit {outcome.exit_code}"
        detail = outcome.stderr.strip() or "(no stderr)"
        return _error(f"{tool.spec.name}: {code}\n{detail}" + ("\n[toolbox] output truncated" if outcome.truncated else ""))
    if tool.spec.outputSchema is None:
        return types.CallToolResult(content=_text(outcome.stdout + ("\n[toolbox] output truncated" if outcome.truncated else "")))
    return _structured(tool, tool.spec.outputSchema, outcome)


def _structured(tool: LoadedTool, schema: Mapping[str, Any], outcome: Outcome) -> types.CallToolResult:
    """outputSchema가 있는 도구의 정상 종료: stdout은 그 스키마의 JSON 객체 하나여야 한다. 아니면 결과를 버리고 오류(fail-closed)."""
    if outcome.truncated:
        return _error(f"{tool.spec.name}: stdout exceeded {MAX_OUTPUT_BYTES} bytes; structured result discarded")
    try:
        loaded: object = json.loads(outcome.stdout)
    except ValueError as e:
        return _error(f"{tool.spec.name}: stdout is not JSON ({e}); outputSchema requires exactly one JSON object")
    if not isinstance(loaded, dict):
        return _error(f"{tool.spec.name}: stdout is not a JSON object")
    result = cast("dict[str, Any]", loaded)
    try:
        jsonschema.validate(result, dict(schema), cls=jsonschema.Draft202012Validator)
    except jsonschema.ValidationError as e:
        return _error(f"{tool.spec.name}: result does not match outputSchema: {e.message}")
    return types.CallToolResult(content=_text(json.dumps(result, ensure_ascii=False)), structured_content=result)


def _audit(tool: LoadedTool, outcome: Outcome) -> None:
    line = {"toolbox": tool.spec.name, "entry_sha256": tool.entry_sha256[:12], "exit": outcome.exit_code, "seconds": round(outcome.seconds, 3), "truncated": outcome.truncated}
    log.info("%s", json.dumps(line, ensure_ascii=False))


def mcp_tools(tools: Mapping[str, LoadedTool]) -> list[types.Tool]:
    return [types.Tool(name=t.spec.name, description=t.spec.description, input_schema=t.spec.inputSchema, output_schema=t.spec.outputSchema) for t in tools.values()]


MAX_CONCURRENT = 4  # 동시 서브프로세스 상한(메모리·CPU 증폭 방지)


def build_server(tools: Mapping[str, LoadedTool], *, timeout: float = DEFAULT_TIMEOUT) -> Server[None]:
    gate = anyio.CapacityLimiter(MAX_CONCURRENT)

    async def on_list_tools(_ctx: object, _params: object) -> types.ListToolsResult:
        return types.ListToolsResult(tools=mcp_tools(tools))

    async def on_call_tool(_ctx: object, params: types.CallToolRequestParams) -> types.CallToolResult:
        tool = tools.get(params.name)
        if tool is None:
            return _error(f"unknown tool {params.name!r}")
        return await anyio.to_thread.run_sync(lambda: call(tool, params.arguments, timeout=timeout), limiter=gate)

    return Server(SERVER_NAME, instructions="Local toolbox: catalog tools (tools/*/tool.json) run as subprocesses next to this harness.", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def serve(directory: Path, *, timeout: float = DEFAULT_TIMEOUT) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[toolbox] %(message)s")
    tools, skipped = load_tools(directory)
    for s in skipped:
        log.warning("skipped %s", s)
    log.info("serving %d tool(s) from %s", len(tools), directory)
    server = build_server(tools, timeout=timeout)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
    return 0
