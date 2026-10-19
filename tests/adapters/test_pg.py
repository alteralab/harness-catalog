"""PostgreSQL 어댑터: 실물 컨테이너(testcontainers)로 DDL 적용·세대 검사·벡터 저장·브레이커. 검색은 앱의 메모리 색인이다(§11 2026-10-19)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg
import pytest
from harness_catalog_core.model import IndexOutcome, IndexSnapshot, SkillEntry
from harness_catalog_server.adapters.pg import Breaker, PgFactStore
from harness_catalog_server.migrate import migrate, yoyo_url
from testcontainers.community.postgres import PostgresContainer

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.pg
# Docker Desktop(macOS)은 소켓이 ~/.docker/run/docker.sock이라 reaper 컨테이너가 그 경로를 마운트하지 못한다(실측). 표준 경로로 알려 준다.
os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        url = pg.get_connection_url()
        migrate(url)
        yield url


def snap(commit: str, *names: str, generation: str | None = None) -> IndexSnapshot:
    entries = tuple(SkillEntry(n, f"{n} description 유튜브 자막" if n == "yt-subs" else f"{n} description", None, {"requires-tools": "uv"}, ("t" + n).ljust(40, "0")[:40], commit) for n in names)
    embeddings = {e.name: (1.0, 0.5, 0.25) for e in entries} if generation else {}
    return IndexSnapshot(entries, commit, datetime.now(UTC), datetime.now(UTC), embeddings=embeddings, embedding_generation=generation)


def test_schema_applied_as_contract(database_url: str) -> None:
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'skill_index' ORDER BY ordinal_position")
        cols = [r[0] for r in cur.fetchall()]
        assert cols == ["name", "description", "compatibility", "metadata", "tree_sha", "commit_sha", "indexed_at", "embedding", "embedding_generation"]  # replaced_by·requires_tools는 0003에서 지웠고 벡터 둘은 0004
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename IN ('skill_index', 'tool_index') ORDER BY 1")
        assert [r[0] for r in cur.fetchall()] == ["skill_index_pkey", "tool_index_pkey"]  # 0005: 어휘 검색의 GIN 인덱스 넷은 없다
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
        cur.execute("SELECT name FROM skill_index ORDER BY name")
        assert cur.fetchall() == [("yt-subs",)]
    # 벡터 저장·세대별 읽기(§11 2026-10-19 검색 0.8.0): 세대가 다른 벡터는 돌아오지 않는다
    assert facts.load_embeddings("m/doc1") == {}
    c = "c" * 40
    assert facts.replace_index(snap(c, "yt-subs", "pin-skill", generation="m/doc1"), lambda stored: stored == b) is IndexOutcome.REPLACED
    got = facts.load_embeddings("m/doc1")
    subs, pin = "tyt-subs".ljust(40, "0")[:40], "tpin-skill".ljust(40, "0")[:40]
    assert got is not None and set(got) == {("yt-subs", subs), ("pin-skill", pin)} and got[("yt-subs", subs)] == (1.0, 0.5, 0.25)  # 키는 (name, tree_sha)
    assert facts.load_embeddings("other/doc1") == {}
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
    assert facts.breaker.is_open and facts.load_embeddings("m/doc1") is None
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
    """0005 뒤: 생성 열도 metadata_values 함수도 없다(검색은 앱 메모리, DESIGN §11 2026-10-19 스키마 정리). CHECK 제약은 그대로."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name, pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum JOIN information_schema.columns c ON c.column_name = a.attname AND c.table_name = 'skill_index' WHERE a.attrelid = 'skill_index'::regclass AND a.attgenerated = 's' ORDER BY a.attnum")
        assert dict(cur.fetchall()) == {}  # 0005 뒤 생성 열은 없다(검색은 앱 메모리)
        cur.execute("SELECT count(*) FROM pg_proc WHERE proname = 'metadata_values'")
        assert cur.fetchone() == (0,)
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
    assert facts.load_embeddings("m/doc1") is None and facts.current_commit() is None
    facts.enable()
    assert facts.current_commit() is not None or facts.replace_index(snap("e" * 40, "x"), lambda _s: True) is IndexOutcome.REPLACED
    facts.close()


def tool_snap(commit: str, *tools: tuple[str, str, str | None]) -> IndexSnapshot:
    from harness_catalog_core.model import ToolEntry

    entries = tuple(ToolEntry(n, f"{n} tool 자막" if n == "subs-fetch" else f"{n} tool", kind, server, {"requires-tools": "uv"}, ("u" + n).ljust(40, "0")[:40], commit) for n, kind, server in tools)
    return IndexSnapshot((), commit, datetime.now(UTC), datetime.now(UTC), tools=entries)


def test_tool_index_contract_and_search(database_url: str) -> None:
    """toolbox(D19): tool_index의 열·생성식·제약·인덱스가 설계의 DDL 문자열과 같고, 두 표가 한 트랜잭션에 바뀐다."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'tool_index' ORDER BY ordinal_position")
        assert [r[0] for r in cur.fetchall()] == ["name", "description", "kind", "server", "metadata", "tree_sha", "commit_sha", "indexed_at", "embedding", "embedding_generation"]
        cur.execute("SELECT a.attname, pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum WHERE a.attrelid = 'tool_index'::regclass AND a.attgenerated = 's' ORDER BY a.attnum")
        assert dict(cur.fetchall()) == {}  # 0005 뒤 생성 열은 없다
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'tool_index' ORDER BY 1")
        assert [r[0] for r in cur.fetchall()] == ["tool_index_pkey"]
        cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'tool_index'::regclass AND contype = 'c'")
        defs = [r[0] for r in cur.fetchall()]
        assert any("'script'" in d and "'mcp'" in d for d in defs) and any("length(description) <= 1024" in d for d in defs)
    facts = PgFactStore(database_url)
    facts.open()
    facts.enable()
    c = "c" * 40
    assert facts.replace_index(tool_snap(c, ("subs-fetch", "script", None), ("graft-ask", "mcp", "graft")), lambda _s: True) is IndexOutcome.REPLACED
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT name, kind, server FROM tool_index ORDER BY name")
        assert cur.fetchall() == [("graft-ask", "mcp", "graft"), ("subs-fetch", "script", None)]
    facts.close()


def test_replace_is_all_or_nothing_across_both_tables(database_url: str) -> None:
    """도구 행 하나가 제약을 어기면 스킬 표·도구 표·index_state 전부 이전 세대로 남는다."""
    facts = PgFactStore(database_url)
    facts.open()
    facts.enable()
    good, bad = "1" * 40, "2" * 40
    assert facts.replace_index(snap(good, "yt-subs"), lambda _s: True) is IndexOutcome.REPLACED
    broken = tool_snap(bad, ("bad-kind", "http", None))  # CHECK (kind IN ('script','mcp')) 위반
    assert facts.replace_index(broken, lambda _s: True) is IndexOutcome.UNAVAILABLE
    assert facts.current_commit() == good
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM skill_index")
        assert cur.fetchall() == [("yt-subs",)]
        cur.execute("SELECT count(*) FROM tool_index")
        assert cur.fetchone() == (0,)
    facts.close()


def test_upgrade_from_0001_on_populated_db() -> None:
    """0001만 적용된 채 데이터가 있는 DB에 0002~0005가 올라가고, 다시 migrate는 0이다."""
    from importlib.resources import as_file, files

    from yoyo import get_backend, read_migrations  # pyright: ignore[reportUnknownVariableType]

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        url = pg.get_connection_url()
        with as_file(files("harness_catalog_server") / "migrations") as path:
            migrations = read_migrations(str(path))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        backend = get_backend(yoyo_url(url))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        with backend.lock():  # pyright: ignore[reportUnknownMemberType]
            first = migrations.filter(lambda m: m.id.startswith("0001"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownLambdaType]
            backend.apply_migrations(backend.to_apply(first))  # pyright: ignore[reportUnknownMemberType]
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO skill_index (name, description, metadata, tree_sha, commit_sha, indexed_at) VALUES ('old', 'd', '{}', %s, %s, now())", ("a" * 40, "b" * 40))
            cur.execute("INSERT INTO index_state (id, commit_sha, indexed_at) VALUES (1, %s, now())", ("b" * 40,))
            conn.commit()
        assert migrate(url) == 4  # 0002~0005
        assert migrate(url) == 0
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM skill_index")
            assert cur.fetchall() == [("old",)]
            cur.execute("SELECT count(*) FROM tool_index")
            assert cur.fetchone() == (0,)


def test_tool_index_ddl_equals_design_contract() -> None:
    """0002_toolbox.sql의 문장은 DESIGN 그림 3 아래 계약 블록의 tool_index 부분과 공백·주석을 빼고 같다(D19 수용 조건)."""
    import re
    from importlib.resources import as_file, files

    def statements(text: str) -> list[str]:
        body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
        # ast-grep-ignore: regex-on-structure — 어휘: 공백 연속을 한 칸으로 접는 정규 언어(구조 해석 아님)
        return [re.sub(r"\s+", " ", s).strip() for s in body.split(";") if s.strip()]

    design = Path(__file__).resolve().parents[2].joinpath("DESIGN.md").read_text()
    start = design.index("CREATE TABLE tool_index")
    end = design.index("CREATE INDEX tool_index_trgm", start)
    end = design.index(";", end) + 1
    with as_file(files("harness_catalog_server") / "migrations" / "0002_toolbox.sql") as path:
        migration = path.read_text()
    assert statements(design[start:end]) == statements(migration)
