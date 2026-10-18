"""검사 일곱(항목 1·2·3·4·7·11·12). 같은 함수를 인덱스 빌드(server)와 CLI(cli)가 부른다. 판정만 하고 출력은 호출자가 한다.

항목 1~7은 스킬, 11은 도구(`tools/<name>/tool.json`), 12는 MCP 서버 레코드(`mcp-servers/<name>/server.json`)다(DESIGN §5, §11 2026-10-11 toolbox).
공통 규칙(시크릿 4·크기 7)은 도구에도 같은 번호로 적용한다. 이름은 스킬·도구를 합쳐 전역 유일이다.
번호 5·6·8·9·10은 비어 있다 — 은퇴 이름 재사용 금지·replaced-by·requires-tools·복사 드리프트는 §11 2026-10-18에서 뺐고(의존성은 스크립트 안에만, 은퇴는 삭제뿐),
그래서 검사는 기준 커밋이 필요 없고 얕은 클론에서도 돈다.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from .catalog_file import MARKER_PATH, MarkerError, parse_marker
from .model import ROOT_MARKERS, SUPPORTED_LAYOUT, ContentError, Root, SkillTree, ToolEntry, TreeEntry, ValidatorFailure
from .ports import ContentStore, SkillValidator
from .toolbox import NAME_RE, SERVER_FILE, TOOL_FILE, McpRuntime, ScriptRuntime, parse_server, parse_tool

MAX_FILES = 50
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
CI_WORKFLOW_HINTS = (".github/workflows/", ".gitlab-ci.yml")
STRUCTURE_ITEM: dict[Root, int] = {"skills": 2, "tools": 11, "mcp-servers": 12}


class Finding(NamedTuple):
    item: int
    skill: str  # 레코드 이름(스킬·도구·서버). 저장소 수준이면 ""
    reason: str
    warning: bool = False  # True면 종료 코드에 안 걸린다(항목 9·10)
    kind: str = "skill"  # 레코드 종류: skill | tool | server | repo


class CheckReport(NamedTuple):
    findings: tuple[Finding, ...]
    checker_failed: str  # 비면 검사기 정상. 아니면 사유(fail-closed, 종료 코드 2)

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if not f.warning)

    def rejected_skills(self) -> frozenset[str]:
        return frozenset(f.skill for f in self.errors if f.skill and f.kind == "skill")

    def rejected_tools(self) -> frozenset[str]:
        return frozenset(f.skill for f in self.errors if f.skill and f.kind == "tool")

    def rejected_servers(self) -> frozenset[str]:
        return frozenset(f.skill for f in self.errors if f.skill and f.kind == "server")


def _marker_findings(store: ContentStore, commit: str) -> list[Finding]:
    """항목 1의 표지: 있고, TOML이고, layout이 지원하는 값이다."""
    marker = store.read_blob(commit, MARKER_PATH)
    if marker is None:
        return [Finding(1, "", f"{MARKER_PATH} missing", kind="repo")]
    try:
        layout = parse_marker(marker.decode("utf-8", errors="replace")).layout
    except MarkerError as e:
        return [Finding(1, "", f"{MARKER_PATH}: {e}", kind="repo")]
    if layout != SUPPORTED_LAYOUT:
        return [Finding(1, "", f"layout {layout} unsupported (expected {SUPPORTED_LAYOUT})", kind="repo")]
    return []


def _required_files_findings(paths: set[str]) -> list[Finding]:
    """항목 1의 파일들: skills/, CI 워크플로, pre-commit 설정, README."""
    required: list[tuple[bool, str]] = [
        (any(p == "skills" or p.startswith("skills/") for p in paths), "skills/ missing"),
        (any(p.startswith(CI_WORKFLOW_HINTS[0]) or p == CI_WORKFLOW_HINTS[1] for p in paths), "CI workflow missing (.github/workflows/ or .gitlab-ci.yml)"),
        (".pre-commit-config.yaml" in paths, ".pre-commit-config.yaml missing"),
        ("README.md" in paths, "README.md missing"),
    ]
    return [Finding(1, "", reason, kind="repo") for present, reason in required if not present]


def _entries_findings(top: tuple[TreeEntry, ...], paths: set[str], root: Root) -> list[Finding]:
    """항목 2(skills)·11(tools)·12(mcp-servers)의 구조: `<root>/` 바로 아래는 디렉토리(와 .gitkeep)뿐이고 각 디렉토리에 표지 파일이 있다."""
    item, marker = STRUCTURE_ITEM[root], ROOT_MARKERS[root]
    record_kind = {"skills": "skill", "tools": "tool", "mcp-servers": "server"}[root]
    out: list[Finding] = []
    for e in top:
        if not e.path.startswith(f"{root}/") or e.path.count("/") != 1:
            continue
        if e.kind == "tree":
            if f"{e.path}/{marker}" not in paths:
                out.append(Finding(item, e.path.removeprefix(f"{root}/"), f"{e.path}/{marker} missing", kind=record_kind))
        elif e.path != f"{root}/.gitkeep":
            out.append(Finding(item, "", f"{e.path}: only directories (and .gitkeep) allowed directly under {root}/", kind="repo"))
    return out


def _structure_findings(store: ContentStore, commit: str, top: tuple[TreeEntry, ...]) -> list[Finding]:
    """항목 1·2 + 11·12의 구조 부분(`tools/`·`mcp-servers/`는 선택 — 있을 때만)."""
    paths = {e.path for e in top}
    out = _marker_findings(store, commit) + _required_files_findings(paths) + _entries_findings(top, paths, "skills")
    for root in ("tools", "mcp-servers"):
        if any(p == root or p.startswith(f"{root}/") for p in paths):
            out.extend(_entries_findings(top, paths, root))
    return out


def structure_findings(store: ContentStore, commit: str) -> list[Finding]:
    """구조 항목만(기동 검사와 CLI가 같이 쓴다)."""
    return _structure_findings(store, commit, store.list_tree(commit))


def _size_findings(name: str, files: Iterable[TreeEntry], kind: str = "skill") -> list[Finding]:
    """항목 7: 파일 수·파일 크기·합계·심볼릭 링크."""
    out: list[Finding] = []
    blobs = [f for f in files if f.kind != "tree"]
    if len(blobs) > MAX_FILES:
        out.append(Finding(7, name, f"{len(blobs)} files > {MAX_FILES}", kind=kind))
    total = 0
    for f in blobs:
        if f.kind == "link":
            out.append(Finding(7, name, f"{f.path}: symbolic link", kind=kind))
        if f.size > MAX_FILE_BYTES:
            out.append(Finding(7, name, f"{f.path}: {f.size} bytes > {MAX_FILE_BYTES}", kind=kind))
        total += f.size
    if total > MAX_TOTAL_BYTES:
        out.append(Finding(7, name, f"total {total} bytes > {MAX_TOTAL_BYTES}", kind=kind))
    return out


class SkillInspection(NamedTuple):
    name: str
    findings: tuple[Finding, ...]


def _export(store: ContentStore, tree: SkillTree, workdir: Path, prefix: str) -> tempfile.TemporaryDirectory[str]:
    tmp = tempfile.TemporaryDirectory(dir=workdir, prefix=prefix)
    dest = Path(tmp.name) / tree.name  # 스펙 검증기가 디렉토리명 = name을 본다
    dest.mkdir()
    store.export_tree(tree.tree_sha, dest)
    return tmp


def _bad_dir_name(tree: SkillTree, item: int, kind: str) -> Finding | None:
    """디렉토리 이름이 카탈로그 이름 문법이 아니면 내보내기(파일 시스템 경로 결합) 전에 그 항목만 거부한다(Codex 코드 리뷰 2026-10-11)."""
    if NAME_RE.match(tree.name):
        return None
    return Finding(item, tree.name, f"directory name {tree.name!r} is not a catalog name (1-64 chars of [a-z0-9-])", kind=kind)


def inspect_skill(store: ContentStore, validator: SkillValidator, tree: SkillTree, workdir: Path) -> SkillInspection:
    """항목 3·4·7을 스킬 하나에 적용한다."""
    files = store.list_tree(tree.tree_sha)
    findings = _size_findings(tree.name, files)
    if (bad := _bad_dir_name(tree, 3, "skill")) is not None:
        return SkillInspection(tree.name, (*findings, bad))
    with _export(store, tree, workdir, "check.") as tmp:
        dest = Path(tmp) / tree.name
        report = validator.inspect(dest)
        findings.extend(Finding(3, tree.name, m) for m in report.errors)
        if report.properties is not None and report.properties.name != tree.name:
            findings.append(Finding(3, tree.name, f"name {report.properties.name!r} != directory"))
        findings.extend(Finding(4, tree.name, m) for m in validator.scan_secrets(dest))
    return SkillInspection(tree.name, tuple(findings))


class ToolInspection(NamedTuple):
    name: str
    findings: tuple[Finding, ...]
    entry: ToolEntry | None  # 위반이 없을 때만


def inspect_tool(store: ContentStore, validator: SkillValidator, tree: SkillTree, workdir: Path, *, servers: frozenset[str], skills: frozenset[str]) -> ToolInspection:
    """항목 11(tool.json의 모양·이름·경로·참조 서버·스킬과의 이름 충돌)과 공통 4·7을 도구 하나에 적용한다."""
    files = store.list_tree(tree.tree_sha)
    findings = _size_findings(tree.name, files, kind="tool")
    entry: ToolEntry | None = None
    if (bad := _bad_dir_name(tree, 11, "tool")) is not None:
        return ToolInspection(tree.name, (*findings, bad), None)
    raw = store.read_blob(tree.tree_sha, TOOL_FILE)
    spec, errors = parse_tool(raw) if raw is not None else (None, [f"{TOOL_FILE} missing"])
    findings.extend(Finding(11, tree.name, m, kind="tool") for m in errors)
    if tree.name in skills:
        findings.append(Finding(11, tree.name, "name also exists as a skill — names are unique across skills and tools", kind="tool"))
    if spec is not None:
        if spec.name != tree.name:
            findings.append(Finding(11, tree.name, f"name {spec.name!r} != directory", kind="tool"))
        if isinstance(spec.runtime, ScriptRuntime):
            blob = next((f for f in files if f.path == spec.runtime.path), None)
            if blob is None or blob.kind != "blob":
                findings.append(Finding(11, tree.name, f"runtime.path {spec.runtime.path!r} is not a regular file in this version", kind="tool"))
        elif spec.runtime.server not in servers:
            findings.append(Finding(11, tree.name, f"runtime.server {spec.runtime.server!r} not found under mcp-servers/ (or rejected by item 12)", kind="tool"))
    with _export(store, tree, workdir, "check-tool.") as tmp:
        findings.extend(Finding(4, tree.name, m, kind="tool") for m in validator.scan_secrets(Path(tmp) / tree.name))
    if spec is not None and not any(not f.warning for f in findings):
        server = spec.runtime.server if isinstance(spec.runtime, McpRuntime) else None
        entry = ToolEntry(tree.name, spec.description, spec.runtime.kind, server, spec.metadata, tree.tree_sha, tree.commit_sha)
    return ToolInspection(tree.name, tuple(findings), entry)


def inspect_server(store: ContentStore, validator: SkillValidator, tree: SkillTree, workdir: Path) -> tuple[Finding, ...]:
    """항목 12(server.json의 모양·이름·packages|remotes·시크릿 리터럴)와 공통 4·7을 서버 레코드 하나에 적용한다."""
    files = store.list_tree(tree.tree_sha)
    findings = _size_findings(tree.name, files, kind="server")
    if (bad := _bad_dir_name(tree, 12, "server")) is not None:
        return (*findings, bad)
    raw = store.read_blob(tree.tree_sha, SERVER_FILE)
    _, errors = parse_server(raw, tree.name) if raw is not None else (None, [f"{SERVER_FILE} missing"])
    findings.extend(Finding(12, tree.name, m, kind="server") for m in errors)
    with _export(store, tree, workdir, "check-server.") as tmp:
        findings.extend(Finding(4, tree.name, m, kind="server") for m in validator.scan_secrets(Path(tmp) / tree.name))
    return tuple(findings)


def _present(store: ContentStore, commit: str, root: Root, top_paths: set[str]) -> tuple[SkillTree, ...]:
    return tuple(t for t in store.list_trees(commit, root) if f"{root}/{t.name}/{ROOT_MARKERS[root]}" in top_paths)


def check_commit(store: ContentStore, validator: SkillValidator, commit: str, *, workdir: Path) -> CheckReport:
    """저장소 구조 + 스킬·도구·서버마다. 커밋(또는 스테이징 트리) 하나만 보고 이력은 보지 않는다(§11 2026-10-18)."""
    try:
        top = store.list_tree(commit)
        top_paths = {e.path for e in top}
        findings = _structure_findings(store, commit, top)
        trees = _present(store, commit, "skills", top_paths)
        tool_trees = _present(store, commit, "tools", top_paths)
        server_trees = _present(store, commit, "mcp-servers", top_paths)
        server_findings: list[Finding] = []
        for tree in server_trees:
            server_findings.extend(inspect_server(store, validator, tree, workdir))
        findings.extend(server_findings)
        rejected_servers = {f.skill for f in server_findings if not f.warning}
        servers = frozenset(t.name for t in server_trees if t.name not in rejected_servers)  # 검사 12를 통과한 서버만 참조 대상(Codex 코드 리뷰)
        skill_names = frozenset(t.name for t in trees)
        for tree in trees:
            findings.extend(inspect_skill(store, validator, tree, workdir).findings)
        for tree in tool_trees:
            findings.extend(inspect_tool(store, validator, tree, workdir, servers=servers, skills=skill_names).findings)
    except ValidatorFailure as e:
        return CheckReport((), f"validator failed: {e}")
    except ContentError as e:
        return CheckReport((), f"repository read failed: {e.detail}")
    return CheckReport(tuple(findings), "")
