# 개발

이 코드 저장소를 고치는 사람을 위한 안내입니다.

## 배치

uv 워크스페이스에 배포물 넷이 있습니다. 의존 방향은 `cli → core`, `server → core`이고 `cli`와 `server`는 서로 import하지 못합니다.

| 패키지 | 배포물 | 내용 |
|---|---|---|
| `packages/core` | `harness-catalog-core` | 모델, 카탈로그 앱(`Catalog`), 검사 항목(`check.py`), 인가(`authz.py`), git·skills-ref 어댑터, 설정(`settings.py`) |
| `packages/server` | `harness-catalog-server` | MCP 서버(Streamable HTTP), OIDC 검증, PostgreSQL 어댑터와 브레이커, 스케줄러, 마이그레이션, `/healthz`·`/readyz` |
| `packages/cli` | `harness-catalog-cli` | `check`·`init`·`config`, 카탈로그 저장소 템플릿(`templates/`) |
| `packages/harbor-langfuse` | `harbor-langfuse` | Harbor 플러그인: 잡 결과를 Langfuse 데이터셋 실험으로 |

앱 층(`core`)은 git·PostgreSQL·OIDC를 모릅니다. 포트는 ContentStore·SkillValidator·FactStore 셋이고 어댑터가 꽂힙니다. 시험은 가짜 어댑터로 앱을 직접 부릅니다.

## 환경

자주 치는 명령은 `make help`에 이름이 있습니다(`make quickstart`·`dev-up`·`serve`·`test`·`typecheck`·`gates`·`check`·`image`). 아래는 그 풀이입니다.

```sh
uv sync -p 3.12
cp .env.example .env                                  # 비밀은 openssl rand -base64 32
docker compose -f docker-compose.dev.yml up -d        # postgres + dex (호스트 127.0.0.1 바인딩)
set -a; . ./.env; set +a
uv run harness-catalog-server serve --port 8000
```

개발 compose는 postgres와 dex만 띄우고 레지스트리는 호스트에서 돌립니다. 카탈로그는 `HC__CATALOG_REPO_URL=file:///…`로 로컬 저장소를 가리켜도 되고 그때 `HC__GIT_DEPLOY_KEY`는 빈 문자열입니다. Dex 설정은 gomplate `{{ getenv }}`로 환경 변수를 읽습니다(Dex 자체의 `$VAR` 확장은 저장소·커넥터 설정에서만 됩니다).

기계 계정 토큰은 `scripts/dev-token.sh`, 사람 토큰(PKCE·장치 흐름)과 Dex 그랜트 실측은 `tools/pilot/dex_grants.py`, 하네스 첫 접촉 캡처는 `tools/pilot/capture_stub.py`입니다.

## 시험과 게이트

```sh
uv run pytest -q tests                      # 65
uv run pyright packages tests tools         # strict, 0
pre-commit install && pre-commit run --all-files
```

`pg` 표시 시험은 docker(testcontainers PostgreSQL)가 필요합니다. macOS Docker Desktop은 `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`이 필요하고 시험이 setdefault로 넣습니다. `http` 표시 시험은 실제 uvicorn 프로세스와 개발 compose의 Dex, 토큰(`HC_TEST_TOKEN`)이 필요합니다.

커밋 훅은 altera-rules 게이트 넷(ruff·ast-grep·shellcheck·표면 선언 드리프트)을 돌립니다. 선언은 `altera-rules.yml`, 리뷰 루브릭은 `REVIEW.md`입니다. CI(`.github/workflows/ci.yml`)는 ubuntu에서 게이트(비공개 altera-rules를 읽을 `ALTERALAB_READ_TOKEN`이 있을 때만)·pyright·pytest를 돌리고, `main` 병합이면 self-hosted 러너(mini)가 이미지를 빌드해 GHCR로 올립니다.

## 의존성과 판

의존성은 `pyproject.toml` 다섯과 PEP 723 스크립트 머리 모두 `==`로 고정합니다. 올리는 것은 값을 바꾸고 `uv lock`을 돌리는 명시 행위입니다.

새 판을 내는 절차는 다음과 같습니다.

1. 네 `pyproject.toml`의 `version`을 같은 값으로 올립니다(lockstep).
2. `uv lock`, 시험·게이트 통과, 커밋.
3. 태그 `vX.Y.Z`를 push합니다. 카탈로그 저장소의 훅과 CI가 이 태그로 `core`·`cli`를 설치하고, `init`은 자기 판의 태그를 템플릿에 박습니다. CI가 이미지를 `ghcr.io/alteralab/harness-catalog:vX.Y.Z`로도 올립니다(판 태그는 보존 정리에서 제외).
4. `main` 병합마다는 짧은 SHA 태그로 빌드됩니다. 운영 호스트에서는 `REGISTRY_IMAGE`에 판 태그를 적어 올립니다.

템플릿(`packages/cli/.../templates/`)을 바꾸면 이미 만들어진 카탈로그 저장소에는 반영되지 않습니다. `init`은 없는 파일만 쓰기 때문입니다. 그 저장소의 워크플로 파일은 손으로 갱신합니다.

## 설계 문서와 원장

설계 계약을 바꾸는 변경은 코드보다 DESIGN.md §11의 결정 행이 먼저입니다. 실행 계획은 PLAN.md(우산)와 `plans/{service,distribution,pilot,skills}.md`이고, 각 문서의 원장 절에 날짜·내용·근거를 남깁니다. 측정 결과(Dex 그랜트, LDAP, 하네스 첫 접촉)는 `plans/pilot/r1~r3.md`에 있습니다. 구현 단계마다 Codex 적대 리뷰를 걸어 반영했고 그 기록도 원장에 있습니다.
