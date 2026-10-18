"""`hc pin`: 내려받기의 결정적 꼬리(DESIGN §11 2026-10-18).

입력은 `get_skill(archive=true)` 또는 `get_tool(archive=true)`의 structuredContent 그대로(`id`·`sha`·`files`·`archive`). 판단(무엇을, 어느 범위에)은 세션의 모델이 `pin` 스킬 산문으로 하고,
이 명령은 받기 → 크기·sha256 대조 → 임시 디렉토리에 풀기 → 파일 목록 대조 → PINNED 쓰기 → 원자적 교체 → 심볼릭 링크·설정을 한 번에 한다. 어느 단계에서 실패해도 기존 사본이 남거나 돌아온다.
이름은 카탈로그 name 문법으로 검증해 디렉토리 밖으로 나가지 못하게 하고, 같은 이름의 pin은 flock으로 직렬화하며, 임시·되돌림 디렉토리는 pid로 고유하다(Codex 2026-10-18).
스킬은 `.agents/skills/<name>/` + `.claude/skills/<name>` 링크, 도구는 `.agents/tools/<name>/` + `.mcp.json`의 `toolbox` 항목(어디서나 MCP 하나).
"""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import shutil
import tarfile
import urllib.request
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from harness_catalog_core.toolbox import NAME_RE

PINNED = "PINNED"
SHA_HEX = frozenset("0123456789abcdef")
Scope = Literal["project", "user"]
MCP_CONFIG = ".mcp.json"
TOOLBOX_ENTRY: dict[str, object] = {"command": "hc", "args": ["toolbox", ".agents/tools"]}


class PinError(Exception):
    """멈춰야 하는 사유(종료 1). 기존 사본은 건드리지 않았다."""


@dataclass(frozen=True)
class Record:
    kind: Literal["skill", "tool"]
    name: str
    sha: str
    files: tuple[str, ...]
    uri: str
    headers: Mapping[str, str]
    size: int
    sha256: str


def parse_response(data: Mapping[str, Any]) -> Record:
    """get_skill / get_tool 응답에서 필요한 것만. `tool` 키가 있으면 도구, 아니면 스킬. `archive`가 없으면 archive=true로 다시 부르라고 말한다."""
    kind: Literal["skill", "tool"] = "tool" if "tool" in data else "skill"
    name, sha = str(data.get("id", "")), str(data.get("sha", ""))
    if not NAME_RE.match(name):
        raise PinError(f"response id {name!r} is not a catalog name — it becomes a directory name, so only [a-z0-9-] is accepted (Codex 2026-10-18)")
    if len(sha) != 40 or not set(sha) <= SHA_HEX:
        raise PinError("response lacks a 40-hex sha — pass the structuredContent of get_skill or get_tool as-is")
    archive = data.get("archive")
    if not isinstance(archive, Mapping):
        raise PinError("response has no archive descriptor — call the registry tool again with archive=true")
    a = cast("Mapping[str, Any]", archive)
    raw_files = data.get("files")
    files = tuple(str(cast("Mapping[str, Any]", f)["path"]) for f in cast("list[Any]", raw_files or [])) if isinstance(raw_files, list) else ()
    if not files:
        raise PinError("response lists no files")
    headers_obj = a.get("headers")
    headers = {str(k): str(v) for k, v in cast("Mapping[str, Any]", headers_obj or {}).items()}
    return Record(kind, name, sha, files, str(a["uri"]), headers, int(a["size"]), str(a["sha256"]))


def download(record: Record, *, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(record.uri, headers=dict(record.headers), method="GET")  # noqa: S310 — 레지스트리가 준 https URI
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = resp.read(record.size + 1)
    except OSError as e:
        raise PinError(f"download failed: {e} (the 5-minute token may have expired — fetch a fresh descriptor)") from e
    if len(data) != record.size:
        raise PinError(f"size mismatch: expected {record.size} bytes, got {len(data)}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != record.sha256:
        raise PinError(f"sha256 mismatch: expected {record.sha256}, got {digest}")
    return data


def extract(tar_bytes: bytes, dest: Path) -> tuple[str, ...]:
    """tar를 dest에 푼다. 절대 경로·`..`·링크·디렉토리 밖 경로는 거부한다. 풀린 파일의 상대 경로를 돌려준다."""
    out: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
        for member in tar.getmembers():
            rel = member.name
            parts = rel.split("/")
            if member.islnk() or member.issym() or rel.startswith("/") or any(p in ("", ".", "..") for p in parts):
                raise PinError(f"tar member {rel!r} rejected")
            if member.isdir():
                continue
            if not member.isfile():
                raise PinError(f"tar member {rel!r} is not a regular file")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            if src is None:
                raise PinError(f"tar member {rel!r} unreadable")
            target.write_bytes(src.read())
            out.append(rel)
    return tuple(sorted(out))


def home_for(scope: Scope, project_root: Path) -> Path:
    return (project_root if scope == "project" else Path.home()) / ".agents"


@contextmanager
def _locked(root: Path, name: str) -> Generator[None]:
    """같은 root·name의 pin을 프로세스 간에 직렬화한다(flock). 동시 호출이 서로의 임시·되돌림 디렉토리를 지우지 못하게(Codex 2026-10-18)."""
    lock_path = root / f".{name}.pin-lock"
    with lock_path.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise PinError(f"another pin of {name!r} is in progress ({lock_path})") from e
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _child_of(root: Path, child: Path) -> None:
    if child.resolve().parent != root.resolve():
        raise PinError(f"{child} is not an immediate child of {root}")


def _stage(record: Record, tar_bytes: bytes, tmp: Path, now: datetime | None) -> None:
    """고유 임시 디렉토리에 풀어 대조하고 PINNED를 쓴다. 실패하면 임시 디렉토리를 지우고 예외를 올린다."""
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        got = extract(tar_bytes, tmp)
        if got != tuple(sorted(record.files)):
            raise PinError(f"file list mismatch: archive {list(got)} vs response {sorted(record.files)}")
        stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
        (tmp / PINNED).write_text(f"{record.name} {record.sha} {stamp}\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _swap(tmp: Path, target: Path, old: Path) -> bool:
    """기존을 old로 비켜 두고 tmp를 target으로. 둘째 이름 바꾸기가 실패하면 old를 되돌린다. 기존이 있었는지 돌려준다."""
    had_old = target.exists()
    if had_old:
        shutil.rmtree(old, ignore_errors=True)
        target.rename(old)
    try:
        tmp.rename(target)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        if had_old:
            old.rename(target)
        raise
    return had_old


def _restore(target: Path, old: Path, had_old: bool) -> None:
    shutil.rmtree(target, ignore_errors=True)
    if had_old:
        old.rename(target)


def install(record: Record, tar_bytes: bytes, *, scope: Scope, project_root: Path, now: datetime | None = None, force: bool = False) -> Path:
    """원자적으로 놓는다: 잠금 → 고유 임시 디렉토리에 풀어 대조 → PINNED → 기존은 `.pin-old`로 비켜 두고 → 이름 바꾸기 → 링크·설정 → 그제야 `.pin-old` 삭제.
    어느 단계에서 실패해도 기존 사본이 남거나 돌아온다(링크·설정 실패 때는 새 사본을 지우고 옛것을 되돌린다 — Codex 2026-10-18)."""
    root = home_for(scope, project_root) / ("skills" if record.kind == "skill" else "tools")
    root.mkdir(parents=True, exist_ok=True)
    target = root / record.name
    tmp = root / f".{record.name}.pin-tmp-{os.getpid()}"
    old = root / f".{record.name}.pin-old-{os.getpid()}"
    for p in (target, tmp, old):
        _child_of(root, p)
    with _locked(root, record.name):
        if target.exists() and not force:
            raise PinError(f"{target} already exists — pass --force to replace it (a local edit would be lost)")
        _stage(record, tar_bytes, tmp, now)
        had_old = _swap(tmp, target, old)
        try:
            if record.kind == "skill":
                link_claude(scope, project_root, record.name)
            else:
                ensure_toolbox_entry(scope, project_root)
        except BaseException:
            _restore(target, old, had_old)
            raise
        shutil.rmtree(old, ignore_errors=True)
    return target


def link_claude(scope: Scope, project_root: Path, name: str) -> Path | None:
    """`.claude/skills/<name>` → `.agents/skills/<name>` 상대 링크. 그 자리에 실제 디렉토리가 있으면 건드리지 않는다(None)."""
    base = project_root if scope == "project" else Path.home()
    claude = base / ".claude" / "skills"
    claude.mkdir(parents=True, exist_ok=True)
    link = claude / name
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        return None
    rel = os.path.relpath(base / ".agents" / "skills" / name, start=claude)
    link.symlink_to(rel, target_is_directory=True)
    return link


def ensure_toolbox_entry(scope: Scope, project_root: Path) -> Path:
    """하네스 설정에 `toolbox` 서버 항목 하나. 프로젝트 범위는 `<root>/.mcp.json`, 사용자 범위는 `~/.claude.json`이 아니라 `~/.agents/mcp.json`에 두고 사용자가 하네스에 맞게 옮긴다(하네스마다 사용자 설정 파일이 달라서)."""
    path = project_root / MCP_CONFIG if scope == "project" else Path.home() / ".agents" / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {}
    if path.exists():
        try:
            loaded: object = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError as e:
            raise PinError(f"{path} is not valid JSON: {e}") from e
        if not isinstance(loaded, dict):
            raise PinError(f"{path} is not a JSON object")
        doc = cast("dict[str, Any]", loaded)
    servers_obj = doc.get("mcpServers")
    servers: dict[str, Any] = cast("dict[str, Any]", servers_obj) if isinstance(servers_obj, dict) else {}
    entry = dict(TOOLBOX_ENTRY)
    if scope == "user":
        entry["args"] = ["toolbox", str(Path.home() / ".agents" / "tools")]
    if servers.get("toolbox") != entry:
        servers["toolbox"] = entry
        doc["mcpServers"] = servers
        staged = path.with_name(path.name + f".pin-{os.getpid()}")
        staged.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged.replace(path)  # 같은 파일시스템 안의 원자적 교체
    return path


def read_pinned(directory: Path) -> tuple[str, str, str] | None:
    p = directory / PINNED
    if not p.is_file():
        return None
    parts = p.read_text(encoding="utf-8").split()
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else None
