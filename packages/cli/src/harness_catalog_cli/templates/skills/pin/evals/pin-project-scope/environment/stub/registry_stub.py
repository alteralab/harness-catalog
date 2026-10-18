# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.3.0"]
# ///
"""레지스트리 스텁 — pin 스킬의 evals 전용. 진짜 레지스트리(OAuth 뒤, tailnet)를 컨테이너 안에 둘 수 없어, 같은 네 도구의 **모양**만
고정 디렉토리에서 낸다(응답 필드는 서버의 pydantic 모델과 같다 — SkillHit·GetSkillResponse·DownloadDescriptor). 검증 대상은 레지스트리가
아니라 pin 스킬이다: 모델이 산문대로 검색 → 판 확인 → archive 명세 → `hc pin` 으로 가는가.

    uv run --script registry_stub.py <fixture-dir>       # stdio MCP 서버. Harbor 가 task.toml 의 mcp_servers 로 띄운다
    uv run --script registry_stub.py --warm               # 의존성만 받고 끝(이미지 빌드 때)

아카이브는 같은 프로세스의 스레드가 127.0.0.1 에서 HTTP 로 낸다(5분 토큰 헤더 검사, GET 한 번). tar 는 결정적(정렬·mtime 0)이라 sha 가 고정이다.
"""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import logging
import secrets
import sys
import tarfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from mcp import types
from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server

TOKEN = secrets.token_urlsafe(24)
ARCHIVES: dict[str, bytes] = {}  # "<name>/<sha>.tar" -> bytes
log = logging.getLogger("stub")


def frontmatter(md: str) -> tuple[dict[str, str], str]:
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, md
    meta: dict[str, str] = {}
    for i, ln in enumerate(lines[1:], start=1):
        if ln.strip() == "---":
            return meta, "\n".join(lines[i + 1 :]).lstrip("\n")
        k, sep, v = ln.partition(":")
        if sep:
            meta[k.strip()] = v.strip()
    return meta, md


def tar_of(skill_dir: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for p in sorted(x for x in skill_dir.rglob("*") if x.is_file()):
            info = tar.gettarinfo(str(p), arcname=p.relative_to(skill_dir).as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            with p.open("rb") as fh:
                tar.addfile(info, fh)
    return buf.getvalue()


class Skill:
    def __init__(self, d: Path) -> None:
        self.name = d.name
        md = (d / "SKILL.md").read_text(encoding="utf-8")
        self.meta, self.body = frontmatter(md)
        paths = sorted(x for x in d.rglob("*") if x.is_file())
        self.paths: list[str] = [p.relative_to(d).as_posix() for p in paths]
        self.sizes: dict[str, int] = {p.relative_to(d).as_posix(): p.stat().st_size for p in paths}
        self.files: list[dict[str, Any]] = [{"path": rel, "size": self.sizes[rel]} for rel in self.paths]
        self.has_scripts = any(rel.startswith("scripts/") for rel in self.paths)
        self.tar = tar_of(d)
        self.sha = hashlib.sha1(self.tar).hexdigest()  # noqa: S324 — git 과 같은 40자 식별자 모양이면 된다
        self.commit = hashlib.sha1(b"commit:" + self.tar).hexdigest()  # noqa: S324
        ARCHIVES[f"{self.name}/{self.sha}.tar"] = self.tar


class ArchiveHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 — 상위 시그니처
        log.info("http " + format, *args)

    def do_GET(self) -> None:  # noqa: N802 — http.server 규약
        key = self.path.removeprefix("/mcp/archive/")
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_error(403, "bad token")
            return
        data = ARCHIVES.get(key)
        if data is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-tar")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_http() -> int:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ArchiveHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def now() -> str:
    return datetime.now(UTC).isoformat()


def ok(payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))], structured_content=payload)


def err(code: str, detail: str) -> types.CallToolResult:
    payload = {"code": code, "detail": detail}  # 서버의 ErrorResponse 와 같은 모양(Codex 2026-10-18)
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))], structured_content=payload, is_error=True)


class Registry:
    """고정 스킬 집합 위의 네 읽기 도구. 응답 모양은 서버의 pydantic 모델과 같다."""

    def __init__(self, fixture: Path, port: int) -> None:
        self.fixture, self.port = fixture, port
        self.skills = {d.name: Skill(d) for d in sorted((fixture / "skills").iterdir()) if (d / "SKILL.md").is_file()}

    def hit(self, s: Skill) -> dict[str, Any]:
        return {"name": s.name, "description": s.meta.get("description", ""), "sha": s.sha, "compatibility": s.meta.get("compatibility"), "has_scripts": s.has_scripts}

    def search_skills(self, args: dict[str, Any]) -> types.CallToolResult:
        q = str(args.get("query", "")).lower()
        found = [self.hit(s) for s in self.skills.values() if not q or q in s.name or q in s.meta.get("description", "").lower()]
        return ok({"skills": found[: int(args.get("limit", 10))], "fetched_at": now()})

    def descriptor(self, s: Skill) -> dict[str, Any]:
        return {"uri": f"http://127.0.0.1:{self.port}/mcp/archive/{s.name}/{s.sha}.tar", "method": "GET", "headers": {"Authorization": f"Bearer {TOKEN}"},
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(), "mimeType": "application/x-tar",
                "size": len(s.tar), "sha256": hashlib.sha256(s.tar).hexdigest(), "digest": f"git-tree:{s.sha}"}

    def file_payload(self, s: Skill, path: str) -> dict[str, Any] | None:
        if path not in s.sizes:
            return None
        text = (self.fixture / "skills" / s.name / path).read_text(encoding="utf-8")
        return {"path": path, "size": s.sizes[path], "blob": hashlib.sha1(text.encode()).hexdigest(), "text": text, "base64": None}  # noqa: S324

    def get_skill(self, args: dict[str, Any]) -> types.CallToolResult:
        s = self.skills.get(str(args.get("id", "")))
        if s is None:
            return err("not_found", f"unknown skill {args.get('id')!r}")
        if args.get("sha") not in (None, "", s.sha):
            return err("unknown_version", f"{s.name} has no version {args.get('sha')}")
        payload: dict[str, Any] = {"id": s.name, "sha": s.sha, "commit": s.commit, "body": s.body, "metadata": {k: v for k, v in s.meta.items() if k not in ("name", "description")},
                                   "files": s.files, "has_scripts": s.has_scripts, "file": None, "archive": None, "fetched_at": now()}
        path = args.get("path")
        if path:
            payload["file"] = self.file_payload(s, str(path))
            if payload["file"] is None:
                return err("not_found", f"{s.name} has no file {path!r}")
            payload["body"] = None
        if args.get("archive"):
            payload["archive"] = self.descriptor(s)
        return ok(payload)

    def search_tools(self, _args: dict[str, Any]) -> types.CallToolResult:
        return ok({"tools": [], "fetched_at": now()})

    def get_tool(self, args: dict[str, Any]) -> types.CallToolResult:
        return err("not_found", f"unknown tool {args.get('id')!r}")


OBJ: dict[str, Any] = {"type": "object"}
TOOLS = [
    types.Tool(name="search_skills", description="Search catalog skills by words in name/description. Returns name, description, sha (version), compatibility, has_scripts.",
               input_schema={**OBJ, "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}),
    types.Tool(name="get_skill", description="Fetch one skill: SKILL.md body and file list; `path` returns one file; `archive=true` adds a download descriptor (uri, 5-minute token header, size, sha256) for `hc pin`.",
               input_schema={**OBJ, "properties": {"id": {"type": "string"}, "sha": {"type": "string"}, "path": {"type": "string"}, "archive": {"type": "boolean", "default": False}}, "required": ["id"]}),
    types.Tool(name="search_tools", description="Search catalog tools by words. (stub: none)", input_schema={**OBJ, "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}),
    types.Tool(name="get_tool", description="Fetch one tool definition. (stub: none)", input_schema={**OBJ, "properties": {"id": {"type": "string"}, "sha": {"type": "string"}, "archive": {"type": "boolean"}}, "required": ["id"]}),
]


def build(fixture: Path, port: int) -> Server[None]:
    reg = Registry(fixture, port)
    handlers = {"search_skills": reg.search_skills, "get_skill": reg.get_skill, "search_tools": reg.search_tools, "get_tool": reg.get_tool}

    async def on_list_tools(_ctx: object, _params: object) -> types.ListToolsResult:
        return types.ListToolsResult(tools=TOOLS)

    async def on_call_tool(_ctx: object, params: types.CallToolRequestParams) -> types.CallToolResult:
        fn = handlers.get(params.name)
        return err("unknown_tool", params.name) if fn is None else fn(dict(params.arguments or {}))

    return Server("harness-catalog", instructions="Stub registry for evals: the four read tools over a fixed skill set.", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def main_async(fixture: Path) -> None:
    port = start_http()
    server = build(fixture, port)
    log.info("serving %s ; archives on 127.0.0.1:%d", fixture, port)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--warm":
        return 0
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[stub] %(message)s")
    if len(sys.argv) != 2:
        log.error("usage: registry_stub.py <fixture-dir> | --warm")
        return 2
    anyio.run(main_async, Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
