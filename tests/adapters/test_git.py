from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness_catalog_core.adapters.git import GitStore
from harness_catalog_core.model import ContentError, ReadyReason
from tests.conftest import CatalogRepo, commit_all, git, write_skill


def test_fetch_list_read_export(tmp_path: Path, catalog_repo: CatalogRepo) -> None:
    store = GitStore(tmp_path / "work" / "clone", str(catalog_repo.path))
    head = store.fetch()
    assert head == catalog_repo.head and store.head() == head
    trees = store.list_skill_trees(head)
    assert [t.name for t in trees] == ["pin-skill", "yt-subs"]
    yt = trees[1]
    assert yt.commit_sha == head and len(yt.tree_sha) == 40
    files = store.list_tree(yt.tree_sha)
    assert {f.path for f in files if f.kind == "blob"} == {"SKILL.md", "scripts/fetch.py", "references/notes.md"}
    assert {f.path for f in files if f.kind == "tree"} == {"scripts", "references"}
    assert store.read_blob(yt.tree_sha, "scripts/fetch.py") == b"print('hi')\n"
    assert store.read_blob(head, ".harness-catalog") == b"layout = 1\n"
    assert store.read_blob(head, "nope") is None
    dest = tmp_path / "export"
    dest.mkdir()
    store.export_tree(yt.tree_sha, dest)
    assert (dest / "SKILL.md").exists() and (dest / "scripts" / "fetch.py").read_bytes() == b"print('hi')\n"


def test_history_and_versions(tmp_path: Path, catalog_repo: CatalogRepo) -> None:
    repo = catalog_repo.path
    store = GitStore(tmp_path / "work" / "clone", str(repo))
    first = store.fetch()
    old_tree = next(t for t in store.list_skill_trees(first) if t.name == "yt-subs").tree_sha
    write_skill(repo, "yt-subs", "Extract YouTube subtitles, v2.")
    (repo / "skills" / "pin-skill" / "SKILL.md").unlink()
    (repo / "skills" / "pin-skill").rmdir()
    second = commit_all(repo, "update yt-subs, retire pin-skill")
    assert store.fetch() == second
    assert store.deleted_skill_names(second) == frozenset({"pin-skill"})
    assert store.resolve_version("yt-subs", old_tree, second) == first
    assert store.resolve_version("yt-subs", "f" * 40, second) is None


def test_no_main_branch_and_unreachable(tmp_path: Path) -> None:
    repo = tmp_path / "nomain"
    repo.mkdir()
    git(tmp_path, "init", "-q", "-b", "develop", str(repo))
    (repo / "x").write_text("x")
    commit_all(repo, "x")
    store = GitStore(tmp_path / "w1" / "clone", str(repo))
    with pytest.raises(ContentError) as e:
        store.fetch()
    assert e.value.reason is ReadyReason.NO_MAIN_BRANCH
    bad = GitStore(tmp_path / "w2" / "clone", str(tmp_path / "does-not-exist"))
    with pytest.raises(ContentError) as e2:
        bad.fetch()
    assert e2.value.reason is ReadyReason.REPO_UNREACHABLE


def test_local_mode_resolves_index(catalog_repo: CatalogRepo) -> None:
    store = GitStore.local(catalog_repo.path)
    assert store.resolve("HEAD") == catalog_repo.head
    write_skill(catalog_repo.path, "staged", "staged only")
    git(catalog_repo.path, "add", "-A")
    tree = store.resolve("INDEX")
    assert tree != catalog_repo.head and any(t.name == "staged" for t in store.list_skill_trees(tree))


def test_archive_skill_is_deterministic_capped_and_clean(tmp_path: Path, catalog_repo: CatalogRepo) -> None:
    import hashlib
    import io
    import tarfile

    import pytest

    from harness_catalog_core.model import ArchiveTooLarge, ContentError

    store = GitStore(tmp_path / "work" / "clone", str(catalog_repo.path))
    head = store.fetch()
    tree = next(t for t in store.list_skill_trees(head) if t.name == "yt-subs")
    a = tmp_path / "a.tar"
    n = store.archive_skill(head, "yt-subs", a, max_bytes=10_000_000)
    assert n == a.stat().st_size > 0
    with tarfile.open(fileobj=io.BytesIO(a.read_bytes())) as tar:
        names = {m.name for m in tar.getmembers() if m.isfile()}
    assert names == {e.path for e in store.list_tree(tree.tree_sha) if e.kind != "tree"}
    b = tmp_path / "b.tar"  # 결정성은 아래 "항목 mtime == 커밋 시각" 단언이 잡는다(tree-ish만 주면 생성 시각이 들어가 어긋난다 — 실측). 시간을 기다릴 필요가 없다
    store.archive_skill(head, "yt-subs", b, max_bytes=10_000_000)
    assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(a.read_bytes())) as tar:
        commit_time = int(subprocess.run(["git", "-C", str(catalog_repo.path), "show", "-s", "--format=%ct", head], capture_output=True, text=True, check=True).stdout.strip())
        assert {m.mtime for m in tar.getmembers()} == {commit_time}
    with pytest.raises(ArchiveTooLarge):
        store.archive_skill(head, "yt-subs", tmp_path / "c.tar", max_bytes=100)
    with pytest.raises(ContentError):
        store.archive_skill(head, "does-not-exist", tmp_path / "d.tar", max_bytes=10_000_000)
    with pytest.raises(ContentError):
        store.archive_skill("f" * 40, "yt-subs", tmp_path / "e.tar", max_bytes=10_000_000)
    assert sorted(p.name for p in tmp_path.glob("*.tar")) == ["a.tar", "b.tar"]  # 실패 때 임시 파일을 남기지 않는다

