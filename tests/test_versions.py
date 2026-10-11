"""배포물 넷의 판과 패키지 간 의존 핀이 같은가 — 태그에서 pip로 설치하는 경로(카탈로그 pre-commit·CI)는 uv 워크스페이스가 아니라 이 핀을 따른다(실측: v0.3.0에서 cli가 core==0.2.0을 요구해 설치 실패)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "packages"
PACKAGES = ("core", "cli", "server", "harbor-langfuse")


def test_versions_and_internal_pins_agree() -> None:
    versions = {name: tomllib.loads((ROOT / name / "pyproject.toml").read_text())["project"]["version"] for name in PACKAGES}
    assert len(set(versions.values())) == 1, versions
    version = versions["core"]
    for name in PACKAGES:
        for dep in tomllib.loads((ROOT / name / "pyproject.toml").read_text())["project"].get("dependencies", []):
            # ast-grep-ignore: regex-on-structure — 어휘: 'harness-catalog-<x>==<판>' 고정 형식
            m = re.match(r"harness-catalog-[a-z-]+==(.+)$", dep)
            if m:
                assert m.group(1) == version, f"{name} pins {dep} but packages are {version}"
