"""HTTP 경유 시험: 실제 uvicorn 프로세스 + 가짜 issuer(JWKS). 도구 넷 호출과 401/403 경계."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.conftest import CatalogRepo
from tests.http.fake_issuer import FakeIssuer, start_fake_issuer

PUBLIC_PATH = "/mcp"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def issuer() -> Iterator[FakeIssuer]:
    fi = start_fake_issuer()
    yield fi
    fi.stop()


@pytest.fixture
def server(tmp_path: Path, catalog_repo: CatalogRepo, issuer: FakeIssuer) -> Iterator[tuple[str, FakeIssuer]]:
    port = _free_port()
    public_url = f"http://127.0.0.1:{port}{PUBLIC_PATH}"
    env = {
        **os.environ,
        "HC__CATALOG_REPO_URL": str(catalog_repo.path),
        "HC__GIT_DEPLOY_KEY": "",
        "HC__OIDC_ISSUER": issuer.issuer,
        "HC__PUBLIC_URL": public_url,
        "HC__DATABASE_URL": "postgresql://unused",
        "HC__FETCH_INTERVAL_SECONDS": "3600",
    }
    proc = subprocess.Popen([sys.executable, "-m", "harness_catalog_server", "serve", "--host", "127.0.0.1", "--port", str(port), "--workdir", str(tmp_path / "work"), "--log-level", "warning"], env=env)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(base + "/readyz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    else:
        proc.kill()
        pytest.fail("server did not become ready")
    yield base, issuer
    proc.terminate()
    proc.wait(10)


def call_tool(base: str, token: str | None, name: str, arguments: dict[str, Any]) -> httpx.Response:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return httpx.post(base + PUBLIC_PATH, headers=headers, json=body, timeout=10)


def result_of(resp: httpx.Response) -> Mapping[str, Any]:
    data = resp.json()
    assert "result" in data, data
    return data["result"]


def test_health_and_ready(server: tuple[str, FakeIssuer]) -> None:
    base, _ = server
    assert httpx.get(base + "/healthz").json() == {"status": "ok"}
    ready = httpx.get(base + "/readyz").json()
    assert ready["ready"] is True and ready["rejected"] == [] and ready["reasons"] == []


def test_protected_resource_metadata_and_401(server: tuple[str, FakeIssuer]) -> None:
    base, _ = server
    r = call_tool(base, None, "list_skills", {})
    assert r.status_code == 401
    www = r.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www
    meta = httpx.get(base + "/.well-known/oauth-protected-resource" + PUBLIC_PATH)
    if meta.status_code == 404:
        meta = httpx.get(base + "/.well-known/oauth-protected-resource")
    doc = meta.json()
    assert doc["resource"].rstrip("/") == base + PUBLIC_PATH
    assert "skills:read" in doc.get("scopes_supported", [])


def test_reader_calls_all_four_tools(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["skills-readers"], scope="skills:read")
    listing = result_of(call_tool(base, token, "list_skills", {}))
    names = [s["name"] for s in listing["structuredContent"]["skills"]]
    assert names == ["pin-skill", "yt-subs"]
    hit = result_of(call_tool(base, token, "search_skills", {"query": "유튜브 자막"}))
    assert [s["name"] for s in hit["structuredContent"]["skills"]] == ["yt-subs"]
    body = result_of(call_tool(base, token, "load_skill", {"id": "yt-subs"}))["structuredContent"]
    assert body["has_scripts"] and body["metadata"] == {"requires-tools": "yt-dlp uv"} and len(body["sha"]) == 40
    f = result_of(call_tool(base, token, "get_skill_file", {"id": "yt-subs", "path": "scripts/fetch.py"}))["structuredContent"]
    assert f["text"] == "print('hi')\n" and f["sha"] == body["sha"] and len(f["blob"]) == 40 and f["blob"] != body["sha"]
    err = result_of(call_tool(base, token, "get_skill_file", {"id": "yt-subs", "path": "../x"}))
    assert err["isError"] is True and err["structuredContent"]["code"] == "path_rejected"


def test_wrong_audience_expired_and_not_a_member(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    wrong_aud = issuer.token(sub="u", aud="claude-code", groups=["skills-readers"], scope="skills:read")
    assert call_tool(base, wrong_aud, "list_skills", {}).status_code == 401
    expired = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["skills-readers"], scope="skills:read", exp_in=-120)
    assert call_tool(base, expired, "list_skills", {}).status_code == 401
    no_scope = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["skills-readers"])
    r = call_tool(base, no_scope, "list_skills", {})
    assert r.status_code == 403 and "insufficient_scope" in r.headers.get("www-authenticate", "")
    outsider = issuer.token(sub="u", aud=base + PUBLIC_PATH, scope="skills:read")
    res = result_of(call_tool(base, outsider, "list_skills", {}))
    assert res["isError"] is True and res["structuredContent"]["code"] == "not_a_member"


def test_service_principal_reads_without_group_or_scope(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    svc = issuer.token(sub="ci-runner", aud=base + PUBLIC_PATH)  # 그룹도 스코프도 없다
    res = result_of(call_tool(base, svc, "list_skills", {}))
    assert "structuredContent" in res and not res.get("isError")
    assert json.loads(res["content"][0]["text"])["skills"]
