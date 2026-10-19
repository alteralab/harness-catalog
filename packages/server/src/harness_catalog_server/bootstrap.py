"""Configurator: 설정값을 읽어 어댑터를 만들고 앱에 꽂고 구동 어댑터 셋을 조립한다. 모든 참가자를 아는 유일한 자리."""

from __future__ import annotations

import contextlib
import secrets
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import NamedTuple

import anyio
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.adapters.validate import SkillsRefValidator
from harness_catalog_core.archive_token import ArchiveSigner
from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import IndexOutcome, IndexSnapshot
from harness_catalog_core.settings import Settings

from .adapters.embed import HttpEmbedder
from .adapters.oidc import JwtTokenVerifier, discover_jwks_uri
from .adapters.pg import PgFactStore
from .driving.mcp_tools import build_server
from .driving.archive_route import ARCHIVE_PATH, TOOL_ARCHIVE_PATH, make_archive_route
from .driving.ops import healthz, make_readyz
from .driving.scheduler import run_migrations, run_scheduler

class NoFactStore:
    """DB 없이 도는 판(시험·`reindex` 전 단계): 기록하지 않는다. 검색은 어차피 앱의 메모리 색인이다(§11 2026-10-19)."""

    def replace_index(self, _snapshot: IndexSnapshot, _is_descendant: Callable[[str], bool], /) -> IndexOutcome:
        return IndexOutcome.REPLACED

    def load_embeddings(self, _generation: str, /) -> dict[tuple[str, str], tuple[float, ...]] | None:
        return None

    def current_commit(self) -> str | None:
        return None


def _enable_after_migration(facts: PgFactStore, ready: anyio.Event) -> Callable[[], None]:
    def enable_db() -> None:
        facts.enable()
        ready.set()

    return enable_db


class App(NamedTuple):
    asgi: Starlette
    catalog: Catalog
    facts: PgFactStore | NoFactStore


class Wiring(NamedTuple):
    catalog: Catalog
    facts: PgFactStore | NoFactStore
    store: GitStore


def make_catalog(settings: Settings, workdir: Path, *, use_db: bool = True) -> Wiring:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "tmp").mkdir(exist_ok=True)
    store = GitStore(workdir / "clone", settings.catalog_repo_url, settings.git_deploy_key.get_secret_value())
    facts: PgFactStore | NoFactStore = PgFactStore(settings.database_url.get_secret_value()) if use_db else NoFactStore()
    embedder = HttpEmbedder(settings.embed_url, settings.embed_model) if settings.embed_url else None  # 비면 BM25 만(§11 2026-10-19 검색 0.8.0)
    return Wiring(Catalog(store, SkillsRefValidator(), facts, workdir=workdir / "tmp", embedder=embedder), facts, store)


def bootstrap(settings: Settings, workdir: Path, *, jwks_uri: str | None = None, use_db: bool = True) -> App:
    catalog, facts, store = make_catalog(settings, workdir, use_db=use_db)
    issuer = str(settings.oidc_issuer).rstrip("/")
    public_url = str(settings.public_url).rstrip("/")
    verifier = JwtTokenVerifier(issuer, public_url, jwks_uri or discover_jwks_uri(issuer))
    signer = ArchiveSigner(secrets.token_bytes(32))  # 프로세스 수명 키: 복제본 하나 전제, 재기동이 곧 회전(DESIGN §11 2026-10-11)
    catalog.evict_archives(retention_seconds=0)  # 새 키라 옛 토큰은 전부 403 — 캐시 tar는 쓸모가 없다
    server = build_server(catalog, issuer=issuer, public_url=public_url, verifier=verifier, signer=signer, reader_group=settings.reader_group)
    mcp_app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, host="0.0.0.0")  # noqa: S104

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncGenerator[None]:
        stop = anyio.Event()
        if isinstance(facts, PgFactStore):
            facts.open()
        try:
            async with mcp_app.router.lifespan_context(mcp_app):
                async with anyio.create_task_group() as tg:
                    db_ready: anyio.Event | None = None
                    if isinstance(facts, PgFactStore):
                        db_ready = anyio.Event()
                        tg.start_soon(run_migrations, settings.database_url.get_secret_value(), stop, _enable_after_migration(facts, db_ready))
                    tg.start_soon(run_scheduler, catalog, settings.fetch_interval_seconds, stop, db_ready)
                    try:
                        yield
                    finally:
                        stop.set()  # 태스크 그룹이 스케줄러 종료를 기다린 뒤에야 아래로 내려온다
        finally:
            if isinstance(facts, PgFactStore):
                facts.close()
            store.close()

    asgi = Starlette(
        # 아카이브 라우트는 MCP Mount("/") 앞에 있어야 한다 — 뒤에 두면 /mcp/... 전부를 MCP 앱이 먼저 받아 401을 낸다
        routes=[Route("/healthz", healthz), Route("/readyz", make_readyz(catalog)), Route(TOOL_ARCHIVE_PATH, make_archive_route(catalog, signer, "tools")), Route(ARCHIVE_PATH, make_archive_route(catalog, signer, "skills")), Mount("/", app=mcp_app)],
        lifespan=lifespan,
    )
    return App(asgi, catalog, facts)
