FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
# uv는 도구 스크립트 규약(`uv run --script`) 때문에 있어야 한다. 검증 도구(pytest·pytest-json-ctrf)는 Harbor 0.24 뼈대와 같은 판을 미리 넣는다 —
# 검증 중 PyPI 내려받기를 없애 검증 예산과 결정성을 지키기 위해서다(Harbor PR #2596, Terminal-Bench check-verifier-tooling-baked). network_mode는 기본 public이라 네트워크가 없는 것은 아니다.
# PyPI에서 받는다: GHCR의 uv 이미지(COPY --from)는 self-hosted 러너에서 pull denied가 난 적이 있다(루트 Dockerfile과 같은 이유).
RUN pip install --no-cache-dir uv==0.11.8 pytest==8.4.1 pytest-json-ctrf==0.3.5 && uv --version
RUN pip install --no-cache-dir --index-url https://ds923plus.tail2f9fe3.ts.net:8443/repository/pypi-public/simple/ harness-catalog-cli==<판>   # hc: toolbox(MCP)·pin·init. 팀 Nexus(tailnet) — 이미지는 tailnet 안에서 굽는다
RUN mkdir -p /skills   # task.toml의 skills_dir. Harbor가 주입 때 만들기도 하지만 문서("이미지에 있게 하라")를 따른다
WORKDIR /work
# 시험용 카탈로그: 이 판의 템플릿 그대로를 hc init 으로(기본 스킬 셋·tools/scaffold·.mcp.json·schemas) + 시험용 스킬 yt-subs. 사본 없음 — 템플릿이 바뀌면 fixture 도 따라온다.
# /work/main.sha 는 검증기의 기준(main 이 그대로인가, 무엇이 새로 생겼나).
RUN git init -q --bare /fixture.git && hc init --host github --pin v<판> file:///fixture.git >/dev/null \
 && git clone -q /fixture.git /work/catalog && cd /work/catalog \
 && mkdir -p skills/yt-subs && printf -- '---\nname: yt-subs\ndescription: YouTube 자막을 추출한다. 유튜브 자막 뽑아줘.\n---\n# yt-subs\n' > skills/yt-subs/SKILL.md \
 && mkdir -p tools/changelog-diff/scripts \
 && printf '%s\n' '{"name": "changelog-diff", "description": "Group the commits between two git refs by kind (feat, fix, docs, other). Not for a single commit.", "inputSchema": {"type": "object", "properties": {"from": {"type": "string", "description": "older ref"}, "to": {"type": "string", "description": "newer ref"}}, "required": ["from", "to"], "additionalProperties": false}, "outputSchema": {"type": "object", "properties": {"groups": {"type": "object", "description": "kind -> list of subjects"}}, "required": ["groups"]}, "runtime": {"kind": "script", "path": "scripts/diff.py", "command": ["uv", "run", "--script", "scripts/diff.py"]}}' > tools/changelog-diff/tool.json \
 && printf '# /// script\n# requires-python = ">=3.12"\n# dependencies = []\n# ///\nimport json, subprocess, sys\na = json.load(sys.stdin)\nrng = a["from"] + ".." + a["to"]\nlog = subprocess.run(["git", "log", "--format=%%s", rng], capture_output=True, text=True, check=True).stdout.splitlines()\ng = {}\nfor s in log:\n    g.setdefault(s.split(":")[0] if ":" in s else "other", []).append(s)\nprint(json.dumps({"groups": g}))\n' > tools/changelog-diff/scripts/diff.py \
 && git add -A && git -c user.email=t@x -c user.name=t commit -q -m "fixture: yt-subs" && git push -q origin main \
 && git rev-parse main > /work/main.sha
