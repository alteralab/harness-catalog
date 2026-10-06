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
    facts.enable()
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
    facts.enable()
    assert facts.replace_index(snap("c" * 40, "x"), lambda _s: True) is IndexOutcome.UNAVAILABLE
    assert facts.breaker.is_open and facts.search("x", 5) is None
    facts.close()


def test_yoyo_url() -> None:
    assert yoyo_url("postgresql://u:p@h:5432/db?sslmode=disable") == "postgresql+psycopg://u:p@h:5432/db?sslmode=disable"


def test_concurrent_first_build_is_all_or_nothing(database_url: str) -> None:
    """빈 index_state에서 두 인스턴스가 동시에 다른 스냅샷을 쓰면 최종 행 집합은 둘 중 하나와 정확히 같다(섞이지 않는다)."""
    import threading

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM skill_index; DELETE FROM index_state")
        conn.commit()
    a_snap = snap("a" * 40, "alpha-1", "alpha-2", "alpha-3")
    b_snap = snap("b" * 40, "beta-1", "beta-2")
    stores = [PgFactStore(database_url), PgFactStore(database_url)]
    for s in stores:
        s.open(); s.enable()
    outcomes: list[IndexOutcome] = []
    barrier = threading.Barrier(2)

    def run(store: PgFactStore, sn: IndexSnapshot) -> None:
        barrier.wait()
        outcomes.append(store.replace_index(sn, lambda _s: True))

    threads = [threading.Thread(target=run, args=(stores[0], a_snap)), threading.Thread(target=run, args=(stores[1], b_snap))]
    for t in threads: t.start()
    for t in threads: t.join()
    assert outcomes == [IndexOutcome.REPLACED, IndexOutcome.REPLACED]
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM skill_index ORDER BY name")
        names = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT commit_sha FROM index_state WHERE id = 1")
        commit = cur.fetchone()[0]  # type: ignore[index]
    expected = {"a" * 40: {"alpha-1", "alpha-2", "alpha-3"}, "b" * 40: {"beta-1", "beta-2"}}
    assert names == expected[commit]
    for s in stores:
        s.close()


def test_ddl_expressions_match_contract(database_url: str) -> None:
    """생성 열의 식·함수의 IMMUTABLE·인덱스 연산자 클래스까지 설계의 DDL 문자열과 같다."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name, pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum JOIN information_schema.columns c ON c.column_name = a.attname AND c.table_name = 'skill_index' WHERE a.attrelid = 'skill_index'::regclass AND a.attgenerated = 's' ORDER BY a.attnum")
        gen = dict(cur.fetchall())
        assert gen["replaced_by"] == "(metadata ->> 'replaced-by'::text)"
        assert gen["requires_tools"] == "string_to_array(NULLIF((metadata ->> 'requires-tools'::text), ''::text), ' '::text)"
        assert "to_tsvector('simple'::regconfig" in gen["search"] and "metadata_values(metadata)" in gen["search_text"]
        cur.execute("SELECT provolatile FROM pg_proc WHERE proname = 'metadata_values'")
        assert cur.fetchone() == ("i",)
        cur.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'skill_index_trgm'")
        assert "gin (search_text gin_trgm_ops)" in cur.fetchone()[0]  # type: ignore[index]
        cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'skill_index'::regclass AND contype = 'c'")
        assert any("length(compatibility) <= 500" in r[0] for r in cur.fetchall())


def test_breaker_half_open_lets_one_probe_through() -> None:
    clock = [0.0]
    br = Breaker(failures=2, open_seconds=10, clock=lambda: clock[0])
    br.record_failure(); br.record_failure()
    assert not br.allow()
    clock[0] = 11.0
    assert br.allow()  # half-open: 시험 요청 하나
    assert not br.allow()  # 둘째는 막힌다
    br.record_failure()  # 시험 실패 → 다시 열림
    assert not br.allow()
    clock[0] = 22.0
    assert br.allow()
    br.record_success()  # 시험 성공 → 닫힘
    assert br.allow() and br.allow()


def test_disabled_until_migrated(database_url: str) -> None:
    facts = PgFactStore(database_url)
    facts.open()
    assert facts.replace_index(snap("e" * 40, "x"), lambda _s: True) is IndexOutcome.UNAVAILABLE
    assert facts.search("x", 5) is None and facts.current_commit() is None
    facts.enable()
    assert facts.current_commit() is not None or facts.replace_index(snap("e" * 40, "x"), lambda _s: True) is IndexOutcome.REPLACED
    facts.close()
