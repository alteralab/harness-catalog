# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""새 스킬의 뼈대를 결정적으로 만든다 — SKILL.md(frontmatter + 본문 절 표지), evals 양성·음성 한 쌍(Harbor 태스크 다섯 파일씩).

호출: uv run --script scripts/scaffold.py <name> --description "<한 문장>" [--positive <case>] [--negative <case>] [--root <skills-dir>] [--script <x.py>]
  name        1~64자, 소문자·숫자·하이픈(agentskills.io name 문법). 디렉토리명이 된다.
  --root      skills/ 디렉토리(기본 ./skills — 카탈로그 클론 루트에서 부른다)
  --positive  써야 하는 과제 케이스 이름(기본 basic)
  --negative  쓰지 말아야 하는 과제 케이스 이름(기본 basic; no-trigger- 접두가 없으면 붙인다)
  --script    scripts/<x.py>에 PEP 723 머리와 종료 코드(2 입력·3 대상 없음·4 도구 없음) 골격을 쓴다
있는 파일은 건드리지 않는다(멱등). 만든 파일을 한 줄씩 찍는다. 종료 코드: 0 성공 · 2 입력 오류.
판단은 여기 없다 — 내용(설명·과제 문장·검증 조건·절차)은 에이전트가 TODO 자리에 쓴다. 규약 문면은 references/conventions.md.
Harbor 쪽 계약(tests/test.sh가 /logs/verifier/reward.txt에 쓰고, solution/solve.sh를 Oracle이 돌린다)은 `harbor tasks init`의 뼈대와 같다;
다른 점은 이미지에 uv를 미리 넣고(검증 때 네트워크 없음) 레지스트리용 `skills_dir`를 두는 것이다.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ast-grep-ignore: regex-on-structure — 어휘: agentskills.io name 문법은 문자집합과 길이만 보는 정규 언어다(중첩 구조 아님)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

SKILL_MD = """---
name: {name}
description: {description}
compatibility: TODO 필요한 시스템 도구·환경을 사람이 읽는 한 문장으로(없으면 이 줄을 지운다)
metadata:
  requires-tools: ""
---

# {name}

TODO 한 문단: 무엇을 하는가, 결과는 어디에 남는가.

## 언제 쓰는가

- 쓴다: TODO 사용자가 실제로 말하는 문장 둘셋.
- 쓰지 않는다: TODO 비슷하지만 이 스킬이 아닌 상황 하나.

## 단계

1. TODO 결정적인 일은 `scripts/`의 스크립트로, 판단은 여기 문장으로.

## 실패 대응

| 상황 | 대응 |
|---|---|
| TODO | TODO |
"""

SCRIPT_PY = '''# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""TODO 한 줄. 호출: uv run --script scripts/{script} <인자>. 종료 코드: 0 성공 · 2 입력 오류 · 3 대상 없음 · 4 시스템 도구 없음."""

import sys


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: {script} <인자>", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

TASK_TOML = """schema_version = "1.4"

[metadata]
description = "{description}"

[environment]
build_timeout_sec = 600.0
skills_dir = "/skills"
# 라이브 소비(레지스트리 MCP)가 필요하면: [[environment.mcp_servers]] name = "harness-catalog" url = "<REGISTRY_URL>"

[agent]
timeout_sec = 600.0

[verifier]
timeout_sec = 120.0
"""

INSTRUCTION_MD = "TODO 사용자가 실제로 할 한 문장. 과제의 입력과 끝 상태가 드러나게.\n"

DOCKERFILE = """FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
WORKDIR /work
# TODO 과제의 시작 상태(파일·저장소)를 여기서 만든다
"""

TEST_SH = """#!/bin/sh
set -eu
mkdir -p /logs/verifier
# {condition}
if false; then  # TODO 끝 상태를 검사하는 조건으로 바꾼다
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""

SOLVE_SH = """#!/bin/sh
# Oracle: 검증기가 참으로 보는 끝 상태를 직접 만든다. 먼저 `harbor run -p skills/{name}/evals -a oracle -e docker`로 reward 1을 확인한다.
set -eu
{body}
"""


def put(path: Path, text: str, created: list[str]) -> None:
    """없는 파일만 쓴다."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    created.append(path.as_posix())


def case_files(case_dir: Path, name: str, description: str, condition: str, solve_body: str, created: list[str]) -> None:
    put(case_dir / "task.toml", TASK_TOML.format(description=description), created)
    put(case_dir / "instruction.md", INSTRUCTION_MD, created)
    put(case_dir / "environment" / "Dockerfile", DOCKERFILE, created)
    put(case_dir / "tests" / "test.sh", TEST_SH.format(condition=condition), created)
    put(case_dir / "solution" / "solve.sh", SOLVE_SH.format(name=name, body=solve_body), created)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="scaffold.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--description", required=True, help="사용자가 실제로 말할 낱말이 든 한 문장")
    ap.add_argument("--positive", default="basic")
    ap.add_argument("--negative", default="basic")
    ap.add_argument("--root", default="skills")
    ap.add_argument("--script", default=None)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not NAME_RE.match(a.name):
        print(f"name은 1~64자 소문자·숫자·하이픈: {a.name}", file=sys.stderr)
        return 2
    negative = a.negative if a.negative.startswith("no-trigger-") else f"no-trigger-{a.negative}"
    d = Path(a.root) / a.name
    created: list[str] = []
    put(d / "SKILL.md", SKILL_MD.format(name=a.name, description=a.description), created)
    if a.script:
        put(d / "scripts" / a.script, SCRIPT_PY.format(script=a.script), created)
    case_files(d / "evals" / a.positive, a.name, "TODO 써야 하는 과제 한 줄", "TODO 스킬이 만들어야 하는 결과(파일·상태)가 있어야 1", "cd /work\n# TODO 끝 상태를 만든다", created)
    case_files(d / "evals" / negative, a.name, "TODO 쓰지 말아야 하는 과제 한 줄(비슷하지만 이 스킬이 아닌 상황)", "TODO 스킬이 발동했을 때 생길 흔적이 없어야 1", "exit 0  # 음성 케이스 — 아무것도 하지 않는 것이 정답", created)
    for c in created:
        print(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
