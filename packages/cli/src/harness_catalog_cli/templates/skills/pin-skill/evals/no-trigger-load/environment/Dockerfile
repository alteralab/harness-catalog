FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
RUN uv pip install --system --no-cache pytest==8.4.1 pytest-json-ctrf==0.3.5   # 검증기(tests/test_outputs.py). Harbor 공식 뼈대와 같은 판
WORKDIR /work
RUN git init -q /work
