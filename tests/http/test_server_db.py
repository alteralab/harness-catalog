"""실제 PostgreSQL로 서버 프로세스를 띄운다: 0001만 적용된(데이터 있는) DB에서 기동 → run_migrations가 0002를 올리고 → DB가 열리고 → 두 표가 같은 커밋으로 동기 → search_tools가 DB 순위로 답한다(Codex 코드 리뷰 2026-10-11)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from harness_catalog_server.migrate import yoyo_url
from tests.conftest import CatalogRepo, commit_all
from tests.http.fake_issuer import FakeIssuer, start_fake_issuer
from tests.http.test_server import PUBLIC_PATH, call_tool, free_port, result_of

pytestmark = pytest.mark.pg
os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")


def _apply_0001_only(url: str, old_commit: str) -> None:
    from importlib.resources import as_file, files

    from yoyo import get_backend, read_migrations  # pyright: ignore[reportUnknownVariableType]

    with as_file(files("harness_catalog_server") / "migrations") as path:
        migrations = read_migrations(str(path))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    backend = get_backend(yoyo_url(url))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    with backend.lock():  # pyright: ignore[reportUnknownMemberType]
        first = migrations.filter(lambda m: m.id.startswith("0001"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownLambdaType]
        backend.apply_migrations(backend.to_apply(first))  # pyright: ignore[reportUnknownMemberType]
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO skill_index (name, description, metadata, tree_sha, commit_sha, indexed_at) VALUES ('stale', 'old row', '{}', %s, %s, now())", ("a" * 40, "0" * 40))
        cur.execute("INSERT INTO index_state (id, commit_sha, indexed_at) VALUES (1, %s, now())", (old_commit,))  # 실제 조상 커밋 — 세대 검사가 자손으로 본다
        conn.commit()


def test_live_upgrade_then_tool_search_through_db(tmp_path: Path, catalog_repo: CatalogRepo) -> None:
    issuer: FakeIssuer = start_fake_issuer()
    try:
        with PostgresContainer("postgres:17-alpine", driver=None) as pg:
            url = pg.get_connection_url()
            old = catalog_repo.head
            (catalog_repo.path / "README.md").write_text("# catalog (advanced)\n")
            head = commit_all(catalog_repo.path, "advance main past the indexed generation")
            _apply_0001_only(url, old)
            port = free_port()
            public_url = f"http://127.0.0.1:{port}{PUBLIC_PATH}"
            env = {**os.environ, "HC__CATALOG_REPO_URL": str(catalog_repo.path), "HC__GIT_DEPLOY_KEY": "", "HC__OIDC_ISSUER": issuer.issuer,
                   "HC__PUBLIC_URL": public_url, "HC__DATABASE_URL": url, "HC__FETCH_INTERVAL_SECONDS": "1"}
            proc = subprocess.Popen([sys.executable, "-m", "harness_catalog_server", "serve", "--host", "127.0.0.1", "--port", str(port), "--workdir", str(tmp_path / "work"), "--log-level", "warning"], env=env)
            base = f"http://127.0.0.1:{port}"
            try:
                deadline = time.time() + 90
                body: dict[str, object] = {}
                while time.time() < deadline:
                    try:
                        r = httpx.get(base + "/readyz", timeout=1)
                        body = r.json()
                        degraded = body.get("degraded")
                        synced = isinstance(degraded, list) and "db_unavailable" not in degraded
                        if r.status_code == 200 and synced and body.get("commit") == head:
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    time.sleep(0.5)
                else:
                    pytest.fail(f"server did not sync with the database: {body}")
                with psycopg.connect(url) as conn, conn.cursor() as cur:
                    cur.execute("SELECT migration_id FROM _yoyo_migration ORDER BY migration_id")
                    assert [r[0] for r in cur.fetchall()] == ["0001_schema", "0002_toolbox", "0003_drop_replaced_requires"]
                    cur.execute("SELECT commit_sha FROM index_state WHERE id = 1")
                    assert cur.fetchone() == (head,)
                    cur.execute("SELECT name FROM skill_index ORDER BY name")
                    assert [r[0] for r in cur.fetchall()] == ["pin-skill", "yt-subs"]  # 구판 행 'stale'은 지워졌다
                    cur.execute("SELECT name, kind, server FROM tool_index ORDER BY name")
                    assert cur.fetchall() == [("graft-ask", "mcp", "graft"), ("subs-fetch", "script", None)]
                token = issuer.token(sub="user-1", aud=public_url, groups=["harness-readers"])
                hits = result_of(call_tool(base, token, "search_tools", {"query": "자막"}))["structuredContent"]["tools"]
                assert [t["name"] for t in hits] == ["subs-fetch"]
            finally:
                proc.terminate()
                proc.wait(10)
    finally:
        issuer.stop()
