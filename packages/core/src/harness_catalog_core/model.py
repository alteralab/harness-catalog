"""순수 데이터: 스킬 항목·스냅샷·주체·상태·오류 코드. 바깥 기술을 모른다."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, cast

Root = Literal["skills", "tools", "mcp-servers"]
ROOT_MARKERS: Mapping[Root, str] = MappingProxyType({"skills": "SKILL.md", "tools": "tool.json", "mcp-servers": "server.json"})
NAME_ROOTS: tuple[Root, ...] = ("skills", "tools")  # 하나의 이름공간을 이루는 뿌리 둘(§3 식별자 — 스킬과 도구를 합쳐 전역 유일)


class ErrorCode(StrEnum):
    """도구 오류 코드 다섯. 이 목록 밖의 코드는 내지 않는다."""

    NOT_FOUND = "not_found"
    UNKNOWN_VERSION = "unknown_version"
    NOT_A_MEMBER = "not_a_member"
    INPUT_LIMIT = "input_limit"
    PATH_REJECTED = "path_rejected"


class ArchiveTooLarge(Exception):
    """tar를 만들다 바이트 상한을 넘었다 — 어댑터가 올리고 앱이 input_limit로 바꾼다."""

    def __init__(self, treeish: str, max_bytes: int) -> None:
        super().__init__(f"archive of {treeish} exceeds {max_bytes} bytes")
        self.treeish = treeish
        self.max_bytes = max_bytes


class CatalogError(Exception):
    """도구 안의 실패. MCP 어댑터가 {code, detail}로 바꾼다."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ReadyReason(StrEnum):
    """준비되지 않은 사유. /readyz 503 본문."""

    REPO_UNREACHABLE = "repo_unreachable"
    NO_MAIN_BRANCH = "no_main_branch"
    NOT_A_CATALOG = "not_a_catalog"
    UNSUPPORTED_LAYOUT = "unsupported_layout"
    LAYOUT_MISMATCH = "layout_mismatch"


class ContentError(Exception):
    """저장소를 읽지 못했다. 사유는 ReadyReason."""

    def __init__(self, reason: ReadyReason, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class ValidatorFailure(Exception):
    """검사기 자체가 실패했다(바이너리 없음·크래시). 통과로 치지 않는다 — fail-closed."""


class IndexOutcome(StrEnum):
    """사실 저장소에 인덱스를 바꿔 달라고 한 결과."""

    REPLACED = "replaced"
    STALE = "stale"  # 저장된 커밋의 자손이 아니라 아무것도 하지 않았다
    UNAVAILABLE = "unavailable"  # DB가 닿지 않는다


def _freeze(m: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(m))


HARNESS_READERS = "harness-readers"
SUPPORTED_LAYOUT = 1
BASE_SCOPES = ("openid", "groups")


def audience_scope(public_url: str) -> str:
    """Dex 교차 클라이언트 스코프: 요청하면 토큰 aud에 레지스트리 URL이 실린다."""
    return f"audience:server:client_id:{public_url.rstrip('/')}"


def required_scopes(public_url: str) -> tuple[str, ...]:
    """RFC 9728 문서에 광고하는 스코프 = 검증기가 유효한 토큰에 부여하는 스코프. 토큰에서 검사하지는 않는다."""
    return (*BASE_SCOPES, audience_scope(public_url))


@dataclass(frozen=True)
class SkillProps:
    """SKILL.md frontmatter에서 읽은 것."""

    name: str
    description: str
    compatibility: str | None
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True)
class SkillReport:
    """검증기의 판정: 스펙 위반 메시지들과(비면) 읽은 속성."""

    errors: tuple[str, ...]
    properties: SkillProps | None


@dataclass(frozen=True)
class Principal:
    subject: str
    groups: frozenset[str]
    client_id: str


@dataclass(frozen=True)
class TreeEntry:
    """git tree의 항목 하나."""

    path: str
    kind: str  # "blob" | "tree" | "link"
    sha: str
    size: int


@dataclass(frozen=True)
class SkillTree:
    """main의 <root>/<name>/ 디렉토리 하나: 판(tree)과 그 판을 넣은 커밋. 스킬·도구·MCP 서버 레코드가 같은 모양이다."""

    name: str
    tree_sha: str
    commit_sha: str


@dataclass(frozen=True)
class ToolEntry:
    """tool_index 행 하나(§11 2026-10-11 toolbox). `kind`는 runtime.kind, `server`는 kind=mcp가 참조하는 mcp-servers/<name>."""

    name: str
    description: str
    kind: str
    server: str | None
    metadata: Mapping[str, str]
    tree_sha: str
    commit_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True)
class SkillEntry:
    """인덱스 행 하나. `has_scripts`는 그 판의 트리에 `scripts/` 파일이 있는가(§11 2026-10-18: 루프 조립기가 거르는 유일한 신호)."""

    name: str
    description: str
    compatibility: str | None
    metadata: Mapping[str, str]
    tree_sha: str
    commit_sha: str
    has_scripts: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True)
class IndexSnapshot:
    """불변 스냅샷 하나. 빌드가 통째로 바꾼다."""

    entries: tuple[SkillEntry, ...]
    commit_sha: str
    built_at: datetime
    fetched_at: datetime
    rejected: tuple[tuple[str, str], ...] = ()  # (name, reason)
    tools: tuple[ToolEntry, ...] = ()  # toolbox(§11 2026-10-11). 스킬과 같은 커밋에서 파생한 한 스냅샷
    embeddings: Mapping[str, tuple[float, ...]] = field(default_factory=lambda: MappingProxyType({}))  # name → 벡터(§11 2026-10-19 검색 0.8.0; 한 스냅샷 안에서 이름은 스킬·도구 합쳐 유일 — 검사 11). 비면 dense 없음
    embedding_generation: str | None = None  # 벡터 세대 "<모델>/<문서형식 판>". 한 스냅샷에 한 세대만

    def get(self, name: str) -> SkillEntry | None:
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def get_tool(self, name: str) -> ToolEntry | None:
        for t in self.tools:
            if t.name == name:
                return t
        return None


@dataclass(frozen=True)
class SkillListing:
    """search_skills의 항목: 선택에 쓰이는 것만(식별자·설명·sha·compatibility·has_scripts)."""

    name: str
    description: str
    sha: str
    compatibility: str | None = None
    has_scripts: bool = False

    @classmethod
    def of(cls, e: SkillEntry) -> SkillListing:
        return cls(e.name, e.description, e.tree_sha, e.compatibility, e.has_scripts)


@dataclass(frozen=True)
class ListResult:
    skills: tuple[SkillListing, ...]
    fetched_at: datetime


@dataclass(frozen=True)
class ToolListing:
    """search_tools의 항목: 선택에 쓰이는 것만(식별자·설명·sha·kind·server)."""

    name: str
    description: str
    sha: str
    kind: str
    server: str | None = None

    @classmethod
    def of(cls, e: ToolEntry) -> ToolListing:
        return cls(e.name, e.description, e.tree_sha, e.kind, e.server)


@dataclass(frozen=True)
class ToolListResult:
    tools: tuple[ToolListing, ...]
    fetched_at: datetime


@dataclass(frozen=True)
class SkillFile:
    path: str
    size: int


@dataclass(frozen=True)
class SkillBody:
    name: str
    body: str
    sha: str
    commit: str
    metadata: Mapping[str, str]
    files: tuple[SkillFile, ...]
    fetched_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))

    @property
    def has_scripts(self) -> bool:
        return any(f.path.startswith("scripts/") for f in self.files)


@dataclass(frozen=True)
class ToolBody:
    """get_tool의 본문: tool.json 전체(spec)와 판·커밋·파일 목록, kind=mcp면 참조하는 server.json(server)."""

    name: str
    spec: Mapping[str, object]
    sha: str
    commit: str
    files: tuple[SkillFile, ...]
    server: Mapping[str, object] | None
    fetched_at: datetime

    @property
    def kind(self) -> str:
        runtime = self.spec.get("runtime")
        if isinstance(runtime, Mapping):
            return str(cast("Mapping[str, object]", runtime).get("kind", ""))
        return ""


@dataclass(frozen=True)
class FileContent:
    path: str
    size: int
    sha: str  # 판 = 스킬 디렉토리의 tree SHA (load_skill·search_skills의 sha와 같은 것)
    blob: str  # 이 파일의 blob SHA
    text: str | None  # UTF-8로 읽히면 본문
    base64: str | None  # 아니면 base64


@dataclass(frozen=True)
class Status:
    ready: bool
    reasons: tuple[ReadyReason, ...] = ()
    degraded: tuple[str, ...] = ()
    commit_sha: str | None = None
    fetched_at: datetime | None = None
    built_at: datetime | None = None
    rejected: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ArchiveInfo:
    """스킬·도구 한 판의 tar(DESIGN §11 2026-10-11). path는 서버 작업 디렉토리 안의 캐시 파일; size·sha256은 그 파일의 실제 바이트."""

    name: str
    sha: str  # 판 = tree SHA
    commit: str
    path: Path
    size: int
    sha256: str
    kind: str = "skills"  # 아카이브 종류(서명 범위·캐시 경로): skills | tools
