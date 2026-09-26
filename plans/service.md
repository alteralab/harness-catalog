# service 계획: harness-catalog 레지스트리 서비스

**상태: 초안 · 작성 2026-09-26.** 이 PLAN은 `~/workspace/harness-catalog/`의 서비스 코드(`src/`·`tests/`·이미지)의 정본이다. 설계의 정본은 상위의 `DESIGN.md`(v3.3)이고 이 문서는 그것을 복제하지 않는다. 관할은 레지스트리 프로세스 하나 — 파이썬 패키지 `harness_catalog/`, 마이그레이션, 시험, 컨테이너 이미지의 빌드 정의 — 이고, 그것이 어디에 어떻게 뜨는가(`plans/distribution.md`), 카탈로그에 실리는 스킬(`plans/skills.md`), 설계의 가정을 재는 일(`plans/pilot.md`)은 관할 밖이다. 상위 `PLAN.md` §3의 공통 규약(기록 규율·식별자·설계와의 관계·교차 검증)을 그대로 따른다.

## 0. 한 장 요약

만드는 것은 프로세스 하나다. 카탈로그 git 저장소를 fetch해 인덱스를 짓고, OIDC 토큰을 검증해 MCP 도구 넷(`list_skills`·`search_skills`·`load_skill`·`get_skill_file`)을 Streamable HTTP(2026-07-28, 무세션)로 내며, 사용 기록을 PostgreSQL에 적는다. 평가 결과는 이 프로세스가 아니라 Harbor 플러그인 `packages/harbor-langfuse/`가 Langfuse에 남긴다(DESIGN v3.4). 구조는 DESIGN 그림 2의 헥사고날(포트 일곱·어댑터 일곱·Configurator)이고 언어는 Python(DESIGN §2.1 결정), 스택은 DESIGN §2.1의 표 그대로다. 이 PLAN이 더하는 것은 셋이다. 설계가 정하지 않은 구현 선택(§3 판정 원장), 짓는 순서와 단계마다의 끝(§4 — 읽기 경로 → 사실 표 → 검사·초기화·플러그인), 그리고 무엇을 어떻게 재어 끝났다고 할지(§7 검증 원장). 설계가 초안이라 남긴 것 중 이 서비스에 직접 걸리는 것은 서비스 주체의 판별 표지 하나이고(§3 D8), 그것은 파일럿 P0의 실측 뒤에만 닫힌다.

## 1. 관할과 경계

**이 PLAN이 소유하는 것.** 저장소 루트의 `src/harness_catalog/`(마이그레이션 포함)·`tests/`·`pyproject.toml`·`uv.lock`, 그리고 `Dockerfile`의 내용. 배치는 우산 §3-8의 오픈소스 공통 골격(src 레이아웃, pip 설치 가능한 패키지)이다. 이미지 태그를 어디에 올리고 compose에 어떻게 꽂는지는 `plans/distribution.md`다.

**DESIGN에서 가져와 그대로 지키는 계약.** 여기 다시 적지 않는다. 절 번호와 한 줄 요지만이다.

| 계약 | DESIGN 위치 | 요지 |
|---|---|---|
| 도구 넷의 시그니처·응답 필드·오류 | §3 도구 표 | 넷 다 `skills:read`. 응답에 `sha`(tree)·`commit`·마지막 fetch 시각. 오류 코드 다섯. 쓰기·기록 도구는 없다 — 게시는 git 호스트(§2, §5), 평가는 Langfuse(§5.1) |
| 설정값 일곱 | §2 그림 2 해설, §2.1 운영자가 아는 것 | 필수 다섯(저장소 URL·deploy key·issuer·공개 URL·PostgreSQL 접속) + 기본값 있는 둘(`USAGE_RETENTION_DAYS` 90, `FETCH_INTERVAL_SECONDS` 60). 여덟째는 없다 |
| 저장소 표지와 기동 검사 넷 | §2.1 저장소 초기화 | `.harness-catalog`의 `layout = 1`, `skills/`, 실패 사유 넷(`repo_unreachable`·`no_main_branch`·`not_a_catalog`·`unsupported_layout`·`layout_mismatch`) |
| DB 스키마 | 그림 3 + DDL + 규칙 여섯 | 업무 표 둘(`skill_index`·`usage_record`) + `index_state` + 마이그레이션 메타. DDL 문자열이 계약이다 |
| 게시 = git 워크플로 | §2 게시, §5, §5.1 ③ | 레지스트리는 `main`을 fetch·검사·인덱스만 한다. 검사 아홉(§5)은 `harness-catalog check` 하나이고 pre-commit·CI·인덱스 빌드가 같은 구현을 돈다. 되감기(`main_rewound`)는 규칙 3이 잡는다 |
| 인증·인가 | §2 인증·인가 표, 그림 4 | JWT 검증 계약(`iss`·`aud`·`exp`·`nbf` 60초·RS256/ES256·`sub`·`scope`), 401/403 챌린지 경계, 스코프↔도구, 역할 reader 하나(그룹 `skills-readers`, 서비스 주체) |
| 실패 시 동작 | §2.1 실패 시 동작 표 | PostgreSQL·push는 시간 초과+브레이커, fetch는 지수 백오프, JWKS는 캐시, DB 단절 시 메모리 사본으로 읽기 |
| 파이썬 스택 | §2.1 Python 쪽 구체 표 | `mcp` v2 + Starlette + uvicorn, PyJWT, psycopg 3 + yoyo, git·gitleaks 서브프로세스, `skills_ref`, anyio, pydantic-settings, pytest·testcontainers, uv·ruff·pyright strict. **표에 없는 것은 넣지 않는다** |

**옆 PLAN과의 접점.** distribution는 이 PLAN이 정한 이미지 이름과 환경 변수 일곱의 이름을 읽는다(§2 표). skills는 카탈로그 저장소에 PR로 게시되고 이 서비스가 병합된 것을 검사해 싣는다. pilot은 이 서비스가 뜬 뒤 가정 셋을 재고, 그 전에 D8의 표지를 준다.

## 2. 코드 배치

DESIGN §2.1이 말한 "대략 모듈 넷(app, adapters, mcp_tools, config)"을 그림 2의 노드 열아홉에 대응시킨 것이다. 구동 어댑터 셋을 `driving/`에 모은 것은 이름 정리이지 층 추가가 아니다(§3 D1).

```
(저장소 루트)
  pyproject.toml            # uv 프로젝트. 패키지 이름 harness-catalog, src 레이아웃. ruff·pyright strict·pytest 설정
  uv.lock                   # 판 고정. P1 첫 커밋에서 생성
  Dockerfile                # python:3.12-slim + git + gitleaks, 다단계. 아티팩트 하나 (배치·태그는 plans/distribution.md)
  src/harness_catalog/
    __main__.py             # uvicorn 기동. 출력 층(T201 면제 자리)
    cli.py                  # `harness-catalog init <repo-url>`(구조·CI·pre-commit·README, 멱등, 호스트별) · `check [<root>]`(종료 0/1/2) · `reindex --accept-rewind`
    config.py               # Settings(pydantic-settings, 일곱) + bootstrap(settings) -> App  [Configurator]
    migrations/             # yoyo SQL 파일, 패키지 데이터로 포함(pip 설치만으로 실행). 0001이 그림 3 DDL 그대로
    app/
      ports.py              # 요구 포트 넷 = typing.Protocol: ContentStore·FactStore·IdentityVerifier·SkillValidator
      model.py              # SkillEntry·IndexSnapshot·Principal·오류 코드 열거. 순수 데이터
      authz.py              # 인가 정책. 그림 4의 표: reader(그룹 `skills-readers` 또는 서비스 주체) -> CATALOG_READ
      catalog.py            # 카탈로그: 목록·검색·본문·파일, 인덱스 빌드(트랜잭션+메모리 사본), 구조 검사, 보존 삭제, 상태
      check.py              # 검사 아홉(§5): 저장소 구조 + 스킬마다. 인덱스 빌드와 CLI가 같은 함수를 부른다
      app.py                # App = 위 셋 + 어댑터 넷을 묶은 이름 붙은 형태. 제공 포트 = 이 객체의 함수 시그니처
    adapters/               # 피구동 어댑터 넷
      git.py                # 로컬 클론, fetch, 스킬 트리 목록, 판 읽기, 삭제 이력 질의. 쓰기 없음
      pg.py                 # psycopg 3 + pool. 인덱스 교체·검색·사용 기록·보존 삭제. 브레이커 상태
      oidc.py               # PyJWT + PyJWKClient. SDK TokenVerifier 구현
      validate.py           # skills_ref.validate + gitleaks 서브프로세스 → 판정
    driving/                # 구동 어댑터 셋
      mcp_tools.py          # MCPServer에 도구 넷 등록, 입력 스키마(pydantic), 오류 코드 → 도구 오류
      ops.py                # Starlette 라우트 /healthz /readyz
      scheduler.py          # anyio 태스크 둘: fetch 주기, 보존 삭제 24시간. 기동 1회 검사도 여기서 부른다
  tests/
    unit/                   # 앱 함수 + 가짜 어댑터(git·OIDC·validate 가짜, PG는 메모리 FactStore 가짜)
    adapters/               # pg: testcontainers PostgreSQL. git: 임시 bare 저장소. validate: 표본 스킬 둘
    http/                   # 실제 uvicorn + Dex 토큰(개발 compose)으로 401/403·도구 호출
    fixtures/               # 템플릿 구조의 시험 카탈로그, 통과·실패 스킬 표본, 시크릿 든 스킬 표본
```

의존 목록(이름만. 판은 `uv.lock`이 잡고 첫 고정값을 §9 진행 원장에 적는다):

| 이름 | 자리 | 이유(DESIGN §2.1 표) |
|---|---|---|
| `mcp` (v2) | 서버·전송·인가 골격 | 2026-07-28과 2025년 세대 동시 서빙, RFC 9728·챌린지 내장(문면) |
| `uvicorn`, `starlette` | HTTP | SDK가 Starlette 앱을 돌려준다(문면). 라우트는 둘뿐 |
| `pydantic`, `pydantic-settings` | 설정·입력 스키마·응답 모델 | SDK가 이미 의존. 우리가 직접 쓰면 중복 |
| `PyJWT[crypto]` | JWT 서명 검증 | `PyJWKClient`가 JWKS 캐시·`kid` 재조회(문면) |
| `psycopg[binary,pool]` | DB | ORM 없음. SQL 직접 |
| `yoyo-migrations` | 마이그레이션 | SQL 파일 + 가벼운 러너 |
| `skills-ref` | 스펙 검증 | 참조 구현 한 곳(DRY). 패키지명·API는 P1에서 실측(R4) |
| `anyio` | 동시성 | SDK가 쓰는 것. 블로킹 호출은 `to_thread` |
| 이미지 안 `git`, `gitleaks` | 서브프로세스 | 런타임이 아니라 바이너리. "런타임 하나" 유지 |
| 개발: `pytest`, `pytest-anyio`, `testcontainers[postgres]`, `ruff`, `pyright` | 시험·도구 | DB 대역은 실물을 보장하지 않는다 |

## 3. 판정 원장

설계가 정하지 않은 구현 선택만이다. 설계에 있는 결정은 여기 없다. 근거 등급: **실측** / **문면** / **설계 판단** / **휴리스틱**.

| # | 물음 | 판정 | 근거(등급) |
|---|---|---|---|
| D1 | 패키지·모듈 이름 | 패키지 `harness_catalog`. 하위는 `app/`·`adapters/`·`driving/`·`config.py`·`__main__.py`. DESIGN의 "모듈 넷"에서 `mcp_tools`를 `driving/`으로 넓힌 것은 구동 어댑터가 셋(MCP·운영·스케줄러)이라 한 파일에 넣으면 프로토콜·HTTP·시계가 섞이기 때문이다. 층은 그대로 셋(앱·피구동·구동) | 설계 판단. 그림 2의 노드 대응이 파일 이름으로 즉답된다 |
| D2 | 메모리 인덱스 사본의 구조와 교체 | 불변 스냅샷 하나(`IndexSnapshot`: 행 튜플 + `commit_sha` + `built_at`)를 카탈로그가 참조 하나로 쥔다. 빌드는 새 스냅샷을 다 만든 뒤 참조를 바꾼다. 읽는 쪽은 호출 시작 때 참조를 한 번 잡고 그것만 본다. 부분 갱신은 없다 | 설계 판단. DESIGN §2.1 "다음 빌드가 통째로 바꾼다"의 구현. 참조 교체는 CPython에서 원자적이고 anyio 단일 스레드 루프에서 경합이 없다(문면) |
| D3 | 클론 잠금 | 프로세스 안 `anyio.Lock` 하나. 쥐는 구간은 fetch 전체와 인덱스 빌드의 스냅샷 읽기. 레지스트리는 클론에 쓰지 않는다 | 설계 판단. DESIGN §2 "클론 하나에 잠금 하나" |
| D6 | `load_skill(id, sha)`·`get_skill_file(id, sha)`의 과거 판 해석 | `git log --format=%H main -- skills/<name>`으로 그 경로를 만진 `main` 커밋을 최신부터 걸으며 `git rev-parse <commit>:skills/<name>`이 `sha`와 같은 첫 커밋을 쓴다. 브랜치는 fetch하지 않으므로 잡히지 않는다. 상한은 그 경로의 커밋 수. tree→commit 캐시는 두지 않는다 | 설계 판단. 과거 판 요청은 재현·사고 조사용이라 드물다(DESIGN §3). 캐시는 지금 재지 않은 최적화다 |
| D7 | JWKS·JWT | 기동 시 issuer의 `.well-known/openid-configuration`에서 `jwks_uri`를 읽고 `PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)`. 검증은 `jwt.decode(algorithms=["RS256","ES256"], audience=<공개 URL>, issuer=<issuer>, leeway=60, options={"require": ["exp","sub"]})` 뒤 `scope` 존재를 따로 확인. SDK `TokenVerifier.verify_token`이 `AccessToken(scopes=…)`을 돌려준다 | 문면(PyJWT·SDK). 모르는 `kid`의 재조회는 `PyJWKClient`의 동작이고 P1 시험이 확인한다 |
| D8 | 서비스 주체 판별 표지 | **P3 착수 전까지 미정.** 판별은 순수 함수 `principal_kind(claims)` 하나에 가두고, 그 함수의 규칙은 파일럿 P0이 Dex 클라이언트 자격 증명 토큰의 실물(`sub`·`azp`·`groups`)을 기록한 뒤 정한다. DESIGN의 임시 규칙("`sub`가 등록된 client ID 집합에 있으면")은 그 집합의 출처가 필요한데 설정값은 일곱뿐이라 여덟째를 더하는 셈이 된다. 토큰 자체의 표지(`azp` 등)로 갈리면 설정 없이 닫고, 안 갈리면 DESIGN §11에 "설정값 여덟째"를 변경 요청으로 올린다. 이 PLAN이 조용히 정하지 않는다 | 설계 판단 + 미실측. P1·P2는 이 판별이 필요 없다(읽기는 인증된 전부). 걸리는 것은 서비스 주체를 그룹 없이 reader로 세우는 한 줄뿐이다(v3.4에서 서비스 주체는 읽기 전용) |
| D9 | 시크릿 스캔 호출 | `check`가 `gitleaks dir <skill-dir> --no-banner --exit-code 2 --report-format json --report-path -`. 종료 0이면 통과, 2면 검출(파일·룰을 출력에), 그 밖(바이너리 없음·크래시)은 검사기 실패(종료 코드 2, fail-closed). 바이너리 파일의 취급은 P3에서 실측해 적는다 | 문면(gitleaks CLI). fail-closed는 DESIGN §5 검사기 운영 |
| D11 | 스케줄러 | Starlette lifespan 안에서 anyio 태스크 그룹 하나에 루프 둘. fetch 루프는 `FETCH_INTERVAL_SECONDS`마다 `catalog.refresh()`를 부르고 실패 시 지수 백오프(2배, 상한 = 간격의 16배)로 늘렸다가 성공하면 되돌린다. 보존 루프는 24시간마다 `catalog.purge_usage()`. 시험은 시계 없이 두 함수를 직접 부른다 | 설계 판단. DESIGN §2.1 실패 표 "fetch는 지수 백오프". 상한 16배는 휴리스틱 |
| D12 | 마이그레이션 시점 | `bootstrap`이 기동 직후 마이그레이션 태스크 하나를 따로 띄운다. 이 태스크는 yoyo 적용을 시도하고 실패하면 자기 백오프(5초에서 2배, 상한 5분)로 다시 한다. fetch 루프와 무관하다. DB 경로(인덱스 트랜잭션·사용 기록·검색 순위)는 마이그레이션이 "적용됨"이 되기 전에는 열리지 않고 그동안은 `degraded: db_unavailable`이다. 기동은 막지 않는다(준비됨 조건이 아니다) | 설계 판단. DESIGN §2.1 "DB 연결은 준비됨의 조건이 아니다"를 마이그레이션에도 적용. fetch 주기와의 결합은 Codex 리뷰(2026-09-26)가 잡아 분리했다. 백오프 수치는 휴리스틱 |
| D13 | 브레이커와 degraded 신호 | PostgreSQL 호출에 시간 초과(문장 5초)와 브레이커(연속 실패 3회 → 30초 열림), fetch에는 지수 백오프. 브레이커는 순수 상태 기계 하나를 `pg.py`가 든다. 열림·닫힘과 되감기 검출이 `degraded` 목록(`db_unavailable`·`main_rewound`)이 되고 **`/readyz` 본문에만** 실린다(DESIGN §2.1). 도구 응답에는 DESIGN §3이 정한 필드만 있다 | 설계 판단. 수치는 휴리스틱. 라이브러리를 들이지 않는 이유: 상태 기계가 열 줄이고 DESIGN 표에 없다 |
| D14 | 오류 어휘 | 인가 실패는 HTTP 401/403(SDK 챌린지). 도구 안의 실패는 MCP 도구 오류 결과에 `{code, detail}`이고 **코드 여섯은 DESIGN §3이 소유한다**. `check`의 위반은 도구 오류가 아니라 CLI 출력(항목 번호·경로·사유 한 줄씩)과 종료 코드다 | 설계 판단. 공개 코드는 계약이라 DESIGN 소유(우산 §1 경계 규칙 ⑵) |
| D15 | DB 접속 | `psycopg_pool.AsyncConnectionPool` 최소 1·최대 4, 문장 시간 초과 5초. 트랜잭션은 인덱스 교체 하나만 명시적이고 나머지는 자동 커밋 | 휴리스틱. 하루 수백 요청(DESIGN 추정)에 연결 넷이면 남는다 |
| D16 | 시험 구성 | `tests/unit`은 어댑터 전부 가짜(FactStore는 메모리 dict). `tests/adapters/pg`는 testcontainers 실물. `tests/adapters/git`은 임시 bare 저장소 + 클론 둘. `tests/http`는 실제 uvicorn 프로세스 + 개발 compose의 Dex 토큰. 마지막 것만 외부 프로세스가 필요하고 표식으로 갈라 CI에서는 P4 뒤에 켠다 | 설계 판단. DESIGN §2.1 "DB 대역은 실물을 보장하지 않는다", "git·OIDC 어댑터는 가짜로" |

## 4. 단계

각 단계의 끝은 상위 `PLAN.md` §4의 완료 조건을 그대로 옮긴 것이다.

### P1. 읽기 경로 (DB 없이 동작)

0. `src/` 첫 커밋: `pyproject.toml`·`uv.lock`·패키지 뼈대. 규약 선언은 새로 없다(`lang/python`은 이미 선언됨). 이 커밋에서 `altera-ruff`·`altera-ast-grep`이 처음으로 파일을 검사하며 돈다 — 그 출력과 `selftest.sh --census src/ tests/` 결과를 §9 진행 원장에 적고, 검출이 있으면 참·거짓을 갈라 기록한다.
1. `config.py`: 일곱 설정값의 `Settings`. 필수 다섯이 비면 기동 실패(종료 코드 ≠ 0, 어느 것이 비었는지 표준 오류에).
2. `app/ports.py`·`app/model.py`: 요구 포트 넷의 Protocol, 스냅샷·주체·오류 코드.
3. `adapters/git.py`: clone·fetch(`origin/main`)·`skills/*/SKILL.md` 트리 열거(각 디렉토리의 tree SHA와 그 판을 넣은 최근 커밋)·파일 읽기(`git show`)·삭제 이력(`git log --diff-filter=D --name-only -- 'skills/*/SKILL.md'`).
4. `adapters/validate.py`: `skills_ref` 호출부. 패키지·함수 시그니처를 실측해 R4를 닫는다. 통과·실패 표본 둘.
5. `app/catalog.py`: 구조 검사 넷 → 인덱스 빌드(메모리 스냅샷만) → 목록·검색(메모리 부분 일치, 순위 없음; 항목은 DESIGN §3의 최소 필드, `model`·`harness` 인자 시 평가 한 행)·본문·파일(경로 이탈·심볼릭 링크·1 MB). 사용 기록은 이 단계에서 버린다(FactStore가 없으면 degraded).
6. `adapters/oidc.py`: D7. `app/authz.py`: 스코프↔도구, 그룹, 주체 종류(D8 미정 부분은 "사람"으로 고정하고 표식 남김 없이 P3에서 함수 본문을 채운다).
7. `driving/mcp_tools.py`: 읽기 도구 넷 등록, `AuthSettings`(issuer·공개 URL·`required_scopes=["skills:read"]`), `streamable_http_app()`. `driving/ops.py`: `/healthz`·`/readyz`(503 사유 넷, 200 + `degraded`). `driving/scheduler.py`: 기동 1회 + fetch 루프(D11). `config.bootstrap`·`__main__`.
8. `Dockerfile` 초판(다단계, git·gitleaks 포함) — 이미지가 P1 끝에 빌드된다. 이미지 이름은 `harness-catalog`, 태그는 git 짧은 SHA.
9. 시험: unit(가짜 어댑터로 구조 검사·인덱스·검색·인가 행렬 읽기 부분), adapters/git, adapters/validate, http(개발 compose의 Dex로 토큰을 받아 HTTP 경유 호출).

**끝:** 템플릿 구조의 시험 저장소를 가리켜 기동하면 `/readyz` 200이고, Dex가 낸 사람 토큰으로 SDK 인메모리 클라이언트가 아닌 **HTTP 경유** 읽기 도구 넷 호출이 전부 성공하며, 토큰 없음·잘못된 aud·만료 셋이 각각 401로 거부된다.

### P2. 사실 표

1. `src/harness_catalog/migrations/0001_schema.sql`: 그림 3 DDL 문자열 그대로(확장·함수·표 넷·생성 열·인덱스·CHECK). 러너는 yoyo, 적용 시점은 D12.
2. `adapters/pg.py`: 인덱스 교체 트랜잭션(`index_state` `FOR UPDATE` → `git merge-base --is-ancestor`는 git 어댑터가 판정한 결과를 인수로 받는다 → `DELETE`+`INSERT`), `tsvector`+`pg_trgm` 검색, 사용 기록 한 건, 보존 삭제(`%(retention_days)s`). 브레이커·시간 초과 D13·D15.
3. `app/catalog.py` 확장: 빌드가 DB 트랜잭션과 메모리 스냅샷을 같은 행 집합으로 함께 갱신(순서: DB 커밋 성공 → 참조 교체. DB 실패 → 참조만 교체하고 degraded). 검색은 DB가 살아 있으면 DB 순위, 아니면 메모리 부분 일치. `list_skills`에 최근 평가 결합.
4. 스케줄러에 보존 루프 24시간 추가. 기동 시 보존 삭제 1회.
5. 패키지 데이터: `pyproject.toml`에 `src/harness_catalog/migrations/*.sql`을 wheel·sdist에 포함하는 규칙을 적고, 러너는 `importlib.resources.files("harness_catalog") / "migrations"`로 경로를 얻는다(작업 트리 상대 경로를 쓰지 않는다). V21이 설치본에서 이를 확인한다.
6. 시험: adapters/pg(testcontainers)에서 DDL 적용, 세대 검사(낡은 커밋 빌드가 아무것도 바꾸지 않음), 보존 삭제 멱등(두 번 돌려 같은 결과, 경계 일수의 행이 정확히 갈림), 검색 문법. unit에서 DB 단절 시 degraded 읽기.

**끝:** testcontainers PostgreSQL에서 그림 3 DDL이 그대로 적용되고, 낡은 커밋의 빌드가 최신 인덱스를 되돌리지 않는 시험과 보존 삭제 멱등 시험이 통과하며, DB를 끊어도 `/readyz` 200 + `degraded`이고 읽기 넷이 답한다.

### P3. 검사 명령·초기화 명령·Langfuse 플러그인

0. 착수 조건: D8의 표지가 `plans/pilot.md`의 실측 기록으로 정해져 있다. 없으면 서비스 주체를 reader로 세우는 한 줄만 뒤로 두고 나머지를 먼저 한다.
1. `app/check.py`: DESIGN §5의 검사 아홉을 순수 함수로. 입력은 검사할 트리(작업 트리 또는 커밋)·기준 커밋·git 어댑터(삭제 이력, 기준 커밋의 트리), 출력은 위반 목록(항목 번호·경로·사유). 기준 커밋이 없으면 5·9를 건너뛰고 그 사실을 출력에 적는다. P1의 인덱스 빌드가 이 함수를 부르도록 바꾼다(스킬 실패 → 인덱스 제외, 구조 실패 → 빌드 실패).
2. `cli.py check [<root>] [--base <commit>]`: 1을 CLI로. `--base`는 항목 5·9의 기준 커밋(DESIGN §2.1: pre-commit은 HEAD, PR CI는 merge-base, main CI는 직전 커밋, 인덱스 빌드는 `index_state.commit_sha`). 얕은 클론이면 항목 5는 종료 2. 종료 0 통과 / 1 위반 / 2 검사기 실패(gitleaks 없음·얕은 클론 등). pre-commit 훅과 CI 워크플로가 이 명령을 부른다(`examples/catalog-template/`의 훅·워크플로 파일이 그렇게 적혀 있다).
3. `cli.py init <repo-url>`: 운영자 git 자격으로 clone → URL에서 호스트 판별(GitHub·GitLab) → 패키지 데이터 `catalog-template/`에서 `.harness-catalog`·`skills/.gitkeep`·README·pre-commit 설정·그 호스트의 CI 워크플로를 없는 것만 쓰고 → 커밋·push. 표지가 있는데 `layout`이 다르면 멈춘다(종료 1). 두 번 돌리면 변경 0.
4. `cli.py reindex --accept-rewind`: 규칙 3의 `main_rewound` 뒤 운영자가 명시적으로 인덱스를 새 `main`으로 다시 짓는 명령.
6. `app/authz.py` 완성: 주체 셋(reader·그룹 없음·서비스) × 도구 넷 × 스코프.
7. `packages/harbor-langfuse/`: 별도 배포물(`pyproject.toml`, `src/harbor_langfuse/plugin.py`), 서비스 이미지에 들어가지 않는다. Harbor `BaseJobPlugin` 구현. `on_job_start`에서 잡의 태스크 경로에서 스킬 이름과 `evals/` 케이스를 읽어 Langfuse dataset `<catalog>/<skill>`과 item(케이스, `input` = `instruction.md`)을 있으면 재사용·없으면 생성하고, dataset run(`run_name` = Harbor 잡 이름, `metadata` = `skill`·`sha`(주입한 스킬 원천의 ref)·`scenario_sha`(`evals/` tree)·`model`·`harness`(agent 이름)·`baseline`(스킬 원천 없음))을 연다. `on_job_end`에서 트라이얼마다 trace(입력 instruction, 출력 검증기 stdout 요약, 메타데이터 `trial_uri`·토큰·비용)와 run item, score `passed`(BOOLEAN, reward ≥ 1)를 만든다. 키는 `LANGFUSE_PUBLIC_KEY`·`LANGFUSE_SECRET_KEY`·`LANGFUSE_HOST` 환경 변수. Harbor의 `packages/harbor-langsmith/src/harbor_langsmith/plugin.py`(852줄, `_create_root_run`·`_create_feedback`·`_request` 재시도)를 본뜨되 ATIF 스텝은 그쪽도 올리지 않으므로 올리지 않는다. Langfuse SDK v3의 저수준 dataset run·score API 이름은 pilot Q14(e)가 실측한 뒤 쓴다.
8. 시험: unit에서 검사 아홉 각각의 위반 표본(구조 결손 다섯, 스킬 위반 넷)과 통과 표본; adapters/git에서 임시 저장소에 `init`을 두 번 돌려 두 번째가 변경 0, GitHub·GitLab URL로 워크플로 파일이 갈리는지; 같은 표본을 CLI·인덱스 빌드 두 경로로 돌려 판정이 같은지; `main`을 되감은 클론으로 fetch해 `main_rewound`; 플러그인은 Harbor `JobResult` 표본으로 Langfuse 호출을 기록하는 가짜 클라이언트에 대해; http에서 403 실물.

**끝:** §5의 검사 아홉 각각을 위반한 표본이 `check`에서 항목 번호와 함께 종료 1로 거부되고 인덱스 빌드에서 같은 스킬이 빠지며, `init`이 빈 저장소를 표지·`skills/`·CI·pre-commit·README가 있는 저장소로 만들고 두 번째 실행에서 변경이 없으며, PR로 병합한 스킬이 `FETCH_INTERVAL_SECONDS` 두 주기 안에 `search_skills`에 나온다.

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
| V2 | 빈 카탈로그 준비됨 | `init`으로 만든 저장소(스킬 0) | `/readyz` 200, `list_skills` 빈 목록, 마지막 fetch 시각 있음 | 대기 |
| V3 | 401 챌린지 | HTTP로 토큰 없음·서명 불일치·`aud` 다름·만료·`iss` 다름 다섯 | 다섯 전부 401 + `WWW-Authenticate: Bearer resource_metadata=… scope="skills:read"`, RFC 9728 메타데이터 GET이 200 | 대기 |
| V4 | 403 두 종 | `skills:read` 없는 토큰(`openid`만)으로 `list_skills`; `skills:read`는 있으나 그룹 없음 | 전자 403 + `error="insufficient_scope"` 챌린지, 후자 403 + 챌린지 없음 + 본문 `not_a_member` | 대기 |
| V5 | 인가 행렬 | 주체 셋(`skills-readers` 사람·그룹 없는 사람·서비스) × 도구 넷 = 12칸을 `authz.decide` 단위 시험으로 | 12칸 전부 DESIGN 그림 4 표와 일치. 그룹 없음은 넷 전부 `not_a_member` | 대기(서비스 주체 칸은 D8 뒤) |
| V6 | 인덱스 세대 검사 | testcontainers: 커밋 B(자손)로 빌드 뒤 커밋 A(조상)로 빌드 | 두 번째 빌드 뒤 `index_state.commit_sha`가 B이고 행 집합이 B의 것 | 대기 |
| V7 | 보존 삭제 | 경계 전후 1초의 행 둘을 넣고 `USAGE_RETENTION_DAYS`를 바꿔 두 번 실행 | 경계 밖 행만 지워지고 두 번째 실행이 0행. 설정값 변경이 삭제 경계를 옮긴다 | 대기 |
| V8 | degraded 읽기 | DB 컨테이너를 멈춘 채 도구 넷 호출과 `/readyz` | 넷 전부 응답(검색은 부분 일치), `/readyz` 200 + `degraded: ["db_unavailable"]`. 도구 응답에 `degraded` 필드가 없다 | 대기 |
| V9 | 검사 아홉 | §5의 아홉 항목 각각을 위반한 표본 저장소·스킬 | `check`가 항목 번호와 경로·사유를 출력하며 종료 1. 검사기(gitleaks)를 치우면 종료 2. 통과 표본은 종료 0 | 대기 |
| V10 | 병합 반영 | 시험 저장소에 PR을 병합 | 우산 V3의 허용오차(`FETCH_INTERVAL_SECONDS` 두 주기) 안에 `search_skills`에 나오고 `sha`가 병합 커밋의 tree와 같다 | 대기 |
| V11 | `init` 멱등·호스트별 | 빈 저장소(GitHub URL, GitLab URL 각각)에 `init` 두 번 | 첫 실행 뒤 표지·`skills/.gitkeep`·README·pre-commit 설정·그 호스트의 워크플로 파일이 있고, 두 번째 실행은 변경 0. `layout = 2` 표지가 있는 저장소에서는 종료 1 | 대기 |
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
