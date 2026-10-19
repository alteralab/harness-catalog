"""배포물 메타데이터에서 읽는 것 하나: 코드 저장소 주소.

왜 상수가 아닌가 — 이 주소는 `hc init`이 템플릿에 박는 핀 URL과 도구 스키마의 `$id` 근거이고, 포크는 자기 주소를 써야 한다(§11 2026-10-20).
정본은 `packages/core/pyproject.toml`의 `[project.urls] Repository` 한 줄이고, 코드는 언제나 core 배포물의 메타데이터를 읽는다 —
cli·server도 core에 의존하므로 자리가 하나로 남는다(배포물마다 적으면 정본이 둘이 된다). 포크는 그 한 줄을 고친다; 고치지 않으면 상류 주소가 남는다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, metadata

DISTRIBUTION = "harness-catalog-core"
REPOSITORY_LABEL = "Repository"


class DistributionMetadataError(Exception):
    """메타데이터를 읽을 수 없다. 조용히 기본값으로 떨어지지 않는다 — 틀린 저장소 주소는 템플릿과 스키마 `$id`로 퍼진다."""


def code_repo_url() -> str:
    """코드 저장소 주소(끝 슬래시 없음). `[project.urls] Repository`는 메타데이터에서 `Project-URL: Repository, <url>` 한 줄이다.

    캐시하지 않는다 — 설치된 배포물의 메타데이터를 읽는 것이라 순수 함수가 아니고(C-STATE-1), 부르는 자리는 `hc init`과 스키마 생성 둘뿐이다.
    """
    try:
        meta = metadata(DISTRIBUTION)
    except PackageNotFoundError as e:  # 설치되지 않은 소스 트리에서 직접 import한 경우
        raise DistributionMetadataError(f"distribution {DISTRIBUTION} is not installed — install it (uv sync) so [project.urls] Repository is readable") from e
    entries: list[str] = [str(v) for v in meta.get_all("Project-URL", [])]
    for entry in entries:
        label, _, url = entry.partition(",")
        if label.strip() == REPOSITORY_LABEL and url.strip():
            return url.strip().rstrip("/")
    raise DistributionMetadataError(f"{DISTRIBUTION} metadata has no '{REPOSITORY_LABEL}' project URL — add [project.urls] Repository to packages/core/pyproject.toml and reinstall")
