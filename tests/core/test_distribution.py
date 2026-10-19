"""코드 저장소 주소의 정본이 하나인가 — 설치된 메타데이터가 core 의 pyproject 한 줄과 같고, 스키마 `$id`가 거기서 조립된다(§11 2026-10-20)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from harness_catalog_core import distribution
from harness_catalog_core.distribution import DistributionMetadataError, code_repo_url
from harness_catalog_core.toolbox import tool_json_schema, tool_schema_id

CORE_PYPROJECT = Path(__file__).resolve().parents[2] / "packages" / "core" / "pyproject.toml"


def test_repo_url_comes_from_core_pyproject() -> None:
    declared = tomllib.loads(CORE_PYPROJECT.read_text())["project"]["urls"]["Repository"]
    assert code_repo_url() == declared.rstrip("/")
    assert tool_schema_id() == f"{declared.rstrip('/')}/schemas/tool.schema.json"
    assert tool_json_schema()["$id"] == tool_schema_id()


def test_missing_metadata_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """읽을 수 없으면 조용한 기본값이 아니라 예외다 — 틀린 주소는 템플릿의 핀과 스키마 `$id`로 퍼진다."""
    monkeypatch.setattr(distribution, "DISTRIBUTION", "harness-catalog-not-installed")
    with pytest.raises(DistributionMetadataError, match="not installed"):
        code_repo_url()
    monkeypatch.setattr(distribution, "REPOSITORY_LABEL", "NoSuchLabel")
    monkeypatch.setattr(distribution, "DISTRIBUTION", "harness-catalog-core")
    with pytest.raises(DistributionMetadataError, match="NoSuchLabel"):
        code_repo_url()
