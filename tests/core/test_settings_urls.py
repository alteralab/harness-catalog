"""settings: issuer·공개 URL의 끝 슬래시는 기동 전에 거부한다(Dex와 레지스트리가 같은 문자열을 봐야 한다)."""

from __future__ import annotations

import pytest
from harness_catalog_core.settings import Settings
from pydantic import ValidationError

BASE = {"catalog_repo_url": "file:///tmp/x.git", "git_deploy_key": "", "database_url": "postgresql://u:p@h/db"}


def test_accepts_canonical_urls() -> None:
    s = Settings(oidc_issuer="https://host/dex", public_url="https://host/mcp", **BASE)  # pyright: ignore[reportArgumentType]
    assert str(s.oidc_issuer) == "https://host/dex"
    assert str(s.public_url) == "https://host/mcp"


@pytest.mark.parametrize("field", ["oidc_issuer", "public_url"])
def test_rejects_trailing_slash(field: str) -> None:
    kwargs = {"oidc_issuer": "https://host/dex", "public_url": "https://host/mcp", **BASE}
    kwargs[field] = kwargs[field] + "/"
    with pytest.raises(ValidationError, match="must not end with '/'"):
        Settings(**kwargs)  # pyright: ignore[reportArgumentType]
