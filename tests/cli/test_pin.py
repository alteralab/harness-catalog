"""hc pin: get_skill/get_tool(archive=true) 응답 → 받기·대조·원자적 교체·링크·.mcp.json. 실패하면 기존 사본은 그대로."""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import tarfile
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from harness_catalog_cli import pin
from harness_catalog_cli.__main__ import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

FILES = {"SKILL.md": b"---\nname: alpha\ndescription: a\n---\nbody\n", "references/x.md": b"ref\n"}


def tar_of(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def served() -> Iterator[tuple[str, dict[str, bytes]]]:
    """토큰 헤더가 맞을 때만 tar를 주는 작은 HTTP 서버(레지스트리의 아카이브 라우트 흉내)."""
    store: dict[str, bytes] = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = store.get(self.path)
            if body is None or self.headers.get("X-Harness-Archive-Token") != "tok":
                self.send_response(403)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}", store
    finally:
        srv.shutdown()


def response(base: str, store: dict[str, bytes], *, name: str = "alpha", files: dict[str, bytes] = FILES, kind: str = "skill", sha: str = "a" * 40, lie_sha256: bool = False) -> dict[str, object]:
    data = tar_of(files)
    path = f"/archive/{'tools/' if kind == 'tool' else ''}{name}/{sha}.tar"
    store[path] = data
    doc: dict[str, object] = {
        "id": name, "sha": sha, "commit": "c" * 40, "files": [{"path": p, "size": len(b)} for p in sorted(files) for b in [files[p]]],
        "archive": {"uri": base + path, "method": "GET", "headers": {"X-Harness-Archive-Token": "tok"}, "expires_at": "2026-01-01T00:00:00Z", "mimeType": "application/x-tar",
                    "size": len(data), "sha256": ("0" * 64) if lie_sha256 else hashlib.sha256(data).hexdigest(), "digest": f"git-tree:{sha}"},
        "fetched_at": "2026-01-01T00:00:00Z",
    }
    if kind == "tool":
        doc["kind"] = "script"
        doc["tool"] = {"name": name, "description": "d", "inputSchema": {"type": "object"}, "runtime": {"kind": "script", "path": "scripts/x.py", "command": ["uv", "run", "--script", "scripts/x.py"]}}
    else:
        doc["body"] = "body"
        doc["metadata"] = {}
        doc["has_scripts"] = False
    return doc


def test_parse_response_requires_archive() -> None:
    with pytest.raises(pin.PinError, match="archive=true"):
        pin.parse_response({"id": "a", "sha": "a" * 40, "files": [{"path": "SKILL.md", "size": 1}], "archive": None})


def test_pin_skill_project_scope(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    base, store = served
    rec = pin.parse_response(response(base, store))
    target = pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path, now=datetime(2026, 10, 18, tzinfo=UTC))
    assert target == tmp_path / ".agents" / "skills" / "alpha"
    assert (target / "references" / "x.md").read_bytes() == b"ref\n"
    assert (target / "PINNED").read_text() == f"alpha {'a' * 40} 2026-10-18T00:00:00Z\n"
    link = tmp_path / ".claude" / "skills" / "alpha"
    assert link.is_symlink() and (link / "SKILL.md").exists()
    assert not (tmp_path / ".mcp.json").exists()  # 스킬은 toolbox 항목을 쓰지 않는다
    with pytest.raises(pin.PinError, match="--force"):
        pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)


def test_pin_tool_writes_mcp_json_and_replaces_atomically(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    base, store = served
    tool_files = {"tool.json": b"{}", "scripts/x.py": b"print(1)\n"}
    rec = pin.parse_response(response(base, store, name="fetch", files=tool_files, kind="tool"))
    target = pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)
    assert target == tmp_path / ".agents" / "tools" / "fetch" and (target / "scripts" / "x.py").exists()
    cfg = json.loads((tmp_path / ".mcp.json").read_text())
    assert cfg["mcpServers"]["toolbox"] == {"command": "hc", "args": ["toolbox", ".agents/tools"]}
    # 새 판: 기존 사본은 교체 성공 전까지 남고, 성공하면 .pin-old는 사라진다
    rec2 = pin.parse_response(response(base, store, name="fetch", files={**tool_files, "scripts/y.py": b"2\n"}, kind="tool", sha="b" * 40))
    pin.install(rec2, pin.download(rec2), scope="project", project_root=tmp_path, force=True)
    assert (target / "scripts" / "y.py").exists() and not (tmp_path / ".agents" / "tools" / ".fetch.pin-old").exists()
    assert pin.read_pinned(target) == ("fetch", "b" * 40, pin.read_pinned(target)[2])  # type: ignore[index]
    # 다른 설정이 이미 있으면 toolbox 항목만 더한다
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    pin.ensure_toolbox_entry("project", tmp_path)
    assert set(json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]) == {"other", "toolbox"}


def test_failures_leave_existing_copy_untouched(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    base, store = served
    rec = pin.parse_response(response(base, store))
    pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)
    target = tmp_path / ".agents" / "skills" / "alpha"
    before = (target / "PINNED").read_text()
    liar = pin.parse_response(response(base, store, sha="b" * 40, lie_sha256=True))
    with pytest.raises(pin.PinError, match="sha256 mismatch"):
        pin.download(liar)
    wrong_list = pin.parse_response(response(base, store, sha="c" * 40))
    wrong = pin.Record(wrong_list.kind, wrong_list.name, wrong_list.sha, ("SKILL.md",), wrong_list.uri, wrong_list.headers, wrong_list.size, wrong_list.sha256)
    with pytest.raises(pin.PinError, match="file list mismatch"):
        pin.install(wrong, pin.download(wrong), scope="project", project_root=tmp_path, force=True)
    assert (target / "PINNED").read_text() == before and not (tmp_path / ".agents" / "skills" / ".alpha.pin-tmp").exists()
    bad_tar = tar_of({"../escape": b"x"})
    with pytest.raises(pin.PinError, match="rejected"):
        pin.extract(bad_tar, tmp_path / "x")


def test_cli_pin_reads_response_from_stdin(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    base, store = served
    doc = response(base, store)
    r = CliRunner().invoke(app, ["pin", "--scope", "project", "--project-root", str(tmp_path)], input=json.dumps(doc))
    assert r.exit_code == 0, r.output
    assert "pinned skill alpha" in r.output and (tmp_path / ".agents" / "skills" / "alpha" / "PINNED").exists()
    r2 = CliRunner().invoke(app, ["pin", "--scope", "nowhere", "--project-root", str(tmp_path)], input="{}")
    assert r2.exit_code == 2


def test_traversal_id_is_rejected_before_any_path_is_built(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    """Codex 2026-10-18 critical: id가 디렉토리명이 되므로 카탈로그 name 문법 밖은 거부한다(.. 등)."""
    base, store = served
    doc = response(base, store)
    for bad in ("../../victim", "a/b", "Bad_Name", "", "-x"):
        doc["id"] = bad
        with pytest.raises(pin.PinError, match="not a catalog name"):
            pin.parse_response(doc)
    doc["id"], doc["sha"] = "alpha", "zz" * 20
    with pytest.raises(pin.PinError, match="40-hex"):
        pin.parse_response(doc)


def test_link_failure_rolls_back_to_previous_copy(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    """Codex 2026-10-18 high: 링크·설정 단계가 실패하면 새 사본을 지우고 옛 사본을 되돌린다 — 되돌림 디렉토리는 그때까지 남아 있다."""
    base, store = served
    rec = pin.parse_response(response(base, store))
    pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)
    target = tmp_path / ".agents" / "skills" / "alpha"
    before = (target / "PINNED").read_text()
    claude = tmp_path / ".claude"
    import shutil

    shutil.rmtree(claude)
    claude.write_text("not a directory")  # .claude/skills를 만들 수 없게 → link_claude가 OSError
    rec2 = pin.parse_response(response(base, store, sha="b" * 40))
    with pytest.raises(OSError):
        pin.install(rec2, pin.download(rec2), scope="project", project_root=tmp_path, force=True)
    assert (target / "PINNED").read_text() == before  # 옛 사본이 돌아왔다
    assert not any(p.name.startswith(".alpha.pin-") and p.is_dir() for p in target.parent.iterdir())  # 임시·되돌림 디렉토리가 남지 않는다


def test_concurrent_pin_of_same_name_is_refused(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    """Codex 2026-10-18 high: 같은 이름의 pin은 flock으로 직렬화된다. 잠금을 쥔 채 두 번째 호출은 즉시 거부된다."""
    import fcntl

    base, store = served
    rec = pin.parse_response(response(base, store))
    root = tmp_path / ".agents" / "skills"
    root.mkdir(parents=True)
    with (root / ".alpha.pin-lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        with pytest.raises(pin.PinError, match="in progress"):
            pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)
    pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)  # 잠금이 풀리면 된다
    assert (root / "alpha" / "PINNED").exists()



def test_link_replacement_is_atomic_and_keeps_old_link_on_failure(served: tuple[str, dict[str, bytes]], tmp_path: Path) -> None:
    """Codex 2026-10-18 2차 medium: 기존 .claude 링크는 새 링크가 준비된 뒤 원자적으로 바뀐다. 새 링크를 못 만들면 옛 링크가 그대로다."""
    import os
    import stat

    base, store = served
    rec = pin.parse_response(response(base, store))
    pin.install(rec, pin.download(rec), scope="project", project_root=tmp_path)
    link = tmp_path / ".claude" / "skills" / "alpha"
    before = os.readlink(link)
    claude = link.parent
    claude.chmod(stat.S_IRUSR | stat.S_IXUSR)  # 쓰기 금지 → 임시 링크 생성 실패
    try:
        rec2 = pin.parse_response(response(base, store, sha="b" * 40))
        with pytest.raises(OSError):
            pin.install(rec2, pin.download(rec2), scope="project", project_root=tmp_path, force=True)
    finally:
        claude.chmod(stat.S_IRWXU)
    assert link.is_symlink() and os.readlink(link) == before  # 옛 링크 보존
    assert (tmp_path / ".agents" / "skills" / "alpha" / "PINNED").read_text().split()[1] == "a" * 40  # 옛 사본도 돌아왔다
    assert not any(p.name.startswith(".alpha.pin-link") for p in claude.iterdir())
