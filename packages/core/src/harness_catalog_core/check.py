"""검사 열(항목 1~10). 같은 함수를 인덱스 빌드(server)와 CLI(cli)가 부른다. 판정만 하고 출력은 호출자가 한다."""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from .catalog_file import MARKER_PATH, MarkerError, parse_marker
from .model import SUPPORTED_LAYOUT, SkillTree, TreeEntry, ValidatorFailure
from .ports import ContentStore, SkillValidator

MAX_FILES = 50
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
TOOL_TOKEN_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._+-")
CI_WORKFLOW_HINTS = (".github/workflows/", ".gitlab-ci.yml")


class Finding(NamedTuple):
    item: int
    skill: str  # 저장소 수준이면 ""
    reason: str
    warning: bool = False  # True면 종료 코드에 안 걸린다(항목 9·10)


class CheckReport(NamedTuple):
    findings: tuple[Finding, ...]
    checker_failed: str  # 비면 검사기 정상. 아니면 사유(fail-closed, 종료 코드 2)

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if not f.warning)

    def rejected_skills(self) -> frozenset[str]:
        return frozenset(f.skill for f in self.errors if f.skill)


def _structure_findings(store: ContentStore, commit: str, top: tuple[TreeEntry, ...]) -> list[Finding]:
    """항목 1·2: 표지, skills/, CI 워크플로, pre-commit 설정, README."""
    out: list[Finding] = []
    paths = {e.path for e in top}
    marker = store.read_blob(commit, MARKER_PATH)
    if marker is None:
        out.append(Finding(1, "", f"{MARKER_PATH} missing"))
    else:
        try:
            layout = parse_marker(marker.decode("utf-8", errors="replace")).layout
            if layout != SUPPORTED_LAYOUT:
                out.append(Finding(1, "", f"layout {layout} unsupported (expected {SUPPORTED_LAYOUT})"))
        except MarkerError as e:
            out.append(Finding(1, "", f"{MARKER_PATH}: {e}"))
    if not any(p == "skills" or p.startswith("skills/") for p in paths):
        out.append(Finding(1, "", "skills/ missing"))
    if not any(p.startswith(CI_WORKFLOW_HINTS[0]) or p == CI_WORKFLOW_HINTS[1] for p in paths):
        out.append(Finding(1, "", "CI workflow missing (.github/workflows/ or .gitlab-ci.yml)"))
    if ".pre-commit-config.yaml" not in paths:
        out.append(Finding(1, "", ".pre-commit-config.yaml missing"))
    if "README.md" not in paths:
        out.append(Finding(1, "", "README.md missing"))
    for e in top:
        if e.path.startswith("skills/") and e.path.count("/") == 1 and e.kind != "tree" and e.path != "skills/.gitkeep":
            out.append(Finding(2, "", f"{e.path}: only directories (and .gitkeep) allowed directly under skills/"))
    return out


def _skill_files(store: ContentStore, tree: SkillTree) -> tuple[TreeEntry, ...]:
    return store.list_tree(tree.tree_sha)


def _size_findings(name: str, files: Iterable[TreeEntry]) -> list[Finding]:
    """항목 7: 파일 수·파일 크기·합계·심볼릭 링크."""
    out: list[Finding] = []
    blobs = [f for f in files if f.kind != "tree"]
    if len(blobs) > MAX_FILES:
        out.append(Finding(7, name, f"{len(blobs)} files > {MAX_FILES}"))
    total = 0
    for f in blobs:
        if f.kind == "link":
            out.append(Finding(7, name, f"{f.path}: symbolic link"))
        if f.size > MAX_FILE_BYTES:
            out.append(Finding(7, name, f"{f.path}: {f.size} bytes > {MAX_FILE_BYTES}"))
        total += f.size
    if total > MAX_TOTAL_BYTES:
        out.append(Finding(7, name, f"total {total} bytes > {MAX_TOTAL_BYTES}"))
    return out


def requires_tools_findings(name: str, value: str | None) -> list[Finding]:
    """항목 8: metadata.requires-tools 토큰 문법 [a-z0-9._+-]+, 공백 구분."""
    if value is None:
        return []
    bad = [t for t in value.split() if not t or not set(t) <= TOOL_TOKEN_CHARS]
    return [Finding(8, name, f"requires-tools token {t!r} invalid") for t in bad]


def replaced_by_findings(entries: dict[str, str | None]) -> list[Finding]:
    """항목 6: replaced-by 대상이 존재하고 그 대상은 다시 대체되지 않았다(연쇄·순환 금지). 입력: name → replaced-by."""
    out: list[Finding] = []
    for name, target in entries.items():
        if target is None:
            continue
        if target not in entries:
            out.append(Finding(6, name, f"replaced-by {target!r} does not exist"))
        elif entries[target] is not None:
            out.append(Finding(6, name, f"replaced-by {target!r} is itself replaced (chain)"))
    return out


def drift_findings(scripts: dict[str, dict[str, str]]) -> list[Finding]:
    """항목 10: 서로 다른 스킬의 scripts/ 아래 같은 상대 경로가 내용이 다르면 경고. 입력: name → {상대 경로 → blob sha}."""
    out: list[Finding] = []
    seen: dict[str, tuple[str, str]] = {}
    for name in sorted(scripts):
        for rel, sha in sorted(scripts[name].items()):
            if rel in seen and seen[rel][1] != sha:
                out.append(Finding(10, name, f"scripts/{rel} differs from {seen[rel][0]}", warning=True))
            seen.setdefault(rel, (name, sha))
    return out


class SkillInspection(NamedTuple):
    name: str
    findings: tuple[Finding, ...]
    replaced_by: str | None


def inspect_skill(store: ContentStore, validator: SkillValidator, tree: SkillTree, workdir: Path) -> SkillInspection:
    """항목 3·4·7·8을 스킬 하나에 적용한다."""
    files = _skill_files(store, tree)
    findings = _size_findings(tree.name, files)
    replaced_by: str | None = None
    with tempfile.TemporaryDirectory(dir=workdir, prefix="check.") as tmp:
        dest = Path(tmp) / tree.name  # 스펙 검증기가 디렉토리명 = name을 본다
        dest.mkdir()
        store.export_tree(tree.tree_sha, dest)
        report = validator.inspect(dest)
        findings.extend(Finding(3, tree.name, m) for m in report.errors)
        if report.properties is not None:
            if report.properties.name != tree.name:
                findings.append(Finding(3, tree.name, f"name {report.properties.name!r} != directory"))
            findings.extend(requires_tools_findings(tree.name, report.properties.metadata.get("requires-tools")))
            replaced_by = report.properties.metadata.get("replaced-by") or None
        findings.extend(Finding(4, tree.name, m) for m in validator.scan_secrets(dest))
    return SkillInspection(tree.name, tuple(findings), replaced_by)


def check_commit(store: ContentStore, validator: SkillValidator, commit: str, *, base: str | None, workdir: Path) -> CheckReport:
    """저장소 구조 + 스킬마다 + 스킬 쌍. base는 항목 5·9의 기준 커밋(없으면 둘을 건너뛴다)."""
    try:
        top = store.list_tree(commit)
        findings = _structure_findings(store, commit, top)
        trees = store.list_skill_trees(commit)
        replaced: dict[str, str | None] = {}
        scripts: dict[str, dict[str, str]] = {}
        for tree in trees:
            ins = inspect_skill(store, validator, tree, workdir)
            findings.extend(ins.findings)
            replaced[tree.name] = ins.replaced_by
            scripts[tree.name] = {
                e.path.removeprefix("scripts/"): e.sha for e in store.list_tree(tree.tree_sha) if e.path.startswith("scripts/") and e.kind == "blob"
            }
        findings.extend(replaced_by_findings(replaced))
        findings.extend(drift_findings(scripts))
        if base is not None:
            findings.extend(_history_findings(store, base, trees))
    except ValidatorFailure as e:
        return CheckReport((), f"validator failed: {e}")
    return CheckReport(tuple(findings), "")


def _history_findings(store: ContentStore, base: str, trees: tuple[SkillTree, ...]) -> list[Finding]:
    """항목 5·9: 기준 커밋 대비 새로 생긴 이름의 재사용, 지워진 스킬의 replaced-by 권고."""
    out: list[Finding] = []
    now = {t.name for t in trees}
    before = {t.name for t in store.list_skill_trees(base)}
    retired = store.deleted_skill_names(base)
    for name in sorted(now - before):
        if name in retired:
            out.append(Finding(5, name, "name was retired before (deleted in history) and must not be reused"))
    for name in sorted(before - now):
        blob = store.read_blob(base, f"skills/{name}/SKILL.md") or b""
        if b"replaced-by" not in blob:
            out.append(Finding(9, name, "retired without replaced-by in the base version", warning=True))
    return out
