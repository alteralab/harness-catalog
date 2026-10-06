"""git 어댑터: bare 클론을 유지하고 fetch·읽기만 한다. commit·push는 없다. git CLI 서브프로세스."""

from __future__ import annotations

import io
import os
import shlex
import shutil
import subprocess
import tarfile
import threading
from collections.abc import Mapping
from pathlib import Path

from ..model import ContentError, ReadyReason, SkillTree, TreeEntry

MAIN_REF = "refs/remotes/origin/main"


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
        # 로컬 경로(file://)의 저장소가 다른 uid 소유여도 읽는다(컨테이너의 bind mount). 레지스트리는 설정된 저장소만 읽는다
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"})
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

    def list_skill_trees(self, commit: str) -> tuple[SkillTree, ...]:
        try:
            out = self._text("ls-tree", "-z", f"{commit}:skills")
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
                last = self._text("log", "-1", "--format=%H", commit, "--", f"skills/{name}").strip()
            except GitError:
                last = ""  # 트리 객체(스테이징)는 이력이 없다
            trees.append(SkillTree(name, sha, last or commit))
        return tuple(trees)

    def deleted_skill_names(self, commit: str) -> frozenset[str]:
        """전체 이력이 필요하다: 얕은 클론이거나 log가 실패하면 빈 집합이 아니라 ContentError(fail-closed)."""
        if self._text("rev-parse", "--is-shallow-repository").strip() == "true":
            raise ContentError(ReadyReason.REPO_UNREACHABLE, "shallow clone: full history required for retired-name check")
        out = self._text("log", "--diff-filter=D", "--name-only", "--format=", "--end-of-options", commit, "--", "skills/*/SKILL.md")
        names = {line.split("/")[1] for line in out.splitlines() if line.startswith("skills/") and line.count("/") >= 2}
        return frozenset(names)

    def resolve_version(self, name: str, tree_sha: str, head: str) -> str | None:
        commits = self._text("log", "--format=%H", head, "--", f"skills/{name}").split()
        for c in commits:
            try:
                sha = self._text("rev-parse", f"{c}:skills/{name}").strip()
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

    def export_tree(self, tree_sha: str, dest: Path) -> None:
        with self._lock:
            data = self._git("archive", "--format=tar", tree_sha, binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")
