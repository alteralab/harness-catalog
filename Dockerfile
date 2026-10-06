# harness-catalog-server 이미지: python:3.12-slim + git + gitleaks, 다단계. 런타임 하나, 아티팩트 하나.
# 빌드 컨텍스트는 저장소 루트. 태그는 CI가 커밋 짧은 SHA로 단다(docker/·plans 참조).
ARG PYTHON_IMAGE=python:3.12-slim
ARG GITLEAKS_IMAGE=zricethezav/gitleaks:v8.30.1

FROM ${GITLEAKS_IMAGE} AS gitleaks

FROM ${PYTHON_IMAGE} AS builder
# uv는 PyPI에서 받는다(GHCR의 uv 이미지는 레지스트리 자격이 섞인 데몬에서 denied가 날 수 있다 — mini 실측)
RUN pip install --no-cache-dir uv==0.11.8
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/cli/pyproject.toml packages/cli/pyproject.toml
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/harbor-langfuse/pyproject.toml packages/harbor-langfuse/pyproject.toml
COPY packages/ packages/
# 서버와 그 의존(core)만 설치한다. CLI·플러그인은 이미지 밖의 배포물이다.
RUN uv sync --frozen --no-dev --no-editable --package harness-catalog-server

FROM ${PYTHON_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /var/lib/harness-catalog harness
COPY --from=gitleaks /usr/bin/gitleaks /usr/local/bin/gitleaks
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" PYTHONUNBUFFERED=1
USER harness
WORKDIR /var/lib/harness-catalog
EXPOSE 8000
ENTRYPOINT ["harness-catalog-server"]
CMD ["serve", "--workdir", "/var/lib/harness-catalog"]
