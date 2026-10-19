"""도구 호출 스팬: SDK가 내는 SERVER 스팬에 MCP 어댑터가 주체·스킬·검색어 속성을 더한다. 인프로세스 ASGI."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harness_catalog_core.settings import Settings
from harness_catalog_server.bootstrap import bootstrap
from tests.conftest import CatalogRepo
from tests.http.fake_issuer import FakeIssuer, start_fake_issuer

PUBLIC = "http://testserver/mcp"

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)


@pytest.fixture(scope="module")
def issuer() -> Iterator[FakeIssuer]:
    fi = start_fake_issuer()
    yield fi
    fi.stop()


@pytest.fixture
async def client(tmp_path: Path, catalog_repo: CatalogRepo, issuer: FakeIssuer) -> Any:
    settings = Settings(catalog_repo_url=str(catalog_repo.path), git_deploy_key="", oidc_issuer=issuer.issuer, public_url=PUBLIC, database_url="postgresql://unused", fetch_interval_seconds=3600)  # pyright: ignore[reportArgumentType]
    app = bootstrap(settings, tmp_path / "work", use_db=False)
    async with app.asgi.router.lifespan_context(app.asgi):  # 스케줄러(첫 빌드)와 MCP 세션 매니저가 여기서 뜬다
        await anyio.to_thread.run_sync(app.catalog.rebuild)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.asgi), base_url="http://testserver") as c:
            yield c, issuer


async def call(c: httpx.AsyncClient, token: str, name: str, arguments: dict[str, Any]) -> httpx.Response:
    return await c.post("/mcp", headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"},
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})


@pytest.mark.anyio
async def test_tool_spans_carry_subject_skill_and_query(client: tuple[httpx.AsyncClient, FakeIssuer]) -> None:
    c, issuer = client
    _exporter.clear()
    token = issuer.token(sub="user-7", aud=PUBLIC, groups=["harness-readers"])
    r = await call(c, token, "get_skill", {"id": "yt-subs"})
    sha = r.json()["result"]["structuredContent"]["sha"]
    await call(c, token, "search_skills", {"query": "nothing-at-all"})
    spans = {s.name: s for s in _exporter.get_finished_spans() if s.name.startswith("tools/call")}
    load = spans["tools/call get_skill"]
    assert load.kind.name == "SERVER" and load.attributes is not None
    assert load.attributes["gen_ai.tool.name"] == "get_skill" and load.attributes["langfuse.user.id"] == "user-7"
    assert load.attributes["langfuse.observation.metadata.skill"] == "yt-subs" and load.attributes["langfuse.observation.metadata.sha"] == sha
    search = spans["tools/call search_skills"]
    assert search.attributes is not None
    assert search.attributes["langfuse.observation.metadata.query"] == "nothing-at-all" and search.attributes["langfuse.observation.metadata.result_count"] == 0
