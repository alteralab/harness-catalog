"""gitleaks 확보: PATH 우선, 없으면 핀된 판을 체크섬 검증해 캐시로."""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from harness_catalog_cli import gitleaks


def tar_with_binary(content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("gitleaks")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_path_binary_is_used_only_when_its_version_matches(tmp_path: Path) -> None:
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    same = gitleaks.ensure_gitleaks(env=env, which=lambda _: "/usr/bin/gitleaks", probe_version=lambda _: gitleaks.GITLEAKS_VERSION, download=lambda _: b"")
    assert same == "/usr/bin/gitleaks"
    data = tar_with_binary(b"bin")
    other = gitleaks.ensure_gitleaks(env=env, which=lambda _: "/usr/bin/gitleaks", probe_version=lambda _: "8.20.0", download=lambda _: data, checksums={"linux_x64": hashlib.sha256(data).hexdigest()}, key="linux_x64")
    assert other != "/usr/bin/gitleaks" and Path(other).is_file()  # 다른 판은 무시하고 핀된 판을 받는다


def test_download_verifies_checksum_and_caches(tmp_path: Path) -> None:
    data = tar_with_binary(b"#!/bin/sh\necho fake gitleaks\n")
    calls: list[str] = []

    def download(url: str) -> bytes:
        calls.append(url)
        return data

    env = {"XDG_CACHE_HOME": str(tmp_path)}
    good = {"linux_x64": hashlib.sha256(data).hexdigest()}
    path = gitleaks.ensure_gitleaks(env=env, which=lambda _: None, download=download, checksums=good, key="linux_x64")
    assert Path(path).is_file() and Path(path).stat().st_mode & 0o111
    assert calls == [f"https://github.com/gitleaks/gitleaks/releases/download/v{gitleaks.GITLEAKS_VERSION}/gitleaks_{gitleaks.GITLEAKS_VERSION}_linux_x64.tar.gz"]
    assert gitleaks.ensure_gitleaks(env=env, which=lambda _: None, download=download, checksums=good, key="linux_x64") == path
    assert len(calls) == 1  # 두 번째는 캐시(옆의 .sha256과 대조)
    Path(path).write_bytes(b"corrupted")  # 캐시가 어긋나면 다시 받는다
    assert gitleaks.ensure_gitleaks(env=env, which=lambda _: None, download=download, checksums=good, key="linux_x64") == path
    assert len(calls) == 2 and Path(path).read_bytes() != b"corrupted"


def test_checksum_mismatch_is_fail_closed(tmp_path: Path) -> None:
    data = tar_with_binary(b"x")
    with pytest.raises(gitleaks.GitleaksUnavailable):
        gitleaks.ensure_gitleaks(env={"XDG_CACHE_HOME": str(tmp_path)}, which=lambda _: None, download=lambda _: data, checksums={"linux_x64": "0" * 64}, key="linux_x64")
    assert not (tmp_path / "harness-catalog").exists() or not any((tmp_path / "harness-catalog").rglob("gitleaks"))


def test_platform_key() -> None:
    assert gitleaks.platform_key("Darwin", "arm64") == "darwin_arm64"
    assert gitleaks.platform_key("Linux", "x86_64") == "linux_x64"
    with pytest.raises(gitleaks.GitleaksUnavailable):
        gitleaks.platform_key("Windows", "AMD64")


def test_malformed_archive_is_unavailable_not_traceback(tmp_path: Path) -> None:
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    bad = b"not a tarball"
    with pytest.raises(gitleaks.GitleaksUnavailable):
        gitleaks.ensure_gitleaks(env=env, which=lambda _: None, download=lambda _: bad, checksums={"linux_x64": hashlib.sha256(bad).hexdigest()}, key="linux_x64")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("README.md")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    no_member = buf.getvalue()
    with pytest.raises(gitleaks.GitleaksUnavailable):
        gitleaks.ensure_gitleaks(env=env, which=lambda _: None, download=lambda _: no_member, checksums={"linux_x64": hashlib.sha256(no_member).hexdigest()}, key="linux_x64")


def test_check_exits_2_when_gitleaks_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from typer.testing import CliRunner

    from harness_catalog_cli import __main__ as cli_main

    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    (repo / ".harness-catalog").write_text("layout = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", "c"], check=True)

    def boom() -> str:
        raise gitleaks.GitleaksUnavailable("offline")

    monkeypatch.setattr(cli_main, "ensure_gitleaks", boom)
    r = CliRunner().invoke(cli_main.app, ["check", str(repo), "--rev", "HEAD"])
    assert r.exit_code == 2 and "checker failed: offline" in r.output
