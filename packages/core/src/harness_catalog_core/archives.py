"""아카이브: 한 판의 tar 발급·캐시·퇴거. `catalog.py` 에서 떼었다(DESIGN §11 2026-10-20 "코드 정리").

떼어 낸 기준은 줄 수가 아니라 **변경 이유**다 — 여기 있는 것은 "캐시 바이트를 언제 믿고 언제 지우는가"(사이드카·형식 판·보존 시간)이고,
재구축 규칙(`indexing.py`)이나 읽기 경로와 함께 바뀌지 않는다. 읽기 경로는 이름→판을 풀어 넘길 뿐이다.

잠금은 **자기 것 하나**(`_lock`)로 캐시 tar 의 확인·생성·해시를 직렬화한다 — 재구축의 잠금과는 다른 잠금이고(아카이브 발급이 빌드를 막지 않는다)
분할 전에도 그랬다(옛 `Catalog._archive_lock`). 인증·서명·전송은 서버 어댑터의 몫이다.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .archive_token import DEFAULT_TTL_SECONDS, LEEWAY_SECONDS
from .model import ArchiveInfo, ArchiveTooLarge, CatalogError, ContentError, ErrorCode

if TYPE_CHECKING:
    from .archive_token import ArchiveKind
    from .ports import ContentStore

MAX_ARCHIVE_BYTES = 20_000_000  # 한 판의 tar 상한(실제 바이트). 넘으면 input_limit
# 캐시 tar 보존: 토큰 수명 + 검증 여유 + 60초. 그 뒤로는 어떤 토큰도 유효하지 않으므로 지워도 안전하다(필요하면 같은 바이트로 다시 만든다)
ARCHIVE_RETENTION_SECONDS = DEFAULT_TTL_SECONDS + LEEWAY_SECONDS + 60
# 캐시 사이드카의 형식 판. 생성 규칙(mtime·umask·속성 고정)이나 캐시 경로 규칙이 바뀌면 올린다 — 옛 규칙으로 만든 캐시는 적중하지 않는다
ARCHIVE_FORMAT_VERSION = "v3"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return float("inf")


def _size_and_sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 16):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


class ArchiveCache:
    """작업 디렉토리의 캐시 tar(`archives/<kind>/<tree>.<commit>.tar` + `.sha256` 사이드카)를 발급하고 퇴거한다."""

    def __init__(self, store: ContentStore, *, workdir: Path, max_bytes: int = MAX_ARCHIVE_BYTES) -> None:
        self._store = store
        self._workdir = workdir
        self._max_bytes = max_bytes
        self._lock = threading.Lock()  # 캐시 tar의 확인·생성·해시를 직렬화한다(동시 발급이 서로의 명세를 깨지 않게)

    def issue(self, kind: ArchiveKind, name: str, tree: str, commit: str) -> ArchiveInfo:
        """한 판의 tar를 캐시에 만들어(있고 온전하면 재사용) 경로·크기·sha256을 돌려준다.

        같은 커밋·트리는 언제 만들어도 같은 바이트(어댑터가 mtime을 커밋 시각으로 고정)라 캐시가 없어지면 다시 만들어도 명세의 sha256이 맞는다.
        캐시 키에 종류와 커밋이 들어가 스킬·도구나 같은 트리의 다른 커밋이 충돌하지 않는다(Codex 설계 리뷰 2026-10-11).
        발급마다 파일 mtime을 갱신해 evict가 "마지막 발급 뒤 보존 시간" 기준으로 지운다.
        """
        archives = self._workdir / "archives" / kind
        dest = archives / f"{tree}.{commit}.tar"
        side = archives / f"{tree}.{commit}.tar.sha256"
        with self._lock:
            info = self._cached(kind, name, tree, commit, dest, side)
            if info is None:
                try:
                    self._store.archive_tree(commit, kind, name, dest, max_bytes=self._max_bytes)
                except ArchiveTooLarge as e:
                    raise CatalogError(ErrorCode.INPUT_LIMIT, f"{name!r} version {tree} is larger than {e.max_bytes} bytes as a tar") from e
                except ContentError as e:
                    raise CatalogError(ErrorCode.NOT_FOUND, f"{name!r}: cannot archive {tree}: {e.detail}") from e
                size, digest = _size_and_sha256(dest)
                side.write_text(f"{ARCHIVE_FORMAT_VERSION} {digest}\n")
                info = ArchiveInfo(name, tree, commit, dest, size, digest, kind)
            os.utime(dest, None)
            return info

    def _cached(self, kind: str, name: str, tree: str, commit: str, dest: Path, side: Path) -> ArchiveInfo | None:
        """캐시 적중 조건: 파일과 사이드카가 있고, 크기가 상한 안이고, sha256이 사이드카와 같다. 아니면 None(다시 만든다)."""
        if not (dest.is_file() and side.is_file()):
            return None
        if dest.stat().st_size > self._max_bytes:
            return None
        try:
            version, _, recorded = side.read_text().strip().partition(" ")
        except OSError:
            return None
        if version != ARCHIVE_FORMAT_VERSION:
            return None
        size, digest = _size_and_sha256(dest)
        if digest != recorded:
            return None
        return ArchiveInfo(name, tree, commit, dest, size, digest, kind)

    def evict(self, *, now: float | None = None, retention_seconds: int = ARCHIVE_RETENTION_SECONDS) -> int:
        """마지막 발급(mtime) 뒤 retention_seconds를 넘은 캐시 tar와 사이드카를 지운다(종류별 하위 디렉토리 전부). 스케줄러가 주기마다 부르고, 기동 때는 retention 0으로 전부 지운다. 지운 파일 수를 돌려준다."""
        archives = self._workdir / "archives"
        if not archives.is_dir():
            return 0
        cutoff = (time.time() if now is None else now) - retention_seconds
        removed = 0
        candidates = [tar for tar in archives.rglob("*.tar") if _mtime(tar) <= cutoff]  # 훑기는 lock 밖에서
        for tar in candidates:
            with self._lock:  # 발급이 방금 mtime을 갱신했을 수 있으니 lock 안에서 다시 보고 지운다
                try:
                    if tar.stat().st_mtime <= cutoff:
                        tar.unlink()
                        Path(str(tar) + ".sha256").unlink(missing_ok=True)
                        removed += 1
                except OSError:
                    pass
        return removed
