"""MCP 어댑터: 도구 넷을 앱 함수 호출로 바꾸고 결과를 MCP 응답으로. 스팬 속성도 여기서 끝난다."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
from opentelemetry import trace
from pydantic import AnyHttpUrl

from harness_catalog_core.authz import authorize, principal_from_claims
from harness_catalog_core.archive_token import TOKEN_HEADER, ArchiveSigner
from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import CatalogError, ErrorCode, ListResult, Principal, required_scopes

ATTR_USER = "langfuse.user.id"
ATTR_SKILL = "harness_catalog.skill"
ATTR_SHA = "harness_catalog.sha"
ATTR_QUERY = "harness_catalog.query"
ATTR_RESULT_COUNT = "harness_catalog.result_count"


def _ok(payload: Mapping[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))], structured_content=dict(payload))


def _error(code: ErrorCode, detail: str) -> CallToolResult:
    payload = {"code": str(code), "detail": detail}
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))], structured_content=payload, is_error=True)


def _listing(result: ListResult) -> Mapping[str, Any]:
    return {"skills": [asdict(s) for s in result.skills], "fetched_at": result.fetched_at.isoformat()}


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

    async def list_skills(self) -> CallToolResult:
        p = self._principal("list_skills")
        if isinstance(p, CallToolResult):
            return p
        try:
            result = await anyio.to_thread.run_sync(self._catalog.list_skills)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attribute(ATTR_RESULT_COUNT, len(result.skills))
        return _ok(_listing(result))

    async def search_skills(self, query: str, limit: int = 10) -> CallToolResult:
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
        return _ok(_listing(result))

    async def load_skill(self, id: str, sha: str | None = None) -> CallToolResult:  # noqa: A002
        p = self._principal("load_skill")
        if isinstance(p, CallToolResult):
            return p
        try:
            body = await anyio.to_thread.run_sync(self._catalog.load_skill, id, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_SKILL: body.name, ATTR_SHA: body.sha})
        return _ok({
            "id": body.name, "body": body.body, "sha": body.sha, "commit": body.commit, "metadata": dict(body.metadata),
            "files": [asdict(f) for f in body.files], "has_scripts": body.has_scripts, "fetched_at": body.fetched_at.isoformat(),
        })

    async def get_skill_archive(self, id: str, sha: str | None = None) -> CallToolResult:  # noqa: A002
        """SEP-2631 다운로드 기술자 모양: uri·method·headers·expires_at·size·sha256·digest. 자격은 헤더에만 있다."""
        p = self._principal("get_skill_archive")
        if isinstance(p, CallToolResult):
            return p
        if self._signer is None or not self._public_url:
            return _error(ErrorCode.NOT_FOUND, "archive download is not enabled on this server")
        try:
            info = await anyio.to_thread.run_sync(self._catalog.get_skill_archive, id, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        token, exp = self._signer.mint(info.name, info.sha)
        trace.get_current_span().set_attributes({ATTR_SKILL: info.name, ATTR_SHA: info.sha})
        return _ok({
            "id": info.name, "sha": info.sha, "commit": info.commit,
            "uri": f"{self._public_url}/archive/{info.name}/{info.sha}.tar", "method": "GET",
            "headers": {TOKEN_HEADER: token}, "expires_at": datetime.fromtimestamp(exp, UTC).isoformat(),
            "mimeType": "application/x-tar", "size": info.size, "sha256": info.sha256, "digest": f"git-tree:{info.sha}",
        })

    async def get_skill_file(self, id: str, path: str, sha: str | None = None) -> CallToolResult:  # noqa: A002
        p = self._principal("get_skill_file")
        if isinstance(p, CallToolResult):
            return p
        try:
            f = await anyio.to_thread.run_sync(self._catalog.get_skill_file, id, path, sha)
        except CatalogError as e:
            return _error(e.code, e.detail)
        trace.get_current_span().set_attributes({ATTR_SKILL: id, ATTR_SHA: f.sha})
        return _ok({"id": id, "path": f.path, "size": f.size, "sha": f.sha, "blob": f.blob, "text": f.text, "base64": f.base64})


def build_server(catalog: Catalog, *, issuer: str, public_url: str, verifier: TokenVerifier, signer: ArchiveSigner | None = None) -> MCPServer[None]:
    """도구 다섯을 등록한 MCPServer. 인가 설정은 SDK가 RFC 9728·챌린지로 낸다(scopes_supported = required_scopes)."""
    auth = AuthSettings(issuer_url=AnyHttpUrl(issuer), resource_server_url=AnyHttpUrl(public_url), required_scopes=list(required_scopes(public_url)), validate_token_resource=True)
    server: MCPServer[None] = MCPServer(name="harness-catalog", instructions="Skill catalog: list, search, load skills and their files.", auth=auth, token_verifier=verifier)
    b = ToolBindings(catalog, signer=signer, public_url=public_url)
    server.tool(name="list_skills", description="List every skill: id, description, sha (tree), replaced_by, requires_tools, compatibility.")(b.list_skills)
    server.tool(name="search_skills", description="Lexical search over id, description and metadata values. limit 1..20 (default 10).")(b.search_skills)
    server.tool(name="load_skill", description="SKILL.md body with sha, commit, metadata and file list. sha optional (default: current main).")(b.load_skill)
    server.tool(name="get_skill_file", description="One file of a skill (text or base64). Path traversal and symlinks are rejected; 1 MB per file.")(b.get_skill_file)
    if signer is not None:
        server.tool(name="get_skill_archive", description="Download descriptor for one skill version as a tar: uri + headers (5-minute token), size, sha256. Fetch it with curl; the files never pass through the model. sha optional (default: current main).")(b.get_skill_archive)
    return server
