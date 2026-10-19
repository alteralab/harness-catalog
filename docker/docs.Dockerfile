# 문서 사이트 이미지: mkdocs 가 만든 정적 site/ 를 nginx 가 섬긴다. 두 단계, 런타임에 파이썬 없음.
# 빌드 컨텍스트는 저장소 루트(레지스트리 이미지와 같다): docker build -f docker/docs.Dockerfile -t <태그> .
# 경로는 /docs/ 하위다 — mkdocs.yml 의 site_url 경로와 같아야 링크·검색·llms.txt 의 절대 URL 이 맞는다.
ARG PYTHON_IMAGE=python:3.12-slim
ARG NGINX_IMAGE=nginx:alpine

FROM ${PYTHON_IMAGE} AS builder
RUN pip install --no-cache-dir uv==0.11.8
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# 워크스페이스 멤버의 pyproject 가 있어야 uv sync 가 lock 을 푼다(docs 그룹은 멤버를 쓰지 않지만 워크스페이스는 읽는다).
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/cli/pyproject.toml packages/cli/pyproject.toml
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/harbor-langfuse/pyproject.toml packages/harbor-langfuse/pyproject.toml
RUN uv sync --frozen --no-install-workspace --only-group docs
# 문서의 소스 — docs/ 와 루트의 README·DESIGN(include), 링크 훅.
COPY mkdocs.yml ./
COPY docs/ docs/
COPY README.md DESIGN.md ./
COPY tools/mkdocs_hooks.py tools/mkdocs_hooks.py
# strict 다 — 링크·앵커가 깨지면 이미지가 만들어지지 않는다.
RUN /opt/venv/bin/mkdocs build --strict

FROM ${NGINX_IMAGE}
COPY docker/docs.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /src/site /usr/share/nginx/html/docs
# 비루트로 돈다 — nginx:alpine 이 이미 만들어 두는 nginx(101) 사용자. 1024 미만 포트를 못 여므로 8080 을 쓴다.
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html
USER nginx
EXPOSE 8080
