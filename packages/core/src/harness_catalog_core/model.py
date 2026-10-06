"""순수 데이터: 스킬 항목·스냅샷·주체·상태·오류 코드. 바깥 기술을 모른다."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    """도구 오류 코드 다섯. 이 목록 밖의 코드는 내지 않는다."""

    NOT_FOUND = "not_found"
    UNKNOWN_VERSION = "unknown_version"
    NOT_A_MEMBER = "not_a_member"
    INPUT_LIMIT = "input_limit"
    PATH_REJECTED = "path_rejected"


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


class PrincipalKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


def _freeze(m: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(m))


SKILLS_READERS = "harness-readers"
REQUIRED_SCOPE = "skills:read"
SUPPORTED_LAYOUT = 1


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
    kind: PrincipalKind
    groups: frozenset[str]
    scopes: frozenset[str]
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
    """main의 skills/<name>/ 디렉토리 하나: 판(tree)과 그 판을 넣은 커밋."""

    name: str
    tree_sha: str
    commit_sha: str


@dataclass(frozen=True)
class SkillEntry:
    """인덱스 행 하나. 생성 열(replaced_by·requires_tools)은 속성으로 유도한다."""

    name: str
    description: str
    compatibility: str | None
    metadata: Mapping[str, str]
    tree_sha: str
    commit_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))

    @property
    def replaced_by(self) -> str | None:
        return self.metadata.get("replaced-by") or None

    @property
    def requires_tools(self) -> tuple[str, ...]:
        return tuple(self.metadata.get("requires-tools", "").split())

    @property
    def search_text(self) -> str:
        values = " ".join(v for _, v in sorted(self.metadata.items()))
        return f"{self.name} {self.description} {values}".lower()


@dataclass(frozen=True)
class IndexSnapshot:
    """불변 스냅샷 하나. 빌드가 통째로 바꾼다."""

    entries: tuple[SkillEntry, ...]
    commit_sha: str
    built_at: datetime
    fetched_at: datetime
    rejected: tuple[tuple[str, str], ...] = ()  # (name, reason)

    def get(self, name: str) -> SkillEntry | None:
        for e in self.entries:
            if e.name == name:
                return e
        return None


@dataclass(frozen=True)
class SkillListing:
    """list_skills·search_skills의 항목: 선택에 쓰이는 것만."""

    name: str
    description: str
    sha: str
    replaced_by: str | None = None
    requires_tools: tuple[str, ...] = ()
    compatibility: str | None = None

    @classmethod
    def of(cls, e: SkillEntry) -> SkillListing:
        return cls(e.name, e.description, e.tree_sha, e.replaced_by, e.requires_tools, e.compatibility)


@dataclass(frozen=True)
class ListResult:
    skills: tuple[SkillListing, ...]
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
class FileContent:
    path: str
    size: int
    sha: str  # 판 = 스킬 디렉토리의 tree SHA (load_skill·list_skills의 sha와 같은 것)
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
