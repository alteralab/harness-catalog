# /// script
# requires-python = ">=3.12"
# dependencies = ["PyJWT[crypto]==2.15.1"]
# ///
"""pilot Q3 측정 도구: 하네스가 첫 접촉에 보내는 요청을 원문으로 받아 적는 인가 서버 stub.

레지스트리를 흉내 내지 않는다 — 레지스트리는 실물을 띄우고, 이 stub은 그 레지스트리의 issuer 자리에 서서
discovery·JWKS를 내고 /authorize·/token·/register에 오는 요청(쿼리·헤더·본문)을 JSON 한 줄씩 기록한다.
토큰은 발급하지 않는다(authorize는 error=access_denied로 되돌려 보낸다).
사용: uv run --script tools/pilot/capture_stub.py --port 5560 --log <파일>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


class CaptureHandler(BaseHTTPRequestHandler):
    """설정(issuer·jwk·log·플래그)은 make_handler가 서브클래스 속성으로 채운다."""

    issuer = ""
    jwk: dict[str, Any] = {}
    log_path = ""
    offer_dcr = True
    oidc_only = False

    def _record(self, body: bytes) -> None:
        u = urlsplit(self.path)
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "method": self.command, "path": u.path,
            "query": {k: v if len(v) > 1 else v[0] for k, v in parse_qs(u.query).items()},
            "headers": {k: v for k, v in self.headers.items() if k.lower() in ("user-agent", "content-type", "accept", "authorization", "mcp-protocol-version")},
            "body": body.decode(errors="replace")[:2000],
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps({k: rec[k] for k in ("method", "path", "query")}, ensure_ascii=False), flush=True)

    def _json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _metadata(self) -> None:
        issuer = self.issuer
        meta: dict[str, Any] = {
            "issuer": issuer, "jwks_uri": issuer + "/keys", "authorization_endpoint": issuer + "/auth", "token_endpoint": issuer + "/token",
            "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"], "scopes_supported": ["openid", "groups"], "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        }
        if self.offer_dcr:
            meta["registration_endpoint"] = issuer + "/register"
        self._json(200, meta)

    def _deny_authorize(self) -> None:
        # 인가 요청을 기록했으니 거절해 되돌린다(토큰은 안 낸다)
        q = parse_qs(urlsplit(self.path).query)
        redirect = q.get("redirect_uri", [""])[0]
        state = q.get("state", [""])[0]
        self.send_response(302)
        self.send_header("Location", f"{redirect}?error=access_denied&error_description=capture_stub&state={state}")
        self.end_headers()

    def do_GET(self) -> None:
        self._record(b"")
        path = urlsplit(self.path).path
        if path == "/.well-known/openid-configuration" or (path == "/.well-known/oauth-authorization-server" and not self.oidc_only):
            self._metadata()
        elif path == "/keys":
            self._json(200, {"keys": [self.jwk]})
        elif path == "/auth":
            self._deny_authorize()
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self._record(body)
        if urlsplit(self.path).path == "/register":
            # 동적 등록을 시도하면 그 사실만 적고 거절한다(설계는 사전 등록)
            self._json(400, {"error": "invalid_client_metadata", "error_description": "capture_stub: dynamic registration not offered"})
        else:
            self._json(400, {"error": "invalid_grant", "error_description": "capture_stub issues no tokens"})

    def log_message(self, format: str, *args: Any) -> None:  # 기반 클래스의 시그니처
        _ = (format, args)  # 표준 오류 로그를 끈다(기록은 _record가 한다)


def make_handler(issuer: str, jwk: dict[str, Any], log_path: str, *, offer_dcr: bool, oidc_only: bool) -> type[BaseHTTPRequestHandler]:
    return type("ConfiguredCaptureHandler", (CaptureHandler,), {"issuer": issuer, "jwk": jwk, "log_path": log_path, "offer_dcr": offer_dcr, "oidc_only": oidc_only})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5560)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--log", required=True)
    p.add_argument("--no-dcr", action="store_true", help="registration_endpoint를 내지 않는다(사전 등록만)")
    p.add_argument("--oidc-only", action="store_true", help="/.well-known/openid-configuration만 낸다(Dex처럼). oauth-authorization-server는 404")
    a = p.parse_args()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "stub-1", "use": "sig", "alg": "RS256"})
    issuer = f"http://{a.host}:{a.port}"
    server = ThreadingHTTPServer((a.host, a.port), make_handler(issuer, jwk, a.log, offer_dcr=not a.no_dcr, oidc_only=a.oidc_only))
    print(f"capture stub issuer={issuer} log={a.log}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
