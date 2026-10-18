"""`uv run python -m bench.search --n 100 1000 5000` — 현재 검색(tsvector + trgm)의 기준선. 결과는 표로 찍고 bench/search/results/ 에 JSON 으로 남긴다.

Postgres 는 testcontainers 로 띄운다(TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock 가 필요할 수 있다, docs/development.md). DATABASE_URL 을 주면 그 DB 를 쓴다(표는 비운다).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from bench.search.bench import HEADER, Result, evaluate
from bench.search.corpus import make_items, make_queries, snapshot
from bench.search.engines import lexical_or
from harness_catalog_server.adapters.pg import PgFactStore
from harness_catalog_server.migrate import migrate


def run_one(url: str, n: int, *, vague: bool) -> dict[str, Result]:
    """같은 색인 위에서 엔진마다 한 번씩."""
    facts = PgFactStore(url)
    facts.open()
    facts.enable()
    items = make_items(n)
    facts.replace_index(snapshot(items, vague=vague, commit=("v" if vague else "g") + str(n).ljust(39, "0")[:39]), lambda _s: True)
    queries = make_queries(items)
    try:
        return {"current": evaluate(facts.search, items, queries), "lexical-or": evaluate(lexical_or(url), items, queries)}
    finally:
        facts.close()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[100, 1000])
    ap.add_argument("--out", type=Path, default=Path("bench/search/results"))
    ns = ap.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    rows: list[tuple[str, Result]] = []

    def go(u: str) -> None:
        for n in ns.n:
            for vague in (False, True):
                for engine, r in run_one(u, n, vague=vague).items():
                    rows.append((f"{engine} · {'막연한' if vague else '좋은'} description", r))

    if url:
        migrate(url)
        go(url)
    else:
        from testcontainers.community.postgres import PostgresContainer

        with PostgresContainer("postgres:17-alpine", driver=None) as pg:
            u = pg.get_connection_url()
            migrate(u)
            go(u)
    print(HEADER)
    for label, r in rows:
        print(r.row(label))
    print()
    for label, r in rows:
        print(f"{label} (n={r.n_items}) by style: " + ", ".join(f"{s} R@3={v[3]:.2f}" for s, v in sorted(r.by_style.items())))
    ns.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    (ns.out / f"{stamp}.json").write_text(json.dumps([{"label": label, **r.__dict__} for label, r in rows], ensure_ascii=False, indent=2, default=str))
    print(f"\nwritten {ns.out / (stamp + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
