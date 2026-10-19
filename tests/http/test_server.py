"""HTTP 경유 시험: 실제 uvicorn 프로세스 + 가짜 issuer(JWKS). 도구 여섯 호출과 401/403 경계."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from tests.http.fake_issuer import FakeIssuer, start_fake_issuer

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator, Mapping
    from pathlib import Path

    from tests.conftest import CatalogRepo

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
    with serve(tmp_path, catalog_repo, issuer) as running:
        yield running


@contextlib.contextmanager
def serve(tmp_path: Path, catalog_repo: CatalogRepo, issuer: FakeIssuer, extra_env: Mapping[str, str] | None = None) -> Generator[tuple[str, FakeIssuer]]:
    """레지스트리 프로세스 하나. `extra_env`로 설정값을 바꿔 띄운다(예: HC__READER_GROUP)."""
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
        **(extra_env or {}),
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
    try:
        yield base, issuer
    finally:
        proc.terminate()
        proc.wait(10)


def call_tool(base: str, token: str | None, name: str, arguments: dict[str, Any]) -> httpx.Response:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return httpx.post(base + PUBLIC_PATH, headers=headers, json=body, timeout=10)


def list_tools(base: str, token: str) -> list[dict[str, Any]]:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    data = httpx.post(base + PUBLIC_PATH, headers=headers, json=body, timeout=10).json()
    assert "result" in data, data
    return list(data["result"]["tools"])


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
    r = call_tool(base, None, "search_skills", {"query": "자막"})
    assert r.status_code == 401
    www = r.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www
    meta = httpx.get(base + "/.well-known/oauth-protected-resource" + PUBLIC_PATH)
    if meta.status_code == 404:
        meta = httpx.get(base + "/.well-known/oauth-protected-resource")
    doc = meta.json()
    assert doc["resource"].rstrip("/") == base + PUBLIC_PATH
    assert doc["scopes_supported"] == ["openid", "groups", f"audience:server:client_id:{base}{PUBLIC_PATH}"]


def test_reader_calls_skill_tools(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])  # Dex처럼 scope 클레임 없음
    listing = result_of(call_tool(base, token, "search_skills", {"query": "pin"}))  # 전체 목록 도구는 없다(DESIGN §11 2026-10-11)
    assert [s["name"] for s in listing["structuredContent"]["skills"]] == ["pin-skill"]
    hit = result_of(call_tool(base, token, "search_skills", {"query": "유튜브 자막"}))
    assert [s["name"] for s in hit["structuredContent"]["skills"]] == ["yt-subs"]
    assert hit["structuredContent"]["skills"][0]["has_scripts"] is True  # 루프 조립기가 거르는 신호
    body = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs"}))["structuredContent"]
    assert body["has_scripts"] and "Do the thing" in body["body"] and body["file"] is None and body["archive"] is None and len(body["sha"]) == 40
    one = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs", "path": "scripts/fetch.py"}))["structuredContent"]
    f = one["file"]
    assert one["body"] is None and f["text"] == "print('hi')\n" and one["sha"] == body["sha"] and len(f["blob"]) == 40 and f["blob"] != body["sha"]
    err = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs", "path": "../x"}))
    assert err["isError"] is True and err["structuredContent"]["code"] == "path_rejected"


def test_wrong_audience_expired_and_not_a_member(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    wrong_aud = issuer.token(sub="u", aud="claude-code", groups=["harness-readers"])  # 교차 클라이언트 스코프 없이 받은 Dex 토큰 꼴
    assert call_tool(base, wrong_aud, "search_skills", {"query": "자막"}).status_code == 401
    multi_aud = issuer.token(sub="u", aud=[base + PUBLIC_PATH, "claude-code"], groups=["harness-readers"], azp="claude-code")  # 교차 클라이언트 스코프로 받은 꼴
    assert "structuredContent" in result_of(call_tool(base, multi_aud, "search_skills", {"query": "자막"}))
    expired = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["harness-readers"], exp_in=-120)
    assert call_tool(base, expired, "search_skills", {"query": "자막"}).status_code == 401
    outsider = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["users"])
    r = call_tool(base, outsider, "search_skills", {"query": "자막"})
    assert r.status_code == 200 and "www-authenticate" not in {k.lower() for k in r.headers}
    res = result_of(r)
    assert res["isError"] is True and res["structuredContent"]["code"] == "not_a_member"


def test_reader_group_follows_the_setting(tmp_path: Path, catalog_repo: CatalogRepo, issuer: FakeIssuer) -> None:
    """HC__READER_GROUP을 바꾼 프로세스는 그 그룹의 토큰만 받는다 — 기본값 harness-readers는 더 이상 reader가 아니다(§11 2026-10-20)."""
    with serve(tmp_path, catalog_repo, issuer, {"HC__READER_GROUP": "platform-readers"}) as (base, fi):
        allowed = fi.token(sub="u", aud=base + PUBLIC_PATH, groups=["platform-readers"])
        assert [s["name"] for s in result_of(call_tool(base, allowed, "search_skills", {"query": "pin"}))["structuredContent"]["skills"]] == ["pin-skill"]
        refused = result_of(call_tool(base, fi.token(sub="u2", aud=base + PUBLIC_PATH, groups=["harness-readers"]), "search_skills", {"query": "pin"}))
        assert refused["isError"] is True and refused["structuredContent"]["code"] == "not_a_member"
        assert "platform-readers" in refused["structuredContent"]["detail"]


def test_machine_account_reads_by_group(server: tuple[str, FakeIssuer]) -> None:
    base, issuer = server
    svc = issuer.token(sub="svc-harness", aud=base + PUBLIC_PATH, groups=["harness-readers"])  # 기계 계정 = 그룹으로 reader
    res = result_of(call_tool(base, svc, "search_skills", {"query": "자막"}))
    assert "structuredContent" in res and not res.get("isError")
    assert json.loads(res["content"][0]["text"])["skills"]


def test_archive_descriptor_then_download_without_bearer(server: tuple[str, FakeIssuer], tmp_path: Path) -> None:  # noqa: ARG001 — 픽스처·콜백 시그니처가 요구하는 인자
    """get_skill(archive=true): 명세(uri·헤더 토큰·크기·sha256) → 헤더만으로 GET → tar가 파일 목록과 같다. 자격은 URL에 없다."""
    import hashlib
    import io
    import tarfile

    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])
    body = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs", "archive": True}))["structuredContent"]
    d = body["archive"]
    assert d["digest"] == f"git-tree:{body['sha']}" and d["mimeType"] == "application/x-tar" and body["body"] is not None  # 본문과 명세가 한 응답에
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
    assert result_of(call_tool(base, outsider, "get_skill", {"id": "yt-subs", "archive": True}))["structuredContent"]["code"] == "not_a_member"
    unknown = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs", "sha": "e" * 40, "archive": True}))["structuredContent"]
    assert unknown["code"] == "unknown_version"



def test_toolbox_search_get_and_script_archive(server: tuple[str, FakeIssuer]) -> None:
    """toolbox 도구 둘: 검색 → 정의(kind=mcp면 server.json 동봉) → kind=script면 명세로 tar를 받는다(tools 라우트, 종류가 서명 범위)."""
    import hashlib
    import io
    import tarfile

    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])
    hits = result_of(call_tool(base, token, "search_tools", {"query": "자막"}))["structuredContent"]["tools"]
    assert [t["name"] for t in hits] == ["subs-fetch"] and hits[0]["kind"] == "script" and set(hits[0]) == {"name", "description", "sha", "kind", "server"}
    assert [t["name"] for t in result_of(call_tool(base, token, "search_tools", {"query": "graph"}))["structuredContent"]["tools"]] == ["graft-ask"]
    assert [s["name"] for s in result_of(call_tool(base, token, "search_skills", {"query": "자막"}))["structuredContent"]["skills"]] == ["yt-subs"]  # 스킬 검색에 도구(subs-fetch)가 섞이지 않는다
    mcp = result_of(call_tool(base, token, "get_tool", {"id": "graft-ask"}))["structuredContent"]
    assert mcp["kind"] == "mcp" and mcp["tool"]["runtime"] == {"kind": "mcp", "server": "graft", "tool": "graft_find_code"}
    assert mcp["server"]["name"] == "lab.altera/graft" and mcp["archive"] is None and len(mcp["sha"]) == 40
    plain = result_of(call_tool(base, token, "get_tool", {"id": "subs-fetch"}))["structuredContent"]
    assert plain["archive"] is None  # 명세는 옵트인(get_skill과 대칭)
    script = result_of(call_tool(base, token, "get_tool", {"id": "subs-fetch", "archive": True}))["structuredContent"]
    assert script["kind"] == "script" and script["server"] is None and sorted(f["path"] for f in script["files"]) == ["scripts/fetch.py", "tool.json"]
    d = script["archive"]
    assert d["uri"] == f"{base}{PUBLIC_PATH}/archive/tools/subs-fetch/{script['sha']}.tar" and d["digest"] == f"git-tree:{script['sha']}"
    r = httpx.get(d["uri"], headers=d["headers"], timeout=10)
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == d["sha256"] and len(r.content) == d["size"]
    with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
        assert sorted(m.name for m in tar.getmembers() if m.isfile()) == ["scripts/fetch.py", "tool.json"]
    # 도구 토큰으로 스킬 라우트를, 스킬 토큰으로 도구 라우트를 열 수 없다(종류가 서명 범위) — 둘 다 빈 403
    assert httpx.get(f"{base}{PUBLIC_PATH}/archive/subs-fetch/{script['sha']}.tar", headers=d["headers"], timeout=10).status_code == 403
    skill = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs", "archive": True}))["structuredContent"]
    assert httpx.get(f"{base}{PUBLIC_PATH}/archive/tools/yt-subs/{skill['sha']}.tar", headers=skill["archive"]["headers"], timeout=10).status_code == 403
    assert httpx.get(d["uri"], timeout=10).status_code == 403
    outsider = issuer.token(sub="u", aud=base + PUBLIC_PATH, groups=["users"])
    assert result_of(call_tool(base, outsider, "search_tools", {"query": "x"}))["structuredContent"]["code"] == "not_a_member"
    assert result_of(call_tool(base, token, "get_tool", {"id": "yt-subs"}))["structuredContent"]["code"] == "not_found"  # 스킬 이름은 도구가 아니다


def test_every_tool_publishes_output_schema_and_results_conform(server: tuple[str, FakeIssuer]) -> None:
    """DESIGN §11 응답 모델: tools/list가 넷 모두에 닫힌 outputSchema를 싣고, 성공 응답의 structuredContent가 그 스키마에 맞으며 text의 JSON과 같다."""
    import jsonschema

    base, issuer = server
    token = issuer.token(sub="user-1", aud=base + PUBLIC_PATH, groups=["harness-readers"])
    tools = {t["name"]: t for t in list_tools(base, token)}
    assert sorted(tools) == ["get_skill", "get_tool", "search_skills", "search_tools"]
    for name, t in tools.items():
        schema = t.get("outputSchema")
        assert schema and schema["type"] == "object" and schema["additionalProperties"] is False, name
    skill = result_of(call_tool(base, token, "get_skill", {"id": "yt-subs"}))["structuredContent"]
    calls: list[tuple[str, dict[str, Any]]] = [
        ("search_skills", {"query": "자막"}),
        ("get_skill", {"id": "yt-subs"}),
        ("get_skill", {"id": "yt-subs", "path": "scripts/fetch.py"}),
        ("get_skill", {"id": "yt-subs", "sha": skill["sha"], "archive": True}),
        ("search_tools", {"query": "자막"}),
        ("get_tool", {"id": "subs-fetch", "archive": True}),  # kind=script → archive 명세가 실린다
        ("get_tool", {"id": "graft-ask"}),  # kind=mcp → server.json이 실린다(별칭 $schema 유지)
    ]
    for name, args in calls:
        res = result_of(call_tool(base, token, name, args))
        assert not res.get("isError"), (name, res)
        jsonschema.validate(res["structuredContent"], tools[name]["outputSchema"])
        assert json.loads(res["content"][0]["text"]) == res["structuredContent"], name
    mcp = result_of(call_tool(base, token, "get_tool", {"id": "graft-ask"}))["structuredContent"]
    assert mcp["server"]["name"] == "lab.altera/graft" and "version" in mcp["server"]
    err = result_of(call_tool(base, token, "get_skill", {"id": "nope"}))
    assert err["isError"] is True and set(err["structuredContent"]) == {"code", "detail"}  # 오류 모양은 스키마 밖이지만 하나다
