"""명령 harness-catalog: check. 출력 층(T201 면제)."""

from __future__ import annotations

import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import typer

from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.adapters.validate import SkillsRefValidator
from harness_catalog_core.check import check_commit
from harness_catalog_core.model import ContentError

from .config import effective_values, merge_docs, render_docs, render_env_example
from .init import InitError, init_repository

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


@app.command()
def check(
    repo_root: Path = typer.Argument(Path("."), help="카탈로그 저장소(작업 트리)"),
    base: str | None = typer.Option(None, "--base", help="변화를 볼 기준 커밋(항목 5·9)"),
    rev: str = typer.Option("INDEX", "--rev", help="검사할 트리: INDEX(스테이징, pre-commit용)·HEAD·커밋"),
) -> None:
    """저장소 구조와 스킬마다의 규칙을 판정한다. 종료 0 통과 / 1 위반 / 2 검사기 실패."""
    with tempfile.TemporaryDirectory(prefix="hc-check.") as tmp:
        work = Path(tmp)
        store = GitStore.local(repo_root.resolve())
        try:
            head = store.resolve(rev)
        except ContentError as e:
            print(f"cannot read {repo_root}: {e.detail}", file=sys.stderr)
            raise typer.Exit(2)
        report = check_commit(store, SkillsRefValidator(), head, base=base, workdir=work)
    if report.checker_failed:
        print(f"checker failed: {report.checker_failed}", file=sys.stderr)
        raise typer.Exit(2)
    for f in report.findings:
        kind = "warning" if f.warning else "error"
        where = f.skill or "(repository)"
        print(f"{kind}: item {f.item}: {where}: {f.reason}")
    if report.errors:
        raise typer.Exit(1)


@app.command()
def init(
    repo_url: str = typer.Argument(..., help="빈(또는 이미 있는) 카탈로그 저장소의 URL. 운영자의 git 자격으로 clone·push한다"),
    pin: str | None = typer.Option(None, "--pin", help="템플릿에 박을 코드 저장소 ref(개발용). 없으면 cli 자기 판의 태그이고 그 태그가 있어야 한다"),
    host: str | None = typer.Option(None, "--host", help="github | gitlab. 없으면 URL에서 판별한다"),
) -> None:
    """표지·skills/·README·pre-commit·호스트별 CI를 없는 것만 써서 커밋·push한다. 두 번 돌리면 변경 0."""
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
