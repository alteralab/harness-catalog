# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""pilot Q2·Q5 측정 도구: Dex의 그랜트 셋과 토큰 클레임 실물을 받아 적는다.

레지스트리를 흉내 내지 않는다. Dex에 실제 요청을 보내고 응답·토큰 페이로드를 원문(JSON 한 줄씩)으로 낸다.
사용: uv run --script tools/pilot/dex_grants.py --issuer http://localhost:5556/dex \
         --user dev@example.com --password password --ci-secret "$DEX_CI_RUNNER_SECRET" \
         --resource http://localhost:8000/mcp
표준 출력: 관측마다 JSON 한 줄({"case": ..., ...}). 종료 코드 0 = 전부 돌았다(판정은 사람이 rN에).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
from collections.abc import Mapping
from html.parser import HTMLParser
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NamedTuple


class Tokens(NamedTuple):
    """토큰 응답에서 뒤에 쓰는 둘. 없으면 빈 문자열."""

    access_token: str
    refresh_token: str


class LoginResult(NamedTuple):
    """로그인 폼 흐름의 결과. final은 redirect_uri로 가는 Location(code= 또는 error=), 실패면 error에 본문."""

    trace: list[dict[str, Any]]
    final: str
    error: str


class TokenResponse(NamedTuple):
    """토큰 응답의 기록용 요약과 뒤에 쓰는 토큰 둘."""

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
        self.prefix = u.path.rstrip("/")  # "/dex"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect()
        )

    def call(
        self,
        method: str,
        url: str,
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        if self.prefix and url.startswith(self.prefix + "/"):
            # Dex의 Location은 issuer 경로를 포함한 절대 경로("/dex/auth/...")다
            url = self.origin + url
        elif url.startswith("/"):
            url = self.issuer + url
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def login_via_form(self, start_url: str, user: str, password: str) -> LoginResult:
        """/auth 시작 → (리다이렉트들) → 로컬 로그인 폼 POST → approval → redirect_uri의 Location을 돌려준다."""
        trace: list[dict[str, Any]] = []
        url = start_url
        status, hdr, body = self.call("GET", url)
        trace.append({"step": "auth", "status": status, "location": hdr.get("Location")})
        hops = 0
        while status in (302, 303) and hops < 5:
            url = hdr["Location"]
            if "code=" in url or "error=" in url:
                return LoginResult(trace, url, "")
            status, hdr, body = self.call("GET", url)
            trace.append({"step": "follow", "status": status, "location": hdr.get("Location")})
            hops += 1
        if status != 200:
            return LoginResult(trace, "", body.decode(errors="replace")[:300])
        parser = _FormAction()
        parser.feed(body.decode(errors="replace"))
        if not parser.action:
            return LoginResult(trace, "", "login form not found")
        action = parser.action
        status, hdr, body = self.call("POST", action, {"login": user, "password": password})
        trace.append({"step": "login", "status": status, "location": hdr.get("Location")})
        hops = 0
        while status in (302, 303) and hops < 5:
            nxt = hdr["Location"]
            if "code=" in nxt or "error=" in nxt:
                return LoginResult(trace, nxt, "")
            status, hdr, body = self.call("GET", nxt)
            trace.append({"step": "follow", "status": status, "location": hdr.get("Location")})
            hops += 1
        return LoginResult(trace, "", body.decode(errors="replace")[:300])


def jwt_payload(token: str) -> Mapping[str, Any] | None:
    """서명 검증 없이 페이로드만 읽는다(관측용). JWT가 아니면 None."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except (IndexError, ValueError):
        return None


def emit(case: str, **kw: Any) -> None:
    print(json.dumps({"case": case, **kw}, ensure_ascii=False))


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def token_summary(body: bytes) -> TokenResponse:
    try:
        tok = json.loads(body)
    except ValueError:
        return TokenResponse({"raw": body.decode(errors="replace")[:300]}, Tokens("", ""))
    out: dict[str, Any] = {k: v for k, v in tok.items() if k not in ("access_token", "id_token", "refresh_token")}
    out["has_refresh_token"] = "refresh_token" in tok
    for k in ("access_token", "id_token"):
        if k in tok:
            out[k + "_payload"] = jwt_payload(tok[k])
            out[k + "_is_jwt"] = out[k + "_payload"] is not None
    return TokenResponse(out, Tokens(tok.get("access_token", ""), tok.get("refresh_token", "")))


def auth_code(  # noqa: PLR0913
    dex: Dex,
    a: argparse.Namespace,
    *,
    client: str,
    scope: str,
    use_pkce: bool,
    extra: dict[str, str],
    user: str,
    label: str,
) -> Tokens:
    redirect_uri = "http://127.0.0.1:43110/callback"
    state = secrets.token_hex(8)
    verifier, challenge = pkce()
    q = {"client_id": client, "redirect_uri": redirect_uri, "response_type": "code", "scope": scope, "state": state}
    if use_pkce:
        q.update({"code_challenge": challenge, "code_challenge_method": "S256"})
    q.update(extra)
    res = dex.login_via_form("/auth?" + urllib.parse.urlencode(q), user, a.password)
    code = urllib.parse.parse_qs(urllib.parse.urlparse(res.final).query).get("code", [None])[0]
    emit(label, request=q, login_trace=res.trace, final=res.final, error=res.error or None)
    if not code:
        return Tokens("", "")
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client}
    if use_pkce:
        form["code_verifier"] = verifier
    form.update({k: v for k, v in extra.items() if k == "resource"})
    status, _, body = dex.call("POST", "/token", form)
    tr = token_summary(body)
    emit(label + ".token", status=status, response=tr.summary)
    return tr.tokens


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--issuer", required=True)
    p.add_argument("--user", default="dev@example.com")
    p.add_argument("--outsider", default="outsider@example.com")
    p.add_argument("--password", default="password")
    p.add_argument("--ci-secret", required=True)
    p.add_argument("--resource", required=True, help="레지스트리 공개 URL (audience 클라이언트 id)")
    a = p.parse_args()
    dex = Dex(a.issuer)

    status, _, body = dex.call("GET", "/.well-known/openid-configuration")
    disc = json.loads(body)
    emit("discovery", status=status, grant_types_supported=disc.get("grant_types_supported"),
         scopes_supported=disc.get("scopes_supported"), code_challenge_methods_supported=disc.get("code_challenge_methods_supported"))

    base_scope = "openid profile email groups offline_access"
    # (a) 인가 코드 + PKCE, 공개 클라이언트, resource 파라미터 동봉
    toks = auth_code(dex, a, client="claude-code", scope=base_scope, use_pkce=True,
                     extra={"resource": a.resource}, user=a.user, label="a.pkce_public_with_resource")
    # (a2) PKCE 없이 — 서버가 강제하는가
    dex2 = Dex(a.issuer)
    auth_code(dex2, a, client="claude-code", scope=base_scope, use_pkce=False, extra={}, user=a.user, label="a2.no_pkce_public")
    # (a3) 설계의 스코프 skills:read를 요청하면
    dex3 = Dex(a.issuer)
    auth_code(dex3, a, client="claude-code", scope=base_scope + " skills:read", use_pkce=True, extra={}, user=a.user, label="a3.custom_scope_skills_read")
    # (e) 교차 클라이언트 audience 스코프
    dex4 = Dex(a.issuer)
    auth_code(dex4, a, client="claude-code", scope=base_scope + " audience:server:client_id:" + a.resource,
              use_pkce=True, extra={}, user=a.user, label="e.cross_client_audience")
    # (c') 그룹 없는 사용자
    dex5 = Dex(a.issuer)
    auth_code(dex5, a, client="claude-code", scope=base_scope, use_pkce=True, extra={}, user=a.outsider, label="c.outsider_no_groups")

    # (r) 리프레시
    if toks.refresh_token:
        status, _, body = dex.call("POST", "/token", {"grant_type": "refresh_token", "refresh_token": toks.refresh_token, "client_id": "claude-code"})
        emit("r.refresh_public", status=status, response=token_summary(body).summary,
             note="같은 사용자·클라이언트로 뒤에 다시 로그인한 경우(a2·a3·e)가 있으면 이 토큰은 이미 무효다(r1)")

    # (b) 클라이언트 자격 증명 — ci-runner
    basic = base64.b64encode(f"ci-runner:{a.ci_secret}".encode()).decode()
    status, _, body = dex.call("POST", "/token", {"grant_type": "client_credentials", "scope": "openid groups"}, {"Authorization": "Basic " + basic})
    emit("b.client_credentials", status=status, body=body.decode(errors="replace")[:400])

    # (d) 장치 흐름 — 공개 클라이언트, client_secret 없이
    dex6 = Dex(a.issuer)
    verifier, challenge = pkce()
    status, _, body = dex6.call("POST", "/device/code", {"client_id": "claude-code", "scope": base_scope, "code_challenge": challenge, "code_challenge_method": "S256"})
    dev = json.loads(body) if status == 200 else {"raw": body.decode(errors="replace")[:300]}
    emit("d.device_code_public", status=status, response={k: v for k, v in dev.items() if k != "device_code"})
    if status == 200:
        # 승인 전 폴링
        status, _, body = dex6.call("POST", "/device/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": dev["device_code"], "code_verifier": verifier})
        emit("d.poll_before_approval", status=status, body=body.decode(errors="replace")[:200])
        # 사람 역할: user_code 입력 → 로그인
        status, hdr, body = dex6.call("POST", "/device/auth/verify_code", {"user_code": dev["user_code"]})
        emit("d.verify_code", status=status, location=hdr.get("Location"))
        if status in (302, 303):
            res = dex6.login_via_form(hdr["Location"], a.user, a.password)
            emit("d.login", trace=res.trace, final=res.final, error=res.error or None)
            if res.final:
                status, hdr, body = dex6.call("GET", res.final)
                emit("d.device_callback", status=status, body_excerpt=body.decode(errors="replace")[:120].replace("\n", " "))
        time.sleep(1)
        status, _, body = dex6.call("POST", "/device/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": dev["device_code"], "code_verifier": verifier})
        emit("d.device_token_public", status=status, response=token_summary(body).summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
