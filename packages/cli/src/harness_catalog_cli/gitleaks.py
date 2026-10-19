"""gitleaks 바이너리 확보: PATH의 같은 판 → 검증된 캐시 → 핀된 판 내려받기(체크섬). 검사 항목 4는 fail-closed.

CI 워크플로가 curl·tar로 설치하던 단계를 CLI 안으로 들였다(DESIGN §11 2026-10-10). 판과 체크섬은 여기 한 곳이다.
Codex 리뷰(2026-10-10) 반영: PATH 바이너리는 판이 같을 때만, 캐시는 기록된 해시와 대조, 임시 파일 뒤 원자적 교체, 모든 실패는 GitleaksUnavailableError.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

GITLEAKS_VERSION = "8.30.1"
# gitleaks_8.30.1_checksums.txt (GitHub release, 2026-10-10 확인) — tar.gz의 sha256
CHECKSUMS: Mapping[str, str] = {
    "linux_x64": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "linux_arm64": "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    "darwin_x64": "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "darwin_arm64": "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
}


class GitleaksUnavailableError(Exception):
    """확보할 수 없거나 검증에 실패했다 — 검사기 실패(종료 2)로 이어진다."""


def platform_key(system: str | None = None, machine: str | None = None) -> str:
    s = (system or platform.system()).lower()
    m = (machine or platform.machine()).lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(m)
    if s not in ("linux", "darwin") or arch is None:
        raise GitleaksUnavailableError(f"no pinned gitleaks build for {s}/{m}")
    return f"{s}_{arch}"


def cache_dir(env: Mapping[str, str]) -> Path:
    root = Path(env["XDG_CACHE_HOME"]) if env.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return root / "harness-catalog" / f"gitleaks-{GITLEAKS_VERSION}"


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:  # 고정 https URL(release 자산)
        return r.read()


def _probe_version(path: str) -> str:
    """`gitleaks version`의 첫 줄(예: '8.30.1' 또는 'v8.30.1'). 실패하면 빈 문자열."""
    try:
        out = subprocess.run([path, "version"], capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip().splitlines()[0].strip().lstrip("v") if out.returncode == 0 and out.stdout.strip() else ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cached(target: Path) -> str | None:
    """캐시 바이너리가 있고 옆에 기록된 해시와 같으면 경로. 없거나 어긋나면 None(다시 받는다).

    위협 모델: 손상·부분 쓰기·중단된 설치를 잡는다. 캐시 디렉토리에 쓸 수 있는 공격자는 사이드카도 바꿀 수 있으므로 범위 밖이다 —
    그 수준의 공격자는 이미 사용자 권한을 가진 것이고, 핀된 체크섬은 내려받는 순간(tar.gz)에만 대조한다.
    """
    sidecar = target.with_suffix(".sha256")
    try:
        if target.is_file() and sidecar.is_file() and _sha256(target.read_bytes()) == sidecar.read_text().strip():
            return str(target)
    except OSError:
        return None
    return None


def _extract_binary(archive: bytes) -> bytes:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            member = tar.getmember("gitleaks")
            f = tar.extractfile(member)
            if f is None or not member.isfile():
                raise GitleaksUnavailableError("archive has no regular file 'gitleaks'")
            return f.read()
    except (tarfile.TarError, KeyError, OSError) as e:
        raise GitleaksUnavailableError(f"archive unreadable: {e}") from e


def _install(target: Path, binary: bytes) -> None:
    """임시 파일에 쓰고 원자적으로 교체한다 — 동시 실행·중단에도 반쪽 실행 파일이 남지 않는다."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="gitleaks.", dir=target.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(binary)
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
        target.with_suffix(".sha256").write_text(_sha256(binary) + "\n")
    except OSError as e:
        raise GitleaksUnavailableError(f"cannot write cache {target}: {e}") from e


def ensure_gitleaks(
    *,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    probe_version: Callable[[str], str] = _probe_version,
    download: Callable[[str], bytes] = _http_get,
    checksums: Mapping[str, str] = CHECKSUMS,
    key: str | None = None,
) -> str:
    """실행 파일 경로. PATH(판이 GITLEAKS_VERSION일 때만) → 검증된 캐시 → 내려받기(tar.gz 체크섬 대조)."""
    env = os.environ if env is None else env
    found = which("gitleaks")
    if found and probe_version(found) == GITLEAKS_VERSION:
        return found
    target = cache_dir(env) / "gitleaks"
    cached = _cached(target)
    if cached:
        return cached
    key = key or platform_key()
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{GITLEAKS_VERSION}/gitleaks_{GITLEAKS_VERSION}_{key}.tar.gz"
    try:
        data = download(url)
    except OSError as e:
        raise GitleaksUnavailableError(f"download failed: {url}: {e}") from e
    digest = _sha256(data)
    if digest != checksums.get(key):
        raise GitleaksUnavailableError(f"checksum mismatch for {url}: {digest}")
    _install(target, _extract_binary(data))
    return str(target)
