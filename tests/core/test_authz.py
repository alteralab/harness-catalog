from __future__ import annotations

import pytest

from harness_catalog_core.authz import READ_TOOLS, authorize, principal_from_claims
from harness_catalog_core.model import ErrorCode, PrincipalKind

SERVICE = frozenset({"ci-runner"})


@pytest.mark.parametrize("tool", sorted(READ_TOOLS))
def test_matrix(tool: str) -> None:
    reader = principal_from_claims({"sub": "u1", "groups": ["skills-readers"], "aud": "claude-code"}, SERVICE)
    outsider = principal_from_claims({"sub": "u2", "aud": "claude-code"}, SERVICE)
    service = principal_from_claims({"sub": "ci-runner", "aud": "ci-runner"}, SERVICE)
    assert authorize(reader, tool).allowed
    assert authorize(service, tool).allowed and service.kind is PrincipalKind.SERVICE
    d = authorize(outsider, tool)
    assert not d.allowed and d.code is ErrorCode.NOT_A_MEMBER


def test_unknown_tool_and_claims_shape() -> None:
    p = principal_from_claims({"sub": "u", "groups": "not-a-list", "scope": "a b", "aud": ["x", "y"], "azp": "x"}, SERVICE)
    assert p.groups == frozenset() and p.scopes == {"a", "b"} and p.client_id == "x"
    assert not authorize(p, "delete_skill").allowed
