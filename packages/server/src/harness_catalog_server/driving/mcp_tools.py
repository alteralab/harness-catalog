"""MCP 어댑터: 도구 여섯(스킬 넷 + toolbox 둘)을 앱 함수 호출로 바꾸고 결과를 MCP 응답으로. 응답 모양은 responses.py의 모델이 정본(outputSchema). 스팬 속성도 여기서 끝난다."""

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
    GetToolResponse,
    LoadSkillResponse,
    SearchSkillsResponse,
    SearchToolsResponse,
    SkillArchiveResponse,
    SkillFileResponse,
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
        return _ok(SearchSkillsResponse(skills=[SkillHit(name=s.name, description=s.description, sha=s.sha, replaced_by=s.replaced_by, requires_tools=list(s.requires_tools), compatibility=s.compatibility) for s in result.skills], fetched_at=result.fetched_at))

    async def load_skill(self, id: str, sha: str | None = None) -> Annotated[CallToolResult, LoadSkillResponse]:  # noqa: A002
        p = self._principal("load_skill")
        if isinstance(p, CallToolResult):
            return p
        try:
            body = await anyio.to_thread.run_sync(self._catalog.load_skill, id, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_SKILL: body.name, ATTR_SHA: body.sha})
        return _ok(LoadSkillResponse(
            id=body.name, body=body.body, sha=body.sha, commit=body.commit, metadata=dict(body.metadata),
            files=[FileEntry(path=f.path, size=f.size) for f in body.files], has_scripts=body.has_scripts, fetched_at=body.fetched_at,
        ))

    async def get_skill_archive(self, id: str, sha: str | None = None) -> Annotated[CallToolResult, SkillArchiveResponse]:  # noqa: A002
        """SEP-2631 다운로드 명세 모양: uri·method·headers·expires_at·size·sha256·digest. 자격은 헤더에만 있다."""
        p = self._principal("get_skill_archive")
        if isinstance(p, CallToolResult):
            return p
        if self._signer is None or not self._public_url:
            return _error(ErrorCode.NOT_FOUND, "archive download is not enabled on this server")
        try:
            info = await anyio.to_thread.run_sync(self._catalog.get_skill_archive, id, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_SKILL: info.name, ATTR_SHA: info.sha})
        return _ok(SkillArchiveResponse(id=info.name, sha=info.sha, commit=info.commit, **dump(self._descriptor(info))))

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
        return _ok(SearchToolsResponse(tools=[ToolHit(name=x.name, description=x.description, sha=x.sha, kind=_kind(x.kind), server=x.server, replaced_by=x.replaced_by, requires_tools=list(x.requires_tools)) for x in result.tools], fetched_at=result.fetched_at))

    async def get_tool(self, id: str, sha: str | None = None) -> Annotated[CallToolResult, GetToolResponse]:  # noqa: A002
        """tool.json 전체 + 판·커밋·파일 목록. kind=mcp면 server.json을 `server`에, kind=script면 다운로드 명세를 `archive`에. 레지스트리는 발견까지 — 도구를 부르지 않는다."""
        p = self._principal("get_tool")
        if isinstance(p, CallToolResult):
            return p
        try:
            body = await anyio.to_thread.run_sync(self._catalog.get_tool, id, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_TOOL: body.name, ATTR_SHA: body.sha})
        archive: DownloadDescriptor | None = None
        if body.kind == "script":
            if self._signer is None or not self._public_url:
                return _error(ErrorCode.NOT_FOUND, "archive download is not enabled on this server — script tools cannot be served")
            try:
                archive = self._descriptor(await anyio.to_thread.run_sync(self._catalog.get_tool_archive, id, body.sha))
            except CatalogError as e:
                return _error(e.code, e.detail)
        return _ok(GetToolResponse(
            id=body.name, sha=body.sha, commit=body.commit, kind=_kind(body.kind), tool=ToolSpec.model_validate(dict(body.spec)),
            server=ServerSpec.model_validate(dict(body.server)) if body.server is not None else None, archive=archive,
            files=[FileEntry(path=f.path, size=f.size) for f in body.files], fetched_at=body.fetched_at,
        ))

    async def get_skill_file(self, id: str, path: str, sha: str | None = None) -> Annotated[CallToolResult, SkillFileResponse]:  # noqa: A002
        p = self._principal("get_skill_file")
        if isinstance(p, CallToolResult):
            return p
        try:
            f = await anyio.to_thread.run_sync(self._catalog.get_skill_file, id, path, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_SKILL: id, ATTR_SHA: f.sha})
        return _ok(SkillFileResponse(id=id, path=f.path, size=f.size, sha=f.sha, blob=f.blob, text=f.text, base64=f.base64))


def build_server(catalog: Catalog, *, issuer: str, public_url: str, verifier: TokenVerifier, signer: ArchiveSigner | None = None) -> MCPServer[None]:
    """도구 여섯을 등록한 MCPServer. 인가 설정은 SDK가 RFC 9728·챌린지로 낸다(scopes_supported = required_scopes)."""
    auth = AuthSettings(issuer_url=AnyHttpUrl(issuer), resource_server_url=AnyHttpUrl(public_url), required_scopes=list(required_scopes(public_url)), validate_token_resource=True)
    server: MCPServer[None] = MCPServer(name="harness-catalog", instructions="Skill and tool catalog: search and load skills and their files; search and read tool definitions (toolbox). No full-listing tools: search by topic.", auth=auth, token_verifier=verifier)
    b = ToolBindings(catalog, signer=signer, public_url=public_url)
    server.tool(name="search_skills", description="Lexical search over id, description and metadata values; each hit: id, description, sha (tree), replaced_by, requires_tools, compatibility. There is no full-listing tool: search by topic. limit 1..20 (default 10).")(b.search_skills)
    server.tool(name="load_skill", description="SKILL.md body with sha, commit, metadata and file list. sha optional (default: current main).")(b.load_skill)
    server.tool(name="get_skill_file", description="One file of a skill (text or base64). Path traversal and symlinks are rejected; 1 MB per file.")(b.get_skill_file)
    server.tool(name="search_tools", description="Toolbox: lexical search over tool definitions (name, description, metadata). Each hit: name, description, sha (tree), kind (script|mcp), server, replaced_by, requires_tools. limit 1..20 (default 10).")(b.search_tools)
    server.tool(name="get_tool", description="Toolbox: one tool definition (tool.json: name, description, inputSchema, runtime) with sha, commit and files; for kind=mcp the referenced mcp-servers/<server>/server.json; for kind=script a download descriptor for its files. The registry never calls the tool. sha optional (default: current main).")(b.get_tool)
    if signer is not None:
        server.tool(name="get_skill_archive", description="Download descriptor for one skill version as a tar: uri + headers (5-minute token), size, sha256. Fetch it with curl; the files never pass through the model. sha optional (default: current main).")(b.get_skill_archive)
    return server
