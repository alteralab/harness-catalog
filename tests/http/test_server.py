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


def free_port() -> int:
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
    port = free_port()
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
    deadline = time.time() + 60  # 마이그레이션 대기(최대 10초) + 첫 빌드
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
    assert doc["scopes_supported"] == ["openid", "groups", f"audience:server:client_id:{base}{PUBLIC_PATH}"]


def test_reader_calls_all_four_tools(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])  # Dex처럼 scope 클레임 없음
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
    wrong_aud = issuer.token(sub="u", aud="claude-code", groups=["harness-readers"])  # 교차 클라이언트 스코프 없이 받은 Dex 토큰 꼴
    assert call_tool(base, wrong_aud, "list_skills", {}).status_code == 401
    multi_aud = issuer.token(sub="u", aud=[base + PUBLIC_PATH, "claude-code"], groups=["harness-readers"], azp="claude-code")  # 교차 클라이언트 스코프로 받은 꼴
    assert "structuredContent" in result_of(call_tool(base, multi_aud, "list_skills", {}))
    expired = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["harness-readers"], exp_in=-120)
    assert call_tool(base, expired, "list_skills", {}).status_code == 401
    outsider = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["users"])
    r = call_tool(base, outsider, "list_skills", {})
    assert r.status_code == 200 and "www-authenticate" not in {k.lower() for k in r.headers}
    res = result_of(r)
    assert res["isError"] is True and res["structuredContent"]["code"] == "not_a_member"


def test_machine_account_reads_by_group(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    svc = issuer.token(sub="svc-harness", aud=base + PUBLIC_PATH, groups=["harness-readers"])  # 기계 계정 = 그룹으로 reader
    res = result_of(call_tool(base, svc, "list_skills", {}))
    assert "structuredContent" in res and not res.get("isError")
    assert json.loads(res["content"][0]["text"])["skills"]


def test_archive_descriptor_then_download_without_bearer(server: tuple[str, FakeIssuer], tmp_path: Path) -> None:
    """다섯째 도구: 기술자(uri·헤더 토큰·크기·sha256) → 헤더만으로 GET → tar가 load_skill의 파일 목록과 같다. 자격은 URL에 없다."""
    import hashlib
    import io
    import tarfile

    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])
    body = result_of(call_tool(base, token, "load_skill", {"id": "yt-subs"}))["structuredContent"]
    d = result_of(call_tool(base, token, "get_skill_archive", {"id": "yt-subs", "sha": body["sha"]}))["structuredContent"]
    assert d["sha"] == body["sha"] and d["digest"] == f"git-tree:{body['sha']}" and d["mimeType"] == "application/x-tar"
    assert d["uri"] == f"{base}{PUBLIC_PATH}/archive/yt-subs/{body['sha']}.tar" and "?" not in d["uri"]  # 자격은 URL 밖
    header_name, header_value = next(iter(d["headers"].items()))
    assert header_name == "X-Harness-Archive-Token" and header_value.startswith("v2.")
    r = httpx.get(d["uri"], headers=d["headers"], timeout=10)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-tar")
    assert r.headers["cache-control"] == "private, no-store" and int(r.headers["content-length"]) == d["size"]
    assert len(r.content) == d["size"] and hashlib.sha256(r.content).hexdigest() == d["sha256"] == r.headers["x-harness-archive-sha256"]
    with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
        names = sorted(m.name for m in tar.getmembers() if m.isfile())
    assert names == sorted(f["path"] for f in body["files"])
    # 라우트는 MCP Mount보다 앞: 토큰 없음·변조·다른 판은 전부 빈 403(401 챌린지가 아니다)
    no_token = httpx.get(d["uri"], timeout=10)
    assert no_token.status_code == 403 and no_token.content == b"" and "www-authenticate" not in no_token.headers  # 빈 403, 챌린지 없음(MCP 401이 아니다 = 라우트가 Mount 앞)
    bad = {header_name: header_value[:-1] + ("A" if header_value[-1] != "A" else "B")}
    assert httpx.get(d["uri"], headers=bad, timeout=10).status_code == 403
    assert httpx.get(f"{base}{PUBLIC_PATH}/archive/yt-subs/{'f' * 40}.tar", headers=d["headers"], timeout=10).status_code == 403
    assert httpx.get(d["uri"], headers=d["headers"], timeout=10).status_code == 200  # TTL 안 재사용은 허용
    outsider = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["users"])
    assert result_of(call_tool(base, outsider, "get_skill_archive", {"id": "yt-subs"}))["structuredContent"]["code"] == "not_a_member"
    unknown = result_of(call_tool(base, token, "get_skill_archive", {"id": "yt-subs", "sha": "e" * 40}))["structuredContent"]
    assert unknown["code"] == "unknown_version"



def test_toolbox_search_get_and_script_archive(server: tuple[str, FakeIssuer]) -> None:
    """toolbox 도구 둘: 검색 → 정의(kind=mcp면 server.json 동봉) → kind=script면 기술자로 tar를 받는다(tools 라우트, 종류가 서명 범위)."""
    import hashlib
    import io
    import tarfile

    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])
    hits = result_of(call_tool(base, token, "search_tools", {"query": "자막"}))["structuredContent"]["tools"]
    assert [t["name"] for t in hits] == ["subs-fetch"] and hits[0]["kind"] == "script" and hits[0]["requires_tools"] == ["uv"]
    assert [t["name"] for t in result_of(call_tool(base, token, "search_tools", {"query": "graph"}))["structuredContent"]["tools"]] == ["graft-ask"]
    assert [s["name"] for s in result_of(call_tool(base, token, "list_skills", {}))["structuredContent"]["skills"]] == ["pin-skill", "yt-subs"]  # 스킬 목록은 그대로
    mcp = result_of(call_tool(base, token, "get_tool", {"id": "graft-ask"}))["structuredContent"]
    assert mcp["kind"] == "mcp" and mcp["tool"]["runtime"] == {"kind": "mcp", "server": "graft", "tool": "graft_find_code"}
    assert mcp["server"]["name"] == "lab.altera/graft" and mcp["archive"] is None and len(mcp["sha"]) == 40
    script = result_of(call_tool(base, token, "get_tool", {"id": "subs-fetch"}))["structuredContent"]
    assert script["kind"] == "script" and script["server"] is None and sorted(f["path"] for f in script["files"]) == ["scripts/fetch.py", "tool.json"]
    d = script["archive"]
    assert d["uri"] == f"{base}{PUBLIC_PATH}/archive/tools/subs-fetch/{script['sha']}.tar" and d["digest"] == f"git-tree:{script['sha']}"
    r = httpx.get(d["uri"], headers=d["headers"], timeout=10)
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == d["sha256"] and len(r.content) == d["size"]
    with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
        assert sorted(m.name for m in tar.getmembers() if m.isfile()) == ["scripts/fetch.py", "tool.json"]
    # 도구 토큰으로 스킬 라우트를, 스킬 토큰으로 도구 라우트를 열 수 없다(종류가 서명 범위) — 둘 다 빈 403
    assert httpx.get(f"{base}{PUBLIC_PATH}/archive/subs-fetch/{script['sha']}.tar", headers=d["headers"], timeout=10).status_code == 403
    skill = result_of(call_tool(base, token, "load_skill", {"id": "yt-subs"}))["structuredContent"]
    sd = result_of(call_tool(base, token, "get_skill_archive", {"id": "yt-subs", "sha": skill["sha"]}))["structuredContent"]
    assert httpx.get(f"{base}{PUBLIC_PATH}/archive/tools/yt-subs/{skill['sha']}.tar", headers=sd["headers"], timeout=10).status_code == 403
    assert httpx.get(d["uri"], timeout=10).status_code == 403
    outsider = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["users"])
    assert result_of(call_tool(base, outsider, "search_tools", {"query": "x"}))["structuredContent"]["code"] == "not_a_member"
    assert result_of(call_tool(base, token, "get_tool", {"id": "yt-subs"}))["structuredContent"]["code"] == "not_found"  # 스킬 이름은 도구가 아니다
