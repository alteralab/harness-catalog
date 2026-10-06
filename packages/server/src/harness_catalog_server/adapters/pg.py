"""PostgreSQL 어댑터: 인덱스 교체 트랜잭션(세대 검사)과 어휘 검색. psycopg 3 + 풀, ORM 없음. 브레이커·시간 초과 포함."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Final

import psycopg
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from harness_catalog_core.model import IndexOutcome, IndexSnapshot

log = logging.getLogger(__name__)

STATEMENT_TIMEOUT_MS: Final = 5000
BREAKER_FAILURES: Final = 3
BREAKER_OPEN_SECONDS: Final = 30.0

INSERT_ROW = """
INSERT INTO skill_index (name, description, compatibility, metadata, tree_sha, commit_sha, indexed_at)
VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
"""
SEARCH = """
SELECT name
FROM skill_index
WHERE search @@ plainto_tsquery('simple', %(q)s)
   OR search_text %% %(q)s
   OR search_text ILIKE %(like)s
ORDER BY ts_rank(search, plainto_tsquery('simple', %(q)s)) DESC, similarity(search_text, %(q)s) DESC, name
LIMIT %(n)s
"""


class Breaker:
    """순수 상태 기계: 연속 실패 N회면 T초 동안 열린다. 시계는 주입한다."""

    def __init__(self, failures: int = BREAKER_FAILURES, open_seconds: float = BREAKER_OPEN_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = failures
        self._open_seconds = open_seconds
        self._clock = clock
        self._count = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        return self._clock() < self._open_until

    def record_success(self) -> None:
        self._count = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._count += 1
        if self._count >= self._limit:
            self._open_until = self._clock() + self._open_seconds
            self._count = 0


class PgFactStore:
    """FactStore 구현. 호출마다 풀에서 연결 하나, 문장 시간 초과 5초."""

    def __init__(self, conninfo: str, *, min_size: int = 1, max_size: int = 4, breaker: Breaker | None = None) -> None:
        self._pool = ConnectionPool(
            conninfo, min_size=min_size, max_size=max_size, open=False, timeout=5.0,
            kwargs={"options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}", "row_factory": tuple_row},
        )
        self._breaker = breaker or Breaker()

    def open(self) -> None:
        self._pool.open(wait=False)

    def close(self) -> None:
        self._pool.close()

    @property
    def breaker(self) -> Breaker:
        return self._breaker

    def current_commit(self) -> str | None:
        """index_state의 커밋. DB가 닿지 않으면 None."""
        if self._breaker.is_open:
            return None
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT commit_sha FROM index_state WHERE id = 1")
                row = cur.fetchone()
        except (psycopg.Error, PoolTimeout) as e:
            self._breaker.record_failure()
            log.warning("index_state read failed: %s", e)
            return None
        self._breaker.record_success()
        return str(row[0]) if row else None

    def replace_index(self, snapshot: IndexSnapshot, is_descendant: Callable[[str], bool], /) -> IndexOutcome:
        """트랜잭션 하나: index_state를 FOR UPDATE로 잠그고, 새 커밋이 저장된 커밋의 자손일 때만 DELETE+INSERT."""
        if self._breaker.is_open:
            return IndexOutcome.UNAVAILABLE
        try:
            with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
                cur.execute("SELECT commit_sha FROM index_state WHERE id = 1 FOR UPDATE")
                row = cur.fetchone()
                stored = str(row[0]) if row else None
                if stored is not None and stored != snapshot.commit_sha and not is_descendant(stored):
                    return IndexOutcome.STALE
                cur.execute("DELETE FROM skill_index")
                for e in snapshot.entries:
                    cur.execute(INSERT_ROW, (e.name, e.description, e.compatibility, Jsonb(dict(e.metadata)), e.tree_sha, e.commit_sha, snapshot.built_at))
                cur.execute(
                    "INSERT INTO index_state (id, commit_sha, indexed_at) VALUES (1, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET commit_sha = EXCLUDED.commit_sha, indexed_at = EXCLUDED.indexed_at",
                    (snapshot.commit_sha, snapshot.built_at),
                )
        except (psycopg.Error, PoolTimeout) as e:
            self._breaker.record_failure()
            log.warning("index replace failed: %s", e)
            return IndexOutcome.UNAVAILABLE
        self._breaker.record_success()
        return IndexOutcome.REPLACED

    def search(self, query: str, limit: int, /) -> tuple[str, ...] | None:
        if self._breaker.is_open:
            return None
        like = "%" + "%".join(t for t in query.split() if t) + "%" if query.strip() else "%"
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute(SEARCH, {"q": query, "like": like, "n": limit})
                rows = cur.fetchall()
        except (psycopg.Error, PoolTimeout) as e:
            self._breaker.record_failure()
            log.warning("search failed: %s", e)
            return None
        self._breaker.record_success()
        return tuple(str(r[0]) for r in rows)
