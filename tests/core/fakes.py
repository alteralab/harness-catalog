"""가짜 어댑터: 포트 시그니처만 지킨다. 스킬·도구·MCP 서버 레코드를 같은 모양(root/<name>/{files})으로 든다."""

from __future__ import annotations

import io
import tarfile
from collections.abc import Callable, Sequence
from pathlib import Path

from harness_catalog_core.model import ArchiveTooLarge, ContentError, IndexOutcome, IndexSnapshot, ReadyReason, Root, SkillProps, SkillReport, SkillTree, TreeEntry

Files = dict[str, bytes]


class FakeStore:
    """메모리 저장소: 커밋 하나, 뿌리 셋(skills·tools·mcp-servers). 파일은 {name: {path: bytes}}."""

    def __init__(self, skills: dict[str, Files], *, tools: dict[str, Files] | None = None, servers: dict[str, Files] | None = None, marker: bytes | None = b"layout = 1\n", extra_top: tuple[str, ...] = (".github/workflows/check.yml", ".pre-commit-config.yaml", "README.md")) -> None:
        self.skills = skills
        self.tools: dict[str, Files] = tools or {}
        self.servers: dict[str, Files] = servers or {}
        self.marker = marker
        self.extra_top = extra_top
        self.commit = "c" * 40
        self.fetch_calls = 0
        self.history: dict[tuple[str, str], str] = {}  # (name, tree) -> commit — skills 뿌리
        self.tool_history: dict[tuple[str, str], str] = {}  # (name, tree) -> commit — tools 뿌리
        self.ancestors: set[tuple[str, str]] = set()  # (ancestor, descendant)

    # ---- 뿌리 ----
    def _records(self, root: Root) -> dict[str, Files]:
        return {"skills": self.skills, "tools": self.tools, "mcp-servers": self.servers}[root]

    def tree_of(self, name: str, root: Root = "skills") -> str:
        prefix = {"skills": "", "tools": "7001", "mcp-servers": "5e2e"}[root]  # 같은 이름의 스킬·도구가 다른 tree를 갖게
        return (prefix + name.replace("-", "a") + "0" * 40)[:40]

    def _lookup(self, tree_sha: str) -> tuple[Root, str, Files] | None:
        for root in ("skills", "tools", "mcp-servers"):
            for name, files in self._records(root).items():  # type: ignore[arg-type]
                if self.tree_of(name, root) == tree_sha:  # type: ignore[arg-type]
                    return root, name, files  # type: ignore[return-value]
        return None

    # ---- ContentStore ----
    def fetch(self) -> str:
        self.fetch_calls += 1
        return self.commit

    def head(self) -> str:
        return self.commit

    def read_blob(self, revision: str, path: str) -> bytes | None:
        if revision == self.commit:
            if path == ".harness-catalog":
                return self.marker
            for root in ("skills", "tools", "mcp-servers"):
                if path.startswith(f"{root}/"):
                    _, name, *rest = path.split("/")
                    return self._records(root).get(name, {}).get("/".join(rest))  # type: ignore[arg-type]
            return None
        found = self._lookup(revision)
        return found[2].get(path) if found else None

    def _entries(self, files: Files, prefix: str = "") -> list[TreeEntry]:
        return [TreeEntry(prefix + p, "link" if p.endswith(".lnk") else "blob", ("b" + p)[:40].ljust(40, "0"), len(d)) for p, d in files.items()]

    def list_tree(self, tree_sha: str) -> tuple[TreeEntry, ...]:
        if tree_sha == self.commit:
            top = [TreeEntry(".harness-catalog", "blob", "m" * 40, 11)] if self.marker is not None else []
            top += [TreeEntry(p, "blob", "x" * 40, 1) for p in self.extra_top]
            for root in ("skills", "tools", "mcp-servers"):
                records = self._records(root)  # type: ignore[arg-type]
                if records:
                    top.append(TreeEntry(root, "tree", "s" * 40, 0))
                    for n, files in records.items():  # 실물 ls-tree -r -t처럼 재귀로 낸다
                        top.append(TreeEntry(f"{root}/{n}", "tree", self.tree_of(n, root), 0))  # type: ignore[arg-type]
                        top += self._entries(files, f"{root}/{n}/")
            return tuple(top)
        found = self._lookup(tree_sha)
        return tuple(self._entries(found[2])) if found else ()

    def list_trees(self, commit: str, root: Root) -> tuple[SkillTree, ...]:
        return tuple(SkillTree(n, self.tree_of(n, root), self.commit) for n in sorted(self._records(root)))

    def list_skill_trees(self, commit: str) -> tuple[SkillTree, ...]:
        return self.list_trees(commit, "skills")

    def resolve_version(self, name: str, tree_sha: str, head: str, root: Root = "skills") -> str | None:
        table = self.tool_history if root == "tools" else self.history
        return table.get((name, tree_sha)) if head == self.commit else None

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return ancestor == descendant or (ancestor, descendant) in self.ancestors

    def archive_tree(self, commit: str, root: Root, name: str, dest: Path, *, max_bytes: int) -> int:
        treeish = f"{commit}:{root}/{name}"
        records = self._records(root)
        if name not in records:
            raise ContentError(ReadyReason.REPO_UNREACHABLE, f"no such treeish {treeish}")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for path, data in sorted(records[name].items()):
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

    def archive_skill(self, commit: str, name: str, dest: Path, *, max_bytes: int) -> int:
        return self.archive_tree(commit, "skills", name, dest, max_bytes=max_bytes)

    def export_tree(self, tree_sha: str, dest: Path) -> None:
        found = self._lookup(tree_sha)
        if found is None:
            return
        for p, d in found[2].items():
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
        self.snapshots.append(snapshot)  # 스킬·도구가 한 스냅샷 객체라 "둘 다 구판 또는 둘 다 신판"이 구조로 보장된다
        return IndexOutcome.REPLACED

    def load_embeddings(self, generation: str, /) -> dict[tuple[str, str], tuple[float, ...]] | None:
        if not self.available:
            return None
        out: dict[tuple[str, str], tuple[float, ...]] = {}
        for snap in self.snapshots:
            if snap.embedding_generation == generation:
                for name, sha in [(e.name, e.tree_sha) for e in snap.entries] + [(t.name, t.tree_sha) for t in snap.tools]:
                    if name in snap.embeddings:
                        out[(name, sha)] = snap.embeddings[name]
        return out

    def current_commit(self) -> str | None:
        return self.snapshots[-1].commit_sha if self.snapshots else None


class FakeEmbedder:
    """문서 텍스트를 결정적 2차원 벡터로 — 낱말 '자막' 쪽은 (1,0), '커밋' 쪽은 (0,1). 호출 횟수를 세어 재사용을 검증한다. available=False 면 None(닿지 않음)."""

    def __init__(self, available: bool = True, model: str = "fake-model") -> None:
        self.available = available
        self.model = model
        self.calls: list[list[str]] = []

    @property
    def generation(self) -> str:
        return f"{self.model}/doc1"

    def embed(self, texts: Sequence[str], /) -> list[list[float]] | None:
        self.calls.append(list(texts))
        if not self.available:
            return None
        return [[1.0 if ("자막" in t or "캡션" in t) else 0.1, 1.0 if ("커밋" in t or "commit" in t) else 0.1] for t in texts]
