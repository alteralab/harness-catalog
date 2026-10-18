# 레지스트리 운영

운영자가 카탈로그 저장소를 세우고, 레지스트리를 띄우고, 돌보는 법입니다. 먼저 한번 돌려 보고 싶으면 [quickstart.md](quickstart.md)가 명령 둘로 전체를 로컬에 띄웁니다.

## 구성

호스트 한 대에 compose로 컨테이너 셋을 띄웁니다.

| 서비스 | 이미지 | 역할 |
|---|---|---|
| `registry` | `ds923plus.tail2f9fe3.ts.net:9443/alteralab/harness-catalog:<판 태그>` | MCP 서버 + 주기 fetch·색인 |
| `postgres` | `postgres:17-alpine` | 색인(`harness_catalog`)과 Dex 저장소(별도 DB·역할) |
| `dex` | `ghcr.io/dexidp/dex:v2.45.1` | LDAP을 OIDC로 감싸는 인가 서버 |

TLS와 라우팅은 앞의 리버스 프록시가 맡습니다. 우리 팀은 mini의 `tailscale serve`이고 접근 통제는 tailnet ACL입니다. 백업 대상은 없습니다. 색인은 `main`에서 언제든 다시 짓고, 사용·평가 기록은 Langfuse에 있습니다.

## 전제 조건

- Docker와 compose v2. 컨테이너가 git 호스트와 LDAP에 닿을 것(macOS는 colima가 LAN에 닿았고 Docker Desktop은 닿지 않았습니다).
- 리버스 프록시(TLS 종단). 경로 셋을 열 수 있어야 합니다(§3).
- LDAP: 그룹 `harness-readers`, 기계 계정 하나, 바인드 DN. 없으면 `docker/dex/config.yaml`의 정적 사용자로 시작할 수 있습니다.
- 카탈로그 저장소와 읽기 전용 deploy key.

## 1. 카탈로그 저장소 세우기

1. git 호스트에 빈 저장소를 만듭니다. 이름은 자유이고 비공개가 좋습니다.
2. CLI로 초기화합니다. 운영자의 git 자격으로 clone해 표지 파일·기본 스킬 둘(`skills/pin`·`skills/write`)과 기본 도구 하나(`tools/scaffold`)·README·pre-commit 설정·호스트별 CI 워크플로를 없는 것만 쓰고 커밋·push합니다. 두 번 돌리면 변경이 없습니다.

   ```sh
   uvx --from "harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v0.1.0#subdirectory=packages/cli" \
     hc init https://github.com/<org>/<catalog>.git
   ```

   템플릿에는 CLI 자기 판의 태그가 박힙니다. 코드 저장소에 그 태그가 없으면 멈춥니다(`--pin`으로 다른 ref를 줄 수 있습니다).
3. 레지스트리용 **읽기 전용 deploy key**를 만들어 등록합니다. 개인 키는 §2의 비밀 디렉토리에 넣습니다.

   ```sh
   ssh-keygen -t ed25519 -N '' -f ~/.ssh/catalog-deploy-key
   gh repo deploy-key add ~/.ssh/catalog-deploy-key.pub --repo <org>/<catalog> --title "registry (read)"
   ```
4. 저자에게 write, 병합할 사람에게 admin을 줍니다. 저장소를 읽을 수 있는 명단과 LDAP 그룹 `harness-readers`를 같게 유지합니다. 이것이 접근 통제의 전부입니다.
5. 코드 저장소가 비공개인 동안 카탈로그 CI가 `harness-catalog check`를 설치하려면 읽기 자격이 필요합니다. 코드 저장소에 읽기 전용 deploy key를 하나 더 등록하고 개인 키를 카탈로그 시크릿 `HARNESS_CATALOG_DEPLOY_KEY`에 넣습니다.

   ```sh
   ssh-keygen -t ed25519 -N '' -f hc-ci-deploy
   gh repo deploy-key add hc-ci-deploy.pub --repo alteralab/harness-catalog --title "catalog CI (read)"
   gh secret set HARNESS_CATALOG_DEPLOY_KEY --repo <org>/<catalog> < hc-ci-deploy
   ```

   자격 경로는 deploy key 하나입니다(PAT 경로는 2026-10-10에 뺐습니다 — 웹에서만 만들 수 있고 만료가 있어 자동화가 끊깁니다). 코드 저장소를 공개하면 이 시크릿도 필요 없습니다.
6. CI evals는 Oracle입니다(모델·자격 없이, 바뀐 스킬의 참조 해답으로 과제와 검증기를 확인). PR마다·`main` push마다 self-hosted 러너에서 돕니다. 켜고 끄는 변수는 없습니다. 모델로 돌리는 측정은 저자가 자기 클론에서 합니다([authoring.md](authoring.md) §5).

## 2. 레지스트리 설치

1. 코드 저장소를 받고 `.env`를 만듭니다.

   ```sh
   git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
   cp docker/.env.example docker/.env && chmod 600 docker/.env
   ```

   채울 것: `REGISTRY_IMAGE`(NAS Harbor 태그 또는 로컬 태그), `HC__CATALOG_REPO_URL`(deploy key로 받을 ssh URL), `HC__OIDC_ISSUER`(`https://<호스트>/dex`), `HC__PUBLIC_URL`(`https://<호스트>/mcp`). Dex의 issuer와 audience 클라이언트 ID는 compose가 이 두 값에서 그대로 건네므로 따로 적을 것이 없습니다. 끝에 `/`를 붙이면 레지스트리가 기동을 거부합니다. 설정값의 뜻은 [configuration.md](configuration.md).
2. 비밀 파일을 만듭니다. DB 비밀번호 셋과 `ci-runner` 시크릿은 무작위로 만들고, deploy key는 둘째 인자의 파일을 복사하며, DB 접속 문자열은 조립합니다. 있는 파일은 건드리지 않습니다.

   ```sh
   scripts/make-secrets.sh secrets ~/.ssh/catalog-deploy-key
   ```
3. 띄우고 확인합니다.

   ```sh
   docker compose -f docker/compose.yml up -d
   # 매번 -f를 치기 싫으면 운영 사용자의 셸에 export COMPOSE_FILE=docker/compose.yml 을 두면 아래 명령에서 -f를 뺄 수 있다
   curl -fsS http://127.0.0.1:8000/readyz
   ```

   `/healthz`는 프로세스가 살아 있는지, `/readyz`는 섬길 준비가 됐는지입니다. 준비되면 본문에 색인한 `commit`과 거부된 스킬 목록이 실립니다.
4. 이미지는 `main` 병합마다 self-hosted 러너가 빌드해 NAS의 Harbor(`ds923plus.tail2f9fe3.ts.net:9443`, portainer 저장소 `stacks/harbor`)에 올립니다(짧은 SHA 태그와 판 태그; 보존은 Harbor 프로젝트 규칙). 프로젝트가 public이라 pull에는 로그인이 필요 없고, push는 robot 계정(GitHub 시크릿 `HARBOR_ROBOT_NAME`·`HARBOR_ROBOT_SECRET`)입니다. 같은 호스트에서 `docker build -t harness-catalog:current .`로 만들어 써도 됩니다.

`HC__PUBLIC_URL`은 토큰의 audience이자 RFC 9728의 resource이고, Dex 설정의 audience 클라이언트 ID도 같은 값입니다. compose가 한 값에서 둘을 채우므로 어긋날 길이 없습니다.

## 3. 프록시

경로 셋을 엽니다.

| 경로 | 대상 | 이유 |
|---|---|---|
| `/mcp` | registry :8000 | MCP 엔드포인트 |
| `/.well-known/oauth-protected-resource` | registry :8000 | 401 응답이 가리키는 보호 자원 메타데이터. 안 열면 하네스가 로그인 절차를 시작하지 못한다 |
| `/dex` | dex :5556 | OIDC issuer |

`tailscale serve`면 이렇습니다.

```sh
tailscale serve --bg --set-path /mcp http://127.0.0.1:8000/mcp
tailscale serve --bg --set-path /.well-known/oauth-protected-resource http://127.0.0.1:8000/.well-known/oauth-protected-resource
tailscale serve --bg --set-path /dex http://127.0.0.1:5556/dex
```

레지스트리 컨테이너는 토큰 검증 때 issuer(자기 공개 호스트 이름)에 닿아야 합니다. 프록시가 같은 호스트면 hairpin이 필요하고, Synology 오버레이의 `extra_hosts`가 그 이름을 호스트의 IP로 풉니다.

## 4. Dex와 LDAP

기본 `docker/dex/config.yaml`은 정적 사용자(`dev`·`outsider`)로 빠른 시작용입니다. 팀 LDAP으로 바꾸려면 오버레이를 겹칩니다.

```sh
docker compose -f docker/compose.yml -f docker/synology-ldap/compose.override.yml up -d
```

`.env`의 `LDAP_HOST`(LDAPS 636 기본)·`LDAP_BIND_DN`·`LDAP_USER_BASE_DN`·`LDAP_GROUP_BASE_DN`을 채우고, 바인드 비밀번호는 `secrets/ldap_bind_pw`에 둡니다. Synology LDAP Server의 인증서를 신뢰하지 않으면 `LDAP_INSECURE_SKIP_VERIFY=true`(기본)입니다.

Dex에 등록된 클라이언트는 다음과 같습니다. 바꾸려면 설정 파일을 고치고 `dex`를 재기동합니다.

| ID | 종류 | 용도 |
|---|---|---|
| `claude-code`, `codex`, `cursor` | 공개 | 하네스. 브라우저 로그인(PKCE) |
| `ci-runner` | 기밀(시크릿 `secrets/dex_ci_runner_secret`) | 기계 계정의 비밀번호 그랜트 |
| `<HC_PUBLIC_URL>` | 공개, `trustedPeers`에 위 넷 | 토큰의 `aud`에 레지스트리 URL이 실리게 하는 audience 등록 |

인가는 레지스트리 안에서 토큰의 `groups`에 `harness-readers`가 있는지로만 판정합니다. 스코프는 보지 않습니다. 기계 계정(우리 팀은 `svc-harness`)도 같은 그룹에 넣습니다.

사내 IdP로 옮기면 Dex와 이 절이 사라지고 `HC__OIDC_ISSUER`만 바뀝니다.

## 런북

**새 판 올리기.** 코드 저장소에서 `make release VERSION=X.Y.Z`(태그·이미지), CI가 끝나면 `make deploy HOST=mini TAG=<짧은 SHA>`. 둘 다 스크립트 하나이고 손으로 하지 않습니다(plans/distribution.md D25). 배포 스크립트는 `/readyz`가 ready이고 `db_unavailable`이 없을 때까지 기다린 뒤 적용된 마이그레이션을 찍습니다.


**`/readyz`가 503일 때.** 본문의 `reasons`를 봅니다.

| 사유 | 뜻 | 조치 |
|---|---|---|
| `repo_unreachable` | 저장소를 받지 못함 | URL, deploy key, 네트워크 |
| `no_main_branch` | 커밋 0인 빈 저장소 | `hc init` |
| `not_a_catalog` | 표지 파일 없음 | `init` |
| `unsupported_layout` | 표지의 `layout`이 지원하지 않는 값 | 레지스트리 판을 올리거나 표지를 맞춘다 |
| `layout_mismatch` | 표지와 실제 배치가 다름 | 저장소 구조를 본다 |

`degraded`는 준비는 됐지만 온전하지 않은 상태입니다. `db_unavailable`이면 PostgreSQL이 끊긴 것이고 레지스트리는 메모리 사본으로 계속 섬기며 브레이커가 30초 뒤 재시도합니다. `main_rewound`는 아래 되감기입니다. `rebuild_failed:…`는 새 커밋의 색인 빌드가 실패해 이전 색인으로 섬기는 중입니다.

**`main`이 되감겼을 때**(강제 push 등). 레지스트리는 색인을 멈추고 `/readyz`에 알립니다. 의도한 것이면 받아들이고 재기동합니다.

```sh
docker compose -f docker/compose.yml exec registry harness-catalog-server reindex --accept-rewind && docker compose -f docker/compose.yml restart registry
```

**이미지 올리기.** `.env`의 `REGISTRY_IMAGE`를 바꾸고 `docker compose -f docker/compose.yml up -d`. 몇 초 끊깁니다. 마이그레이션은 기동 때 자동으로 적용됩니다.

**비밀 회전.** 값을 새로 만들어 `secrets/`의 파일을 바꾸고 그 값을 쓰는 컨테이너만 재기동합니다. 옛 값은 발급처에서 지웁니다. deploy key는 git 호스트에서, `ci-runner` 시크릿은 Dex 설정에서, DB 비밀번호는 PostgreSQL 역할에서. `docker compose -f docker/compose.yml config`의 출력은 비밀을 담으니 기록에 남기지 않습니다.

**관측(Langfuse).** 레지스트리가 Langfuse를 직접 알지는 않습니다. 도구 호출마다 OpenTelemetry 스팬(`tools/call <tool>`, 속성 `langfuse.user.id`·`harness_catalog.skill`·`sha`·`query`·`result_count`)을 내고, 표준 OTLP 환경 변수가 있을 때만 내보냅니다. Langfuse로 보내려면 `.env`에 셋을 둡니다.

```sh
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel     # US는 us.cloud.langfuse.com, 셀프호스팅은 <host>/api/public/otel
printf 'Authorization=Basic %s' "$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)" > secrets/otlp_headers   # 운영은 비밀 파일(D10). 개발·빠른 시작은 환경 변수 OTEL_EXPORTER_OTLP_HEADERS
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf                                   # Langfuse는 gRPC를 받지 않는다
```

`ENDPOINT`가 비면 스팬은 no-op이고 아무 데도 가지 않습니다(`secrets/otlp_headers`가 비어 있어도 됩니다). 평가 결과는 다른 경로입니다. `harbor run`의 플러그인이 러너 환경의 `LANGFUSE_PUBLIC_KEY`·`LANGFUSE_SECRET_KEY`·`LANGFUSE_HOST`로 Langfuse에 직접 씁니다. 같은 Langfuse 프로젝트의 키 한 쌍이면 둘 다 됩니다.

**팀원 온보딩.** LDAP 계정을 `harness-readers`에 넣고, 카탈로그 저장소 read를 줍니다. 두 명단은 같아야 합니다. 그다음 [using.md](using.md)를 건넵니다.
