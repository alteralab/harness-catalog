"""PostgreSQL 어댑터: 실물 컨테이너(testcontainers)로 DDL 적용·세대 검사·검색·브레이커."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from harness_catalog_core.model import IndexOutcome, IndexSnapshot, SkillEntry
from harness_catalog_server.adapters.pg import Breaker, PgFactStore
from harness_catalog_server.migrate import migrate, yoyo_url

pytestmark = pytest.mark.pg
# Docker Desktop(macOS)은 소켓이 ~/.docker/run/docker.sock이라 reaper 컨테이너가 그 경로를 마운트하지 못한다(실측). 표준 경로로 알려 준다.
os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        url = pg.get_connection_url()
        migrate(url)
        yield url


def snap(commit: str, *names: str) -> IndexSnapshot:
    entries = tuple(SkillEntry(n, f"{n} description 유튜브 자막" if n == "yt-subs" else f"{n} description", None, {"requires-tools": "uv"}, ("t" + n).ljust(40, "0")[:40], commit) for n in names)
    return IndexSnapshot(entries, commit, datetime.now(UTC), datetime.now(UTC))


def test_schema_applied_as_contract(database_url: str) -> None:
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'skill_index' ORDER BY ordinal_position")
        cols = [r[0] for r in cur.fetchall()]
        assert cols == ["name", "description", "compatibility", "metadata", "tree_sha", "commit_sha", "indexed_at", "replaced_by", "requires_tools", "search_text", "search"]
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'skill_index' ORDER BY 1")
        assert {r[0] for r in cur.fetchall()} >= {"skill_index_search", "skill_index_trgm", "skill_index_tools"}
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cur.fetchone() is not None
    assert migrate(database_url) == 0  # 멱등


def test_generation_check_and_search(database_url: str) -> None:
    facts = PgFactStore(database_url)
    facts.open()
    a, b = "a" * 40, "b" * 40
    assert facts.replace_index(snap(a, "yt-subs", "pin-skill"), lambda _s: True) is IndexOutcome.REPLACED
    assert facts.current_commit() == a
    # B는 A의 자손 → 교체
    assert facts.replace_index(snap(b, "yt-subs"), lambda stored: stored == a) is IndexOutcome.REPLACED
    assert facts.current_commit() == b
    # 낡은 A로 다시 빌드 → B의 자손이 아니므로 아무것도 바꾸지 않는다
    assert facts.replace_index(snap(a, "yt-subs", "pin-skill"), lambda stored: stored == a) is IndexOutcome.STALE
    assert facts.current_commit() == b
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT name, replaced_by, requires_tools FROM skill_index ORDER BY name")
        assert cur.fetchall() == [("yt-subs", None, ["uv"])]
    assert facts.search("유튜브", 10) == ("yt-subs",)
    assert facts.search("subs", 10) == ("yt-subs",)
    assert facts.search("nothing-here", 10) == ()
    facts.close()


def test_breaker_opens_after_failures() -> None:
    clock = [100.0]
    br = Breaker(failures=3, open_seconds=30, clock=lambda: clock[0])
    assert not br.is_open
    br.record_failure(); br.record_failure()
    assert not br.is_open
    br.record_failure()
    assert br.is_open
    clock[0] += 31
    assert not br.is_open
    br.record_success()
    assert not br.is_open


def test_unreachable_db_is_unavailable_not_exception() -> None:
    facts = PgFactStore("postgresql://nobody:nothing@127.0.0.1:1/nope", breaker=Breaker(failures=1, open_seconds=30))
    facts.open()
    assert facts.replace_index(snap("c" * 40, "x"), lambda _s: True) is IndexOutcome.UNAVAILABLE
    assert facts.breaker.is_open and facts.search("x", 5) is None
    facts.close()


def test_yoyo_url() -> None:
    assert yoyo_url("postgresql://u:p@h:5432/db?sslmode=disable") == "postgresql+psycopg://u:p@h:5432/db?sslmode=disable"
