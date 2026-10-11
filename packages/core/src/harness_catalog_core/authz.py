"""인가 정책: 순수 함수. 입력은 주체·도구, 출력은 허용 여부. 주체 종류는 없다 — 사람도 기계 계정도 그룹으로 reader다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from .model import HARNESS_READERS, ErrorCode, Principal

READ_TOOLS = frozenset({"search_skills", "load_skill", "get_skill_file", "get_skill_archive", "search_tools", "get_tool"})  # CATALOG_READ 여섯(§11 2026-10-11 toolbox·list_skills 제거)


class Decision(NamedTuple):
    allowed: bool
    code: ErrorCode | None
    detail: str


def principal_from_claims(claims: Mapping[str, Any]) -> Principal:
    """검증된 토큰 클레임 → 주체. groups가 없으면 빈 집합."""
    sub = str(claims.get("sub", ""))
    groups_raw: object = claims.get("groups")
    groups: frozenset[str] = frozenset(str(g) for g in groups_raw) if isinstance(groups_raw, list) else frozenset()  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    aud = claims.get("aud")
    client_id = str(claims.get("azp") or (aud if isinstance(aud, str) else ""))
    return Principal(sub, groups, client_id)


def authorize(principal: Principal, tool: str) -> Decision:
    """reader = 그룹 harness-readers. 스코프는 보지 않는다(토큰에 없다)."""
    if tool not in READ_TOOLS:
        return Decision(False, ErrorCode.NOT_FOUND, f"unknown tool {tool}")
    if HARNESS_READERS in principal.groups:
        return Decision(True, None, "")
    return Decision(False, ErrorCode.NOT_A_MEMBER, f"not in group {HARNESS_READERS}")
