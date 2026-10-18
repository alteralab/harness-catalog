"""`init <repo-url>`: 카탈로그 저장소를 한 번 세운다. 운영자 git 자격으로 clone → 호스트 판별 → 템플릿을 없는 것만 쓰고 → 커밋·push. 멱등."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from importlib.metadata import version
from importlib.resources import as_file, files
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

from harness_catalog_core.catalog_file import MARKER_PATH, MarkerError, parse_marker
from harness_catalog_core.model import SUPPORTED_LAYOUT
from harness_catalog_core.toolbox import tool_json_schema

CODE_REPO_URL = "https://github.com/alteralab/harness-catalog"
VERSION_PLACEHOLDER = "<판>"
SCHEMA_PATH = "schemas/tool.schema.json"
MCP_CONFIG_PATH = ".mcp.json"
MCP_CONFIG = json.dumps({"mcpServers": {"toolbox": {"command": "hc", "args": ["toolbox", "./tools"]}}}, ensure_ascii=False, indent=2) + "\n"


class InitError(Exception):
    """멈춰야 하는 사유(종료 1)."""


class InitResult(NamedTuple):
    written: tuple[str, ...]  # 새로 쓴 파일(저장소 기준 상대 경로)
    pin: str  # 템플릿에 박은 판 참조(v<판> 또는 --pin)
    host: str


def detect_host(repo_url: str) -> str:
    """URL에서 git 호스트 종류: github | gitlab. 그 밖이면 InitError."""
    u = repo_url.strip()
    hostname = urlsplit(u).hostname if "://" in u else u.split("@", 1)[-1].split(":", 1)[0]
    labels = (hostname or "").lower().split(".")
    if labels[-2:] == ["github", "com"]:
        return "github"  # github.com과 *.github.com만(GHES 사설 도메인은 --host github로 명시)
    if labels[-2:] == ["gitlab", "com"] or "gitlab" in labels[:-2]:
        return "gitlab"
    raise InitError(f"unsupported git host in {repo_url!r} (github.com·*.github.com·gitlab.com·gitlab.<domain> only — otherwise pass --host)")


def resolve_pin(pin: str | None, *, code_repo_url: str = CODE_REPO_URL) -> str:
    """템플릿의 판 참조. --pin이 없으면 cli 자기 판이고 그 태그가 코드 저장소에 있어야 한다(오핀 방지)."""
    if pin:
        return pin
    tag = f"v{version('harness-catalog-cli')}"
    proc = subprocess.run(["git", "ls-remote", "--tags", "--exit-code", code_repo_url, tag], capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise InitError(f"tag {tag} not found in {code_repo_url} (development build?) — pass --pin <ref> to use an explicit ref")
    return tag


def template_files(host: str) -> Mapping[str, str]:
    """상대 경로 → 내용. 호스트의 워크플로만 싣고, 기본 스킬 셋(templates/skills/)은 파일 전부를 싣고, tool.json의 JSON Schema는 core 모델에서 생성해 싣는다.

    스킬 원본은 이 패키지 데이터 하나다(사본을 두지 않는다, C-DUP-2). 새 카탈로그는 init 직후부터 세 스킬이 검색된다(DESIGN §11 2026-10-10·2026-10-11 write-tool).
    schemas/tool.schema.json은 템플릿 파일이 아니라 `ToolSpec`의 산출물이다 — 모델이 바뀌면 다음 init(새 카탈로그)과 `init --refresh`(기존 카탈로그)가 따라간다; `check`가 낡음을 경고한다.
    .mcp.json은 카탈로그 클론에서 저자가 자기 도구를 바로 MCP로 쓰게 하는 `toolbox` 항목 하나다(§11 2026-10-18 어디서나 MCP 하나).
    """
    base = files("harness_catalog_cli") / "templates"
    out: dict[str, str] = {}
    with as_file(base) as root:
        out[MARKER_PATH] = (root / ".harness-catalog").read_text()
        out["README.md"] = (root / "README.md").read_text()
        out[".pre-commit-config.yaml"] = (root / ".pre-commit-config.yaml").read_text()
        if host == "github":
            out[".github/workflows/check.yml"] = (root / "github" / "check.yml").read_text()
            out[".github/actions/code-repo-credentials/action.yml"] = (root / "github" / "actions" / "code-repo-credentials" / "action.yml").read_text()
        else:
            out[".gitlab-ci.yml"] = (root / "gitlab" / ".gitlab-ci.yml").read_text()
        out[SCHEMA_PATH] = generated_schema()
        out[MCP_CONFIG_PATH] = MCP_CONFIG
        skills_root = root / "skills"
        for p in sorted(skills_root.rglob("*")):
            rel = p.relative_to(skills_root)
            if p.is_file() and "__pycache__" not in rel.parts:  # 스크립트를 import한 흔적(.pyc)은 템플릿이 아니다
                out[f"skills/{rel.as_posix()}"] = p.read_text()
    return out


def generated_schema() -> str:
    return json.dumps(tool_json_schema(), ensure_ascii=False, indent=2) + "\n"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, timeout=600)
    if proc.returncode != 0:
        raise InitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def write_missing(repo: Path, contents: Mapping[str, str], pin: str, *, refresh: bool = False) -> tuple[str, ...]:
    """없는 파일만 쓴다. 표지가 있는데 layout이 다르면 멈춘다. refresh면 생성 파일(schemas/tool.schema.json)이 낡았을 때 다시 쓴다."""
    marker = repo / MARKER_PATH
    if marker.exists():
        try:
            layout = parse_marker(marker.read_text()).layout
        except MarkerError as e:
            raise InitError(f"{MARKER_PATH} unreadable: {e}") from e
        if layout != SUPPORTED_LAYOUT:
            raise InitError(f"{MARKER_PATH} declares layout {layout}, this cli supports {SUPPORTED_LAYOUT}")
    written: list[str] = []
    for rel, text in contents.items():
        target = repo / rel
        if target.exists():
            if refresh and rel == SCHEMA_PATH and target.read_text() != text:
                target.write_text(text)
                written.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.replace(VERSION_PLACEHOLDER, pin.removeprefix("v")))
        written.append(rel)
    return tuple(written)


def init_repository(repo_url: str, *, pin: str | None = None, host: str | None = None, author: str = "harness-catalog init", refresh: bool = False) -> InitResult:
    host = host or detect_host(repo_url)
    if host not in ("github", "gitlab"):
        raise InitError(f"unknown host {host!r} (github·gitlab only)")
    ref = resolve_pin(pin)
    with tempfile.TemporaryDirectory(prefix="hc-init.") as tmp:
        repo = Path(tmp) / "repo"
        proc = subprocess.run(["git", "clone", "-q", repo_url, str(repo)], capture_output=True, text=True, check=False, timeout=600)
        if proc.returncode != 0:
            raise InitError(f"clone failed: {proc.stderr.strip()}")
        has_main = subprocess.run(["git", "-C", str(repo), "ls-remote", "--exit-code", "--heads", "origin", "main"], capture_output=True, check=False).returncode == 0
        unborn = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"], capture_output=True, check=False).returncode != 0
        if has_main:
            _git(repo, "checkout", "-q", "main")  # 기본 브랜치가 다른 것이어도 카탈로그는 main이다
        elif unborn:
            _git(repo, "checkout", "-q", "-b", "main")
        else:
            raise InitError("repository has commits but no 'main' branch — create main (the catalog branch) first, then rerun")
        written = write_missing(repo, template_files(host), ref, refresh=refresh)
        if written:
            _git(repo, "add", "-A")
            _git(repo, "-c", "user.name=harness-catalog", "-c", f"user.email={author}@localhost", "commit", "-q", "-m", f"harness-catalog init{' --refresh' if refresh else ''} (cli {ref})")
            _git(repo, "push", "-q", "origin", "HEAD:main")
    return InitResult(written, ref, host)
