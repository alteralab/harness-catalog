"""스케줄러 어댑터: 기동 1회 + fetch 주기. 실패는 지수 백오프(상한 10 주기)."""

from __future__ import annotations

import logging

import anyio

from harness_catalog_core.catalog import Catalog

log = logging.getLogger(__name__)


async def run_scheduler(catalog: Catalog, interval_seconds: int, stop: anyio.Event) -> None:
    backoff = 1
    while not stop.is_set():
        status = await anyio.to_thread.run_sync(catalog.rebuild)
        if status.reasons:
            log.warning("rebuild not ready: %s", [str(r) for r in status.reasons])
            backoff = min(backoff * 2, 10)
        else:
            backoff = 1
            if status.degraded or status.rejected:
                log.warning("rebuild degraded=%s rejected=%s", status.degraded, status.rejected)
        with anyio.move_on_after(interval_seconds * backoff):
            await stop.wait()
