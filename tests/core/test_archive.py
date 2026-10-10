"""Catalog.get_skill_archive: 캐시 tar, 크기·sha256, 상한, 없는 판."""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from harness_catalog_core.catalog import Catalog, Limits
from harness_catalog_core.model import CatalogError, ErrorCode

from .fakes import FakeStore, FakeValidator, MemoryFacts

SKILL = {"SKILL.md": b"---\nname: alpha\ndescription: a\n---\n", "scripts/x.py": b"print(1)\n", "evals/c/task.toml": b"schema_version = '1.4'\n"}


def make(tmp_path: Path, **kw: object) -> Catalog:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cat = Catalog(FakeStore({"alpha": SKILL}), FakeValidator(), MemoryFacts(), workdir=tmp_path, **kw)  # type: ignore[arg-type]
    assert cat.rebuild().ready
    return cat


def test_archive_is_cached_and_described(tmp_path: Path) -> None:
    cat = make(tmp_path)
    info = cat.get_skill_archive("alpha")
    assert info.name == "alpha" and info.path == tmp_path / "archives" / f"{info.sha}.tar"
    data = info.path.read_bytes()
    assert info.size == len(data) and info.sha256 == hashlib.sha256(data).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        assert sorted(m.name for m in tar.getmembers() if m.isfile()) == sorted(SKILL)
    assert (tmp_path / "archives" / f"{info.sha}.tar.sha256").read_text().strip() == f"v2 {info.sha256}"
    before = info.path.stat().st_mtime_ns
    again = cat.get_skill_archive("alpha", info.sha)
    assert again == info and info.path.stat().st_mtime_ns >= before  # 같은 판은 캐시 재사용, 발급마다 mtime 갱신


def test_archive_errors(tmp_path: Path) -> None:
    cat = make(tmp_path)
    with pytest.raises(CatalogError) as e:
        cat.get_skill_archive("nope")
    assert e.value.code == ErrorCode.NOT_FOUND
    with pytest.raises(CatalogError) as e:
        cat.get_skill_archive("alpha", "f" * 40)
    assert e.value.code == ErrorCode.UNKNOWN_VERSION
    small = make(tmp_path / "small", limits=Limits(archive_bytes=100))
    with pytest.raises(CatalogError) as e:
        small.get_skill_archive("alpha")
    assert e.value.code == ErrorCode.INPUT_LIMIT
    assert not list((tmp_path / "small" / "archives").glob("*")) if (tmp_path / "small" / "archives").exists() else True  # 부분 파일 없음


def test_corrupt_or_oversized_cache_is_rebuilt(tmp_path: Path) -> None:
    cat = make(tmp_path)
    info = cat.get_skill_archive("alpha")
    info.path.write_bytes(b"corrupt")  # 사이드카와 어긋남 → 다시 만든다
    assert cat.get_skill_archive("alpha") == info
    info.path.write_bytes(b"x" * (info.size + 1))
    (tmp_path / "archives" / f"{info.sha}.tar.sha256").write_text("v2 " + hashlib.sha256(b"x" * (info.size + 1)).hexdigest())
    small = Catalog(FakeStore({"alpha": SKILL}), FakeValidator(), MemoryFacts(), workdir=tmp_path, limits=Limits(archive_bytes=info.size))  # type: ignore[arg-type]
    assert small.rebuild().ready
    assert small.get_skill_archive("alpha") == info  # 상한을 넘는 캐시는 믿지 않고 다시 만든다
    (tmp_path / "archives" / f"{info.sha}.tar.sha256").write_text("v1 " + info.sha256)  # 옛 생성 규칙의 캐시 → 자기 일관적이어도 다시 만든다
    assert cat.get_skill_archive("alpha") == info and (tmp_path / "archives" / f"{info.sha}.tar.sha256").read_text().startswith("v2 ")


def test_concurrent_mints_agree_with_served_bytes(tmp_path: Path) -> None:
    import threading

    from harness_catalog_core.model import ArchiveInfo

    cat = make(tmp_path)
    barrier = threading.Barrier(8)
    infos: list[ArchiveInfo] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def mint() -> None:
        try:
            barrier.wait(timeout=5)  # 전부 동시에 출발 — 캐시 미스가 겹치게
            info = cat.get_skill_archive("alpha")
            with lock:
                infos.append(info)
        except BaseException as e:  # noqa: BLE001 — 테스트: 스레드 예외를 모아 단언한다
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=mint) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(infos) == 8 and len({(i.sha256, i.size) for i in infos}) == 1
    assert hashlib.sha256(infos[0].path.read_bytes()).hexdigest() == infos[0].sha256


def test_evict_archives_by_last_issue_time(tmp_path: Path) -> None:
    import os
    import time

    cat = make(tmp_path)
    info = cat.get_skill_archive("alpha")
    now = time.time()
    assert cat.evict_archives(now=now) == 0  # 방금 발급 → 보존
    os.utime(info.path, (now - 1000, now - 1000))
    assert cat.evict_archives(now=now) == 1 and not info.path.exists() and not (tmp_path / "archives" / f"{info.sha}.tar.sha256").exists()
    again = cat.get_skill_archive("alpha")
    assert again.sha256 == info.sha256  # 지워져도 같은 바이트로 다시 만든다
    assert cat.evict_archives(retention_seconds=0) == 1  # 기동 때 전부
