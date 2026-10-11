"""아카이브 내려받기 토큰: HMAC-SHA256, 수명 5분, 헤더로 전달(URL에 자격을 싣지 않는다 — RFC 9110 §17.9).

도구 `get_skill_archive`·`get_tool`이 발급하고 라우트 `GET /mcp/archive/<name>/<tree>.tar`(skills)·`GET /mcp/archive/tools/<name>/<tree>.tar`(tools)가 검증한다.
검증 순서와 서명 범위는 웹훅 서명 규정을 따른다: 만료 시각이 서명 범위에 들어 있어 연장이 불가, 만료 검사가 재생을 제한, 비교는 상수 시간.
형식 위반·만료·불일치는 모두 같은 '거부'다(이유를 새기지 않는다). 종류(`kind`)도 서명 범위에 있어 스킬 토큰으로 도구를 받을 수 없다(토큰 v2, Codex 설계 리뷰 2026-10-11).
키는 프로세스 수명이다(기동 때 무작위) — 복제본 하나 전제, 재기동이 곧 회전(DESIGN §11 2026-10-11).
"""

from __future__ import annotations

import base64
import hmac
import re
import time
from collections.abc import Callable
from typing import Literal

TOKEN_HEADER = "X-Harness-Archive-Token"
TOKEN_VERSION = "v2"
DEFAULT_TTL_SECONDS = 300
LEEWAY_SECONDS = 60
ArchiveKind = Literal["skills", "tools"]
KINDS: tuple[ArchiveKind, ...] = ("skills", "tools")
# ast-grep-ignore: regex-on-structure — 어휘: 토큰은 '판.십진수.base64url 43자'의 고정 형식(정규 언어)
_TOKEN_RE = re.compile(r"^v2\.(\d{1,12})\.([A-Za-z0-9_-]{43})$")
# ast-grep-ignore: regex-on-structure — 어휘: agentskills.io name 문법(문자집합·길이)
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# ast-grep-ignore: regex-on-structure — 어휘: git 객체 id는 40 또는 64자 hex의 고정 형식
_SHA_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")


class ArchiveSigner:
    def __init__(self, key: bytes, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, clock: Callable[[], int] | None = None) -> None:
        if len(key) < 32:
            raise ValueError("signing key must be at least 32 bytes")
        self._key = key
        self.ttl = ttl_seconds
        self._clock = clock or (lambda: int(time.time()))

    @staticmethod
    def _payload(kind: str, name: str, tree: str, exp: int) -> bytes:
        return f"{TOKEN_VERSION}:{kind}:{name}:{tree}:{exp}".encode("ascii")

    def _sig(self, kind: str, name: str, tree: str, exp: int) -> str:
        mac = hmac.new(self._key, self._payload(kind, name, tree, exp), "sha256").digest()
        return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")

    @staticmethod
    def _canonical(kind: str, name: str, tree: str) -> bool:
        return kind in KINDS and bool(_NAME_RE.match(name)) and bool(_SHA_RE.match(tree))

    def mint(self, name: str, tree: str, *, kind: ArchiveKind = "skills") -> tuple[str, int]:
        """(토큰, 만료 unix 초). name·tree는 호출자(앱의 _resolve)가 이미 검증한 값이다."""
        if not self._canonical(kind, name, tree):
            raise ValueError("kind, name or tree is not in canonical form")
        exp = self._clock() + self.ttl
        return f"{TOKEN_VERSION}.{exp}.{self._sig(kind, name, tree, exp)}", exp

    def verify(self, name: str, tree: str, token: str | None, *, kind: ArchiveKind = "skills") -> bool:
        """형식 → 만료 창(now < exp ≤ now + ttl + leeway) → 상수 시간 비교. 어느 단계든 실패는 False 하나."""
        if not token or not self._canonical(kind, name, tree):
            return False
        m = _TOKEN_RE.match(token)
        if m is None:
            return False
        exp = int(m.group(1))
        now = self._clock()
        if not (now < exp <= now + self.ttl + LEEWAY_SECONDS):
            return False
        return hmac.compare_digest(self._sig(kind, name, tree, exp), m.group(2))
