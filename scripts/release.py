# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""릴리스 한 명령: 판 네 곳 + 내부 핀 → lock → 게이트·시험 → 태그 없이 pip 경로로 설치 실측 → 커밋 → 주석 태그 → main과 태그를 원자적으로 push.

호출: uv run --script scripts/release.py <X.Y.Z> [--dry-run] [--skip-check]
  --dry-run     파일을 고치고 설치 실측까지만 하고 커밋·태그·push는 하지 않는다(작업 트리에 변경이 남는다)
  --skip-check  `make check`(게이트·타입·시험)를 건너뛴다 — CI가 같은 것을 돈 뒤에만

왜 스크립트인가(plans/distribution.md D25): 손으로 하는 릴리스가 세 번 어긋났다 — 시험의 하드코딩 판(v0.2.0), 커밋 실패 뒤 옛 커밋에 태그(v0.3.0),
내부 핀 미갱신으로 태그에서 pip 설치 불가(v0.3.0). uv 워크스페이스 안에서는 로컬 소스가 핀을 덮어써 마지막 결함이 드러나지 않으므로,
카탈로그의 pre-commit·CI가 쓰는 길 그대로 — 워크스페이스 밖의 새 venv에 pip로 `<네 패키지 디렉토리>`를 — 설치해 본 뒤에만 태그를 단다(uv pip는 이 어긋남을 통과시킨다 — 실측).
종료 코드: 0 성공 · 2 입력·전제 오류 · 1 단계 실패(어느 단계인지 stderr).
"""

from __future__ import annotations

import argparse
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("core", "cli", "server", "harbor-langfuse")
# ast-grep-ignore: regex-on-structure — 어휘: semver 세 자리의 고정 형식
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def run(*args: str, cwd: Path = ROOT, capture: bool = False) -> str:
    print("$ " + " ".join(args), file=sys.stderr)
    proc = subprocess.run(args, cwd=cwd, check=False, text=True, capture_output=capture)
    if proc.returncode != 0:
        if capture:
            print(proc.stdout, proc.stderr, file=sys.stderr)
        print(f"release: step failed ({args[0]} {args[1] if len(args) > 1 else ''})", file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout if capture else ""


def preflight() -> None:
    if run("git", "branch", "--show-current", capture=True).strip() != "main":
        print("release: not on main", file=sys.stderr)
        raise SystemExit(2)
    if run("git", "status", "--porcelain", capture=True).strip():
        print("release: working tree is not clean — commit or stash first", file=sys.stderr)
        raise SystemExit(2)
    run("git", "fetch", "-q", "origin", "main")
    if run("git", "rev-parse", "HEAD", capture=True).strip() != run("git", "rev-parse", "origin/main", capture=True).strip():
        print("release: local main differs from origin/main — pull or push first", file=sys.stderr)
        raise SystemExit(2)


def set_versions(version: str) -> list[Path]:
    """pyproject 넷의 version과 내부 핀(harness-catalog-*==)을 전부 version으로. 바꾼 파일 목록을 돌려준다."""
    changed: list[Path] = []
    for name in PACKAGES:
        p = ROOT / "packages" / name / "pyproject.toml"
        s = p.read_text()
        # ast-grep-ignore: regex-on-structure — 어휘: 'version = "x"' 한 줄과 'harness-catalog-<x>==<판>' 고정 형식
        s2 = re.sub(r'^version = "[^"]+"', f'version = "{version}"', s, count=1, flags=re.M)
        # ast-grep-ignore: regex-on-structure — 어휘: 'harness-catalog-<x>==<판>' 고정 형식의 핀 문자열
        s2 = re.sub(r'"harness-catalog-([a-z-]+)==[^"]+"', rf'"harness-catalog-\1=={version}"', s2)
        if s2 != s:
            p.write_text(s2)
            changed.append(p)
    return changed


def install_like_pip(tmp: Path) -> None:
    """워크스페이스 밖의 새 venv에 네 패키지 디렉토리를 **pip**로 한 번에 설치한다 — 카탈로그 pre-commit과 같은 해석기. 내부 핀이 어긋나면 여기서 실패한다.

    `uv pip install`은 로컬 디렉토리 요구를 핀보다 우선해 어긋남을 통과시킨다(2026-10-11 실측: core==0.0.1 핀에도 종료 0). pip는 ResolutionImpossible로 실패한다.
    """
    venv = tmp / "venv"
    run("uv", "venv", "-q", "--seed", str(venv))  # --seed: pip를 넣는다
    python = venv / "bin" / "python"
    dirs = [str(ROOT / "packages" / name) for name in PACKAGES]
    run(str(python), "-m", "pip", "install", "-q", *dirs)
    out = run(str(venv / "bin" / "harness-catalog"), "--version", capture=True)
    print(f"release: installed OK — {out.strip()}", file=sys.stderr)


NEXUS_PUBLISH_URL = "https://ds923plus.tail2f9fe3.ts.net:8443/repository/pypi-internal/"
NEXUS_SIMPLE_URL = "https://ds923plus.tail2f9fe3.ts.net:8443/repository/pypi-public/simple/"

# 이미지 주소는 환경이 정한다(§11 2026-10-20) — CI 의 저장소 변수·deploy.sh 와 같은 이름 둘. 우리 값(NAS Harbor)이 기본값이라 지금 동작은 그대로다.
IMAGE_REGISTRY = os.environ.get("IMAGE_REGISTRY") or "ds923plus.tail2f9fe3.ts.net:9443"
IMAGE_REPOSITORY = os.environ.get("IMAGE_REPOSITORY") or "alteralab/harness-catalog"


def publish(version: str) -> bool:
    """core·cli 휠을 NAS Nexus pypi-internal 에 올린다(2026-10-18 결정 — hc 는 git+ssh 가 아니라 인덱스로 받는다).

    자격은 uv publish 가 읽는 환경변수 UV_PUBLISH_USERNAME / UV_PUBLISH_PASSWORD (gopass nas/nexus-publish). URL 은
    HC_PYPI_PUBLISH_URL / HC_PYPI_SIMPLE_URL 로 바꿀 수 있다(LAN 에서는 http://192.168.3.95:8081/...). 자격이 없으면
    올리지 않고 안내만 한다 — 릴리스 자체(태그·push)는 이미 끝난 뒤라 실패로 만들지 않는다. 같은 판이 이미 있으면 --check-url 이 건너뛴다.
    """
    if not os.environ.get("UV_PUBLISH_PASSWORD"):
        print("release: UV_PUBLISH_USERNAME/UV_PUBLISH_PASSWORD 가 없어 Nexus 업로드를 건너뛴다 — 나중에 `release.py --publish-only <판>`", file=sys.stderr)
        return False
    dist = ROOT / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    for pkg in ("harness-catalog-core", "harness-catalog-cli"):
        run("uv", "build", "-q", "--package", pkg, "-o", str(dist))
    files = sorted(str(f) for f in dist.glob(f"harness_catalog_*-{version}*"))
    if len(files) != 4:
        print(f"release: expected 4 dist files for {version}, got {files}", file=sys.stderr)
        raise SystemExit(1)
    publish_url = os.environ.get("HC_PYPI_PUBLISH_URL", NEXUS_PUBLISH_URL)
    simple_url = os.environ.get("HC_PYPI_SIMPLE_URL", NEXUS_SIMPLE_URL)
    run("uv", "publish", "--publish-url", publish_url, "--check-url", simple_url, *files)
    print(f"release: published {len(files)} files to {publish_url}", file=sys.stderr)
    return True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-check", action="store_true")
    ap.add_argument("--publish-only", action="store_true", help="태그·push 없이 그 판의 휠만 Nexus 에 올린다(이미 릴리스된 판)")
    ns = ap.parse_args(argv)
    version: str = ns.version
    if not VERSION_RE.match(version):
        print(f"release: version must be X.Y.Z, got {version!r}", file=sys.stderr)
        return 2
    tag = f"v{version}"
    if ns.publish_only:
        return 0 if publish(version) else 2
    if run("git", "tag", "--list", tag, capture=True).strip():
        print(f"release: tag {tag} already exists", file=sys.stderr)
        return 2
    preflight()
    changed = set_versions(version)
    run("uv", "lock", "-q")
    with tempfile.TemporaryDirectory(prefix="hc-release.") as tmp:
        install_like_pip(Path(tmp))
    if not ns.skip_check:
        run("make", "check")
    if ns.dry_run:
        print(f"release: dry run — {len(changed)} pyproject(s) and uv.lock changed in the working tree, nothing committed", file=sys.stderr)
        return 0
    run("git", "add", "-A", "packages", "uv.lock")
    run("git", "commit", "-q", "-m", f"release: {tag}\n\n판 넷과 내부 핀을 {version}으로. pip 경로 설치 실측 통과(scripts/release.py).")
    run("git", "tag", "-a", tag, "-m", f"{tag}")
    run("git", "push", "--atomic", "origin", "main", tag)  # main과 태그가 함께 가거나 둘 다 안 간다
    print(f"release: {tag} pushed — CI가 이미지 {IMAGE_REGISTRY}/{IMAGE_REPOSITORY}:<짧은 SHA>·:{tag}를 레지스트리에 올린다", file=sys.stderr)
    publish(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
