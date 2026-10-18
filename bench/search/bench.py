"""검색 벤치마크 실행 — 합성 말뭉치를 Postgres 색인에 넣고 질의를 돌려 recall@k·MRR·지연을 잰다.

엔진은 `Engine` 콜러블 하나로 추상화한다: (query, limit, kind) -> 이름 튜플. 지금 것은 `PgFactStore.search`(tsvector + trgm). 하이브리드·리랭커는 같은 자리에 꽂아 같은 숫자로 견준다.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from bench.search.corpus import Item, Query

Engine = Callable[[str, int, str], tuple[str, ...] | None]
KS = (1, 3, 10)


@dataclass(frozen=True)
class Result:
    n_items: int
    n_queries: int
    recall: dict[int, float]
    mrr: float
    p50_ms: float
    p95_ms: float
    by_style: dict[str, dict[int, float]]

    def row(self, label: str) -> str:
        r = " | ".join(f"{self.recall[k]:.3f}" for k in KS)
        return f"| {label} | {self.n_items} | {self.n_queries} | {r} | {self.mrr:.3f} | {self.p50_ms:.1f} | {self.p95_ms:.1f} |"


HEADER = "| 조건 | 항목 | 질의 | R@1 | R@3 | R@10 | MRR | p50 ms | p95 ms |\n|---|---|---|---|---|---|---|---|---|"


def evaluate(engine: Engine, items: Iterable[Item], queries: Iterable[Query], *, limit: int = 10) -> Result:
    items = list(items)
    queries = list(queries)
    hits: dict[int, int] = {k: 0 for k in KS}
    by_style: dict[str, dict[int, list[int]]] = {}
    rr_sum = 0.0
    lat: list[float] = []
    for q in queries:
        kind = "skills" if q.kind == "skill" else "tools"
        t0 = time.perf_counter()
        got = engine(q.text, limit, kind) or ()
        lat.append((time.perf_counter() - t0) * 1000)
        rank = got.index(q.target) + 1 if q.target in got else None
        if rank is not None:
            rr_sum += 1.0 / rank
        for k in KS:
            ok = 1 if rank is not None and rank <= k else 0
            hits[k] += ok
            by_style.setdefault(q.style, {}).setdefault(k, []).append(ok)
    n = len(queries) or 1
    return Result(
        n_items=len(items), n_queries=len(queries),
        recall={k: hits[k] / n for k in KS}, mrr=rr_sum / n,
        p50_ms=statistics.median(lat) if lat else 0.0,
        p95_ms=(sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else 0.0),
        by_style={s: {k: sum(v) / len(v) for k, v in ks.items()} for s, ks in by_style.items()},
    )
