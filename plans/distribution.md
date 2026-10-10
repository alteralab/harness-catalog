# distribution 계획 — 패키징·배포(이미지·compose·예시 설정·템플릿·문서)

**상태: 초안 · 작성 2026-09-26.** 이 PLAN은 `~/workspace/harness-catalog/`의 배포·패키징 표면(루트 Dockerfile, `docker/`, `docs/`, `scripts/`)의 정본이다. 우산 `PLAN.md` §1 표의 "distribution" 행이 관할을 정했고, 설계는 `DESIGN.md`(v3.3) §2 신원 제공자 표·§2.1·§8이다. 이 문서는 설계를 복제하지 않고 "어떤 파일을, 어떤 순서로, 언제 끝났다고 하는가"만 적는다.

## 0. 한 장 요약

플랫폼 팀이 살려 둘 것은 셋이다. 레지스트리 서비스 컨테이너, PostgreSQL 컨테이너(데이터베이스 둘: `harness_catalog`, `dex`), Dex 컨테이너(Synology LDAP을 OIDC로 연합). 셋을 VM 한 대의 docker compose로 띄우고 사내 리버스 프록시가 TLS를 끊어 앞에 선다. 기본 compose는 Dex 정적 사용자로 어느 머신에서나 뜨는 빠른 시작이고, Synology LDAP 연합은 `docker/synology-ldap/` 오버레이다(이 저장소는 오픈소스 패키지로 낸다 — 우산 §3-8). 그 밖에 이 PLAN이 소유하는 것은 카탈로그 저장소를 처음 세울 때 한 번 복사하는 템플릿(`packages/cli/src/harness_catalog_cli/templates/`)과 그 저장소에서 도는 CI 워크플로, `docs/`의 운영자 가이드다. 서비스 코드는 `src/`(plans/service.md)가, 카탈로그에 실리는 두 스킬은 `skills/`(plans/skills.md)가 소유하고 여기는 그것들을 조립만 한다. 단계는 셋이다. 개발용 compose(PostgreSQL + Dex, 서비스 시험용) → 운영 compose(서비스 이미지 포함) → 저장소 템플릿과 첫 카탈로그 저장소.

## 1. 관할과 경계

**소유하는 것.** 루트의 `Dockerfile`(빌드 정의의 내용은 service, 배치와 태그는 여기)·`docker/compose.yml`·`docker/compose.dev.yml`·`docker/.env.example`, `docker/`(빠른 시작용 Dex 설정, PostgreSQL 초기화 SQL), `docker/synology-ldap/`(우리 팀의 LDAP 변형), `packages/cli/src/harness_catalog_cli/templates/` 전부(표지·`skills/.gitkeep`·README·CI 워크플로), `docs/`(설치·설정값 참조·운영자 가이드), `scripts/`. 배치는 우산 §3-8의 오픈소스 공통 골격이다.

**service에서 받는 것.** 컨테이너 이미지 하나(빌드 컨텍스트 저장소 루트, 다단계, git + gitleaks 포함 — DESIGN §2.1 Python 표)와 설정값 여섯의 이름. 필수 다섯은 카탈로그 저장소 URL, git deploy key, OIDC issuer, 레지스트리 공개 URL, PostgreSQL 접속이고, 기본값 있는 선택 하나는 `FETCH_INTERVAL_SECONDS`(60)다(DESIGN §2 "운영자가 아는 것"). 값의 뜻은 service가 정하고 여기는 환경 변수로 건넨다. 그 밖에 표준 OTel exporter 변수 셋(`OTEL_EXPORTER_OTLP_ENDPOINT`·`_HEADERS`·`_PROTOCOL`)을 같은 `.env`로 건네며 이것은 설정값이 아니라 관측 배선이다(D20).

**skills·pilot에 주는 것.** 살아 있는 issuer URL과 레지스트리 URL, 그리고 하네스 셋의 client ID. `skills/`의 두 스킬은 템플릿 복사 시점에 카탈로그 저장소의 첫 스킬로 들어가 CI 초록의 예시가 된다.

설계에서 읽어야 할 자리는 넷이다. §2 신원 제공자 표(Dex로 시작, 저장소는 같은 PostgreSQL의 별도 데이터베이스·역할, 정적 클라이언트 사전 등록), §2.1 원칙 층·실천 층(compose 한 대, 배포 시 수 초 중단 허용, 백업 없음), §2.1 저장소 초기화 표(표지·`skills/`·보호된 `main`·CI·README 다섯, 기동 시 구조 검사 넷), §8 "카탈로그 저장소 신설(최초 1회)" 행(템플릿 복사 + `main` 보호 + deploy key). 계약을 바꾸는 일은 DESIGN §11 행이 먼저다(우산 §1 경계 규칙 ⑶).

## 2. 파일 배치

```
(저장소 루트)
  Dockerfile                # python:3.12-slim + git + gitleaks, 다단계. 빌드 컨텍스트는 루트. 내용은 plans/service.md
  docker/                   # compose 셋과 지원 파일(2026-10-10, DataHub 패턴). compose의 상대 경로·.env·기본 비밀 경로(../secrets)는 이 디렉토리 기준
    compose.yml             #   운영: registry · postgres · dex(정적 사용자). 어느 머신에서나 docker/.env만 채우면 뜬다. name: harness-catalog 고정(볼륨 이름 보존)
    compose.dev.yml         #   개발용: postgres · dex만 (호스트의 uvicorn이 붙는다)
    compose.quickstart.yml  #   빠른 시작(D23): 전체를 기본값으로, 편집 없이. 빌드 컨텍스트는 ..(루트)
    .env.example            #   설정값 여섯 + OTel exporter 변수 셋 + Dex·DB 비밀의 이름과 예시. docker/.env는 gitignore
    postgres/init.sql       #   데이터베이스 둘(harness_catalog, dex)과 역할 둘 생성. 표는 만들지 않는다
    dex/config.yaml         #   빠른 시작용 Dex: issuer · 정적 사용자(staticPasswords) · 정적 클라이언트 · 저장소(postgres)
    synology-ldap/          #   우리 팀 변형(2026-10-10 examples/에서 옮김) — compose.override.yml, dex/config.yaml(LDAP 커넥터, 그룹 harness-readers)
  packages/cli/src/harness_catalog_cli/templates/   # 카탈로그 저장소 템플릿 + 기본 스킬 둘(`init`의 패키지 데이터). 루트에 링크나 사본을 두지 않는다 — 템플릿은 CLI의 데이터다
      .harness-catalog      #     layout = 1
      skills/pin-skill/ · write-skill/   # 기본 스킬 둘의 원본(각자 evals). init이 함께 쓴다(D14 개정 2026-10-10). 내용은 plans/skills.md 관할
      README.md             #     등록 한 줄 · 운영자 체크리스트 · 검색어에 비밀 금지
      .pre-commit-config.yaml #   local 훅 `harness-catalog check`, 설치 명세·판 핀은 D22
      github/check.yml      #     GitHub Actions: PR·main push마다 `harness-catalog check`(D22 명세로 설치) + 선택 잡 evals(D19)
      gitlab/.gitlab-ci.yml #     GitLab CI: 같은 검사
  docs/                     # 설치(빠른 시작·프록시 뒤)·설정값 여섯 참조·운영자 가이드(신설·복구)·LDAP 변형 안내
  scripts/                  # 운영 셸 스크립트: dev-token.sh, membership-diff.sh(저장소 read 명단 vs harness-readers 차이), 복구 절차. 첫 파일과 함께 lang/bash 선언
```

## 3. 판정 원장

설계가 정하지 않은 구현·운영 선택만 적는다. 근거 등급은 우산 §3-1의 넷이다.

| # | 물음 | 판정 | 근거 |
|---|---|---|---|
| D1 | compose 서비스 이름·포트·볼륨 | 서비스 이름은 `registry`·`postgres`·`dex`. 밖으로 여는 포트는 `registry`의 HTTP 하나와 `dex`의 HTTP 하나(둘 다 프록시가 받는다). PostgreSQL은 compose 네트워크 안에서만 — **개발 compose(`docker/compose.dev.yml`)만 예외로 호스트 127.0.0.1에 연다**(호스트의 서비스·시험이 붙는다). 볼륨은 `pgdata` 하나와 레지스트리의 로컬 클론용 `clone` 하나 | 설계 판단. DESIGN §2.1 "인가는 레지스트리 안, 프록시는 TLS와 라우팅만"이라 프록시가 볼 종단은 둘뿐이다. 클론 볼륨은 재기동 때 전량 clone을 피하는 편의이며 잃어도 fetch가 다시 만든다(§2.1 준비됨 정의) |
| D2 | 데이터베이스 둘과 역할 둘은 누가 만드는가 | `docker/postgres/init.sql`이 만든다(postgres 이미지의 초기화 훅으로 마운트, 첫 기동에만 실행. 비밀번호는 환경 변수를 읽을 수 없는 `.sql` 대신 `init.sh`가 psql 변수 `:'hc_password'`로 넘긴다 — 2026-10-07 실측. `pg_trgm`도 슈퍼유저만 만들 수 있어 여기서 만든다). 서비스 마이그레이션은 `harness_catalog` 안의 표·확장(`pg_trgm`)만 소유한다 | 설계 판단. 서비스 역할은 자기 데이터베이스의 `CREATE`만 가지고 남의 데이터베이스를 만들 권한이 없어야 한다(§2 "별도 데이터베이스·역할"). 데이터베이스 생성은 인스턴스 소유자의 일이라 서비스 밖이다 |
| D3 | Dex 저장소 | `postgres`의 `dex` 데이터베이스, 전용 역할 | DESIGN §2 결정. 문면: Dex는 postgres 저장소를 지원한다 |
| D4 | Dex LDAP 커넥터 구조 | 선례를 그대로 쓴다: `~/workspace/dp-charts/argocd/values-override.yaml`의 `dex.config` LDAP 커넥터(Argo CD 내장 Dex가 같은 NAS LDAP에 붙어 운영 중). host `192.168.3.95:389`, `insecureNoSSL: true`(tailnet·사내망 안), `bindDN: uid=admin,cn=users,dc=gyojunan,dc=synology,dc=me`, userSearch `baseDN: cn=users,dc=gyojunan,dc=synology,dc=me`·`username: uid`·`idAttr: dn`·`emailAttr: mail`·`nameAttr: cn`, groupSearch `baseDN: cn=groups,dc=gyojunan,dc=synology,dc=me`·`userMatchers: [{userAttr: dn, groupAttr: member}]`·`nameAttr: cn`. 곧 그룹은 `member`에 사용자 DN을 담는 형태이고 `memberUid`가 아니다. bindPW만 환경 변수(`.env`)로 빼고 나머지는 `docker/synology-ldap/dex/config.yaml`에 적는다. `emailAttr`는 `uid`다(r2: admin·gyojunan에 `mail`이 없고 Dex는 emailAttr가 빈 항목의 로그인을 거부한다 — 선례의 `mail`과 다른 유일한 값). groupSearch `filter`는 비워 두고(선례와 같음. 그룹 하나만 거르면 `(cn=harness-readers)`) `groups` 클레임에 실린 전체 목록에서 레지스트리가 `harness-readers`를 본다. `groups` 스코프를 클라이언트 요청 스코프에 포함 | 선례(2026-10-07 확인): dp-charts argocd(운영 중, `g, devops, role:admin` RBAC가 `groups`로 동작), 같은 값이 dp-eks-charts argocd `values-live.yaml`에 주석으로, grafana·airflow·hue·kyuubi·jupyterhub도 같은 host·DN(사용자 쪽은 `memberOf`도 쓴다 — Synology LDAP이 양방향 속성을 둘 다 낸다). **r2(2026-10-07) 실측 확인**: 그룹은 `posixGroup`이고 `member`(DN)·`memberUid` 둘 다, 사용자에 `memberOf`. Dex(LDAPS 636, `insecureSkipVerify`)가 낸 토큰의 `groups`에 그룹 `cn`이 평탄하게 실린다. 636의 인증서는 만료된 옛 것(DSM 웹은 갱신됨)이라 검증은 운영자가 Directory Server 인증서를 재배정한 뒤에 켠다. 선례 파일에는 bindPW·GitHub App 키가 평문으로 있다 — 복사하지 말고 `.env`로 |
| D5 | 정적 클라이언트 | 공개 클라이언트 셋: `claude-code`·`codex`·`cursor`(각각 `public: true`, `redirectURIs` 비움 — Dex는 공개 클라이언트에 `127.0.0.1:<any>`·`localhost` 루프백과 oob·장치 콜백을 허용한다(`validateRedirectURI` 실측). 제품이 고정 URI를 문서에 적으면 그때 적는다). 기밀 클라이언트 하나: `ci-runner`(시크릿은 `DEX_CI_RUNNER_SECRET`(_FILE). 무인 읽기 = LDAP 기계 계정의 **비밀번호 그랜트**, `oauth2.passwordConnector: ldap`(개발 compose는 `local`) — 우산 §6-10 결정 2026-10-07). 그리고 audience 실험·대안용 클라이언트 하나: id = 레지스트리 공개 URL(`HC_PUBLIC_URL`), `trustedPeers` 넷. 클라이언트 ID 문자열은 제품 이름 그대로. 파일은 `docker/dex/config.yaml`(gomplate: 이미지 entrypoint가 `.yaml`을 렌더링하므로 환경 변수는 `{{ getenv "X" }}`; Dex 자체의 `$X` 치환은 storage·connector·signer config에만 돈다) | 설계 판단 + r1 실측(2026-10-07). DESIGN §2 "에이전트 제품마다 사전 등록" |
| D6 | PKCE 강제 | **Dex v2.45.1에는 강제 설정이 없다**(r1: `code_challenge` 없는 공개 클라이언트 요청이 발급된다, `cmd/dex/config.go`에 설정 없음). 레지스트리도 토큰만 보므로 알 수 없다. PKCE는 클라이언트 몫이고 MCP 인가 스펙이 클라이언트에 요구한다. V2의 "`code_challenge` 없는 요청 거부" 기준을 뺀다 | r1 실측(2026-10-07). 이전 행의 `pkce.enforce`는 문면 오류였다 |
| D7 | 토큰 수명 | Dex `expiry.idTokens`·액세스 토큰을 1시간으로. 리프레시는 Dex 기본 | DESIGN §2 "1시간 이하를 요구한다". 실제 수명은 V4가 잰다 |
| D8 | 장치 흐름 | 기본으로 켜져 있다(`grantTypes` 미지정 = 전부). **공개 클라이언트로 성립한다**(r1: `/device/code` → 사용자 승인 → `/device/token` 200, `client_secret` 없이; `deviceflowhandlers.go:342`는 빈 시크릿끼리 비교). `expiry.deviceRequests 5m` | r1 실측(2026-10-07). 이슈 #3983의 증상은 v2.45.1에서 재현되지 않았다 |
| D9 | 리버스 프록시 | mini의 `tailscale serve`가 TLS 종단이다(우산 §6-3 결정). 경로 둘을 로컬 포트에 잇는다: `/mcp` → `registry`, `/dex` → `dex`(issuer는 `https://mini.tail2f9fe3.ts.net/dex`, Dex는 경로가 붙은 issuer를 지원한다 — 문면). 인증서는 Tailscale이 낸다. 레지스트리 공개 URL(설정값)이 곧 canonical URI = 토큰 audience = RFC 9728 `resource`다. 접근 통제는 tailnet ACL이 전부이고 인가는 레지스트리 안이다(DESIGN §2). 개발 중 로컬은 `http://localhost:<port>`로 프록시 없이 | 사용자 결정(2026-09-26). 문면: MCP 인가 스펙의 RFC 8707·9728(DESIGN §2). tailnet 이름은 `tailscale status` 실측. `serve` 설정은 `scripts/`의 스크립트 하나로 재현 가능하게 둔다 |
| D10 | 비밀의 자리와 취급 | `.env`는 커밋하지 않고 `docker/.env.example`만 커밋한다. 개발 compose는 비밀을 환경 변수로 컨테이너에 넘긴다(`docker inspect`에 보인다 — 개발 전용 예외). 운영 compose는 postgres `POSTGRES_PASSWORD_FILE`·Dex `secretEnv`+파일 주입으로 바꾼다(P2). `.env`는 소유자 `0600`, 값은 §5 체크리스트의 생성 명령으로 만들고(deploy key `ssh-keygen -t ed25519`, 클라이언트 시크릿·DB 비밀번호는 `openssl rand -base64 32`), 전달은 운영 호스트에서 직접 생성하는 것만 허용하며 채팅·이슈에 붙이지 않는다. compose는 비밀을 그 값을 쓰는 컨테이너에만 준다(deploy key·DB 접속은 `registry`, LDAP bind·Dex 시크릿은 `dex`). `docker compose -f docker/compose.yml config`의 출력은 비밀을 담으므로 기록에 남기지 않는다. 회전은 값을 새로 만들어 `.env`를 바꾸고 해당 컨테이너를 재기동하는 것이고, 폐기는 git 호스트(deploy key)·Dex 설정(클라이언트)·PostgreSQL(역할 비밀번호)에서 옛 값을 지우는 것이다. 시크릿 저장소 연동은 두지 않는다 | 우산 §3-7. 설계 판단: VM 한 대·운영자 한 팀이라 파일 하나가 시크릿 저장소보다 단순하다. 취급 절차는 Codex 리뷰(2026-09-26) 반영 |
| D11 | 이미지 빌드·태그·보존 | 빌드 컨텍스트는 저장소 루트, Dockerfile도 루트. **한 번 빌드, 빌드 기계 = 실행 기계**: `main`에 합쳐지면 mini의 self-hosted runner(alteralab/portainer의 것과 같은 방식, 이 저장소 단위로 등록)가 이미지를 한 번 빌드해 `ghcr.io/alteralab/harness-catalog:<커밋 짧은 SHA>`로 push하고 digest를 워크플로 출력에 남긴다. 이미지가 mini의 docker 데몬에 남으므로 운영 compose는 같은 SHA 태그를 `.env`의 `REGISTRY_IMAGE`로 받아 **pull 없이** 쓰고, GHCR의 사본은 보관·복구(V10)용이다. 로컬 개발은 `docker/compose.dev.yml`에서 `build:`로 만들고 태그는 `dev`, GHCR을 건드리지 않는다. `latest`는 쓰지 않는다. **보존 규칙**: 같은 워크플로의 마지막 단계가 `delete-package-versions`로 태그 없는 버전을 전부 지우고 SHA 태그는 최근 5개만 남긴다. 그 밖의 태그(예: 복구 훈련용 고정 태그)는 두지 않는다 | 사용자 결정(2026-09-26, GHCR + 보존 규칙). DESIGN §2.1 "아티팩트는 하나". 근거: GHCR 컨테이너 저장·전송은 문서상 현재 무료(문면, 2026-09-26)이고, 계량되더라도 빌드·실행이 한 기계라 전송은 복구 때뿐이며 저장은 레이어 중복 제거 + 최근 5개로 200~300MB 추정(휴리스틱). V1이 실행 중인 이미지의 digest를 기록한다 |
| D12 | 헬스 체크·재시작 | `registry`는 `/healthz`를 compose healthcheck로, `postgres`는 `pg_isready`, `dex`는 자기 `/healthz`. `restart: unless-stopped`. `registry`는 `postgres`·`dex`의 healthy를 `depends_on` 조건으로 | DESIGN §2.1 "죽으면 다시 뜬다", 살아 있음·준비됨 분리. `/readyz`는 오케스트레이터가 트래픽을 빼는 신호인데 compose 한 대에는 그 소비자가 없어 healthcheck에는 쓰지 않는다 |
| D13 | CI 워크플로 형식 | 파일은 GitHub·GitLab 둘 다 싣는다(DESIGN §2.1). 먼저 실제로 돌리는 것은 우산 §6-2가 고른 호스트의 것이고, 다른 호스트 파일은 문면대로 작성만 된 상태로 남는다(그 사실을 README에 적는다) | 설계 판단. 안 돌린 워크플로는 게이트가 아니다(C-GATE-1). 두 파일을 다 완주시키려면 호스트가 둘 필요하고 지금은 하나다 |
| D14 | 기본 스킬 둘의 경로 | **개정 2026-10-10(사용자 결정).** `init`이 표지·README·CI와 함께 `skills/pin-skill`·`skills/write-skill`을 쓴다. 새 카탈로그는 첫 명령 직후부터 두 스킬이 검색된다. 스킬 원본은 CLI 패키지 데이터 `templates/skills/` 하나로 옮겨 사본을 늘리지 않는다(C-DUP-2 유지). 갱신은 여전히 PR이다(`init`은 없는 것만 쓴다). 이전 판은 "빈 카탈로그 + 첫 PR"이었고 그 근거는 사본 수였는데, 원본을 패키지 데이터로 옮기면 그 근거가 사라진다 | 우산 DESIGN §11 2026-10-10 행. 첫 저장소 alteralab/catalog는 이전 판대로 PR #1로 들어갔다 |
| D15 | 저장소 신설 = `harness-catalog init` + 체크리스트 | 파일 다섯(표지·README·pre-commit 설정·호스트별 CI)과 기본 스킬 둘(D14)은 `init`이 운영자 git 자격으로 쓴다(DESIGN §2.1). git 호스트·Dex 화면에서만 할 수 있는 것(deploy key, 협업자 권한, 리다이렉트 URI)은 §5 체크리스트가 남는다 | DESIGN §2.1 저장소 초기화(v3.3). 템플릿 원본은 `packages/cli/src/harness_catalog_cli/templates/`이고 패키지 데이터로 `init`에 실린다 |
| D16 | compose를 어디서 돌리는가 | 운영은 `mini.altera.lab`(우산 §6-1 결정, 2026-09-26). 개발·시험은 맥북 로컬에서 같은 compose 파일로 띄운다 — P0·P1의 `docker/compose.dev.yml`이 그 자리이고, 운영 compose(P2)도 로컬에서 먼저 한 번 띄운 뒤 mini로 간다 | 사용자 결정. 같은 파일을 두 곳에서 쓰므로 호스트별 값은 전부 `.env`에 있어야 한다(D10) |
| D18 | 빠른 시작 compose의 Dex | 루트 `docker/compose.yml`의 Dex는 `docker/dex/config.yaml`의 정적 사용자(`staticPasswords`)와 정적 클라이언트로 뜬다. LDAP 연합은 `docker/synology-ldap/compose.override.yml`이 Dex 설정 파일을 바꿔 끼우는 오버레이다. 서비스 쪽은 issuer URL 하나라 두 경우가 같다 | 설계 판단(우산 §3-8 오픈소스 패키지). 문면: Dex는 `staticPasswords`와 `docker-compose.yaml`을 루트에 둔 자기 빠른 시작을 낸다(2026-09-26 저장소 실측). 정적 사용자는 시험·데모용이고 운영 안내(docs/)는 LDAP 또는 사내 IdP를 가리킨다 |
| D19 | CI의 evals 잡 | `main` push 워크플로의 선택 잡. 파일에 항상 있고 `if: github.ref == 'refs/heads/main' && vars.HARNESS_EVALS == 'true'`(GitLab은 `rules:if` + `$HARNESS_EVALS == "true"`), `runs-on: [self-hosted, harness-catalog]`(GitLab `tags: [harness-catalog]`). `strategy.matrix.agent`는 `${{ vars.HARNESS_EVALS_AGENTS || 'claude-code codex' }}`를 쪼갠 것(변수가 없으면 기본. `HARNESS_EVALS`도 없으면 빈 문자열이라 잡이 안 생긴다 — 저장소 생성 시 변수는 필요 없다). 첫 단계가 그 하네스의 모델 자격(`claude-code`: `CLAUDE_CODE_OAUTH_TOKEN`+`CLAUDE_FORCE_OAUTH=1` 또는 `ANTHROPIC_API_KEY`; `codex`: `OPENAI_API_KEY` 또는 `CODEX_FORCE_AUTH_JSON=1`+`~/.codex/auth.json`; `cursor-cli`: `CURSOR_API_KEY`; `gemini-cli`: `GEMINI_API_KEY`/`GEMINI_FORCE_OAUTH` — Harbor `agents/installed/*.py` 실측)과 Langfuse 키 셋의 존재를 검사해 비면 이름을 적고 실패. 본 단계는 `harbor run --env docker --plugin harbor_langfuse:LangfusePlugin`으로 변경된 스킬의 `evals/`를 스킬 있이·없이 돌리고 Langfuse에 남긴다. 레지스트리에는 아무것도 적지 않는다. 자격은 mini 러너 루트의 `.env`(D21)에서 온다. 라이브 소비 시험 태스크를 둘 때만 `HC_CI_CLIENT_SECRET`(`ci-runner`)이 더해진다 | 사용자 결정(DESIGN §11 CI 게이트). `[웹]` GitHub `jobs.<id>.if`에 `secrets` 불가·`vars` 가능, GitLab `rules:if`에 프로젝트 변수 가능(실측). Harbor `claude_code.py`의 `CLAUDE_FORCE_OAUTH`(실측). 구독 quota를 대화 세션과 나눠 쓴다. Langfuse Hobby units 한도는 pilot Q14(e)가 실측 |
| D20 | 레지스트리 스팬의 OTel 배선 | `docker/.env.example`에 `OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel`(지역별 호스트는 주석), `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64(pk:sk)>`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_SERVICE_NAME=harness-catalog`. 비워 두면 스팬은 no-op이라 빠른 시작은 Langfuse 없이 뜬다. 셀프호스팅 Langfuse로 옮기면 ENDPOINT만 바뀐다 | 사용자 결정(DESIGN §11 v3.5). `[웹]` Langfuse OTel 수신은 HTTP/protobuf·JSON, Basic 인증(실측). gRPC 미지원이라 `_PROTOCOL`을 명시한다 **구현 2026-10-10**: `server/telemetry.py`, `docker/.env.example` 관측 절, 운영은 헤더를 비밀 파일 `otlp_headers`로(D10) |
| D21 | 러너의 자격 파일과 켜고 끄기 | mini self-hosted 러너 루트의 `.env`에 돌릴 하네스마다의 모델 자격과 Langfuse 키 셋을 적는다(Codex를 구독으로 돌리면 `.env` 대신 러너 사용자의 `~/.codex/auth.json` + `CODEX_FORCE_AUTH_JSON=1`)(`[웹]` actions/runner `Program.cs`가 루트 `.env`를 읽어 잡 환경으로. 실측). 파일의 본은 `docs/`의 운영자 가이드에 `runner.env.example`로 둔다(저장소에는 예시만, `.env`는 러너 머신에만). **켜기**: `.env` 채우고 러너 재기동(`svc.sh restart`), `gh variable set HARNESS_EVALS --body true`(하네스 목록을 바꿀 때만 `HARNESS_EVALS_AGENTS`). `init`은 변수를 만들지 않고 README에 이 절차를 적는다. **끄기**: `gh variable set HARNESS_EVALS --body false`(러너·파일 그대로). 카탈로그 서비스의 `.env`·재기동과 무관하다 — 레지스트리는 저장소에 쓰지 않는다(DESIGN §2) | 사용자 요구(켜고 끄기 양방향, 자격은 설정 파일에). 스위치가 시크릿이 아니라 변수인 이유는 D19의 GitHub 제약 |
| D22 | 이미지 밖 배포물의 설치 명세와 판 핀 | 코드 저장소의 릴리스는 git 태그 `v<판>` 하나이고(service D1 lockstep) 이미지도 그 커밋에서 빌드된다(D11). 이미지 밖에서 설치하는 자리는 셋이고 전부 같은 태그를 박은 git 하위 디렉토리 명세를 쓴다. **(a) 저자의 pre-commit 훅** — 템플릿 `.pre-commit-config.yaml`은 `repo: local` + `language: python` + `entry: harness-catalog check` + `additional_dependencies`에 `harness-catalog-core @ git+https://github.com/alteralab/harness-catalog@v<판>#subdirectory=packages/core`와 `harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v<판>#subdirectory=packages/cli` **둘 다**(pre-commit은 pip로 설치하고 pip는 `tool.uv.sources`를 모르므로 cli 하나만 주면 `core`를 못 찾는다 — 실측). `rev` 키는 local 훅에 없고 핀은 명세 안의 `@v<판>`이다(DESIGN §5 "rev로 핀"의 실체). **(b) CI의 check 잡** — `uvx --from "harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v<판>#subdirectory=packages/cli" harness-catalog check --base <merge-base|직전 커밋>`. uv는 체크아웃의 워크스페이스 소스로 `core`를 같은 판에서 푼다(실측). **(c) evals 러너(D19)** — `uvx --from harbor==<Harbor 판> --with "harbor-langfuse @ git+https://github.com/alteralab/harness-catalog@v<판>#subdirectory=packages/harbor-langfuse" harbor run … --plugin harbor_langfuse:LangfusePlugin`. 플러그인은 서비스 이미지에 없다(service P3-7). **태그 ↔ 이미지 매핑**: 판 태그 `v<판>`은 `main`의 커밋 하나에 달고, 그 커밋을 D11이 빌드한 `:<짧은 SHA>` 이미지가 그 판의 운영 이미지다. 이미지에 v 태그를 더하지 않는다(D11 유지). 운영 `.env`의 `REGISTRY_IMAGE`는 `git rev-parse --short v<판>`으로 채우고 운영자 가이드가 이 한 줄을 적는다 — 그래서 cli·플러그인·이미지가 같은 커밋이다. **`init`의 오핀 방지**: `init`은 `<판>`을 채우기 전에 코드 저장소에 `git ls-remote --tags https://github.com/alteralab/harness-catalog v<판>`으로 그 태그가 있는지 확인하고, 없으면(editable·개발 빌드·태그 전) 종료 1과 사유를 낸다. `--pin <ref>`를 주면 확인 없이 그 ref를 쓴다(개발용). 판 올리기 = 카탈로그 저장소에서 명세의 태그를 바꾸는 PR 하나(service P3-3) | 2026-10-07 실측(uv 0.11.8, pre-commit 4.3.0, 대역 워크스페이스 core+cli, 태그 `v0.1.0`): uv `pip install`·`uvx`는 cli 명세 하나로 두 패키지를 설치·실행했고, pre-commit local 훅은 둘 다 명시하면 통과, cli만이면 `No matching distribution found for hc-core==0.1.0`. 실물 저장소에서의 재확인은 V13 |
| D23 | 빠른 시작 compose(`docker/compose.quickstart.yml`) | 명령 둘(clone, `up -d --build --wait`)로 전체(postgres·dex·catalog-init·registry·welcome)가 뜬다. 모든 변수에 `${VAR:-기본값}`, 비밀은 공개 값(평가·데모 전용이라 파일 머리에 명시). `catalog-init`이 이 저장소의 `skills/`와 init 템플릿으로 bare 저장소를 볼륨에 심고(멱등) registry가 `file:///catalog/catalog.git`을 받는다. registry는 `network_mode: service:dex`로 Dex의 네트워크 네임스페이스를 공유한다 — issuer `http://localhost:5556/dex`가 브라우저와 컨테이너 양쪽에서 같은 곳이어야 하기 때문이고 포트는 dex 서비스가 연다. `welcome`이 준비 뒤 접속 안내를 로그에 찍는다. 운영 compose·개발 compose는 그대로다 | Apache Airflow·Polaris 빠른 시작 실측(2026-10-10, `research/refs/`): Airflow는 compose 파일 하나 + `airflow-init` 서비스(`service_completed_successfully`) + 공개 자격 `airflow/airflow` + "개발 전용" 경고, Polaris는 `curl … \| docker compose -f - up`에 `${ROOT_CLIENT_SECRET:-s3cr3t}` 기본값·setup 사이드카가 자격을 로그에 출력. 사용자 지적("명령어 일일이 입력") |
| D17 | 셸 스크립트 | 복구 절차처럼 명령이 넷을 넘는 것만 `scripts/`에 둔다. 첫 파일과 함께 `altera-rules.yml`에 `lang/bash`를 선언하고 `altera-shellcheck` 훅을 건다 | 우산 §3-5 |

## 4. 단계

### distribution P0. 실측 지원용 개발 compose (우산 P0 안)

1. LDAP 스키마 실측: NAS Directory Server에 `ldapsearch`로 사용자 하나·그룹 하나의 항목을 읽어 객체 클래스와 `member`(그룹 쪽)·`memberOf`(사용자 쪽) 원문을 pilot r에 적는다. D4의 선례(dp-charts argocd)가 `member`에 DN을 담는 형태로 이미 운영 중이라 이 단계는 발견이 아니라 확인이고, `harness-readers` 그룹을 NAS에서 만들고 시험 사용자를 넣은 뒤의 항목을 같이 적는다. Dex 없이 된다.
2. `docker/compose.dev.yml` 초판: `postgres`(init.sql로 데이터베이스·역할 둘) + `dex`(LDAP 커넥터는 1의 실측값, 정적 클라이언트는 공개 PKCE·공개 장치·`ci-runner` 셋). pilot Q2·Q5가 이것으로 토큰 실물을 잰다.
3. `docker/.env.example` 초판: Dex·DB 비밀과 LDAP 바인드 값.

완료 조건(우산 §4 P0 행의 distribution 몫): 개발 compose가 뜨고 pilot Q2의 세 그랜트가 실제로 호출됐다(결과는 pilot r에). **상태(2026-10-07)**: 1·2·3 완료. 1은 r2(로컬 랜, `ldapsearch` + 호스트 빌드 Dex로 연합 토큰까지). 세 그랜트 호출 완료(r1: 둘 성공, client_credentials는 Dex 미지원). **distribution P0 완료.**

### distribution P1. 시험용 토큰 절차와 Dex 확정판 (우산 P1과 함께)

1. `docker/compose.dev.yml`을 P0 실측대로 확정한다(LDAP 스키마 하나, 클라이언트 셋). 서비스는 포함하지 않는다 — service P1·P2가 호스트에서 uvicorn으로 뜨고 이 둘에 붙는다.
2. `docker/dex/config.yaml` 초판: issuer는 `http://localhost:<port>`, LDAP 커넥터는 Synology 실물(D4, pilot P0의 스키마 실측을 받는다), 정적 클라이언트는 시험용 공개 클라이언트 하나와 `ci-runner`.
3. `docker/.env.example` 초판: Dex·DB 비밀과 LDAP 바인드 값.
4. `scripts/dev-token.sh`: 시험용 토큰 취득 절차. (a) 사람 토큰 — PKCE `code_verifier`·`code_challenge`(S256) 생성, `authorize` URL에 `scope=openid groups audience:server:client_id:<레지스트리 공개 URL>`(r1: `resource`는 무시되고 `skills:read`는 `invalid_scope`. 스코프 확정은 우산 §6-11·12), 루프백 콜백(`http://127.0.0.1:<port>/callback`)을 `python3 -m http.server` 대신 스크립트 안의 표준 라이브러리 리스너로 받아 `code`를 교환, 액세스 토큰만 표준 출력. (b) 서비스 토큰 — 우산 §6-10의 결정대로(클라이언트 자격 증명은 Dex에 없다, r1; 권고 (라)면 이 모드는 없다). 토큰·시크릿은 로그에 남기지 않는다(표준 오류에도 안 찍는다). service의 `tests/http`는 `HC_TEST_TOKEN`·`HC_TEST_SERVICE_TOKEN` 환경 변수로 받는다. 이것이 첫 셸 스크립트이므로 `lang/bash` 선언과 shellcheck 게이트 완주(D17)를 같은 커밋에서 한다.

완료 조건(우산 §4 P1 행의 distribution 몫): "distribution P1은 시험용 토큰 취득 절차(`scripts/dev-token.sh`: PKCE + `resource`, 클라이언트 자격 증명)와 Dex 설정의 LDAP 확정판". 판정은 V2·V3·V11 — LDAP 사용자로 로그인한 사람 토큰에 `groups: [skills]`가 있고, `ci-runner`의 클라이언트 자격 증명 토큰 실물이 기록됐으며, 두 토큰이 스크립트 한 번으로 나온다.

### distribution P2. 루트 compose와 LDAP 오버레이 (우산 P5 전반)

1. `docker/compose.yml`: `registry`(D11 이미지, 설정값 여섯을 `.env`에서) + `postgres` + `dex`(D18 정적 사용자). D1 포트·볼륨, D12 healthcheck·재시작. `docker/synology-ldap/`: 오버레이와 LDAP 커넥터 설정(D4), README.
2. 프록시 배치 메모(D9): 프록시가 두 종단(레지스트리·Dex)을 공개 URL로 넘기는 규칙을 README에 적는다. 프록시 자체 설정은 조직 것이라 이 저장소 밖이다.
3. Dex 설정을 운영 값으로: issuer = 공개 URL, 클라이언트 셋의 리다이렉트 URI(pilot P0 실측값), PKCE 강제, 수명 1시간.
4. `docs/`: 설치(빠른 시작·프록시 뒤)·설정값 여섯 참조·LDAP 변형 안내·CI evals 게이트 켜고 끄기(D21). 러너 `.env` 견본은 설정 예시이므로 `.github/runner.env.example`(2026-10-10, docs/에서 옮김).
5. V1·V4·V5 통과.

### distribution P3. 저장소 템플릿과 첫 카탈로그 저장소 (우산 P5 후반)

1. `packages/cli/src/harness_catalog_cli/templates/` 완성(`init`의 패키지 데이터 원본): `.harness-catalog`(`layout = 1`), `skills/{pin-skill,write-skill}/`(D14 개정), README(§5 체크리스트 + 등록 한 줄 + 브랜치 규율 + "검색어에 비밀을 넣지 말라"), `.pre-commit-config.yaml`(`harness-catalog check`, 설치 명세·판 핀은 D22), `github/check.yml`, `gitlab/.gitlab-ci.yml`(PR·`main` push마다 `harness-catalog check`(D22 (b)); `main` push에는 선택 잡 `evals`(D19: 항상 파일에 있고 `HARNESS_EVALS` 변수로 켜고 끈다, 자격 존재 검사 → `harbor run --plugin harbor_langfuse` → Langfuse, 러너 라벨 `harness-catalog`). 모델 자격은 하네스마다 러너 환경에서(D19의 목록; Claude는 `CLAUDE_CODE_OAUTH_TOKEN`+`CLAUDE_FORCE_OAUTH=1`, Codex는 `OPENAI_API_KEY` 또는 auth.json). Harbor 판은 워크플로에 핀).
2. 첫 카탈로그 저장소 신설: §5를 처음부터 끝까지 한 번 따른다(`init` 포함). 우산 P4에서 작성·검증된 두 스킬은 `init`이 함께 쓴다(D14 개정 2026-10-10; 첫 저장소는 PR #1).
3. V6·V7·V8 통과. 우산 V3(우회 push 수용)·V4(fail-closed)·V5(재기동 복구)의 실행 환경을 제공한다.

완료 조건(우산 §4 P5 행의 distribution 몫): "새 VM에서 `.env`만 채우고 `docker compose -f docker/compose.yml up`으로 셋이 뜨고 `/readyz` 200, `init`으로 만든 저장소의 첫 PR CI가 두 스킬로 초록, deploy key(읽기 전용)·권한 체크리스트 전 항목 확인".

## 5. 운영자 체크리스트 (README에 실리는 것)

각 항목은 확인 명령이나 화면이 있다.

1. git 호스트에 빈 저장소를 만든다. 확인: `git ls-remote <url>`이 빈 결과로 성공한다.
2. `harness-catalog init <repo-url>`을 운영자 git 자격으로 돌린다. 확인: 원격의 루트에 `.harness-catalog`(`layout = 1`)·`skills/pin-skill`·`skills/write-skill`·README·pre-commit 설정·이 호스트의 CI 워크플로가 있고, 두 번째 실행이 변경 0이다.
3. `main` 보호는 걸지 않는다(우산 §6-8 결정, DESIGN §11). 강제 push 금지는 규율이다. 확인 항목 없음.
4. deploy key(**읽기 전용**)를 등록하고 개인 키를 `.env`의 자리에 넣는다. 확인: 레지스트리 컨테이너 안에서 `git fetch`가 성공하고 `git push --dry-run`이 거부된다. 저자에게는 저장소 write(브랜치·PR), 병합·설정을 할 사람에게는 admin을 준다. `harness-readers` 그룹 명단과 저장소 read 이상 명단이 같다.
5. `init`이 놓은 CI 워크플로가 도는지 본다. 확인: 첫 PR의 CI가 `harness-catalog check`를 돌려 초록이다(V6; 첫 저장소에서는 두 스킬 PR이었다). pre-commit 훅은 저자마다 `pre-commit install`.
6. Dex에 하네스 제품의 정적 클라이언트가 있고 리다이렉트 URI가 그 제품 문서와 같다. 확인: 그 하네스에서 로그인 한 번(우산 V1).
7. DSM의 LDAP Server 패키지(구 Directory Server) → 그룹 관리에서 `harness-readers`를 만들고(r2: 아직 없다) 첫 팀원을 넣는다. LDAPS 검증을 켜려면 mini에서 `gyojunan.synology.me`를 192.168.3.95로 풀어 주고(/etc/hosts 또는 split DNS) `.env`를 `LDAP_HOST=gyojunan.synology.me:636`, `LDAP_INSECURE_SKIP_VERIFY=false`로 둔다(r2: 인증서는 2026-10-07 패키지 재시작으로 갱신됨; 갱신 뒤 데몬이 안 읽으면 `sudo synopkg restart DirectoryServer`)(r2: 636이 만료된 인증서를 낸다). LDAP 그룹 `harness-readers`에 첫 팀원이 있다. 확인: 그 사람의 토큰에 `groups`가 있다(V2). 카탈로그 저장소의 read 이상 권한을 가진 사람 명단이 이 그룹과 같다(그룹에 없는 사람은 레지스트리에서 `not_a_member`이므로 저장소 쪽만 넓으면 우회가 생긴다).
8. `.env`의 필수 설정값 다섯이 채워졌고 선택 둘은 비워 두거나 의도한 값이다. 확인: `docker compose -f docker/compose.yml config`가 빈 필수 변수를 경고하지 않는다.
9. `docker compose -f docker/compose.yml up -d` 뒤 `/healthz` 200, `/readyz` 200(V1). 503이면 본문의 사유(`not_a_catalog`·`no_main_branch`·`repo_unreachable`·`layout_mismatch`)대로 2·4번을 다시 본다.
10. 하네스에 레지스트리 URL 한 줄을 등록하고 `list_skills`가 두 스킬을 돌려준다.
11. `.env`는 소유자만 읽는다(`0600`). 확인: `stat -f %Lp .env`(macOS) 또는 `stat -c %a .env`가 600이다. 값의 생성·전달·회전·폐기는 D10대로.
12. 검색어에 비밀을 넣지 않는다 — 검색어가 Langfuse의 도구 호출 스팬에 남는다(DESIGN §5 감사).

## 6. 불채택 표

기각 사유는 현재형으로만 적는다.

| 항목 | 기각 근거 (왜 지금 아닌가) |
|---|---|
| Helm 차트 | 인스턴스 하나. compose 한 대가 설계의 v3.0이다(우산 §7) |
| 백업 크론(pg_dumpall·git bundle) | DB는 파생물뿐이고 사용 기록·평가 결과는 Langfuse에 있다(DESIGN §2.1). 동급 셀프호스팅 셋도 compose에 백업이 없다(문면) |
| 가짜 OIDC 서버(모의 issuer) | 개발 compose에 실제 Dex가 뜬다(P1). 단위 시험은 service가 OIDC 어댑터를 가짜로 바꾼다. 셋째 인가 구현이다 |
| 레지스트리의 LDAP 직접 바인드 | 레지스트리가 아는 신원 유형은 OIDC 하나다(DESIGN §2). 비밀번호를 받을 자리가 없다 |
| 동적 클라이언트 등록(RFC 7591) | 스펙이 폐기 예정으로 두었고 Dex 지원을 확인하지 못했다(문면). 정적 클라이언트 넷이면 충분하다 |
| API 게이트웨이(인가·속도 제한·로깅) | 단일 백엔드에 TLS 종단이면 리버스 프록시로 충분하다(DESIGN §2). 인가는 레지스트리 안이다 |
| Kubernetes(관리형 포함) | 서비스 하나에 과잉이다(DESIGN §2.1 실천 층) |
| PaaS(Cloud Run 등) | 조직 표준이 아니다(우산 §6-1 미결이지만 후보에 없다) |
| git 호스트 webhook | 주기 fetch(설정, 기본 60초)가 우회 push를 받는다. webhook은 호스트별 등록·검증·재시도가 따른다(DESIGN §2 인덱스 갱신) |
| 별도 템플릿 저장소 | 템플릿과 그것을 읽는 레지스트리가 같은 판으로 움직여야 한다(DESIGN §2.1, §11 6차 사용자 결정) |
| 호스트 중립 CI 추상(한 파일에서 둘 생성) | 호스트가 하나뿐이고 파일 둘을 손으로 두는 비용이 생성기보다 작다 |
| 레지스트리가 기동 시 저장소 구조를 써넣기 | CI 파일이 호스트별이라 git 어댑터의 호스트 중립이 깨진다. 기동 시 검사만 한다(DESIGN §2.1) |
| Harbor(셀프호스팅 레지스트리, LDAP 연동) | 이미지를 당기는 주체가 mini의 compose 하나, 미는 주체가 runner 하나라 LDAP RBAC·스캔·복제의 소비자가 없다. 컨테이너 아홉과 DB 백업·업그레이드가 이미지 하나의 보관에 붙는다 |
| ECR | AWS 계정·IAM·12시간 만료 토큰이 mini에 붙고 AWS 밖으로의 pull마다 전송 요금이 든다. 이 설계에 AWS 의존은 다른 데 없다 |
| `registry:2` 한 컨테이너 | 계량이 없는 대안이지만 GHCR이 현재 무료이고 빌드·실행이 한 기계라 전송이 사실상 없다. 볼륨 백업 책임만 더한다 |
| 시크릿 저장소 연동 | VM 한 대·팀 하나에 `.env` 파일이 더 단순하다(D10) |

## 7. 리스크 대응표

우산 R1(Dex 장치 흐름)·R2(하네스 MCP 개정판)·R3(LDAP 그룹 클레임)은 Dex 설정(`docker/dex/`, `docker/synology-ldap/`)에 걸리고 대응은 우산 것을 따른다.

| # | 리스크 | 대응 |
|---|---|---|
| R1 | Synology Directory Server의 그룹 스키마가 Dex `groupSearch` 예제와 다르다 | D4를 운영 중인 선례(dp-charts argocd, `member`에 DN)로 고정했다. pilot P0-1의 `ldapsearch`가 `member`·`memberOf` 원문으로 확인하고, 다르면 D4를 고친다 |
| R2 | 프록시가 `X-Forwarded-Proto`를 안 넘겨 RFC 9728 메타데이터의 `resource`가 `http://`로 나온다 | 레지스트리는 헤더를 해석하지 않고 설정값 "레지스트리 공개 URL"을 그대로 canonical URI로 쓴다(DESIGN §2 설정값). V1이 프록시 뒤에서 챌린지 헤더 실물을 본다 |
| R3 | postgres 이미지의 초기화 훅이 볼륨이 이미 있으면 돌지 않아 init.sql 변경이 반영되지 않는다 | init.sql은 데이터베이스·역할 생성만 담아 바뀔 일이 없게 한다(D2). 바꾸면 볼륨을 지우고 다시 만드는 것이 절차이며 V1이 그 경로다 |
| R4 | 템플릿 저장소의 CI가 `skills-ref`·gitleaks 판을 핀하지 않아 서비스 이미지의 검사와 어긋난다 | 워크플로 파일이 두 도구의 판을 명시하고 plans/service.md가 이미지에 핀한 판과 같은 값을 적는다. 어긋남은 V6에서 두 판을 대조해 잡는다 |
| R5 | `.env`가 실수로 커밋된다 | `.gitignore`에 `.env`, V9가 저장소 전체를 gitleaks로 훑는다 |

## 8. 검증 원장

| # | 검증 | 방법 | 통과 기준 | 상태 |
|---|---|---|---|---|
| V1 | 깨끗한 VM에서 기동 | 새 VM에 저장소를 받고 `.env`만 채운 뒤 `docker compose -f docker/compose.yml up -d` | 컨테이너 셋 전부 healthy, `/healthz` 200, `/readyz` 200. 프록시 뒤에서 토큰 없는 호출의 401 챌린지 `resource_metadata`가 공개 URL이다. 실행 중인 `registry` 이미지의 digest가 CI 빌드 출력의 digest와 같다(D11) | 대기 |
| V2 | 사람 토큰 | LDAP 사용자로 공개 클라이언트(PKCE) 로그인 | 토큰의 `iss`가 issuer, `aud`가 레지스트리 URL, `groups`에 `harness-readers`, `sub`가 사용자 | **통과(2026-10-07)**: 클레임은 r2에서 `gyojunan` 토큰으로 확인, 실제 하네스 로그인은 Claude Code 대화형 세션에서 브라우저 로그인 → `list_skills` 200(plans/pilot/r3.md) |
| V3 | 서비스 주체 토큰 | `ci-runner`로 클라이언트 자격 증명 | 토큰 실물(`sub`·`azp`·`groups` 유무)을 pilot r에 기록했고, service의 인가 정책이 그 표지로 서비스 주체를 가른다 | 대기(pilot P0과 같은 실측) |
| V4 | 토큰 수명 | V2·V3 토큰의 `exp - iat` | 3600초 이하 | 대기 |
| V5 | 표지 검사 | `.harness-catalog`가 없는 저장소, `layout = 2`인 저장소, 빈 저장소를 각각 가리켜 기동 | 각각 `/readyz` 503과 사유 `not_a_catalog`·`unsupported_layout`·`no_main_branch` | 대기 |
| V6 | `init` → 첫 PR CI 초록 | `init`으로 만든 저장소에 두 스킬의 PR | 워크플로가 `harness-catalog check`를 돌리고 초록. 검사 항목 하나를 일부러 깨면 붉다. 도구 판(패키지·gitleaks)이 service 이미지의 핀과 같다 | **초록 부분 통과(2026-10-07)**: `alteralab/catalog` PR #1 run 37538600605 — deploy key 시크릿으로 비공개 코드 저장소에서 cli 설치, `check` 통과 12초. 일부러 깨기는 미실측 |
| V7 | 브랜치 보호 | 걸지 않기로 했다(우산 §6-8, DESIGN §11 사용자 결정 2026-09-26). Free 플랜 비공개 저장소에 설정이 없다 | 해당 없음 | 불채택 |
| V8 | 읽기 전용 deploy key와 병합 반영 | 컨테이너 안에서 `git push --dry-run`; 사람이 PR을 병합 | push는 거부되고 fetch는 된다. 병합이 우산 V3의 허용오차(`FETCH_INTERVAL_SECONDS` 두 주기) 안에 `list_skills`에 나온다 | **병합 반영 통과(2026-10-07)**: 사용자가 PR #1 병합(87bec19) → mini `/readyz` `commit`=87bec19, `rejected` 없음(fetched 22:13:18Z), 기계 계정 토큰으로 `list_skills` → `pin-skill`·`write-skill` 둘. main push CI도 초록(run 37539123231). `push --dry-run` 거부는 미실측 |
| V12 | 이미지 보존 규칙 | 커밋 여섯을 연속으로 `main`에 합친 뒤 GHCR 패키지 버전 목록을 본다 | SHA 태그가 정확히 5개, 태그 없는 버전 0개, 마지막 다섯 커밋의 SHA와 일치 | 대기 |
| V9 | 비밀 없음 | 저장소 전체 gitleaks | `.env` 없음, 검출 0 | 대기 |
| V10 | 새 VM 복구 | 우산 V5. 기존 카탈로그 저장소를 가리켜 V1을 다시 | fetch만으로 인덱스가 다시 지어지고 은퇴한 이름을 `check` 항목 5가 여전히 거부한다 | 대기 |
| V13 | 이미지 밖 설치 명세 | 실물 코드 저장소에 태그 `v<판>`을 단 뒤 (a) 빈 카탈로그에서 `pre-commit run --all-files` (b) `uvx --from "<D22 cli 명세>" harness-catalog --version` (c) `uvx --from harbor==<판> --with "<D22 플러그인 명세>" python -c "import harbor_langfuse"` (d) 워크스페이스 체크아웃에서 `uv run harness-catalog init <빈 저장소>`(editable, 태그 없는 커밋) | (a)~(c) 성공하고 (a)·(b)가 보고하는 cli 판이 태그와 같으며, 템플릿에 `<판>` 자리표가 남아 있지 않다. (d)는 종료 1에 "태그 없음" 사유, `--pin <sha>`를 주면 성공 | 대기(대역 실측 2026-10-07 통과, D22) |
| V11 | 시험용 토큰 절차 | `scripts/dev-token.sh`를 사람·서비스 모드로 각각 한 번 | 각각 토큰 하나가 표준 출력에 나오고, `aud`가 레지스트리 공개 URL이며, 표준 오류·셸 이력·로그 어디에도 토큰·시크릿 문자열이 없다 | 대기 |

## 9. 개정 규약

판정 변경은 §3에 행 추가(기존 행 유지, 후속 행 우선). 설계 계약(설정값 이름·표지 형식·CI가 돌리는 검사)의 변경은 DESIGN §11이 먼저. 진행은 §10에 적고 단계 완료만 우산 §11에 올린다. 재심 조건·트리거를 등록하지 않고 기각에는 지금 아닌 이유를, 근거에는 등급을 붙인다(REVIEW.md V-REC-1).

## 10. 진행 원장

| 일자 | 항목 | 내용 | 근거 |
|---|---|---|---|
| 2026-10-10 | 설정 표면 최소성 — Codex 재검증 | 사용자 질문("변수가 너무 많은데 다 필요한가"). 내 판정: 이름 ≈60, 운영자가 적는 것 ≈10 + 파일 2, 트림 넷 제안. Codex: compose 네 파일의 변수명은 중복 제거 28(비밀 파일 더해 36)이라 "≈60"은 CLI 옵션·OTel·CI·러너·시험까지 센 수이고, "10값 + 2파일"은 맞다(단 LDAP 기본값이 실제 환경과 같을 때). 트림 판정 — **승인**: `HC_VERSION` 덮어쓰기 제거(스크립트는 cli version 폴백), 빠른 시작 fetch 주기 10초 고정, Dex 내부 변수 다섯을 접이식 "자동 배선" 표로, `OTEL_SERVICE_NAME` compose·.env.example 덮어쓰기 제거(코드 기본값과 같음). **거부**: 개발 compose 비밀 기본값화(운영과 같은 임의값 생성 습관·필수 입력 검증 약화), `HARNESS_CATALOG_READ_TOKEN` 삭제(지원 중인 PAT 경로), LDAP insecure 플래그 병합(평문 전환과 인증서 검증 생략은 다른 뜻), hairpin 자동 유도(IP는 유도 불가), dev compose 삭제(호스트 실행·DB 포트 공개를 빠른 시작이 못 함). 덧붙여 DESIGN §2의 "이 일곱 밖의 설정값은 없다"가 아직 일곱이라 여섯으로 정정. configuration.md 머리에 §0 "운영자가 꼭 채우는 것" 표 추가 | Codex 리뷰 2026-10-10 |
| 2026-10-10 | 설정 표면 Codex 리뷰 반영 | 사용자 요청("설정 값이 제대로 고려되었는지, Langfuse 설정은?"). Codex 9건 중 distribution 몫: ① D20이 약속한 `.env.example`의 OTEL 넷(ENDPOINT·HEADERS·PROTOCOL·SERVICE_NAME)이 없었다 → 추가(Langfuse 지역별 엔드포인트, Basic 헤더 만드는 법 주석), 빠른 시작 compose에도 전달, 운영 compose에 `OTEL_SERVICE_NAME`. ② OTLP 헤더(Langfuse 키)가 운영 compose에서 평문 환경 변수 — D10 위반 → 비밀 파일 `otlp_headers`(`make-secrets.sh`가 빈 파일 생성, 비면 무시)로 바꾸고 레지스트리가 `_FILE`로 읽는다. ③ `DEX_ISSUER`·`HC_PUBLIC_URL`이 `HC__OIDC_ISSUER`·`HC__PUBLIC_URL`과 따로 적혀 어긋날 수 있었고 운영 compose는 `.env`의 `HC_PUBLIC_URL`을 무시했다 → 세 compose 모두 `HC__*` 한 값에서 Dex 값을 채우고 `.env.example`에서 둘을 뺐다. ④ Synology 오버레이가 `LDAP_BIND_PW_FILE`을 항상 주어 환경 변수 폴백이 죽어 있었다 → gomplate가 "파일이 있고 비어 있지 않을 때만 파일"(dex 이미지의 gomplate로 셋 다 렌더 실측). ⑤ D21의 `runner.env.example`이 없었다 → `docs/runner.env.example`(하네스별 자격 변수 전부 + Langfuse) 추가, operations §1-6·템플릿 README가 가리킨다. 나머지(OTel provider 누락·끝 슬래시)는 service 원장. `docker compose config`로 운영·운영+오버레이·개발·빠른 시작 넷 검증 | Codex 리뷰 2026-10-10 |
| 2026-10-10 | 오픈소스 설치 경험 대조 + 빠른 시작 | 사용자 지적("Airflow·Polaris에 한참 못 미친다")으로 둘을 `research/refs/`에 얕게 받아 설치·배포 표면을 읽었다. **대조**: ① 빠른 시작 — 둘 다 파일 하나·편집 0·기본값 자격·init 서비스. 우리는 clone + `.env` 편집 + `make-secrets.sh` + `up` 넷이었다 → D23 빠른 시작 compose(명령 둘). ② 이미지 태그 — 둘 다 판 태그(`apache/airflow:3.x.y`, `apache/polaris:<tag>`) + `latest`. 우리는 SHA만 → CI가 `v*` 태그 push에도 이미지를 그 이름으로 올리고 보존 정리에서 제외. ③ Make/CLI 래퍼 — Polaris `make help`(자기 문서화 타깃), Airflow `airflow.sh` → `Makefile`(quickstart·dev-up·serve·test·typecheck·gates·check·image). ④ Helm 차트 — 둘 다 있음. 우리는 DESIGN §8 "이후"로 유보(인스턴스 둘 이상 필요할 때). ⑤ PyPI 배포·constraints — Airflow는 PyPI + constraints 파일. 우리는 git 태그 설치(비공개). 공개 전환 때 결정. ⑥ 설정 참조 생성·CI 검증 — Polaris `make config-doc-verify`. 우리는 `config docs`로 생성하되 CI 검증은 없음(후보). ⑦ 마이그레이션의 명시적 단계 — Airflow `db migrate`·Helm 훅 잡. 우리는 기동 시 자동(D12)이고 단계 하나뿐이라 유지. **실측**: 빠른 시작 `up --wait` 뒤 `/readyz` ready, `dev@example.com` 토큰으로 `list_skills` 둘, `outsider@example.com`은 `not_a_member`, PRM `/.well-known/oauth-protected-resource/mcp`. 발견한 결함 하나: GitStore가 `-c`/`GIT_CONFIG_*`로 준 `safe.directory`는 file:// 전송의 upload-pack 자식에 안 먹혀(git 2.47 실측) root 소유 볼륨의 저장소를 못 읽었다 → 레지스트리 모드에서 전용 global 설정 파일(`GIT_CONFIG_GLOBAL`)로 고침(service 원장). 시험 65·pyright 0·게이트 넷 통과 | `research/refs/{polaris,airflow}` (gitignore), docs/quickstart.md |
| 2026-10-07 | mini 운영 배포(P2·P3 실행) | mini = 192.168.1.27(LAN), macOS 26.2 arm64, Docker는 colima(컨테이너가 NAS·tailnet IP에 닿는다), Tailscale 켜짐(tailnet 이름은 `alteraui-macmini.tail2f9fe3.ts.net` — 우산 §6-3의 `mini.tail2f9fe3.ts.net`은 추정이었다). 한 일: 코드 저장소용 self-hosted 러너 `mini-hc`(라벨 `harness-catalog`) 등록 — launchd `svc.sh`는 ssh 세션에서 bootstrap 실패(gui 도메인)라 `run.sh`를 nohup으로 띄웠고 plist는 다음 GUI 로그인에 올라온다; 읽기 전용 deploy key 둘(코드 저장소용 ssh alias `github-harness-catalog`, 카탈로그용은 `secrets/git_deploy_key`) 등록; `~/harness-catalog` 클론에서 이미지 빌드(`harness-catalog:current`; `COPY --from=ghcr.io/astral-sh/uv`가 denied라 PyPI `pip install uv`로 변경); `scripts/make-secrets.sh` + `.env`; `docker compose -f docker-compose.yml -f examples/synology-ldap/docker-compose.override.yml up -d` → `/readyz` 200(8초), 인덱스 = `alteralab/catalog` main. `tailscale serve`에 `/mcp`·`/dex`·**`/.well-known/oauth-protected-resource`**(이 경로를 안 열면 401의 `resource_metadata`가 404) 셋을 열고 `tailscale cert`로 인증서 발급. 컨테이너가 자기 공개 호스트 이름에 닿도록 오버레이의 `extra_hosts`로 tailscale IP를 매핑(hairpin). 실측: tailnet HTTPS로 PRM·discovery·401 챌린지 정상, `svc-harness` 비밀번호 그랜트 → `list_skills` 200(PR #1 병합 전이라 빈 목록). V1·V2(기계 계정)·V5 일부 통과 | ssh 실측 |
| 2026-10-07 | 첫 카탈로그 저장소 + PR #1 + CI 실패 1건 | `gh repo create alteralab/catalog --private`, 코드 저장소 태그 `v0.1.0` push, `harness-catalog init https://github.com/alteralab/catalog.git`(파일 다섯, GitHub 워크플로, pin v0.1.0; 두 번째 실행 변경 0 — V11 통과), 브랜치 `skill/first-two`로 두 스킬 PR #1(로컬 `check --base main` 종료 0). PR의 CI `check` 잡은 **비공개 코드 저장소**를 `uvx --from git+https://…`가 받지 못해 실패(`could not read Username`) → 템플릿에 읽기 토큰 단계(`HARNESS_CATALOG_READ_TOKEN`, 있을 때만)를 더하고 PR 브랜치에 반영. 토큰을 넣거나 코드 저장소를 공개하는 것은 사용자 결정(우산 §3-8) | gh 실측 |
| 2026-10-07 | 카탈로그 CI의 코드 저장소 읽기 자격 — deploy key 경로 추가 | fine-grained PAT는 GitHub API로 만들 수 없어(웹 UI 전용, 최대 1년 만료) 자동화가 끊긴다. 템플릿(GitHub·GitLab)에 둘째 경로 `HARNESS_CATALOG_DEPLOY_KEY`(코드 저장소의 읽기 전용 deploy key 개인 키)를 더했다 — `ssh-keygen`·`gh repo deploy-key add`·`gh secret set` 셋으로 끝나고 만료가 없다. 자격은 `GIT_CONFIG_COUNT/KEY_0/VALUE_0`(url.insteadOf, 코드 저장소 하나로 좁힘)·`GIT_SSH_COMMAND`를 `$GITHUB_ENV`로 건네 **잡 환경에만** 산다(이전의 `git config --global`은 self-hosted 러너의 `~/.gitconfig`를 영구히 바꿨다 — 고침). 호스트 키는 GitHub 공개 ed25519 키를 고정(keyscan 안 함). 실측: 미등록 키로 `uvx --from git+https://…`를 돌리면 `git@github.com: Permission denied (publickey)` — 재작성과 환경 상속이 uv를 지나 git까지 닿는다. 키 등록·시크릿 저장은 자동 모드 분류기가 막아 사용자 터미널 몫 | 로컬 실측 |
| 2026-10-07 | 결정 §6-10·11·12 반영 | Dex 설정 둘에 `passwordConnector`(개발 `local`, LDAP `ldap`), D5 문구, `scripts/dev-token.sh`(기계 계정 비밀번호 그랜트, PRM 스코프). P1-4의 사람 모드는 `tools/pilot/dex_grants.py`의 PKCE 흐름으로 갈음 | DESIGN §11 |
| 2026-10-07 | 사용자 결정: 읽기 그룹 `harness-readers` | DESIGN §11. NAS에 그룹과 첫 사용자 `gyojunan`이 생겼고 그 토큰의 `groups`에 실림을 실측(r2). D4 `emailAttr: uid` | DESIGN §11, r2 |
| 2026-10-07 | r2: LDAP 실물·Dex 연합 토큰 | P0-1 완료. D4 확정(member DN), 체크리스트 7에 그룹 생성·인증서 재배정. 이 맥의 Docker 컨테이너는 LAN에 닿지 않아 Dex를 소스 빌드로 호스트에서 띄워 쟀다 | plans/pilot/r2.md |
| 2026-10-07 | 운영 compose 연기 시험(로컬) + 마지막 Codex 리뷰 반영 | `docker-compose.yml` + `scripts/make-secrets.sh`(비밀 파일 여섯, database_url 조립) + bare 카탈로그(file://, bind mount)로 실 기동: 4초 만에 `/readyz` 200·`degraded: []`, 마이그레이션 1개 적용, `skill_index`에 스킬 둘, PRM 문서·401 챌린지 정상, 병합 push가 12초 안에 인덱스에 반영(`FETCH_INTERVAL_SECONDS=5`), 강제 push 되감기 → `main_rewound`(메모리·DB 불변), `reindex --accept-rewind`는 사라진 기준 커밋 때문에 실패 → 수용 시 이력 기준을 버리도록 수정(서빙 중인 프로세스는 재기동해야 메모리가 새 main이 된다 — 명령 도움말에 적음). 실측 발견: 컨테이너 안 비루트가 다른 uid 소유의 file:// 저장소를 읽으려면 git `safe.directory`가 필요해 어댑터 환경에 넣었다; 운영 compose의 `init.sh`가 `*_FILE`을 읽지 않던 치명 결함(Codex) 수정·양쪽 모드 실측. 리뷰 반영: evals 변경 범위를 check와 같은 push 기준으로, GHCR 보존은 태그 없는 것 삭제 → 최신 5개 순, 코드 CI의 dind 제거, agent 분할 glob 안전, init 호스트 판별은 github.com·*.github.com만(나머지는 `--host`) | D1·D10·D11·V1·V5·V8·V10 일부, Codex 리뷰 |
| 2026-10-07 | P2 초판: 운영 compose·코드 CI | `docker-compose.yml`(registry·postgres·dex, 비밀은 docker secrets 파일 — `*_FILE`; Dex 템플릿은 `_FILE`이 있으면 `file.Read`), `.env.example`에 레지스트리 절(`config docs` 생성)·`REGISTRY_IMAGE`·`SECRETS_DIR`, `docs/configuration.md`, `.github/workflows/ci.yml`(PR: 게이트·pyright·pytest / main: mini 러너가 GHCR로 SHA 태그 push + 보존 5개). 운영 compose는 `config --quiet` 검증만(실 기동은 P5 VM) | D1·D10·D11·D12 |
| 2026-10-07 | 템플릿 원본 = 패키지 데이터 | `examples/catalog-template`은 `packages/cli/src/harness_catalog_cli/templates`의 심볼릭 링크다(원본 하나, 드리프트 없음; D15의 "원본은 examples/"를 이렇게 읽는다). GitHub `check.yml`은 D22 (b)·D19 그대로, GitLab 판은 문면 | service P3 |
| 2026-10-07 | Dockerfile 초판 | 다단계(builder: uv 0.11.8 `uv sync --frozen --no-dev --package harness-catalog-server`; runtime: python:3.12-slim + git + gitleaks v8.30.1 바이너리, 비루트 uid 10001, `/var/lib/harness-catalog`). 로컬 빌드·`--help`·import 확인. 태그는 로컬 `dev`(D11) | service P1-8 |
| 2026-10-07 | Codex 리뷰(aedbff8) 반영 | init.sql을 initdb.d 밖으로(이중 실행 실측), 역할·DB 생성 멱등(\gexec), healthcheck가 초기화 결과를 본다, audience 클라이언트는 public(시크릿 공유 제거), LDAP 오버레이 기본 LDAPS 636(평문은 변수로), D1·D10 개발 예외 명시, P1-4 스코프 문구, 측정 도구 재작성(종료 코드·interval·state·JWKS 검증·`/token` 장치 그랜트) | Codex 리뷰 |
| 2026-10-07 | P0 2·3 완료, r1 반영 | 개발 compose·DB 초기화·Dex 설정(gomplate)·LDAP 오버레이·`.env.example`. D2(init.sh)·D5(redirectURIs·audience 클라이언트·gomplate)·D6(PKCE 강제 불가)·D8(장치 흐름 답) 개정 | plans/pilot/r1.md |
| 2026-10-07 | Codex 리뷰 반영 | 커밋 6586e9f 리뷰(중요 5·경미 3). D22에 태그↔이미지 매핑(`REGISTRY_IMAGE` = 태그 커밋의 SHA)과 `init`의 태그 존재 확인(`--pin`), V13 (d), R1 잔재 | Codex 01a111e5 |
| 2026-10-07 | D4를 선례로 확정 | Dex LDAP 커넥터를 추정(`memberUid`)에서 dp-charts argocd의 운영 설정(`member`에 DN, 사용자·그룹 baseDN, 속성 이름)으로. P0-1은 발견에서 확인으로 좁힘 | `~/workspace/dp-charts/argocd/values-override.yaml` |
| 2026-10-07 | 잔재 정정: 설치 명세 | 워크스페이스 전환 뒤 비어 있던 이미지 밖 설치 경로를 D22로(pre-commit·CI·evals 러너, 태그 핀), V13 추가. §2 템플릿 배치의 v3.3 이전 잔재(`validate.yml` 보고만, 스킬 복사)를 `check.yml`·첫 PR로 정정 | 우산 §11, 실측 |
| 2026-09-27 | 설계 개정 반영 | CI evals 게이트(D19 재작성, D21 신설, 템플릿·docs), `new-skill`→`write-skill` | DESIGN §11 |
| 2026-09-27 | 설계 개정 반영 | v3.5: 설정값 여섯, `.env.example`에 OTel exporter 변수(D20), 체크리스트 12 | DESIGN §11 |
| 2026-09-27 | 설계 개정 반영 | v3.4: D19를 Langfuse 플러그인·시크릿 넷으로, `ci-eval-runner`→`ci-runner`(무인 읽기), dev-token 스코프 `skills:read`만 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | CI evals 단계(D19): mini 러너 + Harbor + setup-token, 워크플로 템플릿 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | v3.3: 저장소 신설은 `harness-catalog init`(D15), deploy key 읽기 전용(체크리스트 4, V8), CI는 `check`(D14·체크리스트 5·V6·P3-1) | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 8차 리뷰: 카탈로그 저장소 쓰기 자격 제한(v3.3에서 읽기 전용 deploy key로 대체) | DESIGN §11 |
| 2026-09-26 | 사용자 결정: 이미지 저장소 | GHCR 비공개 + 보존 규칙(최근 SHA 태그 5개, 태그 없는 버전 삭제), 빌드 기계 = 실행 기계(mini runner)라 운영 pull 없음. Harbor(컨테이너 아홉, 소비자 없는 LDAP RBAC)·ECR(AWS 계정·전송 요금)·`registry:2`는 지금 아님 — 되돌리기는 `.env` 한 줄과 워크플로 한 단계 | D11, V12 |
| 2026-09-26 | Codex 교차 검증 1회 | 반영: P0↔P1 순환 의존을 distribution P0 신설로 끊음(LDAP 스키마 `ldapsearch` 선실측), 시험용 토큰 절차 `scripts/dev-token.sh`(V11), 이미지 한 번 빌드·SHA 태그·digest(D11, V1), 비밀 취급 절차(D10, 체크리스트 11), D6·R2의 미래 조건절 삭제, 우산 단계 번호 재배열(P4 스킬 작성 → P5 배포·게시). 기각 없음 | 우산 §11 |
| 2026-09-26 | PLAN 초판 | 파일 배치, 판정 D1~D18, 단계 셋, 체크리스트 11항, 검증 V1~V10. 코드·설정 파일은 아직 없다 | 우산 §4 |
| 2026-10-10 | compose를 `docker/`로 | 사용자 결정(루트 정리). 루트의 compose 셋과 `.env.example`을 `docker/compose{,.dev,.quickstart}.yml`·`docker/.env.example`로. compose 상대 경로는 `docker/` 기준(`./dex/…`, `../skills`, `../packages/…`, 빌드 컨텍스트 `..`), 기본 비밀 경로 `${SECRETS_DIR:-../secrets}`, `.env`는 `docker/.env`. 운영·개발 compose에 `name: harness-catalog`를 박아 디렉토리 이름(docker)으로 바뀔 프로젝트 이름과 기존 볼륨 이름을 보존. Dockerfile·.dockerignore는 빌드 컨텍스트가 루트라 그대로. 여섯 저장소 재실측: Dex·Langfuse·MCP registry 루트, DataHub `docker/`, Gitea·Polaris compose 없음 | 우산 DESIGN §11 2026-10-10 행, `docker compose config` 셋+오버레이 실측 |
| 2026-10-10 | `examples/`를 없앰 | 사용자 결정. 채울 예시가 없었다 — 카탈로그 템플릿은 CLI 패키지 데이터로 들어갔고 남은 건 우리 팀 LDAP 오버레이 한 쌍과 러너 .env 견본. `examples/synology-ldap/` → `docker/synology-ldap/`(오버레이는 `compose.override.yml`, 안의 경로 `./synology-ldap/…`), `examples/runner.env.example` → `.github/runner.env.example`(워크플로의 인프라). 운영 명령은 `-f docker/compose.yml -f docker/synology-ldap/compose.override.yml`. 공개해도 예시는 문서가 가리키면 되고 변형이 늘면 `docker/<변형>/`이 받는다 | DESIGN §11 2026-10-10 행, `docker compose config` 오버레이 실측 |
| 2026-10-10 | D14 개정: init이 기본 스킬 둘을 함께 쓴다 | 사용자 결정("첫 세팅에 기본 스킬을 다 넣어 주는 것이 바람직하다, PR로 넣는 것은 아니다"). `skills/`를 `packages/cli/src/harness_catalog_cli/templates/skills/`로 옮기고(사본 하나), `template_files`가 `skills/**`를 전부 싣는다. `.gitkeep`은 쓰지 않는다(check 항목 2는 옛 카탈로그를 위해 계속 허용). 빠른 시작 seed는 `/seed/skills` 마운트를 없애고 템플릿의 `skills/`를 복사. `init` 테스트가 두 스킬 파일을 확인. 루트에는 링크도 사본도 두지 않는다(템플릿은 CLI의 데이터, 스캐폴딩 도구의 관례). 실체를 루트에 두고 hatch force-include로 끌어오는 안은 `uv build`가 sdist를 거쳐 패키지 밖 경로를 잃어 실패(실측 "Forced include not found"), 루트 심볼릭 링크는 GitHub 화면·grep·Windows에서 반쪽이라 기각 | 우산 DESIGN §11, pytest, uv build(wheel에 templates 24항목) |
