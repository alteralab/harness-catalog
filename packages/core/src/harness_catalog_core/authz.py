"""인가 정책: 순수 함수. 입력은 주체·도구, 출력은 허용 여부."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from .model import SKILLS_READERS, ErrorCode, Principal, PrincipalKind

READ_TOOLS = frozenset({"list_skills", "search_skills", "load_skill", "get_skill_file"})
# 서비스 주체 표지(확인 전 규칙): sub가 이 집합에 있다. 실측 뒤 정해지는 값이라 한 자리에만 둔다.
DEFAULT_SERVICE_CLIENT_IDS: frozenset[str] = frozenset({"ci-runner"})


def is_service_subject(sub: str, service_client_ids: frozenset[str]) -> bool:
    return sub in service_client_ids


class Decision(NamedTuple):
    allowed: bool
    code: ErrorCode | None
    detail: str


def principal_from_claims(claims: Mapping[str, Any], service_client_ids: frozenset[str]) -> Principal:
    """검증된 토큰 클레임 → 주체. 서비스 주체 표지: sub가 등록된 서비스 client ID 집합에 있다."""
    sub = str(claims.get("sub", ""))
    groups_raw: object = claims.get("groups")
    groups: frozenset[str] = frozenset(str(g) for g in groups_raw) if isinstance(groups_raw, list) else frozenset()  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    scope_raw: object = claims.get("scope")
    scopes: frozenset[str] = frozenset(scope_raw.split()) if isinstance(scope_raw, str) else frozenset()
    aud = claims.get("aud")
    client_id = str(claims.get("azp") or (aud if isinstance(aud, str) else ""))
    kind = PrincipalKind.SERVICE if is_service_subject(sub, service_client_ids) else PrincipalKind.HUMAN
    return Principal(sub, kind, groups, scopes, client_id)


def authorize(principal: Principal, tool: str) -> Decision:
    """reader = 그룹 harness-readers 또는 서비스 주체. 스코프는 전송층(SDK)이 먼저 본다."""
    if tool not in READ_TOOLS:
        return Decision(False, ErrorCode.NOT_FOUND, f"unknown tool {tool}")
    if principal.kind is PrincipalKind.SERVICE or SKILLS_READERS in principal.groups:
        return Decision(True, None, "")
    return Decision(False, ErrorCode.NOT_A_MEMBER, f"not in group {SKILLS_READERS}")
