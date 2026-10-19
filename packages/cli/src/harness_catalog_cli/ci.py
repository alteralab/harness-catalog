"""CI 논리 — 기준 커밋, 바뀐 스킬, 하네스 자격, harbor 호출. 템플릿 워크플로(GitHub·GitLab)는 배선만 하고 `harness-catalog ci …`로 이것을 부른다.

워크플로 YAML에 박혀 있던 셸(호스트마다 두 벌, 잡마다 복제)을 한 곳으로 모아 pytest가 검사한다(DESIGN §11 2026-10-10, distribution D24).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

HARBOR_VERSION = "0.24.0"
ORACLE = "oracle"  # 모델 없이 solution/solve.sh 를 그대로 — 과제가 풀리는지·검증기가 끝 상태를 받는지만 본다. 자격·Langfuse 불필요(CI 의 기본, §11 2026-10-18)
ZERO_SHA = "0" * 40
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git의 빈 트리(SHA-1 저장소). 브랜치 생성 push의 기준 — 선행 커밋이 없다
CI_MARKERS = ("GITHUB_ACTIONS", "GITLAB_CI")
SKILL_REF_ENV = "HARNESS_SKILL_REF"
CATALOG_NAME_ENV = "HARNESS_CATALOG_NAME"

GitRun = Callable[..., "subprocess.CompletedProcess[str]"]


class CIError(Exception):
    """기준 커밋을 정할 수 없거나 git이 실패했다 — 조용히 좁히지 않고 검사기 실패(종료 2)로 끝낸다."""


def git_runner(repo: Path) -> GitRun:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)

    return run


def commit_exists(run: GitRun, sha: str) -> bool:
    return bool(sha) and sha != ZERO_SHA and run("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def _github_event_before(env: Mapping[str, str]) -> str:
    path = env.get("GITHUB_EVENT_PATH", "")
    if not path or not Path(path).is_file():
        return ""
    try:
        payload: object = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(cast("dict[str, object]", payload).get("before") or "")


def empty_tree(run: GitRun) -> str:
    """빈 트리 객체 id. SHA-1 저장소는 상수를 확인해 쓰고, 아니면(SHA-256) git이 계산한다. 어느 쪽도 안 되면 CIError(잘못된 해시로 조용히 넘어가지 않는다)."""
    if run("cat-file", "-t", EMPTY_TREE).stdout.strip() == "tree":
        return EMPTY_TREE
    out = run("hash-object", "-t", "tree", "/dev/null")
    oid = out.stdout.strip()
    if out.returncode == 0 and len(oid) in (40, 64) and all(c in "0123456789abcdef" for c in oid):
        return oid
    raise CIError(f"cannot determine the empty tree id: {out.stderr.strip() or oid}")


def is_branch_creation(base: str, run: GitRun) -> bool:
    """base_commit이 빈 트리를 돌려준 경우(정확 비교) — 선행 이력이 없어 항목 5·9(이력 대조)는 건너뛰고, 변경은 HEAD 전체다."""
    return base == empty_tree(run)


def base_commit(env: Mapping[str, str], run: GitRun) -> str:
    """항목 5·9의 기준 커밋(DESIGN §2.1). 조용히 좁히지 않는다 — CI 안에서 정할 수 없으면 CIError.

    PR/MR: 대상 브랜치와의 merge-base(없으면 CIError).
    push: push 전 커밋. 로컬에 없으면 origin에서 그 커밋을 fetch해 본다(force-push 뒤). 그래도 없으면 CIError.
    push 전 커밋이 0(브랜치 생성 = 첫 push): 빈 트리 — 루트 커밋의 변경까지 전부 '바뀐 것'이고 이력 대조는 건너뛴다.
    CI 표지(GITHUB_ACTIONS·GITLAB_CI)가 있는데 후보가 하나도 없으면(이벤트 파일 깨짐 등) CIError.
    CI 표지가 없으면(로컬 실행): HEAD~1, 첫 커밋이면 HEAD.
    """
    if env.get("GITHUB_EVENT_NAME") == "pull_request" and env.get("GITHUB_BASE_REF"):
        mb = run("merge-base", f"origin/{env['GITHUB_BASE_REF']}", "HEAD")
        if mb.returncode == 0 and mb.stdout.strip():
            return mb.stdout.strip()
        raise CIError(f"merge-base with origin/{env['GITHUB_BASE_REF']} failed (fetch-depth 0 needed): {mb.stderr.strip()}")
    for candidate in (env.get("CI_MERGE_REQUEST_DIFF_BASE_SHA", ""), _github_event_before(env), env.get("CI_COMMIT_BEFORE_SHA", "")):
        if not candidate:
            continue
        if candidate == ZERO_SHA:
            return empty_tree(run)
        if commit_exists(run, candidate):
            return candidate
        run("fetch", "-q", "origin", candidate)
        if commit_exists(run, candidate):
            return candidate
        raise CIError(f"base commit {candidate[:12]} is not reachable (history rewritten?) — refusing to narrow the check")
    if any(env.get(k) for k in CI_MARKERS):
        raise CIError("running in CI but no base candidate (event payload unreadable or base variables missing) — refusing to fall back to HEAD~1")
    prev = run("rev-parse", "--verify", "-q", "HEAD~1")
    if prev.returncode == 0 and prev.stdout.strip():
        return prev.stdout.strip()
    return run("rev-parse", "HEAD").stdout.strip()


def changed_skill_dirs(run: GitRun, base: str, head: str = "HEAD") -> tuple[str, ...]:
    """base..head 사이에 바뀐 `skills/<name>` 디렉토리(정렬, 중복 없음). git이 실패하면 CIError — 빈 튜플은 '정말 변경 없음'만 뜻한다."""
    out = run("diff", "--name-only", base, head, "--", "skills")
    if out.returncode != 0:
        raise CIError(f"git diff {base[:12]}..{head} failed: {out.stderr.strip()}")
    return tuple(sorted({"/".join(p.split("/")[:2]) for p in out.stdout.split() if p.count("/") >= 2}))


def missing_credentials(agent: str, env: Mapping[str, str]) -> str | None:
    """하네스마다 Harbor 에이전트 구현이 읽는 변수 그대로(DESIGN §5.1). 갖춰졌으면 None, 아니면 무엇이 필요한지 한 줄."""

    def has(key: str) -> bool:
        return bool(env.get(key))

    match agent:
        case "claude-code":
            ok = (has("CLAUDE_CODE_OAUTH_TOKEN") and env.get("CLAUDE_FORCE_OAUTH") == "1") or has("ANTHROPIC_API_KEY")
            need = "CLAUDE_CODE_OAUTH_TOKEN+CLAUDE_FORCE_OAUTH=1 또는 ANTHROPIC_API_KEY"
        case "codex":
            auth_json = Path(env.get("CODEX_AUTH_JSON_PATH") or Path(env.get("HOME", "~")).expanduser() / ".codex" / "auth.json")
            ok = has("OPENAI_API_KEY") or (env.get("CODEX_FORCE_AUTH_JSON") == "1" and auth_json.is_file())
            need = "OPENAI_API_KEY 또는 CODEX_FORCE_AUTH_JSON=1 + auth.json"
        case "cursor-cli":
            ok, need = has("CURSOR_API_KEY"), "CURSOR_API_KEY"
        case "gemini-cli":
            ok, need = has("GEMINI_API_KEY") or has("GEMINI_FORCE_OAUTH"), "GEMINI_API_KEY 또는 GEMINI_FORCE_OAUTH"
        case _:
            return f"unknown agent {agent} — 자격 규칙이 없다"
    return None if ok else f"{agent}: {need}"


def missing_langfuse(env: Mapping[str, str]) -> str | None:
    missing = [k for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST") if not env.get(k)]
    return f"Langfuse keys missing: {' '.join(missing)}" if missing else None


def harbor_argv(evals_dir: str, agent: str, *, skill_dir: str | None, cli_version: str, code_repo_url: str) -> tuple[str, ...]:
    """harbor run 한 번의 argv. 플러그인은 cli와 같은 태그에서 받는다(distribution D22: 이미지 밖 배포물은 전부 같은 태그)."""
    if agent == ORACLE:  # 스킬 주입도 Langfuse 도 없다 — Oracle 은 --skill 을 받지 않는다(Harbor 0.24 실측)
        return ("uvx", "--from", f"harbor=={HARBOR_VERSION}", "harbor", "run", "--path", evals_dir, "--agent", ORACLE, "--env", "docker")
    plugin = f"harbor-langfuse @ git+{code_repo_url}@v{cli_version}#subdirectory=packages/harbor-langfuse"
    argv = ["uvx", "--from", f"harbor=={HARBOR_VERSION}", "--with", plugin, "harbor", "run", "--path", evals_dir, "--agent", agent, "--env", "docker", "--plugin", "harbor_langfuse:LangfusePlugin"]
    if skill_dir is not None:
        argv += ["--skill", skill_dir]
    return tuple(argv)


def evals_plan(repo: Path, dirs: tuple[str, ...], agent: str, *, cli_version: str, code_repo_url: str) -> tuple[tuple[str, ...], ...]:
    """바뀐 스킬마다 evals/가 있으면: oracle 은 잡 하나, 모델 에이전트는 두 잡 — 스킬 있이, 없이(baseline). 순서는 결정적."""
    plan: list[tuple[str, ...]] = []
    for d in dirs:
        if not (repo / d / "evals").is_dir():
            continue
        if agent == ORACLE:
            plan.append(harbor_argv(f"{d}/evals", ORACLE, skill_dir=None, cli_version=cli_version, code_repo_url=code_repo_url))
            continue
        plan.append(harbor_argv(f"{d}/evals", agent, skill_dir=f"./{d}", cli_version=cli_version, code_repo_url=code_repo_url))
        plan.append(harbor_argv(f"{d}/evals", agent, skill_dir=None, cli_version=cli_version, code_repo_url=code_repo_url))
    return tuple(plan)


def harbor_env(env: Mapping[str, str], run: GitRun, repo: Path) -> dict[str, str]:
    """플러그인이 읽는 둘을 채운다: HARNESS_SKILL_REF(스킬 원천 커밋 = HEAD), HARNESS_CATALOG_NAME(호스트 변수 또는 디렉토리 이름)."""
    out = dict(env)
    out.setdefault(SKILL_REF_ENV, run("rev-parse", "HEAD").stdout.strip())
    if not out.get(CATALOG_NAME_ENV):
        gh = env.get("GITHUB_REPOSITORY", "")
        out[CATALOG_NAME_ENV] = env.get("CI_PROJECT_NAME") or (gh.rsplit("/", 1)[-1] if gh else repo.resolve().name)
    return out


Exec = Callable[[list[str], Path, Mapping[str, str]], int]


def _exec(argv: list[str], cwd: Path, env: Mapping[str, str]) -> int:
    return subprocess.run(argv, cwd=cwd, env=dict(env), check=False).returncode


def run_plan(plan: tuple[tuple[str, ...], ...], cwd: Path, env: Mapping[str, str], *, execute: Exec = _exec, log: Callable[[str], None] = print) -> int:
    """잡을 순서대로 전부 돌리고(하나가 실패해도 계속) 실패 수를 돌려준다."""
    failed = 0
    for argv in plan:
        log("$ " + " ".join(argv))
        if execute(list(argv), cwd, env) != 0:
            failed += 1
    return failed
