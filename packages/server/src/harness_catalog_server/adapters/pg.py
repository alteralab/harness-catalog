"""PostgreSQL 어댑터: 인덱스 교체 트랜잭션(세대 검사, 두 표)과 어휘 검색. psycopg 3 + 풀, ORM 없음. 브레이커·시간 초과 포함."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Final

import psycopg
from psycopg import sql
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from harness_catalog_core.model import IndexOutcome, IndexSnapshot

log = logging.getLogger(__name__)

STATEMENT_TIMEOUT_MS: Final = 5000
BREAKER_FAILURES: Final = 3
BREAKER_OPEN_SECONDS: Final = 30.0

INSERT_SKILL = """
INSERT INTO skill_index (name, description, compatibility, metadata, tree_sha, commit_sha, indexed_at)
VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
"""
INSERT_TOOL = """
INSERT INTO tool_index (name, description, kind, server, metadata, tree_sha, commit_sha, indexed_at)
VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
"""
# 표 이름은 닫힌 사전에서만 고른다 — 외부 입력이 SQL에 들어가지 않는다
TABLES: Final[dict[str, str]] = {"skills": "skill_index", "tools": "tool_index"}
SEARCH = """
SELECT name
FROM {table}
WHERE search @@ plainto_tsquery('simple', %(q)s)
   OR search_text %% %(q)s
   OR search_text ILIKE %(like)s
ORDER BY ts_rank(search, plainto_tsquery('simple', %(q)s)) DESC, similarity(search_text, %(q)s) DESC, name
LIMIT %(n)s
"""


class Breaker:
    """상태 기계 셋: CLOSED → (연속 실패 N) OPEN → (T초 뒤) HALF_OPEN(시험 요청 하나만) → 성공이면 CLOSED, 실패면 다시 OPEN.
    여러 스레드가 부르므로 잠금 하나로 지킨다. 시계는 주입한다.
    """

    def __init__(self, failures: int = BREAKER_FAILURES, open_seconds: float = BREAKER_OPEN_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = failures
        self._open_seconds = open_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._count = 0
        self._open_until = 0.0
        self._probing = False

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._clock() < self._open_until

    def allow(self) -> bool:
        """이 요청을 DB로 보내도 되는가. 열림이 끝난 뒤의 첫 요청 하나만 시험으로 통과한다."""
        with self._lock:
            if self._clock() < self._open_until:
                return False
            if self._open_until > 0.0:  # 열렸던 상태가 방금 끝났다 → half-open
                if self._probing:
                    return False
                self._probing = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._count = 0
            self._open_until = 0.0
            self._probing = False

    def record_failure(self) -> None:
        with self._lock:
            self._count += 1
            self._probing = False
            if self._count >= self._limit or self._open_until > 0.0:
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
        self._enabled = False  # 마이그레이션이 끝나기 전에는 DB 경로를 열지 않는다(db_unavailable로 동작)

    def open(self) -> None:
        self._pool.open(wait=False)

    def enable(self) -> None:
        """마이그레이션이 적용된 뒤 호출한다. 그 전의 호출은 전부 UNAVAILABLE/None."""
        self._enabled = True

    def _gate(self) -> bool:
        return self._enabled and self._breaker.allow()

    def close(self) -> None:
        self._pool.close()

    @property
    def breaker(self) -> Breaker:
        return self._breaker

    def current_commit(self) -> str | None:
        """index_state의 커밋. DB가 닿지 않으면 None."""
        if not self._gate():
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
        """트랜잭션 하나: advisory lock → index_state FOR UPDATE → 새 커밋이 저장된 커밋의 자손일 때만
        DELETE skill_index → DELETE tool_index → 두 INSERT → index_state upsert. 어느 삽입이 실패해도 전부 롤백된다(D19)."""
        if not self._gate():
            return IndexOutcome.UNAVAILABLE
        try:
            with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
                # 최초 구축에는 잠글 행이 없다 — 트랜잭션 범위 advisory lock으로 교체 전체를 직렬화한다
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('harness_catalog.index_replace'))")
                cur.execute("SELECT commit_sha FROM index_state WHERE id = 1 FOR UPDATE")
                row = cur.fetchone()
                stored = str(row[0]) if row else None
                if stored is not None and stored != snapshot.commit_sha and not is_descendant(stored):
                    return IndexOutcome.STALE
                cur.execute("DELETE FROM skill_index")
                cur.execute("DELETE FROM tool_index")
                for e in snapshot.entries:
                    cur.execute(INSERT_SKILL, (e.name, e.description, e.compatibility, Jsonb(dict(e.metadata)), e.tree_sha, e.commit_sha, snapshot.built_at))
                for t in snapshot.tools:
                    cur.execute(INSERT_TOOL, (t.name, t.description, t.kind, t.server, Jsonb(dict(t.metadata)), t.tree_sha, t.commit_sha, snapshot.built_at))
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

    def search(self, query: str, limit: int, /, kind: str = "skills") -> tuple[str, ...] | None:
        table = TABLES.get(kind)
        if table is None or not self._gate():
            return None
        like = "%" + "%".join(t for t in query.split() if t) + "%" if query.strip() else "%"
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute(sql.SQL(SEARCH).format(table=sql.Identifier(table)), {"q": query, "like": like, "n": limit})
                rows = cur.fetchall()
        except (psycopg.Error, PoolTimeout) as e:
            self._breaker.record_failure()
            log.warning("search failed: %s", e)
            return None
        self._breaker.record_success()
        return tuple(str(r[0]) for r in rows)
