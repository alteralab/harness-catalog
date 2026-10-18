"""MCP 어댑터: 도구 넷(search_skills·get_skill·search_tools·get_tool)을 앱 함수 호출로 바꾸고 결과를 MCP 응답으로. 응답 모양은 responses.py의 모델이 정본(outputSchema). 스팬 속성도 여기서 끝난다."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
from opentelemetry import trace
from pydantic import AnyHttpUrl, BaseModel

from harness_catalog_core.authz import authorize, principal_from_claims
from harness_catalog_core.archive_token import TOKEN_HEADER, ArchiveSigner
from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import ArchiveInfo, CatalogError, ErrorCode, Principal, required_scopes
from harness_catalog_core.toolbox import ServerSpec, ToolSpec

from .responses import (
    DownloadDescriptor,
    ErrorResponse,
    FileEntry,
    GetSkillResponse,
    GetToolResponse,
    SearchSkillsResponse,
    SearchToolsResponse,
    SkillFilePayload,
    SkillHit,
    ToolHit,
    dump,
)

ATTR_USER = "langfuse.user.id"
ATTR_SKILL = "harness_catalog.skill"
ATTR_TOOL = "harness_catalog.tool"
ATTR_SHA = "harness_catalog.sha"
ATTR_QUERY = "harness_catalog.query"
ATTR_RESULT_COUNT = "harness_catalog.result_count"


def _ok(model: BaseModel) -> CallToolResult:
    """성공 응답: 모델을 한 번 직렬화해 text와 structuredContent에 같은 JSON을 싣는다. SDK가 structuredContent를 outputSchema의 모델로 다시 검증한다."""
    payload = dump(model)
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))], structured_content=payload)


def _kind(value: str) -> Literal["script", "mcp"]:
    """core는 kind를 str로 들고 오지만 검사 11이 판별자를 닫아 두었다. 응답 모델의 Literal로 좁힌다."""
    if value == "script" or value == "mcp":
        return value
    raise CatalogError(ErrorCode.NOT_FOUND, f"unknown runtime kind {value!r}")


def _error(code: ErrorCode, detail: str) -> CallToolResult:
    payload = dump(ErrorResponse(code=str(code), detail=detail))
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))], structured_content=payload, is_error=True)


class ToolBindings:
    """인가 → 앱 호출 → 응답. 도구마다 메서드 하나."""

    def __init__(self, catalog: Catalog, *, signer: ArchiveSigner | None = None, public_url: str = "") -> None:
        self._catalog = catalog
        self._signer = signer
        self._public_url = public_url.rstrip("/")

    def _principal(self, tool: str) -> Principal | CallToolResult:
        token = get_access_token()
        claims: Mapping[str, Any] = token.claims if token is not None and token.claims is not None else {}
        principal = principal_from_claims(claims)
        trace.get_current_span().set_attribute(ATTR_USER, principal.subject)
        decision = authorize(principal, tool)
        if not decision.allowed:
            return _error(decision.code or ErrorCode.NOT_A_MEMBER, decision.detail)
        return principal

    async def search_skills(self, query: str, limit: int = 10) -> Annotated[CallToolResult, SearchSkillsResponse]:
        p = self._principal("search_skills")
        if isinstance(p, CallToolResult):
            return p
        span = trace.get_current_span()
        span.set_attribute(ATTR_QUERY, "".join(ch for ch in query[:2000] if ch.isprintable()))
        try:
            result = await anyio.to_thread.run_sync(self._catalog.search_skills, query, limit)
        except CatalogError as e:
            return _error(e.code, e.detail)
        span.set_attribute(ATTR_RESULT_COUNT, len(result.skills))
        return _ok(SearchSkillsResponse(skills=[SkillHit(name=s.name, description=s.description, sha=s.sha, compatibility=s.compatibility, has_scripts=s.has_scripts) for s in result.skills], fetched_at=result.fetched_at))

    async def get_skill(self, id: str, sha: str | None = None, path: str | None = None, archive: bool = False) -> Annotated[CallToolResult, GetSkillResponse]:  # noqa: A002
        """한 판의 스킬. 기본은 SKILL.md 본문·메타데이터·파일 목록; `path`면 그 파일 하나(본문은 null); `archive`면 tar 다운로드 명세(SEP-2631 모양, 자격은 헤더에만). §11 2026-10-18: load_skill·get_skill_file·get_skill_archive를 접은 것."""
        p = self._principal("get_skill")
        if isinstance(p, CallToolResult):
            return p
        try:
            body = await anyio.to_thread.run_sync(self._catalog.get_skill, id, sha)
            payload: SkillFilePayload | None = None
            if path is not None:
                f = await anyio.to_thread.run_sync(self._catalog.get_skill_file, id, path, body.sha)
                payload = SkillFilePayload(path=f.path, size=f.size, blob=f.blob, text=f.text, base64=f.base64)
            descriptor: DownloadDescriptor | None = None
            if archive:
                if self._signer is None or not self._public_url:
                    return _error(ErrorCode.NOT_FOUND, "archive download is not enabled on this server")
                descriptor = self._descriptor(await anyio.to_thread.run_sync(self._catalog.get_skill_archive, id, body.sha))
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_SKILL: body.name, ATTR_SHA: body.sha})
        return _ok(GetSkillResponse(
            id=body.name, sha=body.sha, commit=body.commit, body=None if path is not None else body.body, metadata=dict(body.metadata),
            files=[FileEntry(path=f.path, size=f.size) for f in body.files], has_scripts=body.has_scripts, file=payload, archive=descriptor, fetched_at=body.fetched_at,
        ))

    def _descriptor(self, info: ArchiveInfo) -> DownloadDescriptor:
        """SEP-2631 모양의 다운로드 명세. 자격(헤더 토큰)은 URL 밖. 종류가 서명 범위에 들어 스킬·도구 토큰이 섞이지 않는다."""
        assert self._signer is not None
        kind = "tools" if info.kind == "tools" else "skills"
        token, exp = self._signer.mint(info.name, info.sha, kind=kind)
        prefix = "/archive/tools" if kind == "tools" else "/archive"
        return DownloadDescriptor(
            uri=f"{self._public_url}{prefix}/{info.name}/{info.sha}.tar", method="GET",
            headers={TOKEN_HEADER: token}, expires_at=datetime.fromtimestamp(exp, UTC),
            mimeType="application/x-tar", size=info.size, sha256=info.sha256, digest=f"git-tree:{info.sha}",
        )

    # ---- toolbox (DESIGN §11 2026-10-11) ----
    async def search_tools(self, query: str, limit: int = 10) -> Annotated[CallToolResult, SearchToolsResponse]:
        p = self._principal("search_tools")
        if isinstance(p, CallToolResult):
            return p
        span = trace.get_current_span()
        span.set_attribute(ATTR_QUERY, "".join(ch for ch in query[:2000] if ch.isprintable()))
        try:
            result = await anyio.to_thread.run_sync(self._catalog.search_tools, query, limit)
        except CatalogError as e:
            return _error(e.code, e.detail)
        span.set_attribute(ATTR_RESULT_COUNT, len(result.tools))
        return _ok(SearchToolsResponse(tools=[ToolHit(name=x.name, description=x.description, sha=x.sha, kind=_kind(x.kind), server=x.server) for x in result.tools], fetched_at=result.fetched_at))

    async def get_tool(self, id: str, sha: str | None = None, archive: bool = False) -> Annotated[CallToolResult, GetToolResponse]:  # noqa: A002
        """tool.json 전체 + 판·커밋·파일 목록. kind=mcp면 server.json을 `server`에; kind=script이고 `archive=true`면 다운로드 명세를 `archive`에(옵트인, get_skill과 대칭). 레지스트리는 발견까지 — 도구를 부르지 않는다."""
        p = self._principal("get_tool")
        if isinstance(p, CallToolResult):
            return p
        try:
            body = await anyio.to_thread.run_sync(self._catalog.get_tool, id, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_TOOL: body.name, ATTR_SHA: body.sha})
        descriptor: DownloadDescriptor | None = None
        if archive and body.kind == "script":
            if self._signer is None or not self._public_url:
                return _error(ErrorCode.NOT_FOUND, "archive download is not enabled on this server — script tools cannot be fetched")
            try:
                descriptor = self._descriptor(await anyio.to_thread.run_sync(self._catalog.get_tool_archive, id, body.sha))
            except CatalogError as e:
                return _error(e.code, e.detail)
        return _ok(GetToolResponse(
            id=body.name, sha=body.sha, commit=body.commit, kind=_kind(body.kind), tool=ToolSpec.model_validate(dict(body.spec)),
            server=ServerSpec.model_validate(dict(body.server)) if body.server is not None else None, archive=descriptor,
            files=[FileEntry(path=f.path, size=f.size) for f in body.files], fetched_at=body.fetched_at,
        ))


def build_server(catalog: Catalog, *, issuer: str, public_url: str, verifier: TokenVerifier, signer: ArchiveSigner | None = None) -> MCPServer[None]:
    """도구 넷을 등록한 MCPServer. 인가 설정은 SDK가 RFC 9728·챌린지로 낸다(scopes_supported = required_scopes)."""
    auth = AuthSettings(issuer_url=AnyHttpUrl(issuer), resource_server_url=AnyHttpUrl(public_url), required_scopes=list(required_scopes(public_url)), validate_token_resource=True)
    server: MCPServer[None] = MCPServer(name="harness-catalog", instructions="Skill and tool catalog: search skills and get one (body, a file, or a tar descriptor); search tools and get one definition (toolbox). No full-listing tools: search by topic.", auth=auth, token_verifier=verifier)
    b = ToolBindings(catalog, signer=signer, public_url=public_url)
    server.tool(name="search_skills", description="Lexical search over id, description and metadata values; each hit: id, description, sha (tree), compatibility, has_scripts. There is no full-listing tool: search by topic. limit 1..20 (default 10).")(b.search_skills)
    server.tool(name="get_skill", description="One skill version: SKILL.md body with sha, commit, metadata and file list (default); with `path`, that one file instead of the body (text or base64; traversal and symlinks rejected, 1 MB); with `archive=true`, also a tar download descriptor (uri + headers with a 5-minute token, size, sha256) — fetch it with curl, the files never pass through the model. sha optional (default: current main).")(b.get_skill)
    server.tool(name="search_tools", description="Toolbox: lexical search over tool definitions (name, description, metadata). Each hit: name, description, sha (tree), kind (script|mcp), server. limit 1..20 (default 10).")(b.search_tools)
    server.tool(name="get_tool", description="Toolbox: one tool definition (tool.json: name, description, inputSchema, outputSchema, runtime) with sha, commit and files; for kind=mcp the referenced mcp-servers/<server>/server.json; for kind=script with `archive=true` a tar download descriptor for its files. The registry never calls the tool. sha optional (default: current main).")(b.get_tool)
    return server
