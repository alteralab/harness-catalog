"""진입점: serve(uvicorn 기동). 출력 층."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn
from pydantic import ValidationError

from harness_catalog_core.settings import Settings

from .bootstrap import bootstrap

DEFAULT_WORKDIR = "/var/lib/harness-catalog"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="harness-catalog-server")
    sub = p.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="MCP 서버 + 스케줄러를 띄운다")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workdir", type=Path, default=Path(DEFAULT_WORKDIR))
    serve.add_argument("--log-level", default="info")
    a = p.parse_args(argv)
    logging.basicConfig(level=a.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as e:
        print(f"settings invalid:\n{e}", file=sys.stderr)
        return 2
    app = bootstrap(settings, a.workdir)
    uvicorn.run(app.asgi, host=a.host, port=a.port, log_level=a.log_level)
    return 0


if __name__ == "__main__":
    sys.exit(main())
