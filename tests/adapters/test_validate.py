from __future__ import annotations

from pathlib import Path

import pytest

from harness_catalog_core.adapters.validate import SkillsRefValidator
from harness_catalog_core.model import ValidatorFailure
from tests.conftest import write_skill


def test_inspect_pass_and_fail(tmp_path: Path) -> None:
    write_skill(tmp_path, "good-skill", "A good skill.", metadata={"requires-tools": "uv"})
    v = SkillsRefValidator(gitleaks="/nonexistent/gitleaks")
    r = v.inspect(tmp_path / "skills" / "good-skill")
    assert r.errors == () and r.properties is not None
    assert r.properties.name == "good-skill" and r.properties.metadata == {"requires-tools": "uv"}
    bad = tmp_path / "skills" / "Bad_Name"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: Bad_Name\ndescription: x\n---\n")
    r2 = v.inspect(bad)
    assert r2.errors and r2.properties is None


def test_secret_scan_fails_closed_without_binary(tmp_path: Path) -> None:
    v = SkillsRefValidator(gitleaks="/nonexistent/gitleaks")
    with pytest.raises(ValidatorFailure):
        v.scan_secrets(tmp_path)
