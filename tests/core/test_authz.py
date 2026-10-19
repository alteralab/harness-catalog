from __future__ import annotations

import pytest
from harness_catalog_core.authz import READ_TOOLS, authorize, principal_from_claims
from harness_catalog_core.model import ErrorCode


@pytest.mark.parametrize("tool", sorted(READ_TOOLS))
def test_matrix(tool: str) -> None:
    reader = principal_from_claims({"sub": "u1", "groups": ["users", "harness-readers"], "aud": "claude-code"})
    machine = principal_from_claims({"sub": "svc", "groups": ["harness-readers"], "aud": "ci-runner"})  # 기계 계정도 그룹으로 reader
    outsider = principal_from_claims({"sub": "u2", "groups": ["users"], "aud": "claude-code"})
    assert authorize(reader, tool).allowed and authorize(machine, tool).allowed
    d = authorize(outsider, tool)
    assert not d.allowed and d.code is ErrorCode.NOT_A_MEMBER


def test_unknown_tool_and_claims_shape() -> None:
    p = principal_from_claims({"sub": "u", "groups": "not-a-list", "aud": ["x", "y"], "azp": "x"})
    assert p.groups == frozenset() and p.client_id == "x"
    assert not authorize(p, "delete_skill").allowed
