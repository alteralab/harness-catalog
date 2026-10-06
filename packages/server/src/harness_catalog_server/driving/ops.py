"""운영 어댑터: /healthz(살아 있음)와 /readyz(준비됨 + degraded 사유)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from harness_catalog_core.catalog import Catalog


def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def make_readyz(catalog: Catalog):  # noqa: ANN201
    async def readyz(_: Request) -> JSONResponse:
        s = catalog.status()
        body = {
            "ready": s.ready,
            "reasons": [str(r) for r in s.reasons],
            "degraded": list(s.degraded),
            "commit": s.commit_sha,
            "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
            "built_at": s.built_at.isoformat() if s.built_at else None,
            "rejected": [{"skill": n, "reason": r} for n, r in s.rejected],
        }
        return JSONResponse(body, status_code=200 if s.ready else 503)

    return readyz
