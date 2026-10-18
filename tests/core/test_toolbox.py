"""toolbox 레코드 검증(tool.json·server.json)과 검사 11·12, 카탈로그의 search_tools·get_tool·도구 아카이브."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness_catalog_core.catalog import Catalog
from harness_catalog_core.check import check_commit
from harness_catalog_core.model import CatalogError, ErrorCode, ReadyReason
from harness_catalog_core.toolbox import MAX_INPUT_SCHEMA_BYTES, parse_server, parse_tool, tool_json_schema

from .fakes import FakeStore, FakeValidator, MemoryFacts

SKILL = {"SKILL.md": b"---\nname: yt-subs\ndescription: subtitles\n---\nbody\n"}


def tool_json(name: str = "subs-fetch", **over: object) -> bytes:
    spec: dict[str, object] = {
        "name": name,
        "description": "Fetch YouTube subtitles as text. 유튜브 자막 추출.",
        "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        "runtime": {"kind": "script", "path": "scripts/fetch.py", "command": ["uv", "run", "--script", "scripts/fetch.py"]},
        "metadata": {"requires-tools": "uv yt-dlp"},
    }
    spec.update(over)
    return json.dumps(spec).encode()


def server_json(name: str = "graft", **over: object) -> bytes:
    spec: dict[str, object] = {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": f"lab.altera/{name}",
        "version": "0.21.1",
        "description": "Code graph MCP server",
        "packages": [{"registryType": "npm", "identifier": "@nanonets/graft", "version": "0.21.1", "transport": {"type": "stdio"},
                      "environmentVariables": [{"name": "GRAFT_TOKEN", "isSecret": True}]}],
    }
    spec.update(over)
    return json.dumps(spec).encode()


SCRIPT_TOOL = {"tool.json": tool_json(), "scripts/fetch.py": b"print('subs')\n"}
MCP_TOOL = {"tool.json": tool_json("graft-ask", description="Ask the code graph where a symbol lives.", runtime={"kind": "mcp", "server": "graft", "tool": "graft_find_code"}, metadata={})}
SERVER = {"server.json": server_json()}


# ---- tool.json ----
def test_parse_tool_accepts_both_kinds() -> None:
    spec, errors = parse_tool(SCRIPT_TOOL["tool.json"])
    assert errors == [] and spec is not None and spec.runtime.kind == "script"
    spec, errors = parse_tool(MCP_TOOL["tool.json"])
    assert errors == [] and spec is not None and spec.runtime.kind == "mcp" and spec.runtime.server == "graft"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("over", "needle"),
    [
        ({"runtime": {"kind": "http", "url": "x"}}, "runtime"),  # 닫힌 판별자
        ({"runtime": {"kind": "script", "path": "../x.py", "command": ["python", "../x.py"]}}, "runtime.path"),
        ({"runtime": {"kind": "script", "path": "scripts/fetch.py", "command": ["python"]}}, "exactly one argv element"),
        ({"runtime": {"kind": "script", "path": "scripts/fetch.py", "command": ["sh", "-c", "python scripts/fetch.py scripts/fetch.py"]}}, "exactly one argv element"),
        ({"inputSchema": {"type": "string"}}, "inputSchema.type"),
        ({"inputSchema": {"type": "object", "properties": {"big": {"description": "x" * (MAX_INPUT_SCHEMA_BYTES + 10)}}}}, "bytes >"),
        ({"name": "Bad_Name"}, "name"),
        ({"description": ""}, "description"),
        ({"extra": 1}, "extra"),
        ({"metadata": {"k": 1}}, "metadata"),
        ({"inputSchema": {"type": "object", "properties": 5}}, "not a valid JSON Schema"),  # 메타스키마(§11 2026-10-12 보정)
        ({"inputSchema": {"type": "object", "properties": {"x": {"$ref": "https://example.com/x.json"}}}}, "outside the document"),
        ({"outputSchema": {"type": "string"}}, "outputSchema.type"),
        ({"outputSchema": {"type": "object", "required": "passed"}}, "outputSchema is not a valid JSON Schema"),
    ],
)
def test_parse_tool_rejects(over: dict[str, object], needle: str) -> None:
    name = str(over.get("name", "subs-fetch"))
    spec, errors = parse_tool(tool_json(name, **{k: v for k, v in over.items() if k != "name"}))
    assert spec is None and any(needle in e for e in errors), errors


def test_parse_tool_accepts_output_schema_with_local_refs() -> None:
    """outputSchema는 선택이고 MCP Tool.outputSchema와 같은 이름. 문서 안 $ref는 허용, 도메인 필드는 도구별(공통 강제 없음)."""
    out = {"type": "object", "$defs": {"c": {"type": "object", "properties": {"name": {"type": "string"}, "passed": {"type": "boolean"}, "gap": {"type": "string"}}}}, "properties": {"passed": {"type": "boolean"}, "criteria": {"type": "array", "items": {"$ref": "#/$defs/c"}}, "summary": {"type": "string"}}, "required": ["passed", "summary"]}
    spec, errors = parse_tool(tool_json(outputSchema=out))
    assert errors == [] and spec is not None and spec.outputSchema == out
    assert parse_tool(tool_json())[0].outputSchema is None  # type: ignore[union-attr]
    assert "outputSchema" in tool_json_schema()["properties"]


def test_parse_tool_accepts_editor_schema_pointer_and_generates_json_schema() -> None:
    """`$schema`는 선택 문자열(편집기용)이고, tool.json의 JSON Schema는 ToolSpec에서 나오며 실린 레코드가 그 스키마에 맞는다(§11 2026-10-11 write-tool)."""
    import jsonschema

    spec, errors = parse_tool(tool_json("subs-fetch", **{"$schema": "../../schemas/tool.schema.json"}))
    assert errors == [] and spec is not None and spec.schema_url == "../../schemas/tool.schema.json"
    assert parse_tool(tool_json("subs-fetch", **{"$schema": 1}))[0] is None
    schema = tool_json_schema()
    assert schema["$schema"].startswith("https://json-schema.org/") and schema["additionalProperties"] is False
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(json.loads(tool_json()), schema)
    jsonschema.validate(json.loads(MCP_TOOL["tool.json"]), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(json.loads(tool_json(runtime={"kind": "http", "url": "x"})), schema)


def test_parse_tool_depth_and_json_errors() -> None:
    deep: dict[str, object] = {"type": "object"}
    node = deep
    for _ in range(20):
        child: dict[str, object] = {"type": "object"}
        node["properties"] = {"x": child}
        node = child
    spec, errors = parse_tool(tool_json(inputSchema=deep))
    assert spec is None and any("depth" in e for e in errors)
    assert parse_tool(b"not json")[0] is None and parse_tool(b"[]")[0] is None


# ---- server.json ----
def test_parse_server_rules() -> None:
    spec, errors = parse_server(server_json(), "graft")
    assert errors == [] and spec is not None and spec.name == "lab.altera/graft"
    assert parse_server(server_json(name="graft"), "graft")[1] == []  # 이름공간 없이도
    _, errors = parse_server(server_json(), "other")
    assert any("must be 'other'" in e for e in errors)
    _, errors = parse_server(server_json(packages=None), "graft")
    assert any("packages or remotes" in e for e in errors)
    leaked = server_json(packages=[{"registryType": "npm", "identifier": "x", "version": "1", "transport": {"type": "stdio"},
                                    "environmentVariables": [{"name": "TOKEN", "isSecret": True, "value": "hunter2"}]}])
    _, errors = parse_server(leaked, "graft")
    assert any("isSecret" in e and "'value'" in e for e in errors)
    _, errors = parse_server(server_json(tools=[{"name": "x"}]), "graft")  # 최상위 허용 필드 밖
    assert any("tools" in e for e in errors)


# ---- 검사 11·12 ----
def make(tmp_path: Path, **kw: object) -> tuple[Catalog, FakeStore]:
    store = FakeStore({"yt-subs": SKILL}, **kw)  # type: ignore[arg-type]
    return Catalog(store, FakeValidator(), MemoryFacts(), workdir=tmp_path), store


def test_check_items_11_and_12(tmp_path: Path) -> None:
    store = FakeStore({"yt-subs": SKILL}, tools={"subs-fetch": SCRIPT_TOOL, "graft-ask": MCP_TOOL}, servers={"graft": SERVER})
    report = check_commit(store, FakeValidator(), store.commit, workdir=tmp_path)
    assert report.errors == ()
    # 참조 서버 없음·스킬과 이름 충돌·경로가 트리에 없음·시크릿
    bad_tools = {
        "graft-ask": MCP_TOOL,  # 서버 레코드가 없다
        "yt-subs": {"tool.json": tool_json("yt-subs", runtime={"kind": "script", "path": "a.py", "command": ["python", "a.py"]}), "a.py": b"x"},
        "ghost": {"tool.json": tool_json("ghost")},  # scripts/fetch.py 없음
        "leaky": {"tool.json": tool_json("leaky"), "scripts/fetch.py": b"SECRET=1\n"},
    }
    store = FakeStore({"yt-subs": SKILL}, tools=bad_tools, servers={"bad": {"server.json": server_json(name="other")}})
    report = check_commit(store, FakeValidator(), store.commit, workdir=tmp_path)
    by_name = {(f.item, f.skill, f.kind) for f in report.errors}
    assert (11, "graft-ask", "tool") in by_name and (11, "yt-subs", "tool") in by_name and (11, "ghost", "tool") in by_name
    assert (4, "leaky", "tool") in by_name and (12, "bad", "server") in by_name
    assert report.rejected_tools() == frozenset({"graft-ask", "yt-subs", "ghost", "leaky"}) and report.rejected_skills() == frozenset()


def test_structure_violation_under_tools_makes_catalog_unready(tmp_path: Path) -> None:
    cat, _ = make(tmp_path, tools={"no-json": {"README.md": b"not a tool"}})
    status = cat.rebuild()
    assert not status.ready and status.reasons == (ReadyReason.LAYOUT_MISMATCH,)
    assert any(d.startswith("check:11:tools/no-json/tool.json missing") for d in status.degraded)


# ---- 카탈로그 ----
def test_search_tools_and_get_tool(tmp_path: Path) -> None:
    cat, store = make(tmp_path, tools={"subs-fetch": SCRIPT_TOOL, "graft-ask": MCP_TOOL}, servers={"graft": SERVER})
    assert cat.rebuild().ready
    hits = cat.search_tools("유튜브 자막").tools
    assert [t.name for t in hits] == ["subs-fetch"] and hits[0].kind == "script"
    assert [t.name for t in cat.search_tools("graft").tools] == ["graft-ask"]
    assert cat.search_tools("graft").tools[0].server == "graft"
    assert [s.name for s in cat.search_skills("subtitles").skills] == ["yt-subs"]  # 스킬 검색에 도구가 섞이지 않는다
    body = cat.get_tool("graft-ask")
    assert body.kind == "mcp" and body.server is not None and body.server["name"] == "lab.altera/graft" and body.sha == store.tree_of("graft-ask", "tools")
    script = cat.get_tool("subs-fetch")
    assert script.kind == "script" and script.server is None and sorted(f.path for f in script.files) == ["scripts/fetch.py", "tool.json"]
    info = cat.get_tool_archive("subs-fetch")
    assert info.kind == "tools" and info.path.parent == tmp_path / "archives" / "tools" and info.name == "subs-fetch"
    with pytest.raises(CatalogError) as e:
        cat.get_tool("nope")
    assert e.value.code == ErrorCode.NOT_FOUND
    with pytest.raises(CatalogError) as e:
        cat.get_tool("subs-fetch", "f" * 40)
    assert e.value.code == ErrorCode.UNKNOWN_VERSION
    with pytest.raises(CatalogError) as e:
        cat.get_archive("skills", "subs-fetch")  # 도구 이름을 스킬 아카이브로 — 종류가 다르면 없는 것이다
    assert e.value.code == ErrorCode.NOT_FOUND


def test_rejected_tool_is_excluded_but_skills_still_indexed(tmp_path: Path) -> None:
    cat, _ = make(tmp_path, tools={"graft-ask": MCP_TOOL})  # 서버 레코드 없음 → 항목 11 거부
    status = cat.rebuild()
    assert status.ready and cat.search_tools("graft").tools == () and [s.name for s in cat.search_skills("subtitles").skills] == ["yt-subs"]
    assert ("graft-ask", "11: runtime.server 'graft' not found under mcp-servers/ (or rejected by item 12)") in status.rejected


def test_db_rank_only_when_synced(tmp_path: Path) -> None:
    """DB 교체가 실패한 뒤에는 복구된 DB의 구판 순위를 쓰지 않고 메모리 검색으로 떨어진다(Codex 설계 리뷰 2026-10-11)."""
    store = FakeStore({"yt-subs": SKILL}, tools={"subs-fetch": SCRIPT_TOOL})
    facts = MemoryFacts(available=False)
    calls: list[str] = []

    def search(query: str, limit: int, kind: str = "skills") -> tuple[str, ...] | None:
        calls.append(kind)
        return ("nothing",)

    facts.search = search  # type: ignore[method-assign]
    cat = Catalog(store, FakeValidator(), facts, workdir=tmp_path)
    assert "db_unavailable" in cat.rebuild().degraded
    assert [t.name for t in cat.search_tools("subs").tools] == ["subs-fetch"] and calls == []  # DB를 묻지 않았다
    facts.available = True
    assert cat.rebuild().degraded == ()
    cat.search_tools("subs")
    assert calls == ["tools"]  # 반영된 뒤에는 DB 순위를 쓴다


def test_secret_rule_scoped_to_registry_collections() -> None:
    """isSecret 규칙은 environmentVariables·headers·packageArguments·runtimeArguments 항목에만 — 확장 객체의 isSecret은 보지 않는다."""
    ok = server_json(packages=[{"registryType": "npm", "identifier": "x", "version": "1", "transport": {"type": "stdio"},
                                "_meta": {"vendor.example/ext": {"isSecret": True, "value": "not an env entry"}}}])
    assert parse_server(ok, "graft")[1] == []
    bad = server_json(remotes=[{"type": "streamable-http", "url": "https://x/mcp", "headers": [{"name": "Authorization", "isSecret": True, "default": "Bearer x"}]}], packages=None)
    _, errors = parse_server(bad, "graft")
    assert errors == ["remotes[0].headers[0]: 'default' given for a secret (isSecret: true)"]


def test_tool_referencing_rejected_server_is_rejected(tmp_path: Path) -> None:
    cat, _ = make(tmp_path, tools={"graft-ask": MCP_TOOL}, servers={"graft": {"server.json": server_json(name="wrong-name")}})
    status = cat.rebuild()
    assert status.ready and cat.search_tools("graph").tools == ()
    reasons = {n: r for n, r in status.rejected}
    assert reasons["graft"].startswith("12:") and "rejected by item 12" in reasons["graft-ask"]

