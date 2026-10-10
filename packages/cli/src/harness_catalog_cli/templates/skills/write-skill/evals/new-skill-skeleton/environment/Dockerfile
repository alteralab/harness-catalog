FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
RUN uv pip install --system --no-cache pytest==8.4.1 pytest-json-ctrf==0.3.5   # 검증기(tests/test_outputs.py). Harbor 공식 뼈대와 같은 판
WORKDIR /work
# 시험용 카탈로그 클론: 표지·skills/·README·pre-commit·CI가 있고 스킬 하나(yt-subs)가 있다
RUN git init -q -b main /work/catalog && cd /work/catalog \
 && printf 'layout = 1\n' > .harness-catalog && mkdir -p skills/yt-subs .github/workflows \
 && printf -- '---\nname: yt-subs\ndescription: YouTube 자막을 추출한다. 유튜브 자막 뽑아줘.\n---\n# yt-subs\n' > skills/yt-subs/SKILL.md \
 && printf 'name: check\n' > .github/workflows/check.yml && printf 'repos: []\n' > .pre-commit-config.yaml && printf '# catalog\n' > README.md \
 && git add -A && git -c user.email=t@x -c user.name=t commit -q -m init
