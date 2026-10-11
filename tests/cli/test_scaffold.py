"""write-skill의 scripts/scaffold.py — 결정적 뼈대 스크립트. 템플릿 패키지 데이터라 모듈이 아니므로 파일을 그대로 실행한다."""

import subprocess
import sys
import tomllib
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / "packages/cli/src/harness_catalog_cli/templates/skills"
SCAFFOLD = SKILLS / "write-skill/scripts/scaffold.py"


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
        for f in ("task.toml", "instruction.md", "environment/Dockerfile", "tests/test.sh", "tests/test_outputs.py", "solution/solve.sh"):
            assert (d / "evals" / case / f).is_file(), f"{case}/{f}"
        cfg = tomllib.loads((d / "evals" / case / "task.toml").read_text())
        assert cfg["schema_version"] == "1.4" and cfg["environment"]["skills_dir"] == "/skills"
        assert cfg["verifier"]["environment_mode"] == "shared"  # 검증기가 에이전트 컨테이너의 끝 상태를 본다 — 묵시 기본값에 기대지 않는다
    assert len(created) == 14
    second = run(tmp_path, "demo-skill", "--description", "x", "--positive", "runs-demo", "--negative", "explain", "--script", "demo.py")
    assert second.returncode == 0 and second.stdout == ""  # 있는 파일은 건드리지 않는다
    assert (d / "SKILL.md").read_text().startswith("---\nname: demo-skill\ndescription: 데모.")


def test_rejects_bad_name_and_missing_description(tmp_path: Path) -> None:
    assert run(tmp_path, "Bad_Name", "--description", "x").returncode == 2
    assert run(tmp_path, "ok-name").returncode == 2
    assert not (tmp_path / "skills").exists()


def _scaffold_constants() -> dict[str, str]:
    """스크립트 소스를 실행해 템플릿 상수를 읽는다(__main__ 가드가 있어 부작용 없음). import 경로를 쓰지 않는 이유: 패키지 데이터 안에 __pycache__가 생기면 init이 .pyc를 텍스트로 읽는다(실측)."""
    ns: dict[str, object] = {"__name__": "scaffold_constants"}
    exec(compile(SCAFFOLD.read_text(), str(SCAFFOLD), "exec"), ns)  # noqa: S102 — 저장소 안의 고정 파일, 입력 없음
    return {"head": str(ns["DOCKERFILE_HEAD"]), "test_sh": str(ns["TEST_SH"])}


def test_shipped_base_evals_match_scaffold() -> None:
    """실린 기본 스킬 셋의 evals는 write-skill scaffold.py가 만드는 것과 같은 Dockerfile 머리·test.sh·공유 검증기 선언을 가진다 — 문면은 한 곳(scaffold.py)이 소유한다."""
    k = _scaffold_constants()
    cases = sorted(SKILLS.glob("*/evals/*"))
    assert len(cases) == 6
    for case in cases:
        dockerfile = (case / "environment/Dockerfile").read_text()
        assert dockerfile.startswith(k["head"]), f"{case}: Dockerfile 머리가 scaffold.py DOCKERFILE_HEAD와 다르다"
        assert (case / "tests/test.sh").read_text() == k["test_sh"], f"{case}: test.sh가 scaffold.py TEST_SH와 다르다"
        cfg = tomllib.loads((case / "task.toml").read_text())
        assert cfg["verifier"]["environment_mode"] == "shared" and cfg["environment"]["skills_dir"] == "/skills", case
