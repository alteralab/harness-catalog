"""공용 픽스처: 템플릿 구조의 시험 카탈로그 저장소를 임시로 만든다."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, NamedTuple

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def anyio_backend() -> str:
    """anyio 시험은 asyncio 백엔드만."""
    return "asyncio"

SKILL_MD = """---
name: {name}
description: {description}
{extra}---

# {name}

{body}
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def write_skill(repo: Path, name: str, description: str, *, metadata: dict[str, str] | None = None, body: str = "Do the thing.", files: dict[str, bytes] | None = None) -> None:
    d = repo / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    extra = ""
    if metadata:
        extra = "metadata:\n" + "".join(f"  {k}: \"{v}\"\n" for k, v in metadata.items())
    (d / "SKILL.md").write_text(SKILL_MD.format(name=name, description=description, extra=extra, body=body))
    for rel, data in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", message], check=True)
    return git(repo, "rev-parse", "HEAD")


class CatalogRepo(NamedTuple):
    path: Path
    head: str


@pytest.fixture
def catalog_repo(tmp_path: Path) -> CatalogRepo:
    """표지·skills/·CI·pre-commit·README를 갖춘 저장소에 스킬 둘."""
    repo = tmp_path / "catalog"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / ".harness-catalog").write_text("layout = 1\n")
    (repo / "skills" / ".gitkeep").parent.mkdir()
    (repo / "skills" / ".gitkeep").write_text("")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "check.yml").write_text("name: check\n")
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n")
    (repo / "README.md").write_text("# catalog\n")
    write_skill(repo, "yt-subs", "Extract YouTube subtitles. Use for 유튜브 자막.", metadata={"requires-tools": "yt-dlp uv"}, files={"scripts/fetch.py": b"print('hi')\n", "references/notes.md": b"# notes\n"})
    write_skill(repo, "pin-skill", "Download a skill next to the harness (pin).")
    write_tool(repo, "subs-fetch", {"kind": "script", "path": "scripts/fetch.py", "command": ["uv", "run", "--script", "scripts/fetch.py"]},
               description="Fetch subtitles as text (toolbox script). 자막 텍스트.", files={"scripts/fetch.py": b"print('subs')\n"}, metadata={"requires-tools": "uv"})
    write_tool(repo, "graft-ask", {"kind": "mcp", "server": "graft", "tool": "graft_find_code"}, description="Ask the code graph (toolbox mcp).")
    write_server(repo, "graft", "0.21.1")
    head = commit_all(repo, "two skills, two tools, one server")
    return CatalogRepo(repo, head)


def write_tool(repo: Path, name: str, runtime: dict[str, object], *, description: str, files: dict[str, bytes] | None = None, metadata: dict[str, str] | None = None) -> None:
    """tools/<name>/tool.json(+파일). toolbox(DESIGN §11 2026-10-11)."""
    d = repo / "tools" / name
    d.mkdir(parents=True, exist_ok=True)
    spec: dict[str, object] = {"name": name, "description": description, "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}, "runtime": runtime}
    if metadata:
        spec["metadata"] = metadata
    (d / "tool.json").write_text(json.dumps(spec, indent=2) + "\n")
    for rel, data in (files or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(data)


def write_server(repo: Path, name: str, version: str) -> None:
    """mcp-servers/<name>/server.json — MCP Registry 형식의 부분집합."""
    d = repo / "mcp-servers" / name
    d.mkdir(parents=True, exist_ok=True)
    spec = {"name": f"lab.altera/{name}", "version": version, "description": f"{name} MCP server",
            "packages": [{"registryType": "npm", "identifier": f"@nanonets/{name}", "version": version, "transport": {"type": "stdio"}}]}
    (d / "server.json").write_text(json.dumps(spec, indent=2) + "\n")
