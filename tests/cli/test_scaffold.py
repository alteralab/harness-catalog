"""write-skill의 scripts/scaffold.py — 결정적 뼈대 스크립트. 템플릿 패키지 데이터라 모듈이 아니므로 파일을 그대로 실행한다."""

import subprocess
import sys
import tomllib
from pathlib import Path

SCAFFOLD = Path(__file__).resolve().parents[2] / "packages/cli/src/harness_catalog_cli/templates/skills/write-skill/scripts/scaffold.py"


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCAFFOLD), *args], cwd=cwd, capture_output=True, text=True, check=False)


def test_creates_skill_and_eval_pair_then_is_idempotent(tmp_path: Path) -> None:
    first = run(tmp_path, "demo-skill", "--description", "데모. '데모 돌려줘'.", "--positive", "runs-demo", "--negative", "explain", "--script", "demo.py")
    assert first.returncode == 0, first.stderr
    created = first.stdout.split()
    d = tmp_path / "skills" / "demo-skill"
    assert (d / "SKILL.md").read_text().startswith("---\nname: demo-skill\ndescription: 데모.")
    assert (d / "scripts" / "demo.py").read_text().startswith("# /// script")
    for case in ("runs-demo", "no-trigger-explain"):  # 음성 이름에 no-trigger- 접두가 붙는다
        for f in ("task.toml", "instruction.md", "environment/Dockerfile", "tests/test.sh", "solution/solve.sh"):
            assert (d / "evals" / case / f).is_file(), f"{case}/{f}"
        cfg = tomllib.loads((d / "evals" / case / "task.toml").read_text())
        assert cfg["schema_version"] == "1.4" and cfg["environment"]["skills_dir"] == "/skills"
    assert len(created) == 12
    second = run(tmp_path, "demo-skill", "--description", "x", "--positive", "runs-demo", "--negative", "explain", "--script", "demo.py")
    assert second.returncode == 0 and second.stdout == ""  # 있는 파일은 건드리지 않는다
    assert (d / "SKILL.md").read_text().startswith("---\nname: demo-skill\ndescription: 데모.")


def test_rejects_bad_name_and_missing_description(tmp_path: Path) -> None:
    assert run(tmp_path, "Bad_Name", "--description", "x").returncode == 2
    assert run(tmp_path, "ok-name").returncode == 2
    assert not (tmp_path / "skills").exists()
