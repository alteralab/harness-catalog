"""스케줄러 어댑터: 기동 1회 + fetch 주기. 실패는 지수 백오프(상한 10 주기)."""

from __future__ import annotations

import logging

import anyio

from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import Status

from ..migrate import migrate

log = logging.getLogger(__name__)


async def run_migrations(database_url: str, stop: anyio.Event) -> None:
    """기동 직후 마이그레이션. 실패하면 백오프로 재시도한다 — fetch 루프와 독립이라 DB가 늦게 떠도 서빙은 계속된다."""
    delay = 2.0
    while not stop.is_set():
        try:
            await anyio.to_thread.run_sync(migrate, database_url)
            return
        # ast-grep-ignore: handler-swallows-failure — 장기 실행 재시도 루프: 실패는 백오프로 전파되고 DB 없이도 서빙은 계속된다(설계의 실패 표)
        except Exception as e:  # noqa: BLE001 — DB 드라이버·yoyo의 예외 종류를 전부 알 수 없고, 어느 것이든 재시도가 답이다
            log.warning("migration failed, retrying in %.0fs: %s", delay, e)
        with anyio.move_on_after(delay):
            await stop.wait()
        delay = min(delay * 2, 60.0)


MAX_BACKOFF_FACTOR = 16
FAILURE_PREFIXES = ("checker_failed:", "rebuild_failed:", "repo_unreachable")


def next_backoff(current: int, failed: bool) -> int:
    """실패면 2배(상한 16배), 성공이면 1로 되돌린다. 순수 함수 — 시험은 시계 없이 이것을 부른다."""
    return min(current * 2, MAX_BACKOFF_FACTOR) if failed else 1


def rebuild_failed(status: Status) -> bool:
    """fetch 실패(reasons)나 빌드 실패(degraded의 checker_failed·rebuild_failed)를 실패로 센다. 스킬 거부·DB 단절은 아니다."""
    return bool(status.reasons) or any(d.startswith(FAILURE_PREFIXES) for d in status.degraded)


async def run_scheduler(catalog: Catalog, interval_seconds: int, stop: anyio.Event) -> None:
    backoff = 1
    while not stop.is_set():
        try:
            status = await anyio.to_thread.run_sync(catalog.rebuild)
        # ast-grep-ignore: handler-swallows-failure — 장기 실행 루프: 실패는 백오프 배수와 /readyz의 degraded로 전파된다
        except Exception:  # noqa: BLE001 — 장기 실행 루프는 죽지 않는다; 사유는 로그로, 다음 주기에 다시 시도
            log.exception("rebuild raised")
            backoff = next_backoff(backoff, True)
        else:
            backoff = next_backoff(backoff, rebuild_failed(status))
            if status.reasons or status.degraded or status.rejected:
                log.warning("rebuild reasons=%s degraded=%s rejected=%s backoff=x%d", [str(r) for r in status.reasons], status.degraded, status.rejected, backoff)
        with anyio.move_on_after(interval_seconds * backoff):
            await stop.wait()
