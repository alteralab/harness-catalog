"""문서 사이트의 링크 다시 쓰기 — 저장소에서 맞는 상대 링크를 사이트에서도 맞게 돌린다.

`docs/index.md`·`docs/design.md` 는 루트의 README·DESIGN 을 include 하고, 그 둘은 저장소에서 읽히는 글이라
`DESIGN.md`·`PLAN.md` 같은 저장소 상대 링크를 쓴다. include 플러그인이 그것을 `../DESIGN.md` 로 고쳐 주는데
`docs_dir` 밖이라 MkDocs 가 "target is not found" 경고를 낸다(strict 빌드 실패). `docs/configuration.md` 의
`../.github/runner.env.example` 도 같은 부류다.

원본 README·DESIGN·docs/*.md 는 바꾸지 않는다 — 저장소에서 읽는 사람에게는 지금 링크가 맞다. 사이트용 치환은
이 표 한 곳에만 둔다. 표의 왼쪽이 더 이상 나타나지 않으면 경고를 내므로(strict 에서 실패) 원본이 바뀌면 드러난다.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("mkdocs.hooks.link_fixups")

_BLOB = "https://github.com/alteralab/harness-catalog/blob/main"

# 페이지(docs_dir 기준 경로) → (사이트에서 깨지는 링크, 대신 쓸 링크) 짝들.
_FIXUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "index.md": (
        # DESIGN 은 사이트 페이지로 있다(docs/design.md 가 include 한다).
        ("](../DESIGN.md)", "](design.md)"),
        # PLAN 과 plans/ 는 사이트에 올리지 않는 개발 원장이다 — 저장소로 보낸다.
        ("](../PLAN.md)", f"]({_BLOB}/PLAN.md)"),
    ),
    "configuration.md": (
        ("](../.github/runner.env.example)", f"]({_BLOB}/.github/runner.env.example)"),
    ),
}


def on_page_markdown(markdown: str, *, page: Any, config: Any, files: Any) -> str | None:  # noqa: ARG001
    """include 가 끝난 마크다운에서 저장소 상대 링크를 사이트의 자리로 돌린다."""
    fixups = _FIXUPS.get(str(page.file.src_uri))
    if not fixups:
        return None
    for old, new in fixups:
        if old not in markdown:
            _log.warning("link fixup no longer applies: %s in %s", old, page.file.src_uri)
            continue
        markdown = markdown.replace(old, new)
    return markdown
