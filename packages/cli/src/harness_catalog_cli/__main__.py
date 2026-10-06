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

app = typer.Typer(add_completion=False, help="harness-catalog: 카탈로그 저장소의 검사와 초기화")


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
