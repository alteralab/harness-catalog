"""읽기 도구 여섯의 성공 응답 모델(DESIGN §11 2026-10-11 "응답 모양은 pydantic 모델로 고정"). §4 도구 표의 산문은 이 모델의 설명이다.

MCP 어댑터가 이 모델의 인스턴스를 만들어 직렬화하고, 반환 주석 `Annotated[CallToolResult, <모델>]`로 SDK가 `tools/list`에
`outputSchema`를 싣고 성공 응답의 `structuredContent`를 검증한다. 오류 응답(`isError`)은 `ErrorResponse` 모양이고 스키마 밖이다.
모든 모델은 `extra="forbid"`라 키가 늘면 여기와 시험이 함께 바뀐다. 선언된 키는 값이 없어도 `null`로 실린다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from harness_catalog_core.toolbox import ServerSpec, ToolSpec

TREE_SHA = Field(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$", description="git tree SHA of the skill/tool directory = its version")
COMMIT_SHA = Field(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$", description="commit on main that carries this version")


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillHit(_Closed):
    """search_skills 항목: 선택에 쓰이는 것만(§4 예산)."""

    name: str
    description: str
    sha: str = TREE_SHA
    replaced_by: str | None = None
    requires_tools: list[str] = Field(default_factory=list)
    compatibility: str | None = None


class SearchSkillsResponse(_Closed):
    skills: list[SkillHit]
    fetched_at: datetime = Field(description="when the registry last fetched main")


class FileEntry(_Closed):
    path: str
    size: int = Field(ge=0)


class LoadSkillResponse(_Closed):
    id: str
    body: str = Field(description="SKILL.md body (frontmatter stripped)")
    sha: str = TREE_SHA
    commit: str = COMMIT_SHA
    metadata: dict[str, str]
    files: list[FileEntry]
    has_scripts: bool
    fetched_at: datetime


class SkillFileResponse(_Closed):
    id: str
    path: str
    size: int = Field(ge=0)
    sha: str = TREE_SHA
    blob: str = Field(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$", description="git blob SHA of this file")
    text: str | None = Field(description="UTF-8 text, or null when the file is binary")
    base64: str | None = Field(description="base64 bytes when the file is binary, else null")


class DownloadDescriptor(_Closed):
    """SEP-2631 모양의 다운로드 명세. 자격은 `headers`에만 있고 URI에는 없다(§11 2026-10-11 아카이브 행)."""

    uri: str
    method: Literal["GET"]
    headers: dict[str, str] = Field(description="send as-is; carries the 5-minute archive token")
    expires_at: datetime
    mimeType: Literal["application/x-tar"]  # noqa: N815 — SEP-2631의 필드 이름 그대로
    size: int = Field(ge=0, description="tar bytes; compare after download")
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$", description="tar digest; compare after download")
    digest: str = Field(description="`git-tree:<tree sha>` of the version inside the tar")


class SkillArchiveResponse(DownloadDescriptor):
    id: str
    sha: str = TREE_SHA
    commit: str = COMMIT_SHA


class ToolHit(_Closed):
    """search_tools 항목."""

    name: str
    description: str
    sha: str = TREE_SHA
    kind: Literal["script", "mcp"]
    server: str | None = Field(default=None, description="mcp-servers/<server> for kind=mcp, else null")
    replaced_by: str | None = None
    requires_tools: list[str] = Field(default_factory=list)


class SearchToolsResponse(_Closed):
    tools: list[ToolHit]
    fetched_at: datetime


class GetToolResponse(_Closed):
    id: str
    sha: str = TREE_SHA
    commit: str = COMMIT_SHA
    kind: Literal["script", "mcp"]
    tool: ToolSpec = Field(description="tool.json of this version, exactly as validated by check 11")
    server: ServerSpec | None = Field(default=None, description="mcp-servers/<server>/server.json (MCP Registry format) for kind=mcp, else null")
    archive: DownloadDescriptor | None = Field(default=None, description="download descriptor for the tool directory for kind=script, else null")
    files: list[FileEntry]
    fetched_at: datetime


class ErrorResponse(_Closed):
    """오류 응답(`isError: true`). `outputSchema` 밖이지만 모양은 이것 하나다(§3 오류 코드 다섯)."""

    code: str
    detail: str


def dump(model: BaseModel) -> dict[str, Any]:
    """구조화 응답으로 쓰는 직렬화. 별칭(`$schema`·`_meta`)을 지키고 datetime은 ISO 8601 문자열로."""
    return model.model_dump(mode="json", by_alias=True)
