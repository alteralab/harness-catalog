"""포트(Protocol) 넷. 앱은 이것만 알고 어댑터는 이것만 구현한다."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .model import IndexOutcome, IndexSnapshot, Root, SkillReport, SkillTree, TreeEntry


class ContentStore(Protocol):
    """git 저장소 읽기. 뿌리(`root`)는 닫힌 Literal — 외부 입력이 pathspec이 되지 않는다(Codex 설계 리뷰 2026-10-11)."""

    def fetch(self) -> str:
        """origin/main을 받아 커밋 SHA를 돌려준다. 실패는 ContentError."""
        ...

    def head(self) -> str:
        """마지막으로 받은 main의 커밋 SHA."""
        ...

    def read_blob(self, revision: str, path: str) -> bytes | None:
        """`revision:path`의 내용. 없으면 None."""
        ...

    def list_tree(self, tree_sha: str) -> tuple[TreeEntry, ...]:
        """트리 하나의 항목 전부(재귀, 디렉토리 포함)."""
        ...

    def list_trees(self, commit: str, root: Root) -> tuple[SkillTree, ...]:
        """`<root>/` 바로 아래 디렉토리마다 (이름, tree SHA, 그 판을 넣은 커밋)."""
        ...

    def list_skill_trees(self, commit: str) -> tuple[SkillTree, ...]:
        """= list_trees(commit, "skills")."""
        ...

    def resolve_version(self, name: str, tree_sha: str, head: str, root: Root = "skills") -> str | None:
        """`<root>/<name>`의 이력에서 tree_sha와 같은 판을 넣은 커밋. 없으면 None."""
        ...

    def export_tree(self, tree_sha: str, dest: Path) -> None:
        """트리를 디렉토리로 푼다(검증기가 파일로 읽는다)."""
        ...

    def archive_tree(self, commit: str, root: Root, name: str, dest: Path, *, max_bytes: int) -> int:
        """`<commit>:<root>/<name>`을 결정적 tar로 dest에 쓴다(같은 커밋·트리면 같은 바이트). 쓴 바이트 수를 돌려준다.

        쓰는 동안 max_bytes를 넘으면 ArchiveTooLarge(부분 파일은 남기지 않는다). 없는 커밋·경로는 ContentError.
        """
        ...

    def archive_skill(self, commit: str, name: str, dest: Path, *, max_bytes: int) -> int:
        """= archive_tree(commit, "skills", name, …)."""
        ...

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """ancestor가 descendant의 조상인가(같으면 True). 판정 불가(객체 없음·손상)는 ContentError — 되감기로 오인하지 않는다."""
        ...


class SkillValidator(Protocol):
    """스킬 디렉토리 하나의 스펙 검증과 시크릿 스캔. 도구·서버 디렉토리의 시크릿 스캔에도 같은 scan_secrets를 쓴다."""

    def inspect(self, skill_dir: Path) -> SkillReport:
        """스펙 위반 메시지들과(비면) 읽은 속성."""
        ...

    def scan_secrets(self, skill_dir: Path) -> tuple[str, ...]:
        """시크릿 발견 목록(파일: 규칙). 검사기가 돌지 못하면 ValidatorFailure."""
        ...


class FactStore(Protocol):
    """PostgreSQL 인덱스. 닿지 않으면 결과로 말한다(예외가 아니라)."""

    def replace_index(self, snapshot: IndexSnapshot, is_descendant: Callable[[str], bool], /) -> IndexOutcome:
        """트랜잭션 하나에 skill_index·tool_index를 통째로 바꾼다(저장된 커밋의 자손일 때만). 결과는 IndexOutcome."""
        ...

    def search(self, query: str, limit: int, /, kind: str = "skills") -> tuple[str, ...] | None:
        """어휘 검색 순위(이름 목록). kind는 skills | tools. DB가 닿지 않으면 None(앱이 메모리 검색으로 떨어진다)."""
        ...

    def current_commit(self) -> str | None:
        """index_state의 커밋. DB가 닿지 않으면 None."""
        ...
