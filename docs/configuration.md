# 설정값

harness-catalog의 설정 표면 전부를 층별로 적은 참조입니다. 층은 다섯입니다. 레지스트리 프로세스가 읽는 것, 그 프로세스 곁의 관측·CLI 옵션, compose가 받는 변수와 비밀 파일, Dex·LDAP, 그리고 카탈로그 저장소 CI와 러너. 어느 변수가 어느 층의 것인지가 곧 "어디에 적는가"입니다.

§1의 표는 `harness-catalog config docs`가 코드(`settings.py`)에서 생성합니다. 나머지 절은 손으로 씁니다.

## 0. 운영자가 꼭 채우는 것

이름은 많아 보여도 운영 설치에서 손으로 적는 것은 아래가 전부입니다. 그 밖은 기본값이거나, 스크립트가 만들거나, compose가 채우거나, 외부 도구(OTel·Harbor·각 하네스)가 정한 이름입니다.

| 무엇 | 어디에 | 언제 |
|---|---|---|
| `REGISTRY_IMAGE` | `.env` | 항상 |
| `HC__CATALOG_REPO_URL` · `HC__OIDC_ISSUER` · `HC__PUBLIC_URL` | `.env` | 항상 |
| `git_deploy_key` | `${SECRETS_DIR}/git_deploy_key` (`make-secrets.sh`의 둘째 인자) | 항상 |
| `LDAP_HOST` · `LDAP_BIND_DN` · `LDAP_USER_BASE_DN` · `LDAP_GROUP_BASE_DN` | `.env` | LDAP 오버레이를 쓰고 기본값(우리 NAS)과 다를 때 |
| `ldap_bind_pw` | `${SECRETS_DIR}/ldap_bind_pw` | LDAP 오버레이를 쓸 때 |
| `HC_PUBLIC_HOSTNAME` · `HC_HOST_TAILSCALE_IP` | `.env` | 프록시가 같은 호스트에 있어 hairpin이 필요할 때 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` + `otlp_headers` 파일 | `.env` + `${SECRETS_DIR}/otlp_headers` | Langfuse로 스팬을 보낼 때 |

빠른 시작은 아무것도 채우지 않습니다. 개발 compose는 비밀 넷(`POSTGRES_PASSWORD`·`HC_DB_PASSWORD`·`DEX_DB_PASSWORD`·`DEX_CI_RUNNER_SECRET`)을 직접 만들어 적습니다(운영과 같은 "임의값 생성" 습관을 유지하기 위해 기본값을 두지 않습니다).

## 1. 레지스트리 설정값 (`HC__*`)

레지스트리 프로세스가 환경 변수로 읽습니다. 비밀은 `<이름>_FILE=<경로>`로 파일에서도 읽습니다(docker secrets). 필수 다섯 중 하나라도 비면 기동하지 않고 어느 것이 비었는지 말합니다. `HC__OIDC_ISSUER`·`HC__PUBLIC_URL`은 끝에 `/`를 붙이면 거부됩니다. Dex와 레지스트리가 글자까지 같은 값을 봐야 하기 때문입니다.

<!-- generated: harness-catalog config docs — 이 표만 생성된다. 바깥은 손으로 쓴다 -->

| 변수 | 필수 | 기본값 | 뜻 |
|---|---|---|---|
| `HC__CATALOG_REPO_URL` | 예 |  | 카탈로그 git 저장소 URL (deploy key로 fetch만 한다) |
| `HC__GIT_DEPLOY_KEY` | 예 |  | 읽기 전용 deploy key의 개인 키(PEM). 로컬 file:// 저장소면 빈 문자열 |
| `HC__OIDC_ISSUER` | 예 |  | OIDC issuer URL (토큰의 iss, JWKS 발견) |
| `HC__PUBLIC_URL` | 예 |  | 레지스트리 공개 URL = 토큰의 audience = RFC 9728 resource |
| `HC__DATABASE_URL` | 예 |  | PostgreSQL 접속 문자열 |
| `HC__FETCH_INTERVAL_SECONDS` | 아니오 | 60 | 주기 fetch 간격(초) |

<!-- /generated -->

실효값과 출처(env·file·default·missing)는 `harness-catalog config list`로 봅니다.

## 2. 관측 (OpenTelemetry → Langfuse)

레지스트리의 설정값이 아니라 OTel SDK의 표준 변수입니다. `OTEL_EXPORTER_OTLP_ENDPOINT`가 비면 스팬은 no-op이고 아무것도 나가지 않습니다.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (비움 = 끔) | OTLP/HTTP 수신 주소. Langfuse Cloud는 `https://cloud.langfuse.com/api/public/otel`(EU) · `https://us.cloud.langfuse.com/api/public/otel`(US), 셀프호스팅은 `<host>/api/public/otel` |
| `OTEL_EXPORTER_OTLP_HEADERS` | | `k=v,k2=v2`. Langfuse는 `Authorization=Basic <base64(public_key:secret_key)>`. 개발·빠른 시작용 |
| `OTEL_EXPORTER_OTLP_HEADERS_FILE` | | 같은 내용을 파일에서(운영 compose는 비밀 파일 `otlp_headers`). 비어 있으면 무시하고 위 변수를 쓴다 |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Langfuse는 gRPC를 받지 않는다 |
| `OTEL_SERVICE_NAME` | `harness-catalog`(코드 기본값) | 스팬의 `service.name`. compose·`docker/.env.example`에는 없고 바꿀 때만 표준 변수로 준다 |

스팬 하나는 도구 호출 하나(`tools/call <tool>`)이고 속성은 `langfuse.user.id`(토큰의 `sub`), `harness_catalog.skill`, `harness_catalog.sha`, `harness_catalog.query`(검색어, 2000자까지), `harness_catalog.result_count`입니다. 검색어가 기록에 남는다는 것이 "검색어에 비밀 금지"의 이유입니다.

## 3. 서버 명령의 옵션

| 명령 | 옵션 | 기본값 |
|---|---|---|
| `harness-catalog-server serve` | `--host` | `0.0.0.0` |
| | `--port` | `8000` |
| | `--workdir` | `/var/lib/harness-catalog` (클론·deploy key·git 설정이 놓이는 곳) |
| | `--log-level` | `info` |
| `harness-catalog-server reindex` | `--accept-rewind` | 꺼짐. `main` 되감기를 받아들인다 |
| | `--workdir`, `--log-level` | 위와 같음 |

이미지의 기본 명령은 `serve --workdir /var/lib/harness-catalog`입니다.

## 4. compose 변수와 비밀 파일

compose 파일은 `.env`(같은 디렉토리)와 셸 환경에서 변수를 채웁니다. `docker/.env.example`을 복사해 씁니다.

### 운영 (`docker/compose.yml`)

| 변수 | 필수 | 기본값 | 뜻 |
|---|---|---|---|
| `REGISTRY_IMAGE` | 예 | | `ghcr.io/alteralab/harness-catalog:vX.Y.Z`(판 태그) 또는 짧은 SHA, 또는 로컬 태그 |
| `HC__CATALOG_REPO_URL` · `HC__OIDC_ISSUER` · `HC__PUBLIC_URL` | 예 | | §1 그대로. Dex의 issuer와 audience 클라이언트 ID도 이 둘에서 채워진다 |
| `HC__FETCH_INTERVAL_SECONDS` | 아니오 | 60 | §1 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` · `_PROTOCOL` | 아니오 | §2 | 헤더는 변수가 아니라 비밀 파일 `otlp_headers` |
| `REGISTRY_PORT` | 아니오 | 8000 | 호스트 `127.0.0.1`에 여는 레지스트리 포트(프록시가 받는다) |
| `DEX_PORT` | 아니오 | 5556 | 호스트 `127.0.0.1`에 여는 Dex 포트 |
| `SECRETS_DIR` | 아니오 | `./secrets` | 비밀 파일 디렉토리(0700) |

비밀 파일 여덟은 `scripts/make-secrets.sh <SECRETS_DIR> [deploy_key]`가 만듭니다. 있는 파일은 건드리지 않습니다.

| 파일 | 내용 | 누가 읽나 |
|---|---|---|
| `postgres_password` | 무작위 | postgres(슈퍼유저) |
| `hc_db_password` | 무작위 | postgres 초기화(역할 `harness_catalog`) |
| `dex_db_password` | 무작위 | postgres 초기화(역할 `dex`), dex |
| `database_url` | `hc_db_password`로 조립한 접속 문자열 | registry (`HC__DATABASE_URL_FILE`) |
| `git_deploy_key` | 둘째 인자의 파일 복사. 없으면 빈 파일(file:// 전용) | registry (`HC__GIT_DEPLOY_KEY_FILE`) |
| `dex_ci_runner_secret` | 무작위 | dex(기밀 클라이언트 `ci-runner`) |
| `otlp_headers` | 빈 파일. Langfuse면 `Authorization=Basic …` | registry (`OTEL_EXPORTER_OTLP_HEADERS_FILE`) |
| `ldap_bind_pw` | 빈 파일. LDAP 오버레이를 쓰면 바인드 비밀번호 | dex (`LDAP_BIND_PW_FILE`) |

회전은 파일을 바꾸고 그 파일을 읽는 컨테이너만 재기동하는 것입니다. `docker compose -f docker/compose.yml config`의 출력은 비밀을 담으므로 기록에 남기지 않습니다.

### 개발 (`docker/compose.dev.yml`)

postgres와 dex만 띄우고 비밀을 환경 변수로 넘깁니다(개발 전용 예외). 레지스트리는 호스트에서 §1 변수를 환경으로 읽어 돕니다(`set -a; . ./.env; set +a`).

| 변수 | 필수 | 기본값 | 뜻 |
|---|---|---|---|
| `POSTGRES_PASSWORD` · `HC_DB_PASSWORD` · `DEX_DB_PASSWORD` | 예 | | DB 비밀번호 셋(`openssl rand -base64 32`) |
| `DEX_CI_RUNNER_SECRET` | 예 | | 기밀 클라이언트 시크릿 |
| `HC__OIDC_ISSUER` · `HC__PUBLIC_URL` | 아니오 | `http://localhost:5556/dex` · `http://localhost:8000/mcp` | Dex의 issuer·audience로도 쓰인다 |
| `POSTGRES_PORT` · `DEX_PORT` | 아니오 | 5432 · 5556 | 호스트 `127.0.0.1`에 여는 포트 |

### 빠른 시작 (`docker/compose.quickstart.yml`)

모든 변수에 기본값이 있어 아무것도 적지 않아도 뜹니다. 같은 디렉토리에 `.env`가 있으면 그 값이 기본값을 덮습니다(변수 이름이 개발 compose와 같습니다).

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `POSTGRES_PASSWORD` · `HC_DB_PASSWORD` · `DEX_DB_PASSWORD` · `DEX_CI_RUNNER_SECRET` | `quickstart` | 공개된 값. 평가·데모 전용 |
| `REGISTRY_IMAGE` | `harness-catalog:quickstart` | 없으면 이 저장소에서 빌드 |
| `REGISTRY_PORT` · `DEX_PORT` | 8000 · 5556 | issuer·공개 URL은 이 포트로 `http://localhost:…`가 된다 |
| `OTEL_*` | §2 | 선택 |

fetch 주기는 10초로 고정이고, 심는 카탈로그의 템플릿에 박는 판은 `packages/cli/pyproject.toml`의 version입니다(둘 다 변수가 아닙니다).

## 5. Dex와 LDAP

Dex 설정 파일(`docker/dex/config.yaml`, LDAP 판은 `examples/synology-ldap/dex/config.yaml`)은 gomplate로 환경 변수를 읽습니다. 운영자가 적는 것은 `LDAP_*`과 hairpin 둘뿐입니다.

| 변수 | 출처 | 뜻 |
|---|---|---|
| `LDAP_HOST` | `.env` | 기본 `192.168.3.95:636`(LDAPS) |
| `LDAP_BIND_DN` | `.env` | 검색용 바인드 DN |
| `LDAP_BIND_PW` / `LDAP_BIND_PW_FILE` | `.env` / 비밀 파일 | 파일이 있고 비어 있지 않으면 파일, 아니면 변수 |
| `LDAP_USER_BASE_DN` · `LDAP_GROUP_BASE_DN` | `.env` | 사용자·그룹 검색 베이스 |
| `LDAP_INSECURE_NO_SSL` | `.env`(`false`) | 평문 389로 되돌릴 때 `true` |
| `LDAP_INSECURE_SKIP_VERIFY` | `.env`(`true`) | 자체 서명 인증서면 `true` |
| `HC_PUBLIC_HOSTNAME` · `HC_HOST_TAILSCALE_IP` | `.env` | 오버레이의 hairpin: 레지스트리 컨테이너 안에서 공개 호스트 이름을 호스트 IP로 푼다 |

고정된 규약이라 설정값이 아닌 것: 읽기 그룹 이름 `harness-readers`, 클라이언트 ID `claude-code`·`codex`·`cursor`·`ci-runner`, 토큰 수명(1시간).

<details>
<summary>자동 배선 — compose가 Dex 설정 파일에 채우는 변수(진단용, 직접 적지 않는다)</summary>

| 변수 | 출처 | 뜻 |
|---|---|---|
| `DEX_ISSUER` | compose ← `HC__OIDC_ISSUER` | issuer |
| `HC_PUBLIC_URL` | compose ← `HC__PUBLIC_URL` | audience 클라이언트 ID(`trustedPeers`로 하네스 클라이언트의 토큰 `aud`에 실린다) |
| `DEX_DB_PASSWORD` / `_FILE` | compose | Dex 저장소 비밀번호 |
| `DEX_CI_RUNNER_SECRET` / `_FILE` | compose | 기밀 클라이언트 `ci-runner` |
| `DEX_EXPAND_ENV` | compose(`true`) | Dex 자체 `$VAR` 확장(저장소·커넥터 설정에서만) |

</details>

## 6. 카탈로그 저장소 CI와 러너

`harness-catalog init`이 놓는 워크플로가 읽는 것입니다. 저장소(또는 조직) 설정에 둡니다.

| 이름 | 종류 | 뜻 |
|---|---|---|
| `HARNESS_EVALS` | 변수 | `true`면 `main` push에 evals 잡을 만든다. 없거나 `false`면 `check`만 |
| `HARNESS_EVALS_AGENTS` | 변수 | 공백 구분 하네스 목록. 기본 `claude-code codex` |
| `HARNESS_CATALOG_DEPLOY_KEY` | 시크릿 | 코드 저장소가 비공개일 때 읽기 전용 deploy key의 개인 키 |
| `HARNESS_CATALOG_READ_TOKEN` | 시크릿 | 같은 용도의 fine-grained PAT(Contents: Read). 둘 다 있으면 토큰이 먼저 |

evals 잡이 돌 self-hosted 러너의 루트 `.env`에는 하네스별 모델 자격과 Langfuse 키를 둡니다. 전체 목록은 [runner.env.example](../examples/runner.env.example)이고, 워크플로가 잡 안에서 정하는 `HARNESS_SKILL_REF`(스킬 원천의 커밋 SHA)·`HARNESS_CATALOG_NAME`(저장소 이름)은 `harbor-langfuse` 플러그인이 읽습니다.

코드 저장소(`alteralab/harness-catalog`)의 CI는 시크릿 `ALTERALAB_READ_TOKEN`(비공개 `altera-rules`를 받을 때만, 없으면 규칙 게이트를 건너뜀)을 봅니다.

## 7. 시험

| 변수 | 뜻 |
|---|---|
| `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` | macOS Docker Desktop에서 `/var/run/docker.sock`. `pg` 표시 시험이 setdefault로 넣는다 |

`http` 표시 시험(`tests/http/`)은 실제 uvicorn 프로세스를 띄우고 가짜 issuer(JWKS)로 토큰을 만들어 도구 넷과 401/403 경계, 스팬 속성을 봅니다. Dex도 토큰 변수도 필요 없습니다. 실제 Dex·LDAP·Langfuse까지의 끝에서 끝은 빠른 시작 스택에서 손으로 확인합니다([quickstart.md](quickstart.md) §3).
