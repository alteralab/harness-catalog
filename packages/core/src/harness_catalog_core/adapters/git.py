"""git 어댑터: bare 클론을 유지하고 fetch·읽기만 한다. commit·push는 없다. git CLI 서브프로세스."""

from __future__ import annotations

import io
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path
from typing import IO, TYPE_CHECKING

from ..model import (
    ArchiveTooLarge,
    ContentError,
    ReadyReason,
    Root,
    SkillTree,
    TreeEntry,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

MAIN_REF = "refs/remotes/origin/main"


def _stream_archive(proc: subprocess.Popen[bytes], out: IO[bytes], err: IO[bytes], *, max_bytes: int, treeish: str) -> int:
    """자식의 stdout을 파일로 옮기고 쓴 바이트 수를 돌려준다.

    상한을 넘으면 기다리지 않고 바로 죽이고, 어떤 경로로 나가도 자식을 회수한다. 실패한 git의 사유는 stderr 파일에서 읽는다(Codex 리뷰 2026-10-11).
    """
    assert proc.stdout is not None
    total = 0
    streamed = False
    try:
        while chunk := proc.stdout.read(65536):
            total += len(chunk)
            if total > max_bytes:
                raise ArchiveTooLarge(treeish, max_bytes)
            out.write(chunk)
        streamed = True
    finally:
        proc.stdout.close()
        if not streamed and proc.poll() is None:
            proc.kill()  # 상한 초과·쓰기 실패·취소 — 어느 쪽이든 자식을 기다리지 않고 바로 끝낸다
        rc = proc.wait(timeout=60 if not streamed else 600)
    if rc != 0 and streamed:
        err.seek(0)
        raise GitError(["archive", treeish], err.read().decode(errors="replace"))
    return total


class GitError(ContentError):
    """git 명령 실패. 앱은 ContentError로 받는다(저장소를 읽지 못한 것)."""

    def __init__(self, args: list[str], stderr: str) -> None:
        super().__init__(ReadyReason.REPO_UNREACHABLE, f"git {' '.join(args)}: {stderr.strip()}")
        self.stderr = stderr


class GitStore:
    """ContentStore 구현. 클론 잠금 하나로 fetch와 export를 직렬화한다.

    두 모드: (1) 레지스트리 — remote_url을 bare 클론으로 받아 main을 fetch한다. (2) CLI — 이미 있는 저장소(git_dir)를 그 자리에서 읽는다(fetch 없음).
    """

    def __init__(self, git_dir: Path, remote_url: str | None = None, deploy_key: str = "") -> None:
        self._url = remote_url
        self._dir = git_dir
        self._key_path: Path | None = None
        self._config_path: Path | None = None
        if remote_url is not None:
            # 레지스트리 모드의 전용 global git 설정. safe.directory는 보호 범위(system·global)에서만 읽히고, 로컬 전송(file://)의
            # upload-pack 자식은 -c·GIT_CONFIG_*를 받지 않는다(git 2.47 실측) — 다른 uid가 소유한 볼륨의 저장소를 읽으려면 이 파일이 필요하다.
            git_dir.parent.mkdir(parents=True, exist_ok=True)
            self._config_path = git_dir.parent / "gitconfig"
            self._config_path.write_text("[safe]\n\tdirectory = *\n")
        if deploy_key:
            keydir = git_dir.parent / "ssh"
            keydir.mkdir(parents=True, exist_ok=True, mode=0o700)
            keydir.chmod(0o700)
            self._key_path = keydir / "deploy_key"
            self._key_path.touch(mode=0o600, exist_ok=True)
            self._key_path.chmod(0o600)
            self._key_path.write_text(deploy_key.rstrip("\n") + "\n")
        self._lock = threading.Lock()

    def close(self) -> None:
        """deploy key 파일을 지운다(프로세스 종료 시)."""
        if self._key_path is not None and self._key_path.exists():
            self._key_path.unlink()

    @classmethod
    def local(cls, repo_root: Path) -> GitStore:
        return cls(repo_root)

    def resolve(self, revision: str) -> str:
        """커밋·브랜치·태그 이름 → 커밋 SHA. 'INDEX'는 스테이징된 트리(write-tree)."""
        if revision == "INDEX":
            return self._text("write-tree").strip()
        try:
            return self._text("rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}").strip()
        except GitError as e:
            raise ContentError(ReadyReason.NO_MAIN_BRANCH, f"{revision}: {e.stderr.strip()}") from e

    # ---- 내부 ----
    def _env(self) -> Mapping[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
        env["GIT_TERMINAL_PROMPT"] = "0"
        # 레지스트리 모드에서만 전용 global 설정(safe.directory=*)을 쓴다. CLI(check)는 사용자의 ~/.gitconfig를 그대로 둔다
        if self._config_path is not None:
            env["GIT_CONFIG_GLOBAL"] = str(self._config_path)
        if self._key_path is not None:
            env["GIT_SSH_COMMAND"] = f"ssh -i {shlex.quote(str(self._key_path))} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
        return env

    def _git(self, *args: str, binary: bool = False) -> bytes:
        cmd = ["git", "-C", str(self._dir), *args]
        proc = subprocess.run(cmd, capture_output=True, env=self._env(), check=False, timeout=600)
        if proc.returncode != 0:
            raise GitError(list(args), proc.stderr.decode(errors="replace"))
        return proc.stdout if binary else proc.stdout

    def _text(self, *args: str) -> str:
        return self._git(*args).decode("utf-8", errors="replace")

    def _ensure_clone(self) -> None:
        if self._url is None or (self._dir / "HEAD").exists():
            return
        if self._dir.exists():
            shutil.rmtree(self._dir)
        self._dir.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(["git", "clone", "--bare", "--no-tags", self._url, str(self._dir)], capture_output=True, env=self._env(), check=False, timeout=600)
        if proc.returncode != 0:
            raise ContentError(ReadyReason.REPO_UNREACHABLE, proc.stderr.decode(errors="replace").strip())

    # ---- ContentStore ----
    def fetch(self) -> str:
        if self._url is None:
            return self.resolve("HEAD")
        with self._lock:
            self._ensure_clone()
            try:
                self._git("fetch", "--prune", "--no-tags", "origin", f"+refs/heads/main:{MAIN_REF}")
            except GitError as e:
                reason = ReadyReason.NO_MAIN_BRANCH if "couldn't find remote ref" in e.stderr else ReadyReason.REPO_UNREACHABLE
                raise ContentError(reason, e.stderr.strip()) from e
            return self.head()

    def head(self) -> str:
        try:
            return self._text("rev-parse", "--verify", f"{MAIN_REF}^{{commit}}").strip()
        except GitError as e:
            raise ContentError(ReadyReason.NO_MAIN_BRANCH, "main not fetched yet") from e

    def read_blob(self, revision: str, path: str) -> bytes | None:
        try:
            return self._git("cat-file", "blob", f"{revision}:{path}", binary=True)
        except GitError:
            return None

    def list_tree(self, tree_sha: str) -> tuple[TreeEntry, ...]:
        try:
            out = self._text("ls-tree", "-r", "-t", "-l", "-z", tree_sha)  # -t: 디렉토리 항목도 낸다
        except GitError:
            return ()
        entries: list[TreeEntry] = []
        for rec in out.split("\0"):
            if not rec:
                continue
            meta, _, path = rec.partition("\t")
            mode, kind, sha, size = meta.split()
            k = "link" if mode == "120000" else kind
            entries.append(TreeEntry(path, k, sha, int(size) if size != "-" else 0))
        return tuple(entries)

    def list_trees(self, commit: str, root: Root) -> tuple[SkillTree, ...]:
        """`<root>/` 바로 아래 디렉토리마다 판(tree)과 그 판을 넣은 커밋. root는 닫힌 Literal이라 pathspec은 외부 입력이 아니다."""
        try:
            out = self._text("ls-tree", "-z", f"{commit}:{root}")
        except GitError:
            return ()
        trees: list[SkillTree] = []
        for rec in out.split("\0"):
            if not rec:
                continue
            meta, _, name = rec.partition("\t")
            _, kind, sha = meta.split()
            if kind != "tree":
                continue
            try:
                last = self._text("log", "-1", "--format=%H", commit, "--", f"{root}/{name}").strip()
            except GitError:
                last = ""  # 트리 객체(스테이징)는 이력이 없다
            trees.append(SkillTree(name, sha, last or commit))
        return tuple(trees)

    def list_skill_trees(self, commit: str) -> tuple[SkillTree, ...]:
        return self.list_trees(commit, "skills")

    def resolve_version(self, name: str, tree_sha: str, head: str, root: Root = "skills") -> str | None:
        commits = self._text("log", "--format=%H", head, "--", f"{root}/{name}").split()
        for c in commits:
            try:
                sha = self._text("rev-parse", f"{c}:{root}/{name}").strip()
            except GitError:
                continue
            if sha == tree_sha:
                return c
        return None

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        if ancestor == descendant:
            return True
        proc = subprocess.run(["git", "-C", str(self._dir), "merge-base", "--is-ancestor", "--end-of-options", ancestor, descendant], capture_output=True, env=self._env(), check=False, timeout=60)
        if proc.returncode in (0, 1):
            return proc.returncode == 0
        # 1 = 자손 아님. 그 밖(객체 없음·손상)은 되감기로 오인하지 않고 fail-closed
        raise ContentError(ReadyReason.REPO_UNREACHABLE, f"merge-base failed: {proc.stderr.decode(errors='replace').strip()}")

    def archive_skill(self, commit: str, name: str, dest: Path, *, max_bytes: int) -> int:
        return self.archive_tree(commit, "skills", name, dest, max_bytes=max_bytes)

    def archive_tree(self, commit: str, root: Root, name: str, dest: Path, *, max_bytes: int) -> int:
        """`git archive --format=tar --mtime=@<commit time> <commit>:<root>/<name>`을 파일로 스트리밍한다(git ≥ 2.42).

        상한을 넘으면 프로세스를 죽이고 임시 파일을 지운다. stderr는 파일로 받아 파이프 교착이 없고, 어떤 경로로 나가도 자식을 회수한다(Codex 리뷰 2026-10-11).
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            when = self._text("show", "-s", "--format=%ct", "--end-of-options", commit).strip()
            if not when.isdigit():
                raise GitError(["show", commit], "no commit time")
            treeish = f"{commit}:{root}/{name}"
            fd, tmp = tempfile.mkstemp(prefix=".archive.", suffix=".tar", dir=dest.parent)
            total = 0
            proc: subprocess.Popen[bytes] | None = None
            try:
                with tempfile.TemporaryFile() as err, os.fdopen(fd, "wb") as out:
                    fd = -1
                    # 바이트가 환경에 매이지 않게: tar.umask·속성 파일(export-ignore 등)·전역/시스템 설정을 고정한다
                    proc = subprocess.Popen(
                        ["git", "-C", str(self._dir), "-c", "tar.umask=0022", "-c", "core.attributesfile=/dev/null",
                         "archive", "--format=tar", f"--mtime=@{when}", "--end-of-options", treeish],
                        stdout=subprocess.PIPE, stderr=err, env=self._env(),  # _env()의 GIT_CONFIG_GLOBAL(safe.directory)은 그대로 — 바이트에 걸리는 설정은 -c로 고정했다
                    )
                    total = _stream_archive(proc, out, err, max_bytes=max_bytes, treeish=treeish)
                os.replace(tmp, dest)
                return total
            except BaseException:
                if fd != -1:
                    os.close(fd)
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=60)
                Path(tmp).unlink(missing_ok=True)
                raise

    def export_tree(self, tree_sha: str, dest: Path) -> None:
        with self._lock:
            data = self._git("archive", "--format=tar", tree_sha, binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")
