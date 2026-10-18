FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
# uv는 도구 스크립트 규약(`uv run --script`) 때문에 있어야 한다. 검증 도구(pytest·pytest-json-ctrf)는 Harbor 0.24 뼈대와 같은 판을 미리 넣는다 —
# 검증 중 PyPI 내려받기를 없애 검증 예산과 결정성을 지키기 위해서다(Harbor PR #2596, Terminal-Bench check-verifier-tooling-baked). network_mode는 기본 public이라 네트워크가 없는 것은 아니다.
# PyPI에서 받는다: GHCR의 uv 이미지(COPY --from)는 self-hosted 러너에서 pull denied가 난 적이 있다(루트 Dockerfile과 같은 이유).
RUN pip install --no-cache-dir uv==0.11.8 pytest==8.4.1 pytest-json-ctrf==0.3.5 && uv --version
RUN mkdir -p /skills   # task.toml의 skills_dir. Harbor가 주입 때 만들기도 하지만 문서("이미지에 있게 하라")를 따른다
WORKDIR /work
# 시험용 카탈로그 클론: 점검표의 A1(막연한 description)·B2(두 단계 참조)·C4(시간에 묶인 문장)·D2(이유 없는 scripts/)를 일부러 어긴 yt-subs 스킬
RUN git init -q -b main /work/catalog && cd /work/catalog \
 && printf 'layout = 1\n' > .harness-catalog && mkdir -p skills/yt-subs/references skills/yt-subs/scripts .github/workflows \
 && printf -- '---\nname: yt-subs\ndescription: Helps with videos.\n---\n# yt-subs\n\n2025년 8월 전에는 옛 API를 쓰고, 그 뒤에는 새 API를 쓴다.\n\n자세한 것은 [advanced.md](references/advanced.md)를 본다.\n\n## 단계\n\n1. uv run --script scripts/subs.py <url> 을 돌린다.\n' > skills/yt-subs/SKILL.md \
 && printf '# advanced\n\n세부는 [details.md](details.md)에.\n' > skills/yt-subs/references/advanced.md && printf '# details\n\n여기가 진짜 내용.\n' > skills/yt-subs/references/details.md \
 && printf 'print(1)\n' > skills/yt-subs/scripts/subs.py \
 && printf 'name: check\n' > .github/workflows/check.yml && printf 'repos: []\n' > .pre-commit-config.yaml && printf '# catalog\n' > README.md \
 && git add -A && git -c user.email=t@x -c user.name=t commit -q -m init
