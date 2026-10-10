"""아카이브 라우트: GET /mcp/archive/<name>/<tree>.tar — bearer가 아니라 헤더 토큰(ArchiveSigner)이 자격이다.

검증 순서(웹훅 서명 규정): 형식 → 만료 창 → 상수 시간 비교. 셋 중 어느 실패도 빈 403 하나(존재 여부·이유를 새기지 않는다).
그 뒤에만 앱을 부른다 — 없는 판은 404, 상한 초과는 413. 본문은 작업 디렉토리의 캐시 tar(FileResponse: Content-Length 정확, 메모리 상주 없음).
URL에는 이름과 tree만 있어 uvicorn·프록시 접근 로그에 자격이 찍히지 않는다(RFC 9110 §17.9, DESIGN §11 2026-10-11).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import anyio
from opentelemetry import trace
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from harness_catalog_core.archive_token import TOKEN_HEADER, ArchiveSigner
from harness_catalog_core.catalog import Catalog
from harness_catalog_core.model import CatalogError, ErrorCode

ARCHIVE_PATH = "/mcp/archive/{name}/{tree}.tar"
MEDIA_TYPE = "application/x-tar"
_STATUS = {ErrorCode.NOT_FOUND: 404, ErrorCode.UNKNOWN_VERSION: 404, ErrorCode.INPUT_LIMIT: 413}


def make_archive_route(catalog: Catalog, signer: ArchiveSigner) -> Callable[[Request], Awaitable[Response]]:
    async def archive(request: Request) -> Response:
        name = str(request.path_params.get("name", ""))
        tree = str(request.path_params.get("tree", ""))
        if not signer.verify(name, tree, request.headers.get(TOKEN_HEADER)):
            return Response(status_code=403)
        span = trace.get_current_span()
        span.set_attributes({"harness.archive.skill": name, "harness.archive.sha": tree})
        try:
            info = await anyio.to_thread.run_sync(catalog.get_skill_archive, name, tree)
        except CatalogError as e:
            status = _STATUS.get(e.code)
            if status is None:
                raise  # 예상 밖 코드는 조용히 404가 되지 않고 500으로 드러난다
            return Response(status_code=status)
        return FileResponse(
            info.path,
            media_type=MEDIA_TYPE,
            filename=f"{name}-{tree[:12]}.tar",
            headers={"Cache-Control": "private, no-store", "X-Harness-Archive-Sha256": info.sha256},
        )

    return archive
