"""명령 harness-catalog(별칭 hc): check · evals · init · toolbox · pin · config. 출력 층(T201 면제)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import cast

import anyio
import typer
from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.adapters.validate import SkillsRefValidator
from harness_catalog_core.check import check_commit
from harness_catalog_core.distribution import code_repo_url
from harness_catalog_core.model import ContentError

from . import ci as ci_logic
from . import pin as pin_logic
from . import toolbox as toolbox_logic
from .config import effective_values, merge_docs, render_docs, render_env_example
from .gitleaks import GitleaksUnavailableError, ensure_gitleaks
from .init import SCHEMA_PATH, InitError, generated_schema, init_repository

app = typer.Typer(add_completion=False, help="harness-catalog: 카탈로그 저장소의 검사와 초기화")
config_app = typer.Typer(help="설정값: 실효값 보기, 참조 문서 생성")
app.add_typer(config_app, name="config")


def _version(flag: bool) -> None:
    if flag:
        print(version("harness-catalog-cli"))
        raise typer.Exit()


@app.callback()
def _root(_: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="판을 찍는다")) -> None:
    pass


def _run_check(repo_root: Path, rev: str) -> int:
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
        except GitleaksUnavailableError as e:
            print(f"checker failed: {e}", file=sys.stderr)
            return 2
        report = check_commit(store, SkillsRefValidator(gitleaks=gitleaks), head, workdir=work)
        stale_schema = _schema_is_stale(store, head)
    if report.checker_failed:
        print(f"checker failed: {report.checker_failed}", file=sys.stderr)
        return 2
    for f in report.findings:
        kind = "warning" if f.warning else "error"
        where = (f.skill if f.kind == "skill" else f"{f.kind} {f.skill}") if f.skill else "(repository)"
        print(f"{kind}: item {f.item}: {where}: {f.reason}")
    if stale_schema:
        print(f"warning: {SCHEMA_PATH} differs from this cli's model — regenerate with `hc init <repo-url> --refresh` (editor validation only; the registry validates tool.json with the model directly)")
    return 1 if report.errors else 0


def _schema_is_stale(store: GitStore, rev: str) -> bool:
    """저장된 편집기용 스키마가 현재 core 모델과 다른가(경고, 종료 코드에 안 걸린다 — Codex 2026-10-18 ⑥)."""
    raw = store.read_blob(rev, SCHEMA_PATH)
    return raw is not None and raw.decode("utf-8", errors="replace") != generated_schema()


@app.command()
def check(
    repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소(작업 트리)"),
    rev: str = typer.Option("INDEX", "--rev", help="검사할 트리: INDEX(스테이징, pre-commit용)·HEAD·커밋"),
) -> None:
    """저장소 구조와 스킬·도구·서버마다의 규칙을 판정한다(검사 일곱). 종료 0 통과 / 1 위반 / 2 검사기 실패. 기준 커밋이 필요 없어 pre-commit·CI·색인이 같은 명령이다. gitleaks는 PATH에 없으면 핀된 판을 체크섬 검증해 캐시에 받는다."""
    raise typer.Exit(_run_check(repo_root, rev))


@app.command()
def evals(
    agent: str = typer.Option("oracle", "--agent", help="oracle(기본, 자격 없이 참조 해답만) 또는 Harbor 에이전트 이름(claude-code·codex·cursor-cli·gemini-cli — 저자가 자기 자격으로)"),
    repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소"),
    dry_run: bool = typer.Option(False, "--dry-run", help="돌리지 않고 harbor 명령만 찍는다"),
) -> None:
    """기준 커밋(GitHub Actions·GitLab CI 환경에서 정한다: PR/MR은 merge-base, push는 push 전 커밋, 로컬은 HEAD~1) 이후 바뀐 스킬의 evals를 돌린다. 기본 oracle은 모델·자격 없이 참조 해답으로 "과제가 풀리고 검증기가 받는가"만 본다(CI가 PR마다). 모델 에이전트를 주면 스킬 있이·없이 두 번 돌려 Langfuse에 남긴다 — 저자가 자기 자격으로(§11 2026-10-18). 자격이 없으면 1, 기준·diff를 못 구하면 2, 바뀐 스킬이 없으면 아무것도 하지 않는다."""
    env = dict(os.environ)
    if agent != ci_logic.ORACLE:
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
    plan = ci_logic.evals_plan(repo, dirs, agent, cli_version=version("harness-catalog-cli"), code_repo_url=code_repo_url())
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
    refresh: bool = typer.Option(False, "--refresh", help="생성 파일(schemas/tool.schema.json)이 이 cli의 모델과 다르면 다시 쓴다. 그 밖은 여전히 없는 것만"),
) -> None:
    """표지·skills/·schemas/tool.schema.json·.mcp.json·README·pre-commit·호스트별 CI를 없는 것만 써서 커밋·push한다. 두 번 돌리면 변경 0. `--refresh`는 생성 스키마를 현재 모델로 맞춘다."""
    try:
        result = init_repository(repo_url, pin=pin, host=host, refresh=refresh)
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
def toolbox(
    directory: Path = typer.Argument(Path("./tools"), help="`<dir>/*/tool.json`을 읽는다. 카탈로그 클론은 ./tools, 세션은 .agents/tools"),
    timeout: float = typer.Option(toolbox_logic.DEFAULT_TIMEOUT, "--timeout", help="도구 호출 하나의 상한(초)"),
) -> None:
    """공구 걸이: 디렉토리의 kind: script 도구를 MCP(stdio) 도구로 노출하고 호출을 셸 없는 서브프로세스로 돌린다. 세션은 pin이, 카탈로그 클론은 init의 .mcp.json이, 루프는 조립기가 이 명령을 mcpServers에 등록한다."""
    async def main() -> int:
        return await toolbox_logic.serve(directory.resolve(), timeout=timeout)

    raise typer.Exit(anyio.run(main))


@app.command()
def pin(
    scope: str = typer.Option(..., "--scope", help="project(저장소의 .agents/) 또는 user(~/.agents/)"),
    response: Path | None = typer.Option(None, "--response", help="get_skill/get_tool(archive=true) 응답(structuredContent) JSON 파일. 없으면 표준 입력"),
    project_root: Path = typer.Option(Path("."), "--project-root", help="project 범위의 뿌리"),
    force: bool = typer.Option(False, "--force", help="같은 이름의 사본이 있으면 .pin-old로 비켜 두고 바꾼다"),
) -> None:
    """내려받기의 결정적 꼬리: 받기 → 크기·sha256 대조 → 풀기 → 파일 목록 대조 → PINNED → 원자적 교체 → 링크(스킬) 또는 .mcp.json의 toolbox 항목(도구). 실패해도 기존 사본은 남는다. 무엇을 어느 범위에 받을지는 pin 스킬이 대화로 정한다."""
    if scope not in ("project", "user"):
        print(f"--scope must be project or user, not {scope!r}", file=sys.stderr)
        raise typer.Exit(2)
    text = response.read_text(encoding="utf-8") if response is not None else sys.stdin.read()
    try:
        data: object = json.loads(text)
    except ValueError as e:
        print(f"response is not JSON: {e}", file=sys.stderr)
        raise typer.Exit(2)
    if not isinstance(data, dict):
        print("response is not a JSON object", file=sys.stderr)
        raise typer.Exit(2)
    try:
        record = pin_logic.parse_response(cast("dict[str, object]", data))
        target = pin_logic.install(record, pin_logic.download(record), scope=scope, project_root=project_root.resolve(), force=force)
    except pin_logic.PinError as e:
        print(f"pin stopped: {e}", file=sys.stderr)
        raise typer.Exit(1)
    print(f"pinned {record.kind} {record.name} {record.sha} → {target} ({len(record.files)} files)")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
