# /// script
# requires-python = ">=3.12"
# dependencies = ["PyJWT[crypto]>=2.9"]
# ///
"""Dex의 그랜트 셋과 토큰 클레임 실물을 받아 적는 측정 도구.

레지스트리를 흉내 내지 않는다. Dex에 실제 요청을 보내고 응답·토큰 페이로드를 JSON 한 줄씩 낸다.
서명은 issuer의 JWKS로 검증한다(PyJWT). 측정마다 기대(성공해야 하는 것)가 어긋나면 종료 코드 1.
사용: uv run --script tools/pilot/dex_grants.py --issuer http://localhost:5556/dex \
         --user dev@example.com --password password --outsider outsider@example.com \
         --client claude-code --ci-secret "$DEX_CI_RUNNER_SECRET" --resource http://localhost:8000/mcp
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any, NamedTuple

import jwt
from jwt import PyJWKClient

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class Tokens(NamedTuple):
    access_token: str
    refresh_token: str


class LoginResult(NamedTuple):
    """로그인 폼 흐름의 결과. final은 redirect_uri로 가는 Location(code= 또는 error=), 실패면 error."""

    trace: list[dict[str, Any]]
    final: str
    error: str


class Reply(NamedTuple):
    """HTTP 응답 또는 전송 실패."""

    status: int  # 전송 실패면 0
    headers: dict[str, str]
    body: bytes
    error: str


class TokenResponse(NamedTuple):
    summary: dict[str, Any]
    tokens: Tokens


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다 — Location을 그대로 관측한다."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FormAction(HTMLParser):
    """첫 <form>의 action을 읽는다(Dex 로그인 페이지)."""

    def __init__(self) -> None:
        super().__init__()
        self.action = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "form" and not self.action:
            self.action = dict(attrs).get("action") or ""


class Dex:
    """쿠키를 유지하고 리다이렉트를 따라가지 않는 작은 클라이언트."""

    def __init__(self, issuer: str) -> None:
        self.issuer = issuer.rstrip("/")
        u = urllib.parse.urlparse(self.issuer)
        self.origin = f"{u.scheme}://{u.netloc}"
        self.prefix = u.path.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), _NoRedirect()
        )

    def call(self, method: str, url: str, form: Mapping[str, str] | None = None, headers: Mapping[str, str] | None = None) -> Reply:
        if self.prefix and url.startswith(self.prefix + "/"):
            url = self.origin + url  # Dex의 Location은 issuer 경로를 포함한 절대 경로
        elif url.startswith("/"):
            url = self.issuer + url
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(req, timeout=15) as resp:
                return Reply(resp.status, dict(resp.headers), resp.read(), "")
        except urllib.error.HTTPError as e:
            return Reply(e.code, dict(e.headers), e.read(), "")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return Reply(0, {}, b"", f"transport: {e}")

    def login_via_form(self, start_url: str, user: str, password: str) -> LoginResult:
        trace: list[dict[str, Any]] = []
        r = self.call("GET", start_url)
        trace.append({"step": "auth", "status": r.status, "location": r.headers.get("Location"), "error": r.error})
        hops = 0
        while r.status in (302, 303) and hops < 5:
            url = r.headers["Location"]
            if "code=" in url or "error=" in url:
                return LoginResult(trace, url, "")
            r = self.call("GET", url)
            trace.append({"step": "follow", "status": r.status, "location": r.headers.get("Location"), "error": r.error})
            hops += 1
        if r.status != 200:
            return LoginResult(trace, "", r.error or r.body.decode(errors="replace")[:300])
        parser = _FormAction()
        parser.feed(r.body.decode(errors="replace"))
        if not parser.action:
            return LoginResult(trace, "", "login form not found")
        r = self.call("POST", parser.action, {"login": user, "password": password})
        trace.append({"step": "login", "status": r.status, "location": r.headers.get("Location"), "error": r.error})
        hops = 0
        while r.status in (302, 303) and hops < 5:
            nxt = r.headers["Location"]
            if "code=" in nxt or "error=" in nxt:
                return LoginResult(trace, nxt, "")
            r = self.call("GET", nxt)
            trace.append({"step": "follow", "status": r.status, "location": r.headers.get("Location"), "error": r.error})
            hops += 1
        return LoginResult(trace, "", r.error or r.body.decode(errors="replace")[:300])


class Verifier:
    """issuer의 JWKS로 서명을 검증하고 클레임을 돌려준다(관측용: aud는 검증하지 않는다)."""

    def __init__(self, issuer: str, jwks_uri: str) -> None:
        self.issuer = issuer
        self.jwks = PyJWKClient(jwks_uri)

    def claims(self, token: str) -> Mapping[str, Any] | None:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=["RS256", "ES256"], issuer=self.issuer, options={"verify_aud": False})
        except jwt.PyJWTError as e:
            return {"_signature_error": str(e)}


def parse_json(body: bytes) -> Mapping[str, Any] | None:
    try:
        data = json.loads(body)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def emit(case: str, **kw: Any) -> None:
    print(json.dumps({"case": case, **kw}, ensure_ascii=False))


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def token_summary(body: bytes, verifier: Verifier) -> TokenResponse:
    tok = parse_json(body)
    if tok is None:
        return TokenResponse({"raw": body.decode(errors="replace")[:300]}, Tokens("", ""))
    out: dict[str, Any] = {k: v for k, v in tok.items() if k not in ("access_token", "id_token", "refresh_token")}
    out["has_refresh_token"] = "refresh_token" in tok
    for k in ("access_token", "id_token"):
        if k in tok:
            out[k + "_claims"] = verifier.claims(str(tok[k]))
    return TokenResponse(out, Tokens(str(tok.get("access_token", "")), str(tok.get("refresh_token", ""))))


class Run:
    """측정 한 번의 상태: 설정과 실패 수."""

    def __init__(self, a: argparse.Namespace, verifier: Verifier) -> None:
        self.a = a
        self.verifier = verifier
        self.failures: list[str] = []
        self.redirect_uri = f"http://127.0.0.1:{a.callback_port}/callback"

    def expect(self, case: str, ok: bool, detail: str) -> None:
        if not ok:
            self.failures.append(f"{case}: {detail}")

    def auth_code(self, *, scope: str, use_pkce: bool, extra: Mapping[str, str], user: str, label: str, expect_ok: bool = True) -> Tokens:
        dex = Dex(self.a.issuer)
        state = secrets.token_hex(8)
        verifier, challenge = pkce()
        q: dict[str, str] = {"client_id": self.a.client, "redirect_uri": self.redirect_uri, "response_type": "code", "scope": scope, "state": state}
        if use_pkce:
            q.update({"code_challenge": challenge, "code_challenge_method": "S256"})
        q.update(extra)
        res = dex.login_via_form("/auth?" + urllib.parse.urlencode(q), user, self.a.password)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(res.final).query)
        code = qs.get("code", [""])[0]
        state_ok = qs.get("state", [""])[0] == state
        emit(label, request=q, login_trace=res.trace, final=res.final, state_verified=state_ok, error=res.error or None)
        if not code or not state_ok:
            self.expect(label, not expect_ok, f"no code (state_ok={state_ok}) final={res.final[:120]}")
            return Tokens("", "")
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri, "client_id": self.a.client}
        if use_pkce:
            form["code_verifier"] = verifier
        if "resource" in extra:
            form["resource"] = extra["resource"]
        r = dex.call("POST", "/token", form)
        tr = token_summary(r.body, self.verifier)
        emit(label + ".token", status=r.status, response=tr.summary, error=r.error or None)
        self.expect(label + ".token", (r.status == 200) == expect_ok, f"status {r.status}")
        return tr.tokens

    def refresh(self, label: str, token: str, *, expect_ok: bool) -> Tokens:
        r = Dex(self.a.issuer).call("POST", "/token", {"grant_type": "refresh_token", "refresh_token": token, "client_id": self.a.client})
        tr = token_summary(r.body, self.verifier)
        emit(label, status=r.status, response=tr.summary, error=r.error or None)
        self.expect(label, (r.status == 200) == expect_ok, f"status {r.status}")
        return tr.tokens

    def device_flow(self, label: str) -> None:
        dex = Dex(self.a.issuer)
        verifier, challenge = pkce()
        r = dex.call("POST", "/device/code", {"client_id": self.a.client, "scope": self.a.scope, "code_challenge": challenge, "code_challenge_method": "S256"})
        dev = parse_json(r.body) if r.status == 200 else None
        emit(label + ".device_code", status=r.status, response={k: v for k, v in (dev or {}).items() if k != "device_code"}, error=r.error or (None if dev else r.body.decode(errors="replace")[:200]))
        if dev is None:
            self.expect(label, False, f"device_code status {r.status}")
            return
        interval = int(dev.get("interval", 5))
        poll = {"grant_type": DEVICE_GRANT, "device_code": str(dev["device_code"]), "client_id": self.a.client, "code_verifier": verifier}
        r = dex.call("POST", "/token", poll)  # 승인 전: authorization_pending이어야 한다
        emit(label + ".poll_before_approval", status=r.status, body=r.body.decode(errors="replace")[:200])
        self.expect(label + ".poll_before_approval", r.status == 400 and b"authorization_pending" in r.body, f"status {r.status}")
        r = dex.call("POST", "/device/auth/verify_code", {"user_code": str(dev["user_code"])})
        emit(label + ".verify_code", status=r.status, location=r.headers.get("Location"))
        if r.status not in (302, 303):
            self.expect(label, False, f"verify_code status {r.status}")
            return
        res = dex.login_via_form(r.headers["Location"], self.a.user, self.a.password)
        emit(label + ".login", trace=res.trace, final=res.final, error=res.error or None)
        if res.final:
            r = dex.call("GET", res.final)
            emit(label + ".device_callback", status=r.status)
        time.sleep(interval + 1)  # 서버가 준 interval을 지킨다(slow_down 회피)
        r = dex.call("POST", "/token", poll)
        tr = token_summary(r.body, self.verifier)
        emit(label + ".device_token", status=r.status, response=tr.summary, error=r.error or None)
        self.expect(label + ".device_token", r.status == 200, f"status {r.status}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--issuer", required=True)
    p.add_argument("--client", default="claude-code", help="공개 클라이언트 id")
    p.add_argument("--user", default="dev@example.com")
    p.add_argument("--outsider", default="outsider@example.com", help="그룹 없는 사용자")
    p.add_argument("--password", default="password")
    p.add_argument("--ci-secret", required=True)
    p.add_argument("--resource", required=True, help="레지스트리 공개 URL (audience 클라이언트 id)")
    p.add_argument("--callback-port", type=int, default=43110)
    p.add_argument("--scope", default="openid profile email groups offline_access")
    a = p.parse_args()

    r = Dex(a.issuer).call("GET", "/.well-known/openid-configuration")
    disc = parse_json(r.body) if r.status == 200 else None
    if disc is None:
        emit("discovery", status=r.status, error=r.error or r.body.decode(errors="replace")[:200])
        print("FAIL: discovery", file=sys.stderr)
        return 1
    emit("discovery", status=r.status, grant_types_supported=disc.get("grant_types_supported"), scopes_supported=disc.get("scopes_supported"),
         code_challenge_methods_supported=disc.get("code_challenge_methods_supported"), jwks_uri=disc.get("jwks_uri"))
    run = Run(a, Verifier(a.issuer, str(disc["jwks_uri"])))

    # (a) 인가 코드 + PKCE, resource 동봉 → 바로 리프레시(독립 baseline)
    toks = run.auth_code(scope=a.scope, use_pkce=True, extra={"resource": a.resource}, user=a.user, label="a.pkce_public_with_resource")
    if toks.refresh_token:
        run.refresh("a.refresh_immediately", toks.refresh_token, expect_ok=True)
    # (a2) PKCE 없이 — 서버가 강제하는가(관측: 기대 없음)
    run.auth_code(scope=a.scope, use_pkce=False, extra={}, user=a.user, label="a2.no_pkce_public", expect_ok=True)
    # (a3) 설계 스코프 skills:read → invalid_scope 기대
    run.auth_code(scope=a.scope + " skills:read", use_pkce=True, extra={}, user=a.user, label="a3.custom_scope_skills_read", expect_ok=False)
    # (e) 교차 클라이언트 audience 스코프
    run.auth_code(scope=a.scope + " audience:server:client_id:" + a.resource, use_pkce=True, extra={}, user=a.user, label="e.cross_client_audience")
    # (c) 그룹 없는 사용자
    run.auth_code(scope=a.scope, use_pkce=True, extra={}, user=a.outsider, label="c.outsider_no_groups")
    # (r) 리프레시 토큰의 수: 로그인 A → 로그인 B(같은 사용자·클라이언트) → A 리프레시
    ta = run.auth_code(scope=a.scope, use_pkce=True, extra={}, user=a.user, label="r.login_a")
    tb = run.auth_code(scope=a.scope, use_pkce=True, extra={}, user=a.user, label="r.login_b_same_client")
    if ta.refresh_token and tb.refresh_token:
        run.refresh("r.refresh_a_after_b", ta.refresh_token, expect_ok=False)
        run.refresh("r.refresh_b", tb.refresh_token, expect_ok=True)
    # (b) 클라이언트 자격 증명 — ci-runner (미지원 기대)
    basic = base64.b64encode(f"ci-runner:{a.ci_secret}".encode()).decode()
    r = Dex(a.issuer).call("POST", "/token", {"grant_type": "client_credentials", "scope": "openid groups"}, {"Authorization": "Basic " + basic})
    emit("b.client_credentials", status=r.status, body=r.body.decode(errors="replace")[:300], error=r.error or None)
    run.expect("b.client_credentials", r.status == 400 and b"unsupported_grant_type" in r.body, f"status {r.status}")
    # (d) 장치 흐름 — 공개 클라이언트, client_secret 없이, /token 종단점
    run.device_flow("d.device_public")

    emit("summary", failures=run.failures)
    if run.failures:
        print("FAIL: " + "; ".join(run.failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
