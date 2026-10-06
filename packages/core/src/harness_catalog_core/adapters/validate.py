"""검증 어댑터: skills_ref.validate + gitleaks 서브프로세스 → 판정. 검사기 실패는 ValidatorFailure(fail-closed)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from skills_ref import ParseError, read_properties, validate

from ..model import SkillProps, SkillReport, ValidatorFailure


class SkillsRefValidator:
    """SkillValidator 구현."""

    def __init__(self, gitleaks: str | None = None) -> None:
        self._gitleaks = gitleaks or shutil.which("gitleaks")

    def inspect(self, skill_dir: Path) -> SkillReport:
        try:
            errors = tuple(validate(skill_dir))
            if errors:
                return SkillReport(errors, None)
            p = read_properties(skill_dir)
        except ParseError as e:
            return SkillReport((str(e),), None)
        except OSError as e:
            raise ValidatorFailure(f"cannot read {skill_dir}: {e}") from e
        return SkillReport((), SkillProps(p.name, p.description, p.compatibility, dict(p.metadata or {})))

    def scan_secrets(self, skill_dir: Path) -> tuple[str, ...]:
        if self._gitleaks is None:
            raise ValidatorFailure("gitleaks binary not found")
        with tempfile.NamedTemporaryFile(suffix=".json") as report:
            try:
                proc = subprocess.run(
                    [self._gitleaks, "dir", str(skill_dir), "--no-banner", "--exit-code", "2", "--report-format", "json", "--report-path", report.name],
                    capture_output=True, check=False, timeout=300,
                )
            except (OSError, subprocess.TimeoutExpired) as e:
                raise ValidatorFailure(f"gitleaks could not run: {e}") from e
            if proc.returncode == 0:
                return ()
            if proc.returncode != 2:
                raise ValidatorFailure(f"gitleaks exited {proc.returncode}: {proc.stderr.decode(errors='replace')[:300]}")
            try:
                findings = json.loads(Path(report.name).read_text() or "[]")
            except ValueError as e:
                raise ValidatorFailure(f"gitleaks report unreadable: {e}") from e
        return tuple(f"{f.get('File', '?')}: {f.get('RuleID', '?')}" for f in findings)
