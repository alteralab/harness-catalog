"""진입점: serve(uvicorn 기동). 출력 층."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn
from harness_catalog_core.settings import Settings
from pydantic import ValidationError

from .adapters.pg import PgFactStore
from .bootstrap import bootstrap, make_catalog
from .migrate import migrate
from .telemetry import configure_tracing

DEFAULT_WORKDIR = "/var/lib/harness-catalog"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="harness-catalog-server")
    sub = p.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="MCP 서버 + 스케줄러를 띄운다")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workdir", type=Path, default=Path(DEFAULT_WORKDIR))
    serve.add_argument("--log-level", default="info")
    reindex = sub.add_parser("reindex", help="main을 받아 인덱스를 다시 짓는다(운영 명령). 되감기를 받아들인 뒤에는 서빙 중인 레지스트리를 재기동해 메모리 사본도 새 main으로 바꾼다")
    reindex.add_argument("--accept-rewind", action="store_true", help="main 되감기를 받아들여 세대 검사를 건너뛴다")
    reindex.add_argument("--workdir", type=Path, default=Path(DEFAULT_WORKDIR))
    reindex.add_argument("--log-level", default="info")
    a = p.parse_args(argv)
    logging.basicConfig(level=a.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as e:
        print(f"settings invalid:\n{e}", file=sys.stderr)
        return 2
    if a.command == "reindex":
        migrate(settings.database_url.get_secret_value())
        catalog, facts, store = make_catalog(settings, a.workdir)
        try:
            if isinstance(facts, PgFactStore):
                facts.open()
                facts.enable()
            status = catalog.rebuild(accept_rewind=a.accept_rewind)
        finally:
            if isinstance(facts, PgFactStore):
                facts.close()
            store.close()
        print(f"ready={status.ready} commit={status.commit_sha} reasons={[str(r) for r in status.reasons]} degraded={list(status.degraded)} rejected={list(status.rejected)}")
        return 0 if status.ready and "main_rewound" not in status.degraded else 1
    configure_tracing()   # OTEL_EXPORTER_OTLP_ENDPOINT가 있을 때만 스팬이 나간다
    app = bootstrap(settings, a.workdir)
    uvicorn.run(app.asgi, host=a.host, port=a.port, log_level=a.log_level)
    return 0


if __name__ == "__main__":
    sys.exit(main())
