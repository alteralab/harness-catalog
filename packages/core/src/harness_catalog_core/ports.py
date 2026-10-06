"""요구 포트 셋 = typing.Protocol. 앱은 이 시그니처만 안다."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .model import IndexSnapshot, SkillReport, SkillTree, TreeEntry


class ContentStore(Protocol):
    """For reading skill content: fetch하고 main의 스킬 트리를 읽는다. 쓰기는 없다."""

    def fetch(self) -> str:
        """원격을 받아 main의 커밋 SHA를 돌려준다. 실패는 ContentError."""
        ...

    def head(self) -> str:
        """마지막으로 받은 main의 커밋 SHA. 아직 없으면 ContentError(NO_MAIN_BRANCH)."""
        ...

    def read_blob(self, revision: str, path: str) -> bytes | None:
        """<revision>:<path>의 내용. 없으면 None. revision은 커밋 또는 tree SHA."""
        ...

    def list_tree(self, tree_sha: str) -> tuple[TreeEntry, ...]:
        """tree 아래 전부(재귀). 경로는 tree 기준 상대."""
        ...

    def list_skill_trees(self, commit: str) -> tuple[SkillTree, ...]:
        """커밋의 skills/* 디렉토리마다 (이름, tree SHA, 그 판을 넣은 커밋)."""
        ...

    def deleted_skill_names(self, commit: str) -> frozenset[str]:
        """이력에서 SKILL.md가 지워진 적 있는 스킬 이름 전부(은퇴한 이름)."""
        ...

    def resolve_version(self, name: str, tree_sha: str, head: str) -> str | None:
        """skills/<name>이 그 tree SHA였던 커밋. 현재 판도 이력의 판도 아니면 None."""
        ...

    def export_tree(self, tree_sha: str, dest: Path) -> None:
        """tree를 디렉토리로 풀어 놓는다(검증기가 파일 시스템을 읽으므로)."""
        ...


class SkillValidator(Protocol):
    """For validating a skill: 스펙 준수와 시크릿 스캔. 검사기 실패는 ValidatorFailure."""

    def inspect(self, skill_dir: Path) -> SkillReport:
        """스펙 준수 판정과, 통과했으면 frontmatter 속성."""
        ...

    def scan_secrets(self, skill_dir: Path) -> tuple[str, ...]:
        """검출된 비밀(파일·룰) 메시지들. 비면 통과."""
        ...


class FactStore(Protocol):
    """For recording facts: 인덱스를 커밋 단위로 바꾸고 검색한다."""

    def replace_index(self, snapshot: IndexSnapshot, /) -> bool:
        """스냅샷으로 통째로 바꾼다. 더 오래된 커밋이면 False(거부)."""
        ...

    def search(self, query: str, limit: int, /) -> tuple[str, ...] | None:
        """순위 있는 이름 목록. 닿지 않으면 None(메모리 사본으로 깎아서 답한다)."""
        ...
