"""OIDC 어댑터: issuer의 JWKS로 서명을 검증하고 iss·aud·exp·nbf·sub를 확인해 주체 재료(AccessToken)를 만든다."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Any

import anyio
import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken

from harness_catalog_core.model import required_scopes

ALGORITHMS = ("RS256", "ES256")
LEEWAY_SECONDS = 60


def discover_jwks_uri(issuer: str, timeout: float = 10.0) -> str:
    """issuer의 .well-known/openid-configuration에서 jwks_uri를 읽는다."""
    with urllib.request.urlopen(f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=timeout) as resp:
        doc = json.load(resp)
    uri = doc.get("jwks_uri")
    if not isinstance(uri, str):
        raise ValueError("jwks_uri missing in discovery document")
    return uri


class JwtTokenVerifier:
    """SDK TokenVerifier 구현. 바깥 통신은 JWKS 가져오기뿐(캐시 1시간, 모르는 kid는 즉시 재조회)."""

    def __init__(self, issuer: str, audience: str, jwks_uri: str) -> None:
        self._issuer = issuer
        self._audience = audience
        self._scopes = list(required_scopes(audience))
        self._jwks = PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)

    def decode(self, token: str) -> Mapping[str, Any] | None:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(
                token, key, algorithms=list(ALGORITHMS), audience=self._audience, issuer=self._issuer,
                leeway=LEEWAY_SECONDS, options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError:
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        claims = await anyio.to_thread.run_sync(self.decode, token)  # JWKS 조회가 루프를 막지 않게
        if claims is None:
            return None
        aud = claims.get("aud")
        client_id = str(claims.get("azp") or (aud if isinstance(aud, str) else ""))
        # 스코프는 토큰에서 보지 않는다(Dex 토큰에 scope 클레임이 없다): 유효한 토큰에 요구 스코프를 그대로 부여한다
        return AccessToken(
            token=token, client_id=client_id, scopes=list(self._scopes), expires_at=int(claims["exp"]),
            resource=self._audience, subject=str(claims["sub"]), claims=dict(claims),
        )
