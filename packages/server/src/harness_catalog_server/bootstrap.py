"""Configurator: 설정값을 읽어 어댑터를 만들고 앱에 꽂고 구동 어댑터 셋을 조립한다. 모든 참가자를 아는 유일한 자리."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import NamedTuple

import anyio
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.adapters.validate import SkillsRefValidator
from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import IndexSnapshot
from harness_catalog_core.settings import Settings

from .adapters.oidc import JwtTokenVerifier, discover_jwks_uri
from .driving.mcp_tools import build_server
from .driving.ops import healthz, make_readyz
from .driving.scheduler import run_scheduler

SERVICE_CLIENT_IDS: frozenset[str] = frozenset({"ci-runner"})


class NoFactStore:
    """DB 없이 도는 판: 기록하지 않고 검색은 메모리 사본에 맡긴다."""

    def replace_index(self, _snapshot: IndexSnapshot, /) -> bool:
        return True

    def search(self, _query: str, _limit: int, /) -> tuple[str, ...] | None:
        return None


class App(NamedTuple):
    asgi: Starlette
    catalog: Catalog


def bootstrap(settings: Settings, workdir: Path, *, jwks_uri: str | None = None) -> App:
    workdir.mkdir(parents=True, exist_ok=True)
    store = GitStore(workdir / "clone", settings.catalog_repo_url, settings.git_deploy_key.get_secret_value())
    catalog = Catalog(store, SkillsRefValidator(), NoFactStore(), workdir=workdir / "tmp")
    (workdir / "tmp").mkdir(exist_ok=True)
    issuer = str(settings.oidc_issuer).rstrip("/")
    public_url = str(settings.public_url).rstrip("/")
    verifier = JwtTokenVerifier(issuer, public_url, jwks_uri or discover_jwks_uri(issuer))
    server = build_server(catalog, issuer=issuer, public_url=public_url, verifier=verifier, service_client_ids=SERVICE_CLIENT_IDS)
    mcp_app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, host="0.0.0.0")  # noqa: S104

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncGenerator[None]:
        stop = anyio.Event()
        async with mcp_app.router.lifespan_context(mcp_app), anyio.create_task_group() as tg:
            tg.start_soon(run_scheduler, catalog, settings.fetch_interval_seconds, stop)
            try:
                yield
            finally:
                stop.set()

    asgi = Starlette(
        routes=[Route("/healthz", healthz), Route("/readyz", make_readyz(catalog)), Mount("/", app=mcp_app)],
        lifespan=lifespan,
    )
    return App(asgi, catalog)
