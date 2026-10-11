"""toolbox 레코드의 검증(DESIGN §11 2026-10-11): `tools/<name>/tool.json`과 `mcp-servers/<name>/server.json`.

pydantic 모델(새 의존 없음)로 모양을, 함수로 모양 밖의 규칙(이름 문법·경로 정규형·스키마 상한·시크릿 리터럴)을 본다. 판정만 하고 출력은 호출자가 한다.
단위는 도구 = 스키마가 있는 호출 가능한 것. `runtime.kind`는 닫힌 판별자 `script | mcp`. MCP 서버는 `kind: mcp` 도구가 참조하는 배선 레코드(MCP Registry 형식)다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, cast

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, ValidationError

TOOL_FILE = "tool.json"
SERVER_FILE = "server.json"
MAX_DESCRIPTION_CHARS = 1024
MAX_INPUT_SCHEMA_BYTES = 32 * 1024  # 파일럿 조정 대상(Codex 설계 리뷰 2026-10-11)
MAX_INPUT_SCHEMA_DEPTH = 16
MAX_PATH_CHARS = 1024
# ast-grep-ignore: regex-on-structure — 어휘: 스킬과 같은 name 문법(문자집합·길이)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# ast-grep-ignore: regex-on-structure — 어휘: MCP Registry server.json의 name = 선택 역-DNS 이름공간 + '/' + 이름
SERVER_NAME_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9.-]{0,200}/)?[a-z0-9][a-z0-9-]{0,63}$")
SECRET_FLAG = "isSecret"
LITERAL_KEYS = ("value", "default")
SECRET_COLLECTIONS = ("environmentVariables", "headers", "packageArguments", "runtimeArguments")  # Registry 형식에서 isSecret을 갖는 항목 목록들


class ScriptRuntime(BaseModel):
    """카탈로그 안의 스크립트. `command`는 셸을 거치지 않는 argv이고 `path`는 그 원소 정확히 하나다."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["script"]
    path: str = Field(min_length=1, max_length=MAX_PATH_CHARS)
    command: list[str] = Field(min_length=1)


class McpRuntime(BaseModel):
    """MCP 서버의 도구 하나. `server`는 `mcp-servers/<server>/server.json`."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["mcp"]
    server: str = Field(min_length=1, max_length=64)
    tool: str = Field(min_length=1, max_length=256)


Runtime = Annotated[ScriptRuntime | McpRuntime, Field(discriminator="kind")]


class ToolSpec(BaseModel):
    """tool.json. `$schema`는 저자의 편집기 검증용 포인터(`schemas/tool.schema.json`)이고 레지스트리는 해석하지 않는다(§11 2026-10-11 write-tool)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_url: str | None = Field(default=None, alias="$schema", description="editor-only pointer to schemas/tool.schema.json; the registry ignores it")
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_CHARS)
    inputSchema: dict[str, Any]  # noqa: N815 — MCP 도구 정의의 필드 이름 그대로
    outputSchema: dict[str, Any] | None = Field(default=None, description="MCP Tool.outputSchema; when declared the script prints exactly one JSON object conforming to it on exit 0 (§11 2026-10-12)")  # noqa: N815
    runtime: Runtime
    metadata: dict[str, str] = Field(default_factory=dict)


class ServerSpec(BaseModel):
    """MCP Registry generic server.json의 최상위 필드만 닫아서 받는다. 내부(packages·remotes)는 시크릿 리터럴 규칙만 본다."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_url: str | None = Field(default=None, alias="$schema")
    name: str = Field(min_length=1, max_length=270)
    version: str = Field(min_length=1, max_length=64)
    title: str | None = None
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    websiteUrl: str | None = None  # noqa: N815 — 형식의 필드 이름 그대로
    repository: dict[str, Any] | None = None
    packages: list[dict[str, Any]] | None = None
    remotes: list[dict[str, Any]] | None = None
    meta: dict[str, Any] | None = Field(default=None, alias="_meta")


TOOL_SCHEMA_ID = "https://github.com/alteralab/harness-catalog/schemas/tool.schema.json"


def tool_json_schema() -> dict[str, Any]:
    """tool.json의 JSON Schema — `ToolSpec`에서 생성한다. `harness-catalog init`이 카탈로그의 `schemas/tool.schema.json`으로 쓰고 `harness-catalog schema tool`이 찍는다.

    문법 밖의 규칙(이름 정규식·경로 정규형·inputSchema 상한·command가 path를 정확히 한 번)은 검사 11만 본다 — 스키마는 모양까지다.
    """
    schema = ToolSpec.model_json_schema(by_alias=True)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": TOOL_SCHEMA_ID, **schema}


def _messages(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in err['loc']) or '$'}: {err['msg']}" for err in e.errors()]


def _load_json(text: bytes | str, what: str) -> tuple[dict[str, object] | None, list[str]]:
    try:
        data: object = json.loads(text.decode("utf-8") if isinstance(text, bytes) else text)
    except (UnicodeDecodeError, ValueError) as e:
        return None, [f"{what}: not valid JSON ({e})"]
    if not isinstance(data, dict):
        return None, [f"{what}: top level must be an object"]
    return cast("dict[str, object]", data), []


def bad_path(path: str) -> str | None:
    """`get_skill_file`과 같은 경로 규칙: 절대 경로·역슬래시·NUL·빈 조각·`.`·`..` 거부. 위반 사유 또는 None."""
    if not path or len(path) > MAX_PATH_CHARS:
        return f"path must be 1..{MAX_PATH_CHARS} chars"
    parts = path.split("/")
    if path.startswith("/") or "\\" in path or "\0" in path or any(p in ("", ".", "..") for p in parts):
        return f"path {path!r} rejected"
    return None


def schema_depth(node: object, depth: int = 1) -> int:
    if isinstance(node, dict):
        return max((schema_depth(v, depth + 1) for v in cast("Mapping[object, object]", node).values()), default=depth)
    if isinstance(node, list):
        return max((schema_depth(v, depth + 1) for v in cast("Sequence[object]", node)), default=depth)
    return depth


def _remote_refs(node: object) -> list[str]:
    """문서 밖을 가리키는 `$ref`(원격·상대 URI). 등록 시 네트워크 해석을 하지 않으므로 거부 대상(§11 2026-10-12 보정)."""
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in cast("Mapping[object, object]", node).items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#"):
                out.append(v)
            out.extend(_remote_refs(v))
    elif isinstance(node, list):
        for v in cast("Sequence[object]", node):
            out.extend(_remote_refs(v))
    return out


def _schema_errors(schema: dict[str, Any], where: str = "inputSchema") -> list[str]:
    """inputSchema·outputSchema 공통: 최상위 object, 크기·깊이 상한, Draft 2020-12 메타스키마, `$ref`는 문서 안만."""
    errors: list[str] = []
    if cast("Mapping[str, object]", schema).get("type") != "object":
        errors.append(f"{where}.type must be 'object'")
    size = len(json.dumps(schema, separators=(",", ":")).encode("utf-8"))
    if size > MAX_INPUT_SCHEMA_BYTES:
        errors.append(f"{where} is {size} bytes > {MAX_INPUT_SCHEMA_BYTES}")
    if (depth := schema_depth(schema)) > MAX_INPUT_SCHEMA_DEPTH:
        errors.append(f"{where} nesting depth {depth} > {MAX_INPUT_SCHEMA_DEPTH}")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        errors.append(f"{where} is not a valid JSON Schema (draft 2020-12): {e.message}")
    errors.extend(f"{where}: $ref {ref!r} points outside the document (only '#…' allowed)" for ref in _remote_refs(schema))
    return errors


def _runtime_errors(runtime: ScriptRuntime | McpRuntime) -> list[str]:
    if isinstance(runtime, McpRuntime):
        return [] if NAME_RE.match(runtime.server) else [f"runtime.server {runtime.server!r}: not a catalog name"]
    errors: list[str] = []
    if (reason := bad_path(runtime.path)) is not None:
        errors.append(f"runtime.path: {reason}")
    if runtime.command.count(runtime.path) != 1:
        errors.append("runtime.command must contain runtime.path as exactly one argv element")
    if any(not c for c in runtime.command):
        errors.append("runtime.command must not contain empty elements")
    return errors


def parse_tool(text: bytes | str) -> tuple[ToolSpec | None, list[str]]:
    """tool.json → (spec, 위반). 위반이 하나라도 있으면 spec은 None."""
    data, errors = _load_json(text, TOOL_FILE)
    if data is None:
        return None, errors
    try:
        spec = ToolSpec.model_validate(data)
    except ValidationError as e:
        return None, _messages(e)
    if not NAME_RE.match(spec.name):
        errors.append(f"name {spec.name!r}: 1-64 chars of [a-z0-9-], starting with [a-z0-9]")
    errors.extend(_schema_errors(spec.inputSchema))
    if spec.outputSchema is not None:
        errors.extend(_schema_errors(spec.outputSchema, "outputSchema"))
    errors.extend(_runtime_errors(spec.runtime))
    return (spec if not errors else None), errors


def _secret_entry_findings(entries: object, where: str) -> list[str]:
    out: list[str] = []
    if not isinstance(entries, list):
        return out
    for i, entry in enumerate(cast("Sequence[object]", entries)):
        if isinstance(entry, dict):
            mapping = cast("Mapping[object, object]", entry)
            if mapping.get(SECRET_FLAG) is True:
                out.extend(f"{where}[{i}]: {k!r} given for a secret ({SECRET_FLAG}: true)" for k in LITERAL_KEYS if k in mapping)
    return out


def secret_literal_findings(node: object) -> list[str]:
    """`packages[*]`·`remotes[*]`의 `environmentVariables`·`headers`·`packageArguments`·`runtimeArguments` 항목이 `isSecret: true`이면서
    `value`·`default`를 가지면 위반(시크릿은 저장소에 없다 — 검사 12). 그 밖의 확장 객체는 보지 않는다(Codex 코드 리뷰 2026-10-11)."""
    out: list[str] = []
    if not isinstance(node, dict):
        return out
    top = cast("Mapping[str, object]", node)
    for group in ("packages", "remotes"):
        items = top.get(group)
        if not isinstance(items, list):
            continue
        for i, item in enumerate(cast("Sequence[object]", items)):
            if isinstance(item, dict):
                entry = cast("Mapping[str, object]", item)
                for coll in SECRET_COLLECTIONS:
                    out.extend(_secret_entry_findings(entry.get(coll), f"{group}[{i}].{coll}"))
    return out


def parse_server(text: bytes | str, dir_name: str) -> tuple[ServerSpec | None, list[str]]:
    """server.json → (spec, 위반). `name`은 디렉토리명 또는 `<이름공간>/<디렉토리명>`, `packages`·`remotes` 중 하나 이상, 시크릿 리터럴 없음."""
    data, errors = _load_json(text, SERVER_FILE)
    if data is None:
        return None, errors
    try:
        spec = ServerSpec.model_validate(data)
    except ValidationError as e:
        return None, _messages(e)
    if not SERVER_NAME_RE.match(spec.name) or spec.name.rsplit("/", 1)[-1] != dir_name:
        errors.append(f"name {spec.name!r} must be {dir_name!r} or '<namespace>/{dir_name}'")
    if not spec.packages and not spec.remotes:
        errors.append("at least one of packages or remotes is required")
    errors.extend(secret_literal_findings({"packages": spec.packages or [], "remotes": spec.remotes or []}))
    return (spec if not errors else None), errors
