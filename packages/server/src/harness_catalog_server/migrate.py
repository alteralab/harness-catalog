"""마이그레이션 러너: 패키지 데이터의 SQL을 yoyo로 적용한다(기동 직후 별도 태스크, 실패 시 재시도)."""

from __future__ import annotations

import logging
from importlib.resources import as_file, files
from urllib.parse import urlsplit, urlunsplit

from yoyo import get_backend, read_migrations  # pyright: ignore[reportUnknownVariableType]

log = logging.getLogger(__name__)


def yoyo_url(database_url: str) -> str:
    """postgresql://… → postgresql+psycopg://… (yoyo의 psycopg 3 백엔드)."""
    parts = urlsplit(database_url)
    scheme = parts.scheme
    if scheme in ("postgresql", "postgres"):
        scheme = "postgresql+psycopg"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def migrate(database_url: str) -> int:
    """적용한 마이그레이션 수. 예외는 그대로 전파한다(호출자가 재시도)."""
    with as_file(files("harness_catalog_server") / "migrations") as path:
        migrations = read_migrations(str(path))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        backend = get_backend(yoyo_url(database_url))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        with backend.lock():  # pyright: ignore[reportUnknownMemberType]
            pending = backend.to_apply(migrations)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            backend.apply_migrations(pending)  # pyright: ignore[reportUnknownMemberType]
    applied = len(pending)  # pyright: ignore[reportUnknownArgumentType]
    log.info("migrations applied: %d", applied)
    return applied
