"""시험용 가짜 OIDC issuer: discovery + JWKS만 낸다(로그인 없음). 토큰은 시험이 직접 서명한다."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NamedTuple

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

KID = "test-key-1"


class FakeIssuer(NamedTuple):
    issuer: str
    private_pem: bytes
    server: ThreadingHTTPServer

    def token(self, *, sub: str, aud: str | list[str], groups: list[str] | None = None, scope: str | None = None, exp_in: int = 3600, **extra: Any) -> str:
        claims: dict[str, Any] = {"iss": self.issuer, "sub": sub, "aud": aud, "iat": int(time.time()), "exp": int(time.time()) + exp_in, **extra}
        if groups is not None:
            claims["groups"] = groups
        if scope is not None:
            claims["scope"] = scope
        return jwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": KID})

    def stop(self) -> None:
        self.server.shutdown()


def start_fake_issuer() -> FakeIssuer:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    state: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/.well-known/openid-configuration":
                body = {"issuer": state["issuer"], "jwks_uri": state["issuer"] + "/keys", "authorization_endpoint": state["issuer"] + "/auth", "token_endpoint": state["issuer"] + "/token", "response_types_supported": ["code"], "code_challenge_methods_supported": ["S256"]}
            elif self.path == "/keys":
                body = {"keys": [jwk]}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state["issuer"] = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return FakeIssuer(state["issuer"], private_pem, server)
