"""명령 harness-catalog: check · init · config · ci. 출력 층(T201 면제)."""

from __future__ import annotations

import json

import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import typer

from harness_catalog_core.toolbox import tool_json_schema

from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.adapters.validate import SkillsRefValidator
from harness_catalog_core.check import check_commit
from harness_catalog_core.model import ContentError

from . import ci as ci_logic
from .config import effective_values, merge_docs, render_docs, render_env_example
from .gitleaks import GitleaksUnavailable, ensure_gitleaks
from .init import CODE_REPO_URL, InitError, init_repository

app = typer.Typer(add_completion=False, help="harness-catalog: 카탈로그 저장소의 검사와 초기화")
config_app = typer.Typer(help="설정값: 실효값 보기, 참조 문서 생성")
app.add_typer(config_app, name="config")
ci_app = typer.Typer(help="CI에서 부르는 것: 기준 커밋·검사·evals. 워크플로 YAML은 이것만 부른다")
app.add_typer(ci_app, name="ci")


def _version(flag: bool) -> None:
    if flag:
        print(version("harness-catalog-cli"))
        raise typer.Exit()


@app.callback()
def _root(_: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="판을 찍는다")) -> None:
    pass


def _run_check(repo_root: Path, base: str | None, rev: str) -> int:
    """종료 코드: 0 통과 / 1 위반 / 2 검사기 실패. 출력은 항목 번호와 사유."""
    with tempfile.TemporaryDirectory(prefix="hc-check.") as tmp:
        work = Path(tmp)
        store = GitStore.local(repo_root.resolve())
        try:
            head = store.resolve(rev)
        except ContentError as e:
            print(f"cannot read {repo_root}: {e.detail}", file=sys.stderr)
            return 2
        try:
            gitleaks = ensure_gitleaks()
        except GitleaksUnavailable as e:
            print(f"checker failed: {e}", file=sys.stderr)
            return 2
        report = check_commit(store, SkillsRefValidator(gitleaks=gitleaks), head, base=base, workdir=work)
    if report.checker_failed:
        print(f"checker failed: {report.checker_failed}", file=sys.stderr)
        return 2
    for f in report.findings:
        kind = "warning" if f.warning else "error"
        where = (f.skill if f.kind == "skill" else f"{f.kind} {f.skill}") if f.skill else "(repository)"
        print(f"{kind}: item {f.item}: {where}: {f.reason}")
    return 1 if report.errors else 0


@app.command()
def check(
    repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소(작업 트리)"),
    base: str | None = typer.Option(None, "--base", help="변화를 볼 기준 커밋(항목 5·9)"),
    rev: str = typer.Option("INDEX", "--rev", help="검사할 트리: INDEX(스테이징, pre-commit용)·HEAD·커밋"),
) -> None:
    """저장소 구조와 스킬마다의 규칙을 판정한다. 종료 0 통과 / 1 위반 / 2 검사기 실패. gitleaks는 PATH에 없으면 핀된 판을 체크섬 검증해 캐시에 받는다."""
    raise typer.Exit(_run_check(repo_root, base, rev))


def _base_or_exit(repo: Path) -> str:
    try:
        return ci_logic.base_commit(os.environ, ci_logic.git_runner(repo))
    except ci_logic.CIError as e:
        print(f"ci: {e}", file=sys.stderr)
        raise typer.Exit(2)


@ci_app.command("base")
def ci_base(repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소")) -> None:
    """호스트 환경(GitHub Actions·GitLab CI)에서 기준 커밋을 정해 찍는다: PR/MR은 merge-base, push는 push 전 커밋(브랜치 생성이면 루트), 로컬은 HEAD~1. 정할 수 없으면 2."""
    print(_base_or_exit(repo_root.resolve()))


@ci_app.command("check")
def ci_check(repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소")) -> None:
    """`check --rev HEAD --base <ci base>`. 워크플로의 check 잡이 부르는 한 줄."""
    repo = repo_root.resolve()
    base = _base_or_exit(repo)
    if ci_logic.is_branch_creation(base, ci_logic.git_runner(repo)):
        print("base: branch creation — no prior history, items 5/9 skipped", file=sys.stderr)
        raise typer.Exit(_run_check(repo_root, None, "HEAD"))
    print(f"base {base[:12]}", file=sys.stderr)
    raise typer.Exit(_run_check(repo_root, base, "HEAD"))


@ci_app.command("evals")
def ci_evals(
    agent: str = typer.Option(..., "--agent", help="Harbor 에이전트 이름(claude-code·codex·cursor-cli·gemini-cli)"),
    repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소"),
    dry_run: bool = typer.Option(False, "--dry-run", help="돌리지 않고 harbor 명령만 찍는다"),
) -> None:
    """기준 커밋 이후 바뀐 스킬마다 evals를 스킬 있이·없이 두 번 돌려 Langfuse에 남긴다. 자격이 없으면 1, 기준·diff를 못 구하면 2, 바뀐 스킬이 없으면 아무것도 하지 않는다."""
    env = dict(os.environ)
    for problem in (ci_logic.missing_credentials(agent, env), ci_logic.missing_langfuse(env)):
        if problem:
            print(problem, file=sys.stderr)
            raise typer.Exit(1)
    repo = repo_root.resolve()
    run = ci_logic.git_runner(repo)
    try:
        base = ci_logic.base_commit(env, run)
        dirs = ci_logic.changed_skill_dirs(run, base)
    except ci_logic.CIError as e:
        print(f"ci: {e}", file=sys.stderr)
        raise typer.Exit(2)
    plan = ci_logic.evals_plan(repo, dirs, agent, cli_version=version("harness-catalog-cli"), code_repo_url=CODE_REPO_URL)
    print(f"base {base[:12]}; changed skills: {' '.join(dirs) or '(none)'}; harbor jobs: {len(plan)}")
    if not plan:
        return
    if dry_run:
        for argv in plan:
            print("$ " + " ".join(argv))
        return
    failed = ci_logic.run_plan(plan, repo, ci_logic.harbor_env(env, run, repo))
    if failed:
        print(f"{failed} harbor job(s) failed", file=sys.stderr)
        raise typer.Exit(1)


@app.command()
def init(
    repo_url: str = typer.Argument(..., help="빈(또는 이미 있는) 카탈로그 저장소의 URL. 운영자의 git 자격으로 clone·push한다"),
    pin: str | None = typer.Option(None, "--pin", help="템플릿에 박을 코드 저장소 ref(개발용). 없으면 cli 자기 판의 태그이고 그 태그가 있어야 한다"),
    host: str | None = typer.Option(None, "--host", help="github | gitlab. 없으면 URL에서 판별한다"),
) -> None:
    """표지·skills/(기본 스킬 셋)·schemas/tool.schema.json·README·pre-commit·호스트별 CI를 없는 것만 써서 커밋·push한다. 두 번 돌리면 변경 0."""
    try:
        result = init_repository(repo_url, pin=pin, host=host)
    except InitError as e:
        print(f"init stopped: {e}", file=sys.stderr)
        raise typer.Exit(1)
    if result.written:
        print(f"wrote {len(result.written)} file(s) ({result.host}, pin {result.pin}): " + ", ".join(result.written))
    else:
        print("nothing to do — repository already initialized")


@config_app.command("list")
def config_list() -> None:
    """설정값마다 실효값과 출처(env·file·default·missing)."""
    for v in effective_values():
        print(f"{v.name:32} {v.source:8} {v.value}")


@config_app.command("docs")
def config_docs(out_dir: Path = typer.Option(Path("docs"), "--out-dir", help="configuration.md를 쓸 디렉토리")) -> None:
    """docs/configuration.md를 설정 정의에서 생성하고 .env.example용 절을 표준 출력에 낸다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "configuration.md"
    target.write_text(merge_docs(target.read_text() if target.exists() else None, render_docs()))
    print(render_env_example(), end="")


@app.command()
def schema(kind: str = typer.Argument("tool", help="tool — tool.json의 JSON Schema(core ToolSpec에서 생성)")) -> None:
    """카탈로그 레코드의 JSON Schema를 표준 출력에 찍는다. 저자가 `schemas/tool.schema.json`을 다시 쓸 때: `harness-catalog schema tool > schemas/tool.schema.json`."""
    if kind != "tool":
        print(f"unknown schema kind {kind!r} (tool only — server.json follows the MCP Registry schema at its own $schema URL)", file=sys.stderr)
        raise typer.Exit(2)
    print(json.dumps(tool_json_schema(), ensure_ascii=False, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
