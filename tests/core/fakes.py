"""가짜 어댑터: 포트 시그니처만 지킨다."""

from __future__ import annotations

from pathlib import Path

from collections.abc import Callable

from harness_catalog_core.model import IndexOutcome, IndexSnapshot, SkillProps, SkillReport, SkillTree, TreeEntry


class FakeStore:
    """메모리 저장소: 커밋 하나, 스킬 몇 개. 파일은 {name: {path: bytes}}."""

    def __init__(self, skills: dict[str, dict[str, bytes]], *, marker: bytes | None = b"layout = 1\n", extra_top: tuple[str, ...] = (".github/workflows/check.yml", ".pre-commit-config.yaml", "README.md")) -> None:
        self.skills = skills
        self.marker = marker
        self.extra_top = extra_top
        self.commit = "c" * 40
        self.fetch_calls = 0
        self.deleted: frozenset[str] = frozenset()
        self.history: dict[tuple[str, str], str] = {}  # (name, tree) -> commit
        self.ancestors: set[tuple[str, str]] = set()  # (ancestor, descendant)

    def tree_of(self, name: str) -> str:
        return (name + "0" * 40)[:40]

    def fetch(self) -> str:
        self.fetch_calls += 1
        return self.commit

    def head(self) -> str:
        return self.commit

    def read_blob(self, revision: str, path: str) -> bytes | None:
        if revision == self.commit:
            if path == ".harness-catalog":
                return self.marker
            if path.startswith("skills/"):
                _, name, *rest = path.split("/")
                return self.skills.get(name, {}).get("/".join(rest))
            return None
        for name, files in self.skills.items():
            if self.tree_of(name) == revision:
                return files.get(path)
        return None

    def list_tree(self, tree_sha: str) -> tuple[TreeEntry, ...]:
        if tree_sha == self.commit:
            top = [TreeEntry(".harness-catalog", "blob", "m" * 40, 11)] if self.marker is not None else []
            top += [TreeEntry(p, "blob", "x" * 40, 1) for p in self.extra_top]
            if self.skills:
                top.append(TreeEntry("skills", "tree", "s" * 40, 0))
                for n, files in self.skills.items():  # 실물 ls-tree -r -t처럼 재귀로 낸다
                    top.append(TreeEntry(f"skills/{n}", "tree", self.tree_of(n), 0))
                    top += [TreeEntry(f"skills/{n}/{p}", "link" if p.endswith(".lnk") else "blob", ("b" + p)[:40].ljust(40, "0"), len(d)) for p, d in files.items()]
            return tuple(top)
        for name, files in self.skills.items():
            if self.tree_of(name) == tree_sha:
                return tuple(TreeEntry(p, "link" if p.endswith(".lnk") else "blob", ("b" + p)[:40].ljust(40, "0"), len(d)) for p, d in files.items())
        return ()

    def list_skill_trees(self, commit: str) -> tuple[SkillTree, ...]:
        return tuple(SkillTree(n, self.tree_of(n), self.commit) for n in sorted(self.skills))

    def deleted_skill_names(self, commit: str) -> frozenset[str]:
        return self.deleted

    def resolve_version(self, name: str, tree_sha: str, head: str) -> str | None:
        return self.history.get((name, tree_sha))

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return ancestor == descendant or (ancestor, descendant) in self.ancestors

    def archive_skill(self, commit: str, name: str, dest: Path, *, max_bytes: int) -> int:
        import io
        import tarfile

        from harness_catalog_core.model import ArchiveTooLarge, ContentError, ReadyReason

        treeish = f"{commit}:skills/{name}"
        if name not in self.skills:
            raise ContentError(ReadyReason.REPO_UNREACHABLE, f"no such treeish {treeish}")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for path, data in sorted(self.skills[name].items()):
                info = tarfile.TarInfo(path)
                info.size = len(data)
                info.mtime = 1_700_000_000  # 결정적
                tar.addfile(info, io.BytesIO(data))
        data = buf.getvalue()
        if len(data) > max_bytes:
            raise ArchiveTooLarge(treeish, max_bytes)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return len(data)

    def export_tree(self, tree_sha: str, dest: Path) -> None:
        for name, files in self.skills.items():
            if self.tree_of(name) == tree_sha:
                for p, d in files.items():
                    (dest / p).parent.mkdir(parents=True, exist_ok=True)
                    (dest / p).write_bytes(d)


class FakeValidator:
    """SKILL.md의 첫 줄 'name:'·'description:'만 읽는 가짜. 'SECRET'이 든 파일은 비밀로 친다."""

    def __init__(self, reject: frozenset[str] = frozenset()) -> None:
        self.reject = reject

    def inspect(self, skill_dir: Path) -> SkillReport:
        md = (skill_dir / "SKILL.md").read_text() if (skill_dir / "SKILL.md").exists() else ""
        fields: dict[str, str] = {}
        metadata: dict[str, str] = {}
        for line in md.splitlines():
            if line.startswith("name:") or line.startswith("description:"):
                k, _, v = line.partition(":")
                fields[k] = v.strip()
            if line.startswith("  ") and ":" in line:
                k, _, v = line.strip().partition(":")
                metadata[k] = v.strip().strip('"')
        if "name" not in fields or fields["name"] in self.reject:
            return SkillReport(("invalid frontmatter",), None)
        return SkillReport((), SkillProps(fields["name"], fields.get("description", ""), None, metadata))

    def scan_secrets(self, skill_dir: Path) -> tuple[str, ...]:
        return tuple(f"{p.name}: fake-rule" for p in skill_dir.rglob("*") if p.is_file() and b"SECRET" in p.read_bytes())


class MemoryFacts:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.snapshots: list[IndexSnapshot] = []

    def replace_index(self, snapshot: IndexSnapshot, is_descendant: Callable[[str], bool], /) -> IndexOutcome:
        if not self.available:
            return IndexOutcome.UNAVAILABLE
        if self.snapshots and not is_descendant(self.snapshots[-1].commit_sha):
            return IndexOutcome.STALE
        self.snapshots.append(snapshot)
        return IndexOutcome.REPLACED

    def search(self, query: str, limit: int) -> tuple[str, ...] | None:
        return None

    def current_commit(self) -> str | None:
        return self.snapshots[-1].commit_sha if self.snapshots else None
