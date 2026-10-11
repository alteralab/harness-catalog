# service 계획: harness-catalog 레지스트리 서비스

**상태: 초안 · 작성 2026-09-26.** 이 PLAN은 `~/workspace/harness-catalog/`의 서비스 코드(`packages/`·`tests/`·이미지)의 정본이다. 설계의 정본은 상위의 `DESIGN.md`(v3.3)이고 이 문서는 그것을 복제하지 않는다. 관할은 레지스트리 프로세스 하나 — 파이썬 패키지 `harness_catalog/`, 마이그레이션, 시험, 컨테이너 이미지의 빌드 정의 — 이고, 그것이 어디에 어떻게 뜨는가(`plans/distribution.md`), 카탈로그에 실리는 스킬(`plans/skills.md`), 설계의 가정을 재는 일(`plans/pilot.md`)은 관할 밖이다. 상위 `PLAN.md` §3의 공통 규약(기록 규율·식별자·설계와의 관계·교차 검증)을 그대로 따른다.

## 0. 한 장 요약

만드는 것은 배포물 넷(§2)이고 그중 상시 도는 프로세스는 하나(`harness-catalog-server`)다. 카탈로그 git 저장소를 fetch해 인덱스를 짓고, OIDC 토큰을 검증해 MCP 읽기 도구(2026-10-11 기준 여섯: `search_skills`·`load_skill`·`get_skill_file`·`get_skill_archive`·`search_tools`·`get_tool`)을 Streamable HTTP(2026-07-28, 무세션)로 내며, 인덱스를 PostgreSQL에 둔다. 사용 기록은 MCP SDK가 도구 호출마다 내는 OpenTelemetry 스팬이고 MCP 어댑터가 속성을 더해 표준 exporter로 Langfuse에 간다(DESIGN v3.5). 평가 결과는 이 프로세스가 아니라 Harbor 플러그인 `packages/harbor-langfuse/`가 Langfuse에 남긴다(DESIGN v3.4). 구조는 DESIGN 그림 2의 헥사고날(포트 일곱·어댑터 일곱·Configurator)이고 언어는 Python(DESIGN §2.1 결정), 스택은 DESIGN §2.1의 표 그대로다. 이 PLAN이 더하는 것은 셋이다. 설계가 정하지 않은 구현 선택(§3 판정 원장), 짓는 순서와 단계마다의 끝(§4 — 읽기 경로 → 인덱스 표·스팬 → 검사·초기화·플러그인), 그리고 무엇을 어떻게 재어 끝났다고 할지(§7 검증 원장). 설계가 초안이라 남긴 것 중 이 서비스에 직접 걸리는 것은 서비스 주체의 판별 표지 하나이고(§3 D8), 그것은 파일럿 P0의 실측 뒤에만 닫힌다.

## 1. 관할과 경계

**이 PLAN이 소유하는 것.** `packages/` 아래 배포물 넷(§2, D1. 마이그레이션은 `server`의 패키지 데이터)·`tests/`·루트 `pyproject.toml`(워크스페이스 선언, 배포물 아님)·`uv.lock`, 그리고 `Dockerfile`의 내용. 배치는 우산 §3-8의 오픈소스 공통 골격(배포물마다 src 레이아웃, pip 설치 가능한 패키지)이다. 이미지 태그를 어디에 올리고 compose에 어떻게 꽂는지는 `plans/distribution.md`다.

**DESIGN에서 가져와 그대로 지키는 계약.** 여기 다시 적지 않는다. 절 번호와 한 줄 요지만이다.

| 계약 | DESIGN 위치 | 요지 |
|---|---|---|
| 도구 넷의 시그니처·응답 필드·오류 | §3 도구 표 | 넷 다 `skills:read`. 응답에 `sha`(tree)·`commit`·마지막 fetch 시각. 오류 코드 다섯. 쓰기·기록 도구는 없다 — 게시는 git 호스트(§2, §5), 평가는 Langfuse(§5.1) |
| 설정값 여섯 | §2 그림 2 해설, §2.1 운영자가 아는 것 | 필수 다섯(저장소 URL·deploy key·issuer·공개 URL·PostgreSQL 접속) + 기본값 있는 하나(`FETCH_INTERVAL_SECONDS` 60). 일곱째는 없다. OTel exporter는 표준 `OTEL_EXPORTER_OTLP_*` 환경 변수이고 우리 설정값이 아니다 |
| 저장소 표지와 기동 검사 넷 | §2.1 저장소 초기화 | `.harness-catalog`의 `layout = 1`, `skills/`, 실패 사유 넷(`repo_unreachable`·`no_main_branch`·`not_a_catalog`·`unsupported_layout`·`layout_mismatch`) |
| DB 스키마 | 그림 3 + DDL + 규칙 다섯 | 업무 표 하나(`skill_index`) + `index_state` + 마이그레이션 메타. DDL 문자열이 계약이다 |
| 게시 = git 워크플로 | §2 게시, §5, §5.1 ③ | 레지스트리는 `main`을 fetch·검사·인덱스만 한다. 검사 열(§5)은 `harness-catalog check` 하나이고 pre-commit·CI·인덱스 빌드가 같은 구현을 돈다. 되감기(`main_rewound`)는 규칙 3이 잡는다 |
| 인증·인가 | §2 인증·인가 표, 그림 4 | JWT 검증 계약(`iss`·`aud`·`exp`·`nbf` 60초·RS256/ES256·`sub`·`scope`), 401/403 챌린지 경계, 스코프↔도구, 역할 reader 하나(그룹 `harness-readers`, 서비스 주체) |
| 실패 시 동작 | §2.1 실패 시 동작 표 | PostgreSQL·push는 시간 초과+브레이커, fetch는 지수 백오프, JWKS는 캐시, DB 단절 시 메모리 사본으로 읽기 |
| 파이썬 스택 | §2.1 Python 쪽 구체 표 | `mcp` v2 + Starlette + uvicorn, PyJWT, psycopg 3 + yoyo, git·gitleaks 서브프로세스, `skills_ref`, anyio, pydantic-settings, pytest·testcontainers, uv·ruff·pyright strict. **표에 없는 것은 넣지 않는다** |

**옆 PLAN과의 접점.** distribution는 이 PLAN이 정한 이미지 이름과 환경 변수 일곱의 이름을 읽는다(§2 표). skills는 카탈로그 저장소에 PR로 게시되고 이 서비스가 병합된 것을 검사해 싣는다. pilot은 이 서비스가 뜬 뒤 가정 셋을 재고, 그 전에 D8의 표지를 준다.

## 2. 코드 배치

배포물 넷의 uv 워크스페이스다(사용자 결정 2026-09-27: 배포물을 소비자 단위로 가른다). 의존 방향은 `cli → core`, `server → core`이고 `cli`와 `server`는 서로 import하지 못한다(별도 패키지라 관례가 아니라 강제다). 판은 lockstep — 태그 하나에 넷이 같은 판으로 빌드되고 `cli`·`server`는 `harness-catalog-core == <같은 판>`을 핀한다. 선례는 Airflow(`apache-airflow-core`·`apache-airflow-ctl`, uv 워크스페이스)와 Polaris(`polaris-core`·`runtime/server`·`runtime/admin`)이고, 우리 규모에서 판을 따로 굴릴 이유가 아직 없어 lockstep이다. DESIGN 그림 2의 헥사고날은 그대로이고, 층(앱·피구동·구동)이 패키지 경계와 겹친다: 앱과 읽기 어댑터가 `core`, 구동 어댑터와 DB·OIDC 어댑터가 `server`, 사람이 부르는 진입점이 `cli`.

```
(저장소 루트)
  pyproject.toml            # [tool.uv.workspace] members = packages/*. 루트는 배포물이 아니다(ruff·pyright·pytest 설정만)
  uv.lock                   # 워크스페이스 하나의 잠금. P1 첫 커밋에서 생성
  Dockerfile                # python:3.12-slim + git + gitleaks, 다단계. `pip install packages/core packages/server` → 진입점 harness-catalog-server
  packages/
    core/                   # 배포물 harness-catalog-core — 서버·CLI가 공유하는 것. 서버 의존 없음
      pyproject.toml        #   deps: pydantic, pydantic-settings, skills-ref, anyio
      src/harness_catalog_core/
        settings.py         #   Settings(pydantic-settings, env_prefix HC__, 구분자 __, 여섯, 필드마다 description·기본값·_FILE 허용) — 설정 정의의 유일한 자리
        catalog_file.py     #   harness-catalog.toml 파서·허용 키(layout, [evals] enabled·agents). check 항목 1과 CI gate가 같은 파서를 쓴다
        model.py            #   SkillEntry·IndexSnapshot·Principal·오류 코드 열거. 순수 데이터
        ports.py            #   요구 포트 넷 = typing.Protocol: ContentStore·FactStore·IdentityVerifier·SkillValidator
        authz.py            #   인가 정책(그림 4): reader(그룹 harness-readers 또는 서비스 주체) -> CATALOG_READ
        catalog.py          #   카탈로그: 목록·검색·본문·파일, 인덱스 빌드(메모리 스냅샷), 구조 검사, 상태. FactStore는 포트로만
        check.py            #   검사 열(§5): 저장소 구조 + 스킬마다 + 스킬 쌍. 인덱스 빌드(server)와 CLI(cli)가 같은 함수를 부른다
        adapters/
          git.py            #   로컬 클론, fetch, 스킬 트리 목록, 판 읽기, 삭제 이력 질의. 쓰기 없음(init의 push는 cli가 자기 git 호출로)
          validate.py       #   skills_ref.validate + gitleaks 서브프로세스 → 판정
    cli/                    # 배포물 harness-catalog-cli — 명령 `harness-catalog`. 운영자·저자 머신, 소비 조직 CI의 check
      pyproject.toml        #   deps: harness-catalog-core==<판>, typer. [project.scripts] harness-catalog
      src/harness_catalog_cli/
        __main__.py         #   출력 층(T201 면제 자리)
        init.py             #   `init <repo-url>`: clone(운영자 git 자격) → 호스트 판별 → 템플릿을 없는 것만 쓰고 → 커밋·push. 멱등
        check.py            #   `check [<root>] [--base <commit>]`: core.check → 항목 번호·경로·사유 출력, 종료 0/1/2
        config.py           #   `config list`(실효값·출처 env/file/default) · `config docs`(docs/configuration.md·.env.example 생성)
        templates/          #   카탈로그 템플릿 패키지 데이터(.harness-catalog, skills/{pin-skill,write-skill}, README, .pre-commit-config.yaml, github/·gitlab/)
    server/                 # 배포물 harness-catalog-server — 레지스트리 프로세스(MCP 서버 + 스케줄러 태스크). 컨테이너 이미지
      pyproject.toml        #   deps: harness-catalog-core==<판>, mcp, starlette, uvicorn, PyJWT[crypto], psycopg[binary,pool], yoyo-migrations, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http. [project.scripts] harness-catalog-server
      src/harness_catalog_server/
        __main__.py         #   `serve`(uvicorn 기동) · `reindex --accept-rewind`(DB를 만지므로 cli가 아니라 여기)
        bootstrap.py        #   bootstrap(settings) -> App  [Configurator]. 어댑터 넷을 만들어 core.catalog에 꽂는다
        migrations/         #   yoyo SQL 파일, 패키지 데이터. 0001이 그림 3 DDL 그대로
        adapters/
          pg.py             #   psycopg 3 + pool. 인덱스 교체·검색. 브레이커 상태. FactStore 구현
          oidc.py           #   PyJWT + PyJWKClient. SDK TokenVerifier 구현
        driving/
          mcp_tools.py      #   MCPServer에 도구 넷 등록, 입력 스키마, 오류 코드 → 도구 오류, 현재 스팬에 속성(sub·스킬·sha·검색어·결과 수)
          ops.py            #   Starlette 라우트 /healthz /readyz
          scheduler.py      #   anyio 태스크 하나: 기동 1회 검사 뒤 fetch 주기
    harbor-langfuse/        # 배포물 harbor-langfuse — Harbor JobPlugin → Langfuse. 위 셋과 무관(core도 안 본다)
      pyproject.toml        #   deps: harbor, langfuse
      src/harbor_langfuse/plugin.py
  tests/
    core/                   # 앱 함수 + 가짜 어댑터(git·validate 가짜, FactStore 메모리 가짜), check 표본, settings·catalog_file
    cli/                    # init(임시 bare 저장소, 두 번 실행), check 종료 코드, config docs 생성물 diff
    server/
      adapters/             # pg: testcontainers PostgreSQL. oidc: 가짜 JWKS
      http/                 # 실제 uvicorn + Dex 토큰(개발 compose)으로 401/403·도구 호출
    fixtures/               # 템플릿 구조의 시험 카탈로그, 통과·실패 스킬 표본, 시크릿 든 스킬 표본
```

배포물마다 의존 목록(이름만. 판은 `uv.lock`이 잡고 첫 고정값을 §9 진행 원장에 적는다):

| 배포물 | 의존 | 이유(DESIGN §2.1 표) |
|---|---|---|
| `harness-catalog-core` | `pydantic`, `pydantic-settings`, `skills-ref`, `anyio` | 설정·모델·검사가 전부. 서버도 CLI도 이 위에 선다. `skills-ref`는 참조 구현 한 곳(DRY), 패키지명·API는 P1에서 실측(R4) |
| `harness-catalog-cli` | `core`, `typer` | 저자 머신에 서버 의존(mcp·psycopg·PyJWT)이 깔리지 않게 하는 것이 이 배포물의 존재 이유 |
| `harness-catalog-server` | `core`, `mcp`(v2), `uvicorn`·`starlette`, `PyJWT[crypto]`, `psycopg[binary,pool]`, `yoyo-migrations`, `opentelemetry-sdk`·`opentelemetry-exporter-otlp-proto-http` | SDK 골격(2026-07-28, RFC 9728 내장), `PyJWKClient`의 JWKS 캐시, ORM 없이 SQL, OTel exporter는 환경 변수 자동 구성 |
| `harbor-langfuse` | `harbor`, `langfuse` | Harbor 플러그인 계약. 레지스트리 이미지에 들어가지 않는다 |
| 이미지 안 `git`, `gitleaks` | 서브프로세스 | 런타임이 아니라 바이너리. "런타임 하나" 유지 |
| 개발(루트) | `pytest`, `pytest-anyio`, `testcontainers[postgres]`, `ruff`, `pyright` | DB 대역은 실물을 보장하지 않는다 |

## 3. 판정 원장

설계가 정하지 않은 구현 선택만이다. 설계에 있는 결정은 여기 없다. 근거 등급: **실측** / **문면** / **설계 판단** / **휴리스틱**.

| # | 물음 | 판정 | 근거(등급) |
|---|---|---|---|
| D1 | 배포물과 패키지 경계 | 배포물 넷 `harness-catalog-core`·`harness-catalog-cli`·`harness-catalog-server`·`harbor-langfuse`, 파이썬 패키지 `harness_catalog_core`·`harness_catalog_cli`·`harness_catalog_server`·`harbor_langfuse`. 경계 규칙 셋: ① `core`는 서버 의존(mcp·starlette·psycopg·PyJWT·uvicorn·otel)을 갖지 않는다 — 저자 머신의 `check`가 그것을 끌고 오면 안 된다. ② `cli`와 `server`는 서로 import하지 않는다. DB를 만지는 `reindex`는 `server`의 부명령이고 `init`의 push는 `cli`의 git 호출이다. ③ 판은 lockstep이고 `cli`·`server`가 `core`를 정확한 판으로 핀한다. 헥사고날의 층은 유지되고 패키지 경계와 겹친다: 앱·읽기 어댑터 = core, DB·OIDC 어댑터와 구동 어댑터 = server. extras(`harness-catalog[server]`)로 한 wheel에 두는 안은 관례로만 경계를 지키므로 채택하지 않았다 | 사용자 결정(2026-09-27) + 설계 판단. 선례 Airflow `airflow-core`·`airflow-ctl`, Polaris `polaris-core`·`runtime/admin`(clone 실측). 소비 조직에서 CLI는 서버 없이 쓰인다(운영자 `init`, 저자·CI `check`) |
| D2 | 메모리 인덱스 사본의 구조와 교체 | 불변 스냅샷 하나(`IndexSnapshot`: 행 튜플 + `commit_sha` + `built_at`)를 카탈로그가 참조 하나로 쥔다. 빌드는 새 스냅샷을 다 만든 뒤 참조를 바꾼다. 읽는 쪽은 호출 시작 때 참조를 한 번 잡고 그것만 본다. 부분 갱신은 없다 | 설계 판단. DESIGN §2.1 "다음 빌드가 통째로 바꾼다"의 구현. 참조 교체는 CPython에서 원자적이고 anyio 단일 스레드 루프에서 경합이 없다(문면) |
| D3 | 클론 잠금 | 프로세스 안 `anyio.Lock` 하나. 쥐는 구간은 fetch 전체와 인덱스 빌드의 스냅샷 읽기. 레지스트리는 클론에 쓰지 않는다 | 설계 판단. DESIGN §2 "클론 하나에 잠금 하나" |
| D6 | `load_skill(id, sha)`·`get_skill_file(id, sha)`의 과거 판 해석 | `git log --format=%H main -- skills/<name>`으로 그 경로를 만진 `main` 커밋을 최신부터 걸으며 `git rev-parse <commit>:skills/<name>`이 `sha`와 같은 첫 커밋을 쓴다. 브랜치는 fetch하지 않으므로 잡히지 않는다. 상한은 그 경로의 커밋 수. tree→commit 캐시는 두지 않는다 | 설계 판단. 과거 판 요청은 재현·사고 조사용이라 드물다(DESIGN §3). 캐시는 지금 재지 않은 최적화다 |
| D7 | JWKS·JWT | 기동 시 issuer의 `.well-known/openid-configuration`에서 `jwks_uri`를 읽고 `PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)`. 검증은 `jwt.decode(algorithms=["RS256","ES256"], audience=<공개 URL>, issuer=<issuer>, leeway=60, options={"require": ["exp","sub"]})`. 스코프는 토큰에서 보지 않는다(우산 §6-12): 검증기는 유효한 토큰에 요구 스코프(`openid groups audience:server:client_id:<공개 URL>`)를 그대로 부여해 SDK의 `required_scopes` 검사를 통과시키고, 같은 목록이 RFC 9728 문서의 `scopes_supported`가 된다 | 문면(PyJWT·SDK). 모르는 `kid`의 재조회는 `PyJWKClient`의 동작이고 P1 시험이 확인한다 |
| D8 | 서비스 주체 판별 표지 | **닫힘(우산 §6-10, 2026-10-07): 서비스 주체 종류가 없다.** 무인 주체는 LDAP 기계 계정이고 `groups`로 reader다. 판별 함수·표지 집합을 지웠다. 판별은 순수 함수 `principal_kind(claims)` 하나에 가두고, 그 함수의 규칙은 파일럿 P0이 Dex 클라이언트 자격 증명 토큰의 실물(`sub`·`azp`·`groups`)을 기록한 뒤 정한다. DESIGN의 임시 규칙("`sub`가 등록된 client ID 집합에 있으면")은 그 집합의 출처가 필요한데 설정값은 일곱뿐이라 여덟째를 더하는 셈이 된다. 토큰 자체의 표지(`azp` 등)로 갈리면 설정 없이 닫고, 안 갈리면 DESIGN §11에 "설정값 여덟째"를 변경 요청으로 올린다. 이 PLAN이 조용히 정하지 않는다 | 설계 판단 + 미실측. P1·P2는 이 판별이 필요 없다(읽기는 인증된 전부). 걸리는 것은 서비스 주체를 그룹 없이 reader로 세우는 한 줄뿐이다(v3.4에서 서비스 주체는 읽기 전용) |
| D9 | 시크릿 스캔 호출 | `check`가 `gitleaks dir <skill-dir> --no-banner --exit-code 2 --report-format json --report-path -`. 종료 0이면 통과, 2면 검출(파일·룰을 출력에), 그 밖(바이너리 없음·크래시)은 검사기 실패(종료 코드 2, fail-closed). 바이너리 파일의 취급은 P3에서 실측해 적는다 | 문면(gitleaks CLI). fail-closed는 DESIGN §5 검사기 운영 |
| D11 | 스케줄러 | Starlette lifespan 안에서 anyio 태스크 그룹 하나에 루프 하나. fetch 루프는 `FETCH_INTERVAL_SECONDS`마다 `catalog.refresh()`를 부르고 실패 시 지수 백오프(2배, 상한 = 간격의 16배)로 늘렸다가 성공하면 되돌린다. 시험은 시계 없이 함수를 직접 부른다 | 설계 판단. DESIGN §2.1 실패 표 "fetch는 지수 백오프". 상한 16배는 휴리스틱 |
| D12 | 마이그레이션 시점 | `bootstrap`이 기동 직후 마이그레이션 태스크 하나를 따로 띄운다. 이 태스크는 yoyo 적용을 시도하고 실패하면 자기 백오프(5초에서 2배, 상한 5분)로 다시 한다. fetch 루프와 무관하다. DB 경로(인덱스 트랜잭션·검색 순위)는 마이그레이션이 "적용됨"이 되기 전에는 열리지 않고 그동안은 `degraded: db_unavailable`이다. 기동은 막지 않는다(준비됨 조건이 아니다) | 설계 판단. DESIGN §2.1 "DB 연결은 준비됨의 조건이 아니다"를 마이그레이션에도 적용. fetch 주기와의 결합은 Codex 리뷰(2026-09-26)가 잡아 분리했다. 백오프 수치는 휴리스틱 |
| D13 | 브레이커와 degraded 신호 | PostgreSQL 호출에 시간 초과(문장 5초)와 브레이커(연속 실패 3회 → 30초 열림), fetch에는 지수 백오프. 브레이커는 순수 상태 기계 하나를 `pg.py`가 든다. 열림·닫힘과 되감기 검출이 `degraded` 목록(`db_unavailable`·`main_rewound`)이 되고 **`/readyz` 본문에만** 실린다(DESIGN §2.1). 도구 응답에는 DESIGN §3이 정한 필드만 있다 | 설계 판단. 수치는 휴리스틱. 라이브러리를 들이지 않는 이유: 상태 기계가 열 줄이고 DESIGN 표에 없다 |
| D14 | 오류 어휘 | 인가 실패는 HTTP 401/403(SDK 챌린지). 도구 안의 실패는 MCP 도구 오류 결과에 `{code, detail}`이고 **코드 여섯은 DESIGN §3이 소유한다**. `check`의 위반은 도구 오류가 아니라 CLI 출력(항목 번호·경로·사유 한 줄씩)과 종료 코드다 | 설계 판단. 공개 코드는 계약이라 DESIGN 소유(우산 §1 경계 규칙 ⑵) |
| D15 | DB 접속 | `psycopg_pool.AsyncConnectionPool` 최소 1·최대 4, 문장 시간 초과 5초. 트랜잭션은 인덱스 교체 하나만 명시적이고 나머지는 자동 커밋 | 휴리스틱. 하루 수백 요청(DESIGN 추정)에 연결 넷이면 남는다 |
| D16 | 시험 구성 | `tests/unit`은 어댑터 전부 가짜(FactStore는 메모리 dict). `tests/adapters/pg`는 testcontainers 실물. `tests/adapters/git`은 임시 bare 저장소 + 클론 둘. `tests/http`는 실제 uvicorn 프로세스 + 개발 compose의 Dex 토큰. 마지막 것만 외부 프로세스가 필요하고 표식으로 갈라 CI에서는 P4 뒤에 켠다 | 설계 판단. DESIGN §2.1 "DB 대역은 실물을 보장하지 않는다", "git·OIDC 어댑터는 가짜로" |
| D17 | 스킬 아카이브 내려받기 | 도구 `get_skill_archive(id, sha?)` → 다운로드 명세(uri·헤더 토큰·size·sha256·digest·expires_at). 라우트 `GET /mcp/archive/<id>/<tree>.tar`(core `archive_token.ArchiveSigner`, server `driving/archive_route.py`). 앱 `Catalog.get_skill_archive`가 `workdir/archives/<tree>.tar`를 `ContentStore.archive_tree("<commit>:skills/<name>")`로 만들어(쓰면서 20 MB 상한, 임시 파일 뒤 교체) 재사용·1시간 뒤 정리. 키는 프로세스 수명 | 우산 DESIGN §11 2026-10-11 |
| D18 | toolbox 단위와 레코드 | `tools/<name>/tool.json`: 선택 `$schema`(문자열, 편집기용 포인터 — 레지스트리는 해석하지 않음; §11 2026-10-11 write-tool)·`name`(= 디렉토리명, 스킬 문법; **스킬과 합쳐 전역 유일**)·`description`(1..1024)·`inputSchema`·선택 `outputSchema`(둘 다 최상위 `type: object`, 직렬화 ≤ 32 KiB, 깊이 ≤ 16, Draft 2020-12 메타스키마 통과, `$ref`는 `#…`만; `outputSchema`는 MCP `Tool.outputSchema`와 같은 이름)·`runtime`(`{kind: script, path, command[]}` — `command`는 셸 없는 argv, `path`는 argv 원소 정확히 하나이고 `get_skill_file`의 경로 규칙을 지키며 그 판 트리의 non-link blob; 또는 `{kind: mcp, server, tool}` — `server`는 `mcp-servers/`에 있고 `tool` 비지 않음)·선택 `metadata`(문자열 맵; `replaced-by`·`requires-tools`는 스킬 규칙). `kind: script` 실행 ABI(§11 2026-10-12 보정): `runtime.command`를 셸 없이 argv로 직접 실행하고 cwd는 도구 디렉토리, 입력은 `inputSchema`에 맞는 JSON 객체 하나를 stdin으로. `outputSchema`를 선언한 도구는 정상 완료 시 그 스키마에 맞는 UTF-8 JSON 객체 **하나만** stdout에 내고 종료 0 — 통과·불통과 같은 도메인 판정은 오직 그 객체의 도구별 필드로 표현하고(공통 필드를 강제하지 않는다), 사람이 읽을 설명이 필요하면 `summary`·`message` 같은 스키마에 선언된 필드에 넣어 소비자가 렌더한다; 로그·진행 표시·별도 PASS/FAIL 줄을 stdout에 섞지 않는다. `outputSchema`가 없는 도구의 정상 결과는 stdout 텍스트와 종료 0. **0이 아닌 종료는 신뢰할 결과를 만들지 못한 도구 실행 실패**이며 사유를 stderr에 내고 stdout에 부분 결과를 두지 않는다 — 종료 1을 "결과가 부정"의 뜻으로 쓰지 않는다(mirror도 금지: 소비자마다 정본이 둘이 된다). 소비자 규약: 종료 코드·stdout·stderr를 **구분된 관측**으로 모델에 되돌리되 크기 상한과 잘림 표시를 적용한다; 구조화 결과는 JSON 파싱과 `outputSchema` 검증을 통과해야만 코드가 쓰고, 실패하면 정상 판정이 아니라 계약 오류 관측으로 바꾼다; 사전 승인 거부는 실행 결과와 구별된 `not_executed` 관측이다. 뒷날 MCP 어댑터는 검증된 정상 객체를 `structuredContent`와 같은 JSON의 `TextContent`로, 비정상 종료를 진단 `content`와 `isError: true`로 **결정적으로 변환**한다(무번역이 아니다). `mcp-servers/<name>/server.json`: MCP Registry 형식 — 최상위 허용 필드 닫힘(`$schema`·`name`·`version`·`title`·`description`·`websiteUrl`·`repository`·`packages`·`remotes`·`_meta`), `name`은 디렉토리명 또는 `<ns>/<디렉토리명>`, `version` 필수, `packages`|`remotes` 하나 이상, `isSecret: true` 항목은 `value`·`default` 금지. 검증은 core의 pydantic 모델(새 의존 없음). 판 = tree SHA, 과거 판은 `git log -- <root>/<name>`(D6). ContentStore에 `root: Literal['skills','tools','mcp-servers']` 매개 메서드(`list_trees`·`deleted_names`·`resolve_version`·`archive_tree`)를 두고 스킬 메서드는 그 포장 | 우산 DESIGN §11 2026-10-11 toolbox + Codex 설계 리뷰 반영 행 |
| D19 | toolbox 읽기 도구·인덱스 | `search_tools(query, limit)`·`get_tool(id, sha?)`. `tool_index` DDL은 DESIGN 그림 3 아래 계약 문자열(마이그레이션 0002). `IndexSnapshot.tools` 추가; `replace_index`는 한 트랜잭션에 `DELETE skill_index` → `DELETE tool_index` → 두 INSERT → `index_state` upsert(중간 실패 주입 시험). `search(query, limit, kind)`로 표를 고른다. 검색은 `_db_synced`일 때만 DB 순위. 아카이브: 토큰 v2(payload에 kind), 라우트 `/mcp/archive/tools/<id>/<tree>.tar`, 캐시 `archives/<kind>/<tree>.<commit>.tar`. `authz.READ_TOOLS` 일곱. 수용 시험: tool_index 계약 문자열·0001→0002 업그레이드·재실행 0 | 우산 DESIGN §11 2026-10-11 toolbox |
| D20 | `list_skills` 제거 | 읽기 도구 여섯(`search_skills`·`load_skill`·`get_skill_file`·`get_skill_archive`·`search_tools`·`get_tool`). core `Catalog.list_skills` 삭제, `authz.READ_TOOLS` 여섯, MCP 등록 해제. 둘러보기·pin 새 판 확인·은퇴 판정은 전부 `search_skills`. 다음 판 0.4.0(비호환) | 우산 DESIGN §11 2026-10-11 `list_skills` 제거 |
| D21 | 응답 모델 | 읽기 도구 여섯의 성공 응답은 `driving/responses.py`의 pydantic 모델(`extra="forbid"`). 반환 주석 `Annotated[CallToolResult, <모델>]`로 SDK가 `outputSchema` 공개 + `structuredContent` 검증. `get_tool.tool`=core `ToolSpec`, `.server`=core `ServerSpec`(별칭 유지), 다운로드 명세=`DownloadDescriptor`. 오류는 `{code, detail}`·`isError`, 스키마 밖. 수용 시험: `tools/list`의 여섯 `outputSchema`와 여섯 호출의 적합성(jsonschema) | 우산 DESIGN §11 2026-10-11 응답 모델 행 |

## 4. 단계

각 단계의 끝은 상위 `PLAN.md` §4의 완료 조건을 그대로 옮긴 것이다.

### P1. 읽기 경로 (DB 없이 동작)

0. `src/` 첫 커밋: `pyproject.toml`·`uv.lock`·패키지 뼈대. 규약 선언은 새로 없다(`lang/python`은 이미 선언됨). 이 커밋에서 `altera-ruff`·`altera-ast-grep`이 처음으로 파일을 검사하며 돈다 — 그 출력과 `selftest.sh --census src/ tests/` 결과를 §9 진행 원장에 적고, 검출이 있으면 참·거짓을 갈라 기록한다.
1. `config.py`: 일곱 설정값의 `Settings`. 필수 다섯이 비면 기동 실패(종료 코드 ≠ 0, 어느 것이 비었는지 표준 오류에).
2. `app/ports.py`·`app/model.py`: 요구 포트 넷의 Protocol, 스냅샷·주체·오류 코드.
3. `adapters/git.py`: clone·fetch(`origin/main`)·`skills/*/SKILL.md` 트리 열거(각 디렉토리의 tree SHA와 그 판을 넣은 최근 커밋)·파일 읽기(`git show`)·삭제 이력(`git log --diff-filter=D --name-only -- 'skills/*/SKILL.md'`).
4. `adapters/validate.py`: `skills_ref` 호출부. 패키지·함수 시그니처를 실측해 R4를 닫는다. 통과·실패 표본 둘.
5. `app/catalog.py`: 구조 검사 넷 → 인덱스 빌드(메모리 스냅샷만) → 목록·검색(메모리 부분 일치, 순위 없음; 항목은 DESIGN §3의 최소 필드)·본문·파일(경로 이탈·심볼릭 링크·1 MB).
6. `adapters/oidc.py`: D7. `app/authz.py`: 스코프↔도구, 그룹, 주체 종류(D8 미정 부분은 "사람"으로 고정하고 표식 남김 없이 P3에서 함수 본문을 채운다).
7. `driving/mcp_tools.py`: 읽기 도구 넷 등록, `AuthSettings`(issuer·공개 URL·`required_scopes=["skills:read"]`), `streamable_http_app()`. `driving/ops.py`: `/healthz`·`/readyz`(503 사유 넷, 200 + `degraded`). `driving/scheduler.py`: 기동 1회 + fetch 루프(D11). `config.bootstrap`·`__main__`.
8. `Dockerfile` 초판(다단계, git·gitleaks 포함) — 이미지가 P1 끝에 빌드된다. 이미지 이름은 `harness-catalog`, 태그는 git 짧은 SHA.
9. 시험: unit(가짜 어댑터로 구조 검사·인덱스·검색·인가 행렬 읽기 부분), adapters/git, adapters/validate, http(개발 compose의 Dex로 토큰을 받아 HTTP 경유 호출).

**끝:** 템플릿 구조의 시험 저장소를 가리켜 기동하면 `/readyz` 200이고, Dex가 낸 사람 토큰으로 SDK 인메모리 클라이언트가 아닌 **HTTP 경유** 읽기 도구 넷 호출이 전부 성공하며, 토큰 없음·잘못된 aud·만료 셋이 각각 401로 거부된다.

### P2. 인덱스 표·스팬

1. `packages/server/src/harness_catalog_server/migrations/0001_schema.sql`: 그림 3 DDL 문자열 그대로(확장·함수·표 넷·생성 열·인덱스·CHECK). 러너는 yoyo, 적용 시점은 D12.
2. `adapters/pg.py`: 인덱스 교체 트랜잭션(`index_state` `FOR UPDATE` → `git merge-base --is-ancestor`는 git 어댑터가 판정한 결과를 인수로 받는다 → `DELETE`+`INSERT`), `tsvector`+`pg_trgm` 검색. 브레이커·시간 초과 D13·D15.
3. `app/catalog.py` 확장: 빌드가 DB 트랜잭션과 메모리 스냅샷을 같은 행 집합으로 함께 갱신(순서: DB 커밋 성공 → 참조 교체. DB 실패 → 참조만 교체하고 degraded). 검색은 DB가 살아 있으면 DB 순위, 아니면 메모리 부분 일치. `list_skills`에 최근 평가 결합.
4. `driving/mcp_tools.py`에서 도구 호출마다 `opentelemetry.trace.get_current_span()`에 속성을 더한다(DESIGN §2 데이터 표의 규약: `langfuse.user.id`, `langfuse.observation.metadata.skill`·`.sha`·`.query`·`.result_count`). exporter는 `opentelemetry-sdk`의 환경 변수 자동 구성(`opentelemetry-exporter-otlp-proto-http`)을 의존에 넣고 코드에서 조립하지 않는다.
5. 패키지 데이터: `packages/server/pyproject.toml`에 `migrations/*.sql`을 wheel·sdist에 포함하는 규칙을 적고, 러너는 `importlib.resources.files("harness_catalog_server") / "migrations"`로 경로를 얻는다(작업 트리 상대 경로를 쓰지 않는다). V21이 설치본에서 이를 확인한다.
6. 시험: adapters/pg(testcontainers)에서 DDL 적용, 세대 검사(낡은 커밋 빌드가 아무것도 바꾸지 않음), 검색 문법. unit에서 DB 단절 시 degraded 읽기; `InMemorySpanExporter`로 도구 넷의 스팬 이름·속성.

**끝:** testcontainers PostgreSQL에서 그림 3 DDL이 그대로 적용되고, 낡은 커밋의 빌드가 최신 인덱스를 되돌리지 않는 시험과 스팬 속성 시험이 통과하며, DB를 끊어도 `/readyz` 200 + `degraded`이고 읽기 넷이 답한다.

### P3. 검사 명령·초기화 명령·Langfuse 플러그인

0. 착수 조건: D8의 표지가 `plans/pilot.md`의 실측 기록으로 정해져 있다. 없으면 서비스 주체를 reader로 세우는 한 줄만 뒤로 두고 나머지를 먼저 한다.
1. `app/check.py`: DESIGN §5의 검사 열을 순수 함수로. 입력은 검사할 트리(작업 트리 또는 커밋)·기준 커밋·git 어댑터(삭제 이력, 기준 커밋의 트리), 출력은 위반 목록(항목 번호·경로·사유). 기준 커밋이 없으면 5·9를 건너뛰고 그 사실을 출력에 적는다. P1의 인덱스 빌드가 이 함수를 부르도록 바꾼다(스킬 실패 → 인덱스 제외, 구조 실패 → 빌드 실패).
2. `cli.py check [<root>] [--base <commit>]`: 1을 CLI로. `--base`는 항목 5·9의 기준 커밋(DESIGN §2.1: pre-commit은 HEAD, PR CI는 merge-base, main CI는 직전 커밋, 인덱스 빌드는 `index_state.commit_sha`). 얕은 클론이면 항목 5는 종료 2. 종료 0 통과 / 1 위반 / 2 검사기 실패(gitleaks 없음·얕은 클론 등). pre-commit 훅과 CI 워크플로가 이 명령을 부른다(CLI 패키지 데이터 `templates/`의 훅·워크플로 파일이 그렇게 적혀 있다).
2b. `ci.py`·`gitleaks.py` + `cli ci base|check|evals`: 워크플로가 부르는 CI 논리(distribution D24, 2026-10-10). `check`는 gitleaks를 PATH→캐시→핀된 판 내려받기(체크섬)로 확보한다.
3. `cli.py init <repo-url>`: 운영자 git 자격으로 clone → URL에서 호스트 판별(GitHub·GitLab) → 패키지 데이터 `templates/`에서 `.harness-catalog`·`skills/{pin-skill,write-skill}`·README·pre-commit 설정·그 호스트의 CI 워크플로를 없는 것만 쓰고(템플릿의 판 자리표 `<판>`은 cli 자기 판 `importlib.metadata.version("harness-catalog-cli")`로 채우되, 먼저 코드 저장소에 태그 `v<판>`이 있는지 `git ls-remote --tags`로 확인하고 없으면 종료 1. `--pin <ref>`는 확인 없이 그 ref — distribution D22) → 커밋·push. 표지가 있는데 `layout`이 다르면 멈춘다(종료 1). 두 번 돌리면 변경 0.
4. `cli.py reindex --accept-rewind`: 규칙 3의 `main_rewound` 뒤 운영자가 명시적으로 인덱스를 새 `main`으로 다시 짓는 명령.
6. `app/authz.py` 완성: 주체 셋(reader·그룹 없음·서비스) × 도구 넷 × 스코프.
7. `packages/harbor-langfuse/`: 별도 배포물(`pyproject.toml`, `src/harbor_langfuse/plugin.py`), 서비스 이미지에 들어가지 않는다. Harbor `BaseJobPlugin` 구현. `on_job_start`에서 잡의 태스크 경로에서 스킬 이름과 `evals/` 케이스를 읽어 Langfuse dataset `<catalog>/<skill>`과 item(케이스, `input` = `instruction.md`)을 있으면 재사용·없으면 생성하고, dataset run(`run_name` = Harbor 잡 이름, `metadata` = `skill`·`sha`(주입한 스킬 원천의 ref)·`scenario_sha`(`evals/` tree)·`model`·`harness`(agent 이름)·`baseline`(스킬 원천 없음))을 연다. `on_job_end`에서 트라이얼마다 trace(입력 instruction, 출력 검증기 stdout 요약, 메타데이터 `trial_uri`·토큰·비용)와 run item, score `passed`(BOOLEAN, reward ≥ 1)를 만든다. 키는 `LANGFUSE_PUBLIC_KEY`·`LANGFUSE_SECRET_KEY`·`LANGFUSE_HOST` 환경 변수. Harbor의 `packages/harbor-langsmith/src/harbor_langsmith/plugin.py`(852줄, `_create_root_run`·`_create_feedback`·`_request` 재시도)를 본뜨되 ATIF 스텝은 그쪽도 올리지 않으므로 올리지 않는다. Langfuse SDK v3의 저수준 dataset run·score API 이름은 pilot Q14(e)가 실측한 뒤 쓴다.
8. 시험: unit에서 검사 열 각각의 위반 표본(구조 결손 다섯, 스킬 위반 넷, 스킬 쌍의 복사본 드리프트 하나)과 통과 표본; adapters/git에서 임시 저장소에 `init`을 두 번 돌려 두 번째가 변경 0, GitHub·GitLab URL로 워크플로 파일이 갈리는지; 같은 표본을 CLI·인덱스 빌드 두 경로로 돌려 판정이 같은지; `main`을 되감은 클론으로 fetch해 `main_rewound`; 플러그인은 Harbor `JobResult` 표본으로 Langfuse 호출을 기록하는 가짜 클라이언트에 대해; http에서 403 실물.

**끝:** §5의 검사 열 각각을 위반한 표본이 `check`에서 항목 번호와 함께 종료 1로 거부되고 인덱스 빌드에서 같은 스킬이 빠지며, `init`이 빈 저장소를 표지·`skills/`·CI·pre-commit·README가 있는 저장소로 만들고 두 번째 실행에서 변경이 없으며, PR로 병합한 스킬이 `FETCH_INTERVAL_SECONDS` 두 주기 안에 `search_skills`에 나온다.

## 5. 불채택 표

기각 사유는 현재형으로만 적는다.

| 항목 | 기각 근거 (왜 지금 아닌가) |
|---|---|
| ORM(SQLAlchemy 등) | 표 셋 + 상태 행 하나이고 SQL이 DDL 계약 그대로다. ORM은 그 DDL(생성 열·GIN·CHECK)을 감추고 다시 적게 한다 |
| DI 프레임워크 | 주입 수준이 하나(어댑터 넷 → 앱)라 `bootstrap` 함수 하나가 곧 합성 루트다(DESIGN §2.1) |
| FastAPI | HTTP 라우트가 둘이고 SDK가 이미 Starlette 앱을 준다. 프레임워크를 얹는 것이 곧 인터페이스 비용이다 |
| 태스크 큐(Celery 등) | 비동기 작업이 fetch·보존 둘이고 둘 다 프로세스 안 주기 루프로 충분하다. push 실패는 큐에 쌓지 않고 저자에게 돌려준다(DESIGN §2.1) |
| 인덱스 갱신 webhook | 우회 push의 허용 지연은 fetch 간격(설정)으로 운영자가 정한다. webhook은 git 호스트별 형식과 수신 엔드포인트 인증을 더한다 |
| `retired_name` 표 | 읽는 곳이 `check`의 이름 재사용 검사 하나이고 게시는 드물다. git 이력 질의 한 번이면 된다(그림 3 규칙 2) |
| 쓰기 도구(`publish_skill`·`certify_skill`) | git 호스트가 이미 주는 리뷰·권한·이력·CAS를 다시 만드는 것이고, 그 위에 "현재 판" 둘의 모순이 생겼다(DESIGN §11 8차 리뷰·v3.3). 게시는 브랜치·PR·병합 |
| 병합 즉시 반영(webhook·`/refresh`) | 반영 지연 상한이 설정값 `FETCH_INTERVAL_SECONDS`이고 그것이 문제 된 적이 없다(DESIGN §7) |
| SQLite 폴백 | 파일럿·운영 엔진이 다르면 방언 차이로 초록 시험이 운영에서 깨진다. 엔진은 PostgreSQL 하나다(DESIGN §2.1) |
| 세션 기반 전송(2025-11-25) | 서버는 무상태이고 2026-07-28 무세션이 설계의 결정이다. 구세대 클라이언트는 SDK가 감지해 응답한다(문면) |
| 자체 JWT 검증 | 서명·JWKS 캐시·`kid` 재조회는 표준이 있는 계산이고 PyJWT가 한다. 자작은 C-LIB-1 위반이다 |
| 벡터 열 | 어휘 검색의 miss가 실측되지 않았다. 파일럿이 처음 잰다 |
| tree→commit 캐시 표 | 과거 판 요청이 드물고 `git log` 걸음이 그 경로의 커밋 수에 묶인다. 재지 않은 최적화다 |
| 브레이커 라이브러리 | 상태 기계가 열 줄이고 DESIGN 표에 없다. 측정·판정 인프라가 아니라 C-LIB-1의 대상이 아니다 |

## 6. 리스크 대응표

상위 `PLAN.md` §8의 R1~R8은 반복하지 않는다. 서비스 안의 것만이다.

| # | 리스크 | 대응 |
|---|---|---|
| S1 | `mcp` v2의 `TokenVerifier`·`AuthSettings`·`streamable_http_app` 이름이 문면과 다르다(상위 R5의 구체) | P1 3~7단계에서 실제 패키지를 핀하고 HTTP 시험이 401 챌린지 헤더 실물을 본다. 이름이 다르면 `driving/mcp_tools.py`·`adapters/oidc.py` 둘만 바뀐다 |
| S2 | 인덱스 빌드가 DB와 메모리를 함께 갱신하다 한쪽만 성공 | 순서 고정(DB 커밋 → 참조 교체). DB 실패는 degraded이고 다음 fetch 회차가 다시 시도한다. 메모리 사본이 DB보다 앞서는 것은 허용(같은 저장소 스냅샷에서 나온다) |
| S4 | gitleaks가 바이너리(`assets/`)를 텍스트로 읽어 오탐 | P3에서 표본 바이너리(PNG·zip)로 gitleaks의 실제 동작을 재고 결과를 §9에 적는다. 저자 예외 승인 절차는 두지 않는다(DESIGN §5) |
| S5 | `skills_ref`가 라이브러리 API를 안 주고 CLI만 준다 | 같은 포트(`SkillValidator`)를 서브프로세스 어댑터로 채운다. 앱은 모른다 |

## 7. 검증 원장

| # | 검증 | 방법 | 통과 기준 | 상태 |
|---|---|---|---|---|
| V1 | 기동 구조 검사 | 저장소 넷(닿지 않음·빈 저장소·표지 없음·`layout=2`·`skills/` 없음)을 각각 가리켜 기동 | 각각 `/readyz` 503 + 사유(`repo_unreachable`·`no_main_branch`·`not_a_catalog`·`unsupported_layout`·`layout_mismatch`)가 정확히 대응하고 저장소에 쓰기 0 | 대기 |
| V2 | 빈 카탈로그 준비됨 | `init`으로 만든 저장소(스킬 0) | `/readyz` 200, `search_skills` 빈 결과, 마지막 fetch 시각 있음 | 대기 |
| V3 | 401 챌린지 | HTTP로 토큰 없음·서명 불일치·`aud` 다름·만료·`iss` 다름 다섯 | 다섯 전부 401 + `WWW-Authenticate: Bearer resource_metadata=… scope="skills:read"`, RFC 9728 메타데이터 GET이 200 | 대기 |
| V4 | 403 두 종 | `skills:read` 없는 토큰(`openid`만)으로 `search_skills`; `skills:read`는 있으나 그룹 없음 | 전자 403 + `error="insufficient_scope"` 챌린지, 후자 403 + 챌린지 없음 + 본문 `not_a_member` | 대기 |
| V5 | 인가 행렬 | 주체 셋(`harness-readers` 사람·그룹 없는 사람·서비스) × 도구 넷 = 12칸을 `authz.decide` 단위 시험으로 | 12칸 전부 DESIGN 그림 4 표와 일치. 그룹 없음은 넷 전부 `not_a_member` | 대기(서비스 주체 칸은 D8 뒤) |
| V6 | 인덱스 세대 검사 | testcontainers: 커밋 B(자손)로 빌드 뒤 커밋 A(조상)로 빌드 | 두 번째 빌드 뒤 `index_state.commit_sha`가 B이고 행 집합이 B의 것 | 대기 |
| V7 | 도구 호출 스팬 | `InMemorySpanExporter`를 꽂고 도구 넷을 사람 토큰으로 호출(`search_skills`는 결과 0인 검색어 하나 포함) | 호출마다 `SERVER` 스팬 하나, 이름 `tools/call <tool>`, `gen_ai.tool.name`=도구, `langfuse.user.id`=토큰 `sub`; `load_skill`·`get_skill_file`에 `metadata.skill`·`.sha`(응답 `sha`와 같음); `search_skills`에 `.query`·`.result_count`(0). DB를 끊어도 스팬은 같다 | 대기 |
| V8 | degraded 읽기 | DB 컨테이너를 멈춘 채 도구 넷 호출과 `/readyz` | 넷 전부 응답(검색은 부분 일치), `/readyz` 200 + `degraded: ["db_unavailable"]`. 도구 응답에 `degraded` 필드가 없다 | 대기 |
| V9 | 검사 열 | §5의 열 항목 각각을 위반한 표본 저장소·스킬 | `check`가 항목 번호와 경로·사유를 출력하며 종료 1(항목 9·10은 경고 출력 + 종료 0). 검사기(gitleaks)를 치우면 종료 2. 통과 표본은 종료 0 | 대기 |
| V10 | 병합 반영 | 시험 저장소에 PR을 병합 | 우산 V3의 허용오차(`FETCH_INTERVAL_SECONDS` 두 주기) 안에 `search_skills`에 나오고 `sha`가 병합 커밋의 tree와 같다 | 대기 |
| V11 | `init` 멱등·호스트별 | 빈 저장소(GitHub URL, GitLab URL 각각)에 `init` 두 번 | 첫 실행 뒤 표지·기본 스킬 둘·README·pre-commit 설정·그 호스트의 워크플로 파일이 있고, 두 번째 실행은 변경 0. `layout = 2` 표지가 있는 저장소에서는 종료 1 | 대기 |
| V12 | 세 자리 동일 판정 | 같은 표본을 pre-commit 훅(`check`), CI(`check`), 인덱스 빌드 세 경로로 | 셋의 위반 목록이 같다 | 대기 |
| V13 | 은퇴 이름 | 스킬 디렉토리를 지운 PR 뒤 같은 이름의 디렉토리를 다시 넣은 PR | `check` 항목 5로 거부. 규율 위반으로 병합해도 인덱스 빌드가 그 스킬을 뺀다 | 대기 |
| V14 | `replaced-by` | 없는 대상·이미 대체된 대상·자기 자신·순환 둘 | `check` 항목 6으로 넷 전부 거부. 유효한 대상은 통과하고 목록에 실린다 | 대기 |
| V17 | 파일 읽기 경계 | `../`, 절대 경로, 심볼릭 링크, 1 MB + 1 바이트 | 넷 전부 `path_rejected` 또는 `input_limit`, 정상 파일과 바이너리(base64)는 통과 | 대기 |
| V18 | 크기 상한 | 51개, 1 MB + 1 파일, 합계 5 MB + 1, 심볼릭 링크 | `check` 항목 7로 넷 전부 거부. 바이너리(`assets/`)는 통과 | 대기 |
| V19 | fetch 간격 설정 | `FETCH_INTERVAL_SECONDS=5`로 기동하고 우회 push | 5~10초 안에 인덱스 반영, 기본값 기동은 60~120초 안 | 대기 |
| V20 | 규칙 게이트 첫 완주 | P1 첫 커밋에서 `pre-commit run --all-files`와 `selftest.sh --census src/ tests/` | ruff·ast-grep이 파일을 검사하며 돌았고 검출마다 참·거짓 판정이 §9에 있다 | 대기 |
| V22 | `main` 되감기 | 시험 저장소의 `main`을 이전 커밋으로 강제 push한 뒤 fetch | 인덱스가 갱신되지 않고 `/readyz` 200 + `degraded: ["main_rewound"]`. `reindex --accept-rewind` 뒤 새 `main`으로 인덱스가 지어진다 | 대기 |
| V26 | Langfuse 플러그인 | 시험 카탈로그의 스킬 하나에 Harbor 태스크 둘을 두고 `harbor run --plugin harbor_langfuse:LangfusePlugin`을 스킬 있이·없이(Langfuse 시험 프로젝트 키) | Langfuse에 dataset `<catalog>/<skill>` 하나·item 둘, run 둘(메타데이터 `sha`·`model`·`harness`·`baseline` 실물), 트라이얼마다 trace + `passed` score가 reward와 같다. `GET /api/public/datasets/{name}/runs`로 두 run이 보인다 | 대기 |
| V21 | 마이그레이션 패키징 | `uv build`로 wheel·sdist를 만들고 각각 빈 가상 환경에 설치한 뒤 `python -c` 한 줄로 `importlib.resources`에서 `0001_schema.sql`을 열고, testcontainers PostgreSQL에 설치본의 러너로 yoyo를 적용 | wheel·sdist 둘 다에서 파일이 열리고 적용이 성공한다. 작업 트리가 없는 디렉토리에서 실행한다 | 대기 |

## 8. 개정 규약

판정 변경은 §3 원장에 행 추가(기존 행 유지, 후속 행이 우선). 설계 계약(도구·설정·스키마·오류 코드)을 바꾸는 일은 DESIGN §11에 먼저 적는다. 진행은 §9에 단계별로, 단계 완료는 상위 `PLAN.md` §11에도. 기록은 현재 상태만 적는다(REVIEW.md V-REC-1) — 재심 조건·트리거를 등록하지 않고, 기각에는 지금 아닌 이유를, 근거에는 등급을 붙인다.

## 9. 진행 원장

| 일자 | 항목 | 내용 | 근거 |
|---|---|---|---|
| 2026-10-07 | 우산 §6-10·11·12 반영 — P1 끝 조건 실물 충족 | 서비스 주체 종류·`PrincipalKind`·표지 집합 삭제(기계 계정은 그룹으로 reader), 요구 스코프 = `required_scopes(public_url)` = `openid groups audience:server:client_id:<URL>`(PRM 광고 + 검증기가 유효 토큰에 부여, 토큰에서 검사 안 함), `insufficient_scope` 경계 삭제, Dex 설정 `passwordConnector`, `scripts/dev-token.sh`(기계 계정 비밀번호 그랜트). 시험 65. 실물 왕복(r2): gyojunan PKCE → 200, audience 스코프 없음 → 401, svc-harness 비밀번호 그랜트 → 200, admin → not_a_member | DESIGN §11, plans/pilot/r2.md |
| 2026-10-10 | OTel 배선 누락 수정 + 설정 검증(Codex 설정 리뷰) | Codex 적대 리뷰(설정 표면, 9건) 중 **높음 1**: 서버 어디에서도 TracerProvider·OTLP exporter를 만들지 않아 `OTEL_EXPORTER_OTLP_*`를 줘도 스팬이 no-op이었다(MCP SDK는 `get_tracer("mcp-python-sdk")`로 스팬을 내지만 전역 provider가 없으면 비기록). 수정 — `server/telemetry.py` `configure_tracing()`: ENDPOINT가 있을 때만 provider(service.name = `OTEL_SERVICE_NAME`, 기본 harness-catalog) + BatchSpanProcessor(OTLP/HTTP)를 전역에 꽂고 `serve`가 bootstrap 전에 부른다. 헤더는 `OTEL_EXPORTER_OTLP_HEADERS_FILE`(docker secret, D10)이 있으면 그 파일(`k=v,k2=v2`), 없으면 exporter의 환경 변수. **실측**(빠른 시작 + 호스트 OTLP 수신기): `search_skills` 한 번에 989바이트 수신, 안에 `tools/call`·`search_skills`·`mcp-python-sdk`·`langfuse.user.id`·`harness_catalog.query`·`result_count`·service.name 전부 있음(Q15(a) 절반 — Langfuse 실물 도착은 미실측). **중간**: issuer·공개 URL 끝 슬래시가 Dex(원문)와 레지스트리(rstrip) 사이를 갈라놓을 수 있다 → `Settings` `field_validator(mode=before)`가 끝 `/`를 거부(시험 2). 시험 +7(telemetry 4, settings 2, …) | Codex 리뷰 2026-10-10, 로컬 실측 |
| 2026-10-10 | GitStore safe.directory 결함 수정 | 레지스트리가 다른 uid가 소유한 file:// 저장소(빠른 시작의 root 소유 볼륨)를 clone하지 못했다: `fatal: detected dubious ownership`. 원인 — `safe.directory`는 보호 범위(system·global)에서만 읽히고, 로컬 전송의 `git-upload-pack` 자식은 `-c`·`GIT_CONFIG_COUNT`를 받지 않는다(git 2.47.3 컨테이너 실측: `-c`와 환경 둘 다 실패, `GIT_CONFIG_GLOBAL`만 성공). 수정 — `remote_url`이 있을 때(레지스트리 모드)만 `<workdir>/gitconfig`에 `[safe] directory = *`를 쓰고 `_env`가 `GIT_CONFIG_GLOBAL`로 가리킨다. CLI(`check`, 로컬 모드)는 사용자의 `~/.gitconfig`를 건드리지 않는다. 기존 `GIT_CONFIG_COUNT` 줄은 제거(동작하지 않는 주장이었다) | 빠른 시작 실측(distribution D24) |
| 2026-10-07 | 의존성 판 고정(사용자 결정) | pyproject.toml 다섯(루트 dev 그룹 + 패키지 넷)의 `>=`·`<` 범위 지정 21건을 uv.lock에 잠겨 있던 판 그대로 `==`로 고정. 해석 결과는 변화 0(uv.lock의 `version =` 줄 변경 0), 게이트 넷·pyright·시험 65 통과. 판 올리기는 이제 pyproject의 `==` 값을 바꾸는 명시 행위다 | 사용자 지시("버전을 픽스해라 ==로") |
| 2026-10-07 | P3 Codex 리뷰 반영 | 리뷰(Codex 01a1122c, 중요 8·경미 1): ① CI 템플릿 — agent 목록을 셸 잡이 JSON으로 쪼개 matrix에, 자격 검사를 D19 그대로(CLAUDE_FORCE_OAUTH·auth.json·cursor/gemini·미지 agent 실패), push 기준을 `github.event.before`(push 전체), 스킬 있이(`--skill ./skills/<name>`)·없이 두 번 `harbor run --path`; ② `init` — 원격에 main이 있으면 checkout, 커밋은 있는데 main이 없으면 종료 1, 호스트 판별은 DNS 라벨 일치; ③ 플러그인 — Harbor가 스킬 원천을 캐시 경로로 바꾸므로 `sha`는 `HARNESS_SKILL_REF`(CI가 `github.sha`), `scenario_sha`는 `git rev-parse HEAD:./`(evals tree), `VerifierResult`는 `rewards`뿐이라 출력은 rewards JSON, 토큰·비용은 `compute_token_cost_totals()`(다단계 합산); 시험은 Harbor 실물 모델(`TrialResult`·`VerifierResult`·`AgentContext`·`ExceptionInfo`)로; ④ 기동 경합 — 스케줄러가 마이그레이션 완료(상한 30초)를 기다린 뒤 첫 빌드, resync의 STALE은 `main_rewound`로 표시 | Codex 리뷰 |
| 2026-10-07 | P3 구현 + P2 Codex 리뷰 반영 | **P3**: `cli init <repo-url> [--pin] [--host]`(clone → 호스트 판별 → 없는 파일만 → 커밋·push, 멱등, 표지 layout 불일치 종료 1, 판 자리표 `<판>`을 cli 판으로·태그 존재 확인), `cli config list|docs`(실효값·출처, `docs/configuration.md` 생성), 템플릿 패키지 데이터 `packages/cli/src/harness_catalog_cli/templates/`(표지·`skills/.gitkeep`·README(사용자 안내 셋·게시 규율·운영자 체크리스트)·pre-commit(local 훅, core+cli 명세)·`github/check.yml`(check + 선택 evals matrix)·`gitlab/.gitlab-ci.yml`(문면)) — `examples/catalog-template`은 그 디렉토리의 심볼릭 링크(원본 하나), `packages/harbor-langfuse/`(`LangfusePlugin`: on_job_start에 dataset·item, on_job_end에 trial마다 trace·run item·score `passed`; Harbor는 TYPE_CHECKING에서만, Langfuse는 `Sink` 포트 뒤 — v4.17 API 시그니처 실측: `api.dataset_run_items.create`·`start_observation`·`create_score(trace_id)`; Cloud 왕복은 Q14(e)). **P2 리뷰(Codex 01a11221, 치명 1·중요 7·경미 2) 반영**: 빈 `index_state` 레이스 → `pg_advisory_xact_lock` 선행; 같은 커밋에서도 DB 미반영이면 재시도(`_db_synced`); 첫 기동의 기준 커밋은 `FactStore.current_commit()`(DB); 되감기 재기동은 base 세대를 git에서 지어 읽기를 잇되 DB에 쓰지 않음; 마이그레이션 전 DB 경로 차단(`PgFactStore.enable()`, 5초→5분 백오프 = D12); 브레이커 half-open(시험 요청 하나) + 잠금; lifespan은 태스크 그룹 합류 뒤 풀·deploy key 정리; `reindex`는 finally로 정리; `merge-base` 오류는 fail-closed. 시험 63(+ 동시 최초 구축 all-or-nothing, DDL 식·IMMUTABLE·CHECK·연산자 클래스, half-open, 마이그레이션 게이트, DB 재동기, 재기동 기준 세대, init 멱등·호스트별·layout, config, 플러그인 가짜 Job/Sink). pyright 0, 게이트 0 | 우산 §4 P3, Codex 리뷰 |
| 2026-10-07 | P2 인덱스 표·스팬 구현 + P1 Codex 리뷰 반영 | **P2**: `migrations/0001_schema.sql`(그림 3 DDL 그대로, 패키지 데이터), `migrate.py`(yoyo, `postgresql+psycopg://`), `adapters/pg.py`(풀 1~4, 문장 5초, 브레이커 3회→30초, 인덱스 교체 트랜잭션 `index_state FOR UPDATE` + 자손 검사 콜백, tsvector+pg_trgm+ILIKE 검색), `ContentStore.is_ancestor`(`git merge-base --is-ancestor`), `FactStore.replace_index → IndexOutcome(REPLACED·STALE·UNAVAILABLE)`, `Catalog.rebuild(accept_rewind)`(되감기면 메모리도 안 바꾸고 `main_rewound`), `harness-catalog-server reindex --accept-rewind`, 기동 시 마이그레이션 태스크(실패 시 백오프, fetch 루프와 독립), 스케줄러 백오프 D11(2배·상한 16·성공 시 1; 실패 = reasons 또는 `checker_failed`/`rebuild_failed`), 스팬 속성 4종. 시험: pg(testcontainers 실물: DDL 열 순서·인덱스·확장·멱등, 세대 검사 STALE, 한국어/영어 검색, 브레이커, 닿지 않는 DB → UNAVAILABLE)·spans(인프로세스 ASGI + InMemorySpanExporter: `tools/call <tool>` SERVER 스팬, `gen_ai.tool.name`·`langfuse.user.id`·skill·sha·query·result_count). **P1 리뷰(Codex 01a11210, 치명 1·중요 11·경미 4) 반영**: 항목 5 fail-closed(얕은 클론·log 실패 → 검사기 실패, CLI 종료 2), 항목 2에 SKILL.md 존재, 항목 9는 기준판 frontmatter를 파서로, 항목 1·2 위반은 `layout_mismatch`(503)로 빌드 자체를 막음, `get_skill_file.sha`=판(tree)+`blob` 별도, 서비스 주체는 검증기가 `skills:read`를 채워 스코프 무관(D8의 표지 집합은 `authz.DEFAULT_SERVICE_CLIENT_IDS` 한 자리), deploy key는 0700 디렉토리에 0600으로 한 번·`shlex.quote`·종료 시 삭제, `--end-of-options`, JWKS 조회는 스레드, 빌드 예외 경계 전부(상태에 `rebuild_failed`). 시험 50(+ 항목 2·9 표본, 저장소 수준 위반 503, 얕은 클론 종료 2, 스코프 없는 서비스 주체, 파일 sha). pyright strict 0, 게이트 0. **실측**: testcontainers는 macOS Docker Desktop에서 `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`이 필요; Docker VM 디스크가 차면 postgres가 recovery 루프에 빠진다(빌드 캐시 8.9GB 정리로 복구) | 우산 §4 P2, Codex 리뷰 |
| 2026-10-07 | P1 읽기 경로 구현 (DB 없이) | 워크스페이스 첫 커밋(루트 `pyproject.toml`·`uv.lock`, 배포물 넷의 pyproject). core: `settings`(HC__·`_FILE`)·`catalog_file`·`model`·`ports`·`authz`·`check`(항목 1~10)·`catalog`(구조 검사·스냅샷·목록·검색·본문·파일)·`adapters/git`(bare 클론, `ls-tree -r -t`, 이력)·`adapters/validate`(skills_ref + gitleaks, fail-closed). server: `adapters/oidc`(PyJWKClient, aud=공개 URL, leeway 60)·`driving/mcp_tools`(도구 넷, `CallToolResult` `{code, detail}`, 스팬 속성)·`ops`·`scheduler`·`bootstrap`·`__main__ serve`. cli: `check`(`--rev INDEX|HEAD|<commit>`, `--base`, 종료 0/1/2). Dockerfile(python:3.12-slim + git + gitleaks v8.30.1, uv 0.11.8, 비루트). 시험 39: core 가짜 어댑터 13, adapters(git 임시 저장소·validate) 6, cli 4, http 5(실제 uvicorn + 가짜 issuer/JWKS: PRM, 401, 403 insufficient_scope, not_a_member, 도구 넷, path_rejected, 서비스 주체). pyright strict 0, ruff·ast-grep 0. 첫 고정 판: mcp 2.3.0, starlette 1.7.0, uvicorn 0.54.0, PyJWT 2.15.1, psycopg 3.3.6, yoyo 9.0.0, otel 1.45.0, pydantic 2.13.5, pydantic-settings 2.15.0, skills-ref 0.1.1, anyio 4.15.1, typer 0.27.2, harbor 0.24.0, langfuse 4.17.0. **실측 발견 넷**: ① `skills_ref.validate`는 디렉토리명 = name을 요구해 export 경로를 `<tmp>/<name>`으로; ② `ls-tree -r`은 디렉토리를 안 내므로 `-t` 필요; ③ `read_properties().metadata`가 None일 수 있다; ④ `skills/.gitkeep`은 항목 2의 예외. **P1 끝 조건의 미달 하나**: "Dex 토큰으로 HTTP 호출 성공"은 우산 §6-11·12(aud·스코프) 결정 전까지 가짜 issuer 토큰(aud=공개 URL, scope=skills:read)으로만 통과한다 | 우산 §4 P1, r1 |
| 2026-10-07 | Codex 리뷰 반영 | `init`의 태그 존재 확인·`--pin`(P3-3), ruff.toml 면제 경로를 배포물 둘의 `__main__.py`로 | Codex 01a111e5 |
| 2026-10-07 | 잔재 정정 | 워크스페이스 전환(2026-09-27) 뒤 남은 단일 패키지 경로 `src/harness_catalog/`를 §0·§1·P2-1·P2-5에서 `packages/`로. `init`이 템플릿의 판 자리표를 자기 판으로 채운다(P3-3, distribution D22) | D1, 우산 §11 |
| 2026-09-27 | 설계 개정 반영 | `check` 항목 10(복사본 드리프트 경고): §1 표, P3-8 표본, V9 | DESIGN §11 |
| 2026-09-27 | 설계 개정 반영 | v3.5: `usage_record`·보존 삭제·`USAGE_RETENTION_DAYS` 제거(설정값 여섯·표 하나·규칙 다섯), 스팬 속성을 `mcp_tools.py`에(P2-4), 스케줄러 루프 하나(D11), V7을 스팬 시험으로 | DESIGN §11 |
| 2026-09-27 | 설계 개정 반영 | v3.4: `record_eval`·`eval_result`·`skills:write` 제거(도구 넷·포트 일곱·표 둘·오류 코드 다섯. `evals.py`·V15·V16 삭제, D6·D8·D12·P2-2·P3·V4·V8 개정), 플러그인을 `packages/harbor-langfuse/`로(P3-7, V26) | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | Harbor 플러그인 모듈(P3-7a, V26). 서비스 이미지 밖의 선택 extra — v3.4에서 Langfuse 플러그인으로 대체 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | `list_skills` 필드 최소화: D10·S6 삭제, P1-5·V16 개정(`model`·`harness` 인자) | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 9차 리뷰: `check --base`, 브랜치 판 `record_eval` 제거(D6·V16), D13에서 push 브레이커 제거 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | v3.3(git 워크플로): 쓰기 도구·인증·역할 계층 제거, `check`·`init`·`reindex` CLI, P3 재작성, V5 15칸, V9~V14·V18·V22 개정, V23~V25 삭제 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 8차 리뷰(publish·certify 모순): 유효 판 인덱스, 인증 ref, fail-closed, 인증 세대, `retire_requires_revoke`. P3-5 재작성, V22 개정, V23~V25 추가 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 역할 3단 계층(reader·editor·admin, 그룹 셋): V5 35칸, `insufficient_role` | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 권한 모델(DESIGN 그림 4): `authz.py`가 표를 그대로 옮기고 V5가 그 표와 대조 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 인증된 판(DESIGN §11, `certify_skill`·`certification`·규칙 7). P3에 5단계, V5를 28칸으로, V22 추가. 표 넷·도구 다섯 | DESIGN §11 |
| 2026-09-26 | Codex 교차 검증 1회 | 반영: 도구 응답의 `degraded` 필드 삭제(D13, V8), 오류 코드 어휘를 DESIGN §3으로 이관(D14), 마이그레이션 재시도를 fetch 루프에서 분리(D12), 패키지 데이터 포함·`importlib.resources` 로딩과 설치본 검증(P2-5, V21), S4·S6의 미래 조건절 삭제. 기각 없음 | 상위 PLAN §11 |
| 2026-09-26 | PLAN 초판 | 코드 배치·판정 D1~D16·단계 P1~P3·검증 V1~V20. 서비스 주체 판별(D8)은 파일럿 실측 전이라 미정으로 두었다 | 상위 PLAN §3-6 |
| 2026-10-11 | D17 구현 | 선례 조사(UC·Codex·Vercel·Claude Code·Anthropic Skills API·SEP-2631), syntopicon kb-query(웹훅 HMAC 검증 절차·RFC 9110 §17.9·Newman 회전), Codex 설계 리뷰 1회 반영(URI 경로 `/mcp/archive`, 자격을 헤더로, 실제 tar 바이트 상한, sha256 사전 검증, 엄격 파싱·만료 창, 단일 복제본 명문화, 라우트 순서). 구현: core `archive_token.py`·`ArchiveInfo`·`ContentStore.archive_tree`·`Catalog.get_skill_archive`, GitStore 스트리밍 archive(Popen, 상한, mkstemp+replace), server 라우트·도구·authz. 테스트: 서명 15경우, 캐시·상한, git 결정성(같은 판 두 번 = 같은 sha256), HTTP 통합(명세→GET→tar==files, 403 셋, 재사용, not_a_member, unknown_version). pin-skill 절차 6단계 개정 | pytest, Codex 코드 리뷰 아래 |
| 2026-10-11 | Codex 코드 리뷰 반영(아카이브) | BUG 4·RISK 2·NIT 1. ① `git archive <commit>:skills/<name>`은 **결정적이지 않다**(tree-ish → 생성 시각 mtime; 2초 간격 sha256 상이 실측) → `--mtime=@<커밋 시각>`(git ≥ 2.42, 이미지 2.47), 초 경계를 넘긴 결정성 테스트와 항목 mtime==커밋 시각 단언. ② 동시 캐시 미스가 서로의 명세를 깨뜨릴 수 있음 → 확인·생성·해시를 `_archive_lock`으로 직렬화 + 8스레드 동시 발급 테스트. ③ stderr 파이프 교착 → stderr를 임시 파일로. ④ 서빙 중 삭제 경쟁 → 발급 때 mtime 갱신, 보존 = 토큰 수명+여유+60초(그 뒤엔 유효 토큰이 없음), 정리는 발급 경로가 아니라 스케줄러 틱과 기동 때. ⑤ 자식 프로세스 미회수 → 어떤 예외 경로에서도 kill·wait. ⑥ 캐시 적중이 상한·무결성을 건너뜀 → 사이드카 sha256과 크기 상한 검증, 어긋나면 다시 만듦(테스트). ⑦ 라우트 오류 매핑 암묵 → not_found·unknown_version=404, input_limit=413, 그 밖은 500으로 드러남. 포트는 `archive_skill(commit, name, …)`로 바뀜. HTTP 테스트에 Cache-Control·Content-Length·빈 403 본문 추가 | Codex 코드 리뷰 1회, 2회 아래 |
| 2026-10-11 | Codex 코드 리뷰 2차 반영(아카이브) | BUG 0·RISK 4·NIT 2. ① tar 바이트가 git 설정(`tar.umask`·속성 파일·전역/시스템 설정)에 매임 → `-c tar.umask=0022 -c core.attributesfile=/dev/null`(레지스트리 전용 `GIT_CONFIG_GLOBAL`의 safe.directory는 유지). ② 사이드카가 자기 일관성만 보장 → 형식 판 `v2 <sha256>`을 기록하고 판이 다르면 재생성(옛 규칙의 캐시 불채택). ③ 정리가 lock을 쥔 채 전체 훑기 → 훑기는 lock 밖, 재확인·삭제만 lock 안. ④ 상한 초과 외 예외 때 자식을 600초까지 기다릴 수 있음 → 스트리밍이 정상 종료하지 않았으면 즉시 kill, 60초 대기. ⑤ 동시성 테스트에 출발 장벽·예외 수집. ⑥ 결정성 테스트의 1.1초 sleep 제거(항목 mtime == 커밋 시각 단언이 회귀를 잡는다). 미해결로 남긴 것: 사이드카는 외부 파일 시스템 변조에 대한 인증이 아니다(캐시 디렉토리에 쓸 수 있는 공격자는 범위 밖 — gitleaks 캐시와 같은 위협 모델) | Codex 2차, tests 97(pg 제외) |
| 2026-10-11 | D18·D19: toolbox | 사용자 결정("harness-catalog가 toolbox 지원토록 구현해라", kind는 판별자로). 선례 조사 아티팩트 2판 + Codex 검증. 레지스트리는 발견까지; 턴마다의 선택은 하네스. 스크립트 도구의 로컬 MCP 어댑터는 다음 결정(§7) | 구현은 이 행 뒤의 커밋 |
| 2026-10-11 | D18·D19 구현 완료 | core `toolbox.py`(pydantic 검증)·`check.py` 11·12·`catalog.py` search_tools/get_tool/종류별 아카이브·`archive_token` v2·git/pg 어댑터 일반화·마이그레이션 0002·MCP 도구 둘·tools 라우트. 시험 139개(pg 포함, 라이브 0001→0002 업그레이드 통합 시험 포함), pyright 0, ruff 0. Codex 설계 리뷰 21건·코드 리뷰 10건 반영. 판 0.3.0 | DESIGN §11 두 리뷰 반영 표 |
| 2026-10-11 | D20: `list_skills` 제거 | 사용자 결정("list skills는 제거하라"). 전체 응답이 카탈로그 크기에 비례하고 쓰임 셋이 전부 `search_skills`로 대체됨. 코드·시험·문서 같은 커밋 | DESIGN §11 2026-10-11 행 |
| 2026-10-11 | D21: 응답 모델 pydantic·outputSchema | 사용자 결정. 입력은 닫혀 있는데 응답은 산문뿐이던 비대칭을 닫는다. 응답 내용 동일(없는 값은 null로 실림) | DESIGN §11 2026-10-11 행 |
| 2026-10-11 | D18 보정: `tool.json` 선택 `$schema` | write-tool·`schemas/tool.schema.json`(DESIGN §11 2026-10-11 도구 저작 행). core `tool_json_schema()`, CLI `schema tool`, init이 스키마 생성 | DESIGN §11 행 |
| 2026-10-12 | D18 보정: 종료 코드 0/1/2 + 소비자 규약 | 사용자 결정. 1 = 돌았지만 부정, 2 = 도구 실패; 소비자는 종료 코드·stdout·stderr를 전부 모델의 관측으로 되돌린다(Oracle·Deep Agents 선례). 서버 코드 변경 없음 | DESIGN §11 2026-10-12 행 |
| 2026-10-12 | D18 보정 2(Codex 리뷰 `수정`): 종료 1 폐지, `outputSchema` | 결과는 선언된 스키마의 stdout JSON 객체 하나(종료 0), 0 아님 = 실행 실패. 검사 11이 두 스키마에 메타스키마·`$ref` 규칙. 소비자 규약에 상한·잘림·`not_executed`. core에 jsonschema 의존 | DESIGN §11 2026-10-12 보정 행 |

