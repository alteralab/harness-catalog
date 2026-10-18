"""엔진 변형 — 같은 표(skill_index·tool_index) 위에서 SQL 만 다르게. 서버 코드를 바꾸기 전에 여기서 숫자로 견준다.

- current: 서버의 PgFactStore.search 그대로(tsvector AND + trgm similarity + ILIKE).
- lexical-or: 낱말을 OR 로 묶고(한 낱말만 맞아도 후보), 순위는 ts_rank 에 pg_trgm word_similarity(질의가 긴 본문의 일부와 얼마나 닮았나)를 더한다.
  한국어 활용·조사는 여전히 못 잇는다 — 그 한계가 숫자로 보이면 임베딩 변형의 근거가 된다.
"""

from __future__ import annotations

from collections.abc import Callable

import psycopg
from psycopg import sql

TABLES = {"skills": "skill_index", "tools": "tool_index"}

LEXICAL_OR = sql.SQL("""
WITH q AS (SELECT to_tsquery('simple', %(ors)s) AS tsq, %(q)s AS raw)
SELECT name
FROM {table}, q
WHERE search @@ q.tsq OR q.raw <%% search_text OR search_text ILIKE %(like)s
ORDER BY ts_rank(search, q.tsq) + word_similarity(q.raw, search_text) DESC, name
LIMIT %(n)s
""")


def _or_query(text: str) -> str:
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in text).split() if len(w) > 1]
    return " | ".join(words) or "zzzz"


def lexical_or(url: str) -> Callable[[str, int, str], tuple[str, ...] | None]:
    conn = psycopg.connect(url)
    with conn.cursor() as cur:
        cur.execute("SET pg_trgm.word_similarity_threshold = 0.4")
    conn.commit()

    def search(query: str, limit: int, kind: str = "skills") -> tuple[str, ...] | None:
        table = TABLES.get(kind)
        if table is None:
            return None
        with conn.cursor() as cur:
            cur.execute(LEXICAL_OR.format(table=sql.Identifier(table)), {"ors": _or_query(query), "q": query, "like": f"%{query}%", "n": limit})
            return tuple(str(r[0]) for r in cur.fetchall())

    return search
