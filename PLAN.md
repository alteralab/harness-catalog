# harness-catalog 계획 (우산)

**상태: 초안 · 작성 2026-09-26.** 이 PLAN은 `~/workspace/harness-catalog/`의 정본이다. 설계의 정본은 같은 디렉토리의 `DESIGN.md`(v3.2, 단일 팀)이고 **이 PLAN은 설계를 복제하지 않는다.** 설계가 "무엇을·왜"를 적었으니 PLAN은 "누가·어떤 순서로·언제 끝났다고 하는가"만 적는다. 구성 요소마다 PLAN이 하나씩 있고 이 문서는 그 넷의 경계·순서·공통 규약·시스템 검증만 관할한다.

## 0. 한 장 요약

만드는 것은 넷이다(DESIGN §2 "새로 만드는 것"). 스킬 저장소 하나(템플릿으로 세운다), PostgreSQL 하나, harness-catalog 서비스 하나(Python, MCP 도구 여섯), CI 검증 워크플로 하나. 운영 부품으로 Dex(인가 서버)가 compose에 함께 뜬다. 소비자는 둘(사람의 세션, 루프)이고 루프 자체는 이 저장소의 범위 밖이다. 설계는 초안이고 §9의 열린 질문 아홉이 남아 있다. 첫째(소유 팀·언어)는 사용자 결정(§6-1)이고, 그래서 첫 단계는 코드가 아니라 **나머지 여덟 중 서비스 없이 답할 수 있는 다섯을 실측으로 닫는 것**이며, 나머지 셋은 파일럿에서 잰다.

```
harness-catalog/                  # 코드 저장소 하나. 카탈로그(스킬) 저장소는 별개다. 배치는 오픈소스 공통 골격(§3-8)
  README.md  LICENSE              # LICENSE는 §6 미결 6
  DESIGN.md                    # 설계 정본 (v3.2). 설계 변경은 여기 §11에 행을 더한다
  PLAN.md                         # 이 문서 — 경계·순서·공통 규약·시스템 검증
  plans/                          # 구성 요소 계획 넷: service.md · distribution.md · skills.md · pilot.md
  REVIEW.md, altera-rules.yml, ruff.toml   # 규약 설치 (2026-09-26, common·lang/python·review)
  pyproject.toml  uv.lock  Dockerfile      # 파이썬 패키지(pip 설치)와 이미지 하나 — plans/service.md
  src/harness_catalog/            #   app · adapters · driving(mcp_tools·ops·scheduler) · config · migrations(패키지 데이터)
  tests/
  docker-compose.yml  docker-compose.dev.yml  .env.example   # 빠른 시작: registry + postgres + dex — plans/distribution.md
  docker/                         #   compose 지원 파일: dex/config.yaml(정적 사용자), postgres/init.sql
  examples/synology-ldap/         #   우리 팀 변형: Dex LDAP 커넥터 설정과 compose 오버레이
  examples/catalog-template/      #   카탈로그 저장소 템플릿(.harness-catalog, skills/, CI, README)
  docs/                           #   설치·설정값 일곱·운영자 가이드·카탈로그 저장소 신설
  scripts/                        #   운영 셸 스크립트. 첫 파일과 함께 lang/bash 선언
  skills/                         # 카탈로그에 실리는 절차 스킬 pin-skill·new-skill — plans/skills.md
  research/                       # 실측 기록 rN과 측정 도구 tools/ — plans/pilot.md
```

## 1. 구성 요소와 정본 계획

| 구성 요소 | 정체 | 정본 계획 | 소유 | 완료의 뜻 |
|---|---|---|---|---|
| **service** | MCP 서버(Streamable HTTP 2026-07-28 무세션), 헥사고날(포트 여덟·어댑터 일곱·Configurator), 도구 여섯, 인덱스·사용 기록·평가 결과 | `plans/service.md` | 플랫폼 팀(§6 미결 1) | 도구 여섯이 실제 Dex 토큰으로 호출되고 검증 원장 전 항목 통과 |
| **distribution** | 이미지·루트 compose(빠른 시작: 서비스·PostgreSQL·Dex 정적 사용자), `examples/synology-ldap/`(우리 팀의 LDAP 연합 변형), 리버스 프록시 뒤 배치, `examples/catalog-template/`과 CI 워크플로, `docs/`(설치·설정·운영자 가이드) | `plans/distribution.md` | 플랫폼 팀 | 새 VM에서 `.env`만 채운 compose 한 번으로 `/readyz` 200, 템플릿 저장소의 CI 초록 |
| **skills** | `pin-skill`(내려받기 절차)·`new-skill`(뼈대와 팀 규약)·카탈로그 README | `plans/skills.md` | 팀(스킬 저자) | 두 스킬이 카탈로그에 게시되고 파일럿 하네스 셋에서 지시대로 동작 |
| **pilot** | §9 열린 질문 아홉 중 사용자 결정(첫째, §6-1)을 뺀 여덟과 **가정:** 태그 넷의 실측, 파일럿 하네스 셋(Claude Code·Codex·Cursor) 연결 | `plans/pilot.md` | 사용자 + 에이전트 | 여덟 질문 전부에 기록된 답(답·기각·범위 제외 중 하나) |

경계 규칙 셋. ⑴ 한 커밋은 한 구성 요소만 만진다(루트 PLAN·DESIGN 커밋은 예외). ⑵ 구성 요소 사이의 계약은 DESIGN이 소유한다 — 도구 여섯의 시그니처(§3), 설정값 일곱(필수 다섯 + 기본값 있는 둘: 보존 일수·fetch 간격, §2), 저장소 표지 `.harness-catalog`(§2.1), `PINNED` 형식(§4). 어느 PLAN도 그 계약을 다시 적지 않고 DESIGN의 절을 가리킨다. ⑶ 계약을 바꾸는 일은 코드 변경이 아니라 설계 변경이라 DESIGN §11에 행을 먼저 더하고 그다음 해당 PLAN의 판정 원장에 적는다.

## 2. 범위

**안.** DESIGN v3.2 = v3.0 배포 형태(compose 한 대) + 단일 팀 + 도구 여섯(`record_eval` 포함) + 사람의 내려받기(pin) + 평가 결과 표. 구현 언어 Python(§2.1 결정). 인가 서버는 Dex로 시작(§2 신원 제공자 표).

**밖.** 루프(우리가 만드는 무인 에이전트)는 카탈로그의 소비자이지 이 저장소의 산출물이 아니다. 루프 쪽 다섯 장치(트리거·정지·상태·검증·예산)와 루프 쪽 서킷 브레이커(§2.1 실패 표 마지막 행)는 루프 저장소가 짓는다. Helm 차트·백업 크론·벡터 검색·멀티 팀·toolbox·프롬프트 카탈로그는 §7의 "뺀 것"이고 이 계획에 단계가 없다(§7 불채택 표).

## 3. 공통 규약 (네 PLAN이 함께 지키는 것)

1. **기록 규율(REVIEW.md V-REC-1).** 판정은 현재 상태의 진단만 적는다. 재심 조건·트리거·이연 시점을 미리 등록하지 않는다. 기각에는 "왜 지금 아닌가"를 붙인다. 근거의 등급을 밝힌다 — **실측**(이 프로젝트에서 직접 돌린 것), **문면**(벤더·스펙 문서), **설계 판단**(DESIGN이 내린 결정), **휴리스틱**(재지 않은 추정). 완료 조건은 전수 판정형으로 적는다(건수 목표 금지).
2. **식별자.** 각 PLAN의 판정은 `D1…`, 검증은 `V1…`, 실측 기록은 `r1…`이고 PLAN 안에서만 유일하다. 다른 PLAN의 것을 가리킬 때는 `plans/service D3`처럼 경로를 붙인다.
3. **설계와의 관계.** DESIGN에 이미 있는 결정은 PLAN의 판정 원장에 다시 올리지 않는다. PLAN의 판정은 "설계가 정하지 않은 구현·운영 선택"과 "실측이 설계를 뒤집은 것"만이다. 후자는 DESIGN §11 행이 먼저다.
4. **진행 상태.** 각 PLAN의 진행 원장(마지막 절)이 정본이고, 이 우산의 §11은 단계 완료만 적는다.
5. **규칙 게이트.** altera-rules `common`·`lang/python`·`review`가 설치되어 있고 `altera-ruff`(`ruff.toml`이 base를 extend)·`altera-ast-grep` 훅이 걸려 있다(2026-09-26). 파이썬 게이트 둘은 파이썬 소스가 0이라 아직 한 파일도 검사한 적이 없고, `src/`의 첫 파이썬 커밋이 첫 완주다(C-GATE-1). `scripts/`의 첫 셸 스크립트에서 `lang/bash`를, `skills/`의 첫 SKILL.md에서 `purpose/agent-skill`을 선언한다. 선언마다 그 축의 게이트를 한 번 완주시킨다.
6. **교차 검증.** 판정 원장에 행을 더하거나 단계를 완료로 올리기 전에 Codex 독립 리뷰를 한 번 받는다(DESIGN이 여섯 차례 그렇게 했다). 발견은 반영·기각을 사유와 함께 해당 PLAN 진행 원장에 적는다.
7. **비밀.** deploy key·클라이언트 시크릿·DB 접속값은 저장소에 없다. compose는 `.env`를 읽고 `.env`는 gitignore다. 예시는 `.env.example`.
8. **배치는 오픈소스 공통 골격.** 이 저장소는 어디서든 설치되는 패키지로 만든다(사용자 결정 2026-09-26, DESIGN §11). 저장소 자체는 비공개(`alteralab` 다른 저장소와 같다)로 시작하고 공개 여부는 별도 결정이다. 골격을 따르는 이유는 공개가 아니라 설치 가능성이다. 그래서 소스 배치는 설계가 인용한 오픈소스 여섯(Dex·Langfuse·MCP registry·Gitea·DataHub·Polaris, 2026-09-26 `gh api` 실측)의 공통 골격을 따른다 — compose·Dockerfile은 루트, 파이썬 패키지는 `src/`, compose 지원 파일은 `docker/`, 예시 설정은 `examples/`, 문서는 `docs/`, 스크립트는 `scripts/`, Helm은 `helm/`(지금 없음). 계획 문서는 `plans/`에 모아 소스 배치에 종속시키지 않는다(REVIEW.md V-REC-1의 적용 경로 `plans/**`와 같다). 우리 팀의 Synology LDAP 변형은 `examples/synology-ldap/`이고 기본 compose는 Dex 정적 사용자로 어느 머신에서나 뜬다.

## 4. 단계 (순서가 곧 의존이다)

| 단계 | 정본 계획 | 내용 | 완료 조건 (전수 판정형) |
|---|---|---|---|
| **P0 착수 전 닫기** | pilot P0 · distribution P0 + §6 | §9 아홉 중 첫째(소유 팀·언어)는 §6-1이고, 나머지 여덟 중 서비스 없이 답할 수 있는 다섯: Synology SSO Server 능력, Dex+LDAP 실측 둘(장치 흐름·클라이언트 자격 증명 `sub`), 파일럿 하네스 셋의 MCP 개정판·RFC 9728·PKCE·장치 인가·클라이언트 등록 방식, 심볼릭 링크 단일 로드, 서비스 주체 표지. Dex 실측에는 개발 compose가 필요하므로 distribution P0(PostgreSQL+Dex 개발 compose, LDAP 스키마를 `ldapsearch`로 먼저 실측해 커넥터에 반영)이 P0 안에 있다. 그리고 §6의 사용자 결정 | 다섯 질문마다 `research/rN`에 실측 기록이 있고 DESIGN §9의 해당 항목이 답·기각·범위 제외 중 하나로 표시됐다. §6의 미결이 0이다 |
| **P1 읽기 경로** | service P1 · distribution P1 | Configurator, 포트(Protocol), git 어댑터(clone·fetch·tree SHA), 검증 어댑터(validate), 기동 시 구조 검사 넷, 메모리 인덱스, 읽기 도구 넷, OIDC 어댑터(PyJWT+JWKS), `/healthz`·`/readyz`. DB 없이 동작(설계상 DB는 준비됨 조건이 아니다). distribution P1은 시험용 토큰 취득 절차(`scripts/dev-token.sh`: PKCE + `resource`, 클라이언트 자격 증명)와 Dex 설정의 LDAP 확정판 | 템플릿 구조의 시험 저장소를 가리켜 기동하면 `/readyz` 200이고, Dex가 낸 사람 토큰으로 SDK 인메모리 클라이언트가 아닌 **HTTP 경유** 읽기 도구 넷 호출이 전부 성공하며, 토큰 없음·잘못된 aud·만료 셋이 각각 401로 거부된다 |
| **P2 사실 표** | service P2 | 마이그레이션(yoyo, 그림 3 DDL 그대로), PostgreSQL 어댑터, 인덱스 트랜잭션(규칙 3, `index_state` FOR UPDATE·자손 검사), 사용 기록, 스케줄러(기동 1회 · fetch 간격 `FETCH_INTERVAL_SECONDS` 기본 60초 · 보존 삭제 24시간 고정), 보존 삭제, DB 단절 시 degraded | testcontainers PostgreSQL에서 그림 3 DDL이 그대로 적용되고, 낡은 커밋의 빌드가 최신 인덱스를 되돌리지 않는 시험과 보존 삭제 멱등 시험이 통과하며, DB를 끊어도 `/readyz` 200 + `degraded`이고 읽기 넷이 답한다 |
| **P3 쓰기 경로** | service P3 | `publish_skill`(검사 다섯, 임시 작업 트리, 사용자 명의 커밋, deploy key push, non-fast-forward 재시도 3회, tree SHA 멱등, `name_taken` git 질의, `replaced-by` 연쇄 검사, `retire`), `record_eval`(검증 넷, `run_id` 멱등, `scenario_sha` 서버 산출), 인가 정책(주체 종류·스코프·그룹) | §5의 검사 다섯 각각을 위반한 요청이 설계가 정한 오류(`name_taken`·`conflict`·403 `not_a_member`·validate 실패·시크릿 검출)로 거부되고, 통과한 게시가 push 직후 `search_skills`에 나오며, 같은 요청을 두 번 보내면 커밋이 하나다 |
| **P4 카탈로그 스킬 작성** | skills P1 | `pin-skill`·`new-skill` 작성과 로컬 검증, 팀 규약(종료 코드 2/3/4, PEP 723 + `uv run --script`, `metadata.requires-tools`, evals 최소 예시)을 `new-skill`의 `references/conventions.md`에, README 사용자 안내 절 문장. 게시는 아직이다(P5) | 두 스킬이 `skills-ref validate`를 통과하고 각자 양성·음성 evals 한 쌍이 있으며 `purpose/agent-skill` 게이트가 SKILL.md 둘을 검사하며 한 번 돌았다 |
| **P5 배포·첫 카탈로그 저장소·게시** | distribution P2 · P3 · skills P2 | 이미지(다단계, git+gitleaks, CI가 한 번 빌드해 커밋 SHA 태그·digest 발행), 루트 compose(빠른 시작)와 `examples/synology-ldap/` 오버레이(Dex↔Synology LDAP, `skills` 그룹), 정적 클라이언트(하네스 셋 + CI 러너), 리버스 프록시 뒤 공개 URL, `examples/catalog-template/` 완성(표지·`skills/.gitkeep`·CI github/gitlab·README 체크리스트), `docs/` 초판, **첫 카탈로그 저장소 신설**(P4의 두 스킬을 첫 커밋에 넣는다), 그 뒤 두 스킬을 `publish_skill`로 게시해 `list_skills`에 보이게 한다 | 새 VM에서 `.env`만 채우고 `docker compose up`으로 셋이 뜨고 `/readyz` 200, 템플릿 복사본 저장소의 CI가 두 스킬로 초록, 브랜치 보호·deploy key 체크리스트 전 항목 확인, 두 스킬이 `list_skills`에 보인다 |
| **P6 파일럿** | pilot P1 | §9의 나머지: 가정 셋(매 반복 검색 비용, 트라이그램 한국어 검색, 부하)과 하네스 몫 둘(`load_skill` 본문 잔존, 이름순 목록 한계), `pin-skill` 준수. 사용자 하나·루프 없이 세션 기반 측정 | §9 아홉 항목 전부에 기록된 답(첫째는 §6-1의 결정). 파일럿 하네스 셋에서 `pin-skill` 지시대로 임시 디렉토리→대조→이름 바꾸기가 관찰됐다. 설계를 뒤집은 것은 DESIGN §11 행으로 |

**v3.0 완료** = P0~P6 완료 조건 전부 + §9 시스템 검증 전 항목 통과. 그 뒤의 일(순위, 폐기 후보, 백업, Helm)은 이 PLAN에 단계가 없고 §7의 기각 사유가 현재 상태다.

병렬 가능한 것: P1의 service와 distribution은 함께 간다. P4의 스킬 작성은 P1 뒤 언제든 시작할 수 있고(도구 계약은 DESIGN §3에 있다), 게시(P5)만 P3 뒤다. P0의 하네스 실측과 Dex 실측은 서로 독립이다.

## 5. 설계에서 이미 정해진 것 (다시 묻지 않는다)

DESIGN §11의 사용자 결정 전부. 그중 구현에 직접 걸리는 것만 적는다 — 이름 `harness-catalog`, 단일 팀·경로 `skills/<name>/`·그룹 `skills`, Python, MCP 2026-07-28 무세션, PostgreSQL 컨테이너(SQLite 아님), Dex로 시작, 백업 크론 없음, 보존 일수 설정값(기본 90)·검색어 저장, `record_eval` 포함, toolbox 없음, 저장소 템플릿은 이 저장소의 `examples/catalog-template/`, 서비스 주체는 읽기 + `record_eval`. 이 목록을 뒤집는 것은 새 실측이 있을 때 DESIGN §11에 행을 더하는 일이지 PLAN 판정이 아니다.

## 6. 사용자 결정 미결 (P0에서 닫는다)

| # | 물음 | 왜 사용자만 답할 수 있는가 | 상태 |
|---|---|---|---|
| 1 | 레지스트리의 소유 팀과 운영 호스트. compose를 어느 VM(또는 mini)에 올리는가 | 조직·기계의 사실 | **결정(2026-09-26)**: 소유는 GitHub org `alteralab`, 운영 호스트는 `mini.altera.lab`. 개발 중에는 로컬(맥북)에서 compose를 띄워 시험한다(distribution P0·P1의 개발 compose가 그 자리다) |
| 2 | git 호스트. 카탈로그 저장소와 이 코드 저장소를 GitHub(`alteralab` org, chronicle 선례)에 두는가. CI 워크플로 파일은 그 호스트 것만 먼저 쓴다 | 조직의 저장소 정책 | **결정(2026-09-26)**: GitHub `alteralab`(1번에서 따라옴). 코드 저장소 `alteralab/harness-catalog`, 카탈로그 저장소는 이름 미정. CI는 GitHub Actions 파일을 먼저 돌리고 GitLab 파일은 작성만(distribution D13). 브랜치 흐름은 §6-7 |
| 3 | 공개 URL과 TLS 종단. 레지스트리 canonical URI(토큰 audience)와 Dex issuer URL이 여기서 정해진다. 리버스 프록시의 "사내 표준"이 무엇인가 | 네트워크·도메인의 사실 | **결정(2026-09-26)**: Tailscale. mini의 `tailscale serve`가 TLS를 끊고 경로로 나눈다. 레지스트리 `https://mini.tail2f9fe3.ts.net/mcp`, Dex issuer `https://mini.tail2f9fe3.ts.net/dex`(tailnet 이름은 2026-09-26 `tailscale status` 실측). 개발 중 로컬은 `http://localhost` 그대로 |
| 4 | 인가 서버. P0의 SSO Server 실측 결과에 따라 Dex를 유지할지 SSO Server로 바꿀지 | 실측 뒤의 선택 | **결정(2026-09-26)**: Dex. pilot Q1(SSO Server 능력)은 기록용 실측으로만 남고 결정에 걸리지 않는다 |
| 5 | 파일럿 사용자 범위. 사용자 하나로 시작하는가, `skills` 그룹에 몇 명을 넣는가 | 팀 구성의 사실 | **결정(2026-09-26)**: 실사용자 한 명. 시험(그룹 가입·탈퇴, 두 주체 동시 갱신 등)에 필요하면 LDAP에 시험 계정을 더한다. 시험 계정의 사용 기록은 Q8 집계에서 주체로 갈라 적는다 |
| 7 | 브랜치 흐름. 코드 저장소는 `main` 하나에 PR로 합치는가, `dev` 브랜치를 두는가. 카탈로그 저장소는 설계상 `main` 하나(레지스트리가 직접 push, 사람 승인이 필요한 변경만 PR) | 팀의 작업 방식 | **결정(2026-09-26)**: 코드 저장소는 `main` + PR. CI는 PR에서 테스트·게이트, `main`에서 이미지 빌드·push(distribution D11) |
| 8 | 브랜치 보호의 자리. `alteralab`은 Free 플랜이라 **비공개 저장소에는 브랜치 보호도 룰셋도 걸리지 않는다**(2026-09-26 실측: 룰셋·classic protection API 둘 다 403 "Upgrade to GitHub Pro or make this repository public"). 코드 저장소의 `main` + PR(§6-7)과 카탈로그 저장소의 "보호된 `main`"(DESIGN §2.1 저장소 초기화 표, 강제 push 금지)이 둘 다 이 제약에 걸린다. 선택지: (a) org를 Team으로(좌석 1, 유료) (b) 저장소를 공개로 (c) 서버 보호 없이 로컬 훅(`pre-push`에서 `main` 직접 push·강제 push 거부)과 규율로만 | 조직의 비용·공개 정책 | 미결 |
| 6 | 라이선스와 배포 이름. 오픈소스로 내기로 했으니 LICENSE 파일, PyPI 패키지 이름(`harness-catalog`), 이미지 이름(예: `ghcr.io/alteralab/harness-catalog`) | 조직의 법·공개 정책 | **결정(2026-09-26)**: Apache-2.0. 이미지는 `ghcr.io/alteralab/harness-catalog`(비공개) + 보존 규칙(최근 SHA 태그 5개, 태그 없는 버전 삭제 — distribution D11). 빌드 기계 = 실행 기계(mini runner)라 운영 pull이 없다. PyPI에는 올리지 않는다(§7) — 패키지 이름 `harness-catalog`는 `pyproject.toml`에만 있고 설치는 이미지 또는 git 경로다. 저장소와 이미지는 비공개. GHCR의 컨테이너 저장·전송은 문서상 "currently free"(2026-09-26 확인, 비공개 포함)이고 Actions가 `GITHUB_TOKEN`으로 받는 전송은 계량 밖이다. org 플랜은 Free(좌석 1, 2026-09-26 `gh api` 실측)이며 지금 이미지 비용은 0이다 |

## 7. 불채택 표

기각 사유는 현재형으로만 적는다. DESIGN §7의 "다시 넣는 조건" 열은 설계 문서의 것이고 이 PLAN은 그것을 일정으로 옮기지 않는다.

| 항목 | 기각 근거 (왜 지금 아닌가) |
|---|---|
| 루프 구현을 이 저장소에 | 루프는 소비자다. 카탈로그와 닿는 자리가 둘뿐(반복마다 검색·로드, `publish_skill` 되쓰기)이고 그 둘은 도구 여섯으로 닫힌다. 루프의 다섯 장치는 카탈로그와 무관하다(§1.3) |
| 사전 통합 시험용 가짜 Dex(OIDC 모의 서버) | 개발 compose에 실제 Dex가 뜬다(distribution P1). 단위 시험은 OIDC 어댑터를 가짜로 바꾸면 되고, 통합은 실물로 한다. 모의 서버는 세 번째 인가 구현이다 |
| Helm 차트를 지금 | 인스턴스 하나, 하루 수백 요청 추정(휴리스틱). compose 한 대가 설계의 v3.0이고 수 초 중단을 받아들였다(§2.1) |
| 백업 크론 | 사용 기록은 v3.0이 읽지 않고 평가 결과의 손실은 감수하기로 했다(§2.1, §11 사용자 결정). 동급 셀프호스팅 셋도 compose에 백업이 없다(문면) |
| 순위·폐기 후보·유사 스킬 경고 | 스킬 수가 한 화면 안이다(파일럿 시작 시 둘). 사용 기록은 쌓기만 한다(§5) |
| 벡터·하이브리드 검색 | 어휘 검색의 miss가 아직 실측되지 않았다. 파일럿 P6이 처음 잰다 |
| 멀티 팀 경로·그룹 | 팀이 하나다. 식별자 `<name>`이 전역 유일이라 나중에 더해도 소비자 쪽 식별자가 변하지 않는다(§7) |
| 서비스 주체의 게시 | 무인 게시 수요가 없다. 게시는 사람의 지시 뒤에만이다(§6) |
| 관측 스택(OTel·Grafana) | 집계 원천(사용 기록)은 DB에 있고 대시보드를 요구하는 결정이 아직 없다 |
| 프레임워크(FastAPI·ORM·DI·태스크 큐) | SDK가 Starlette 앱을 주고 HTTP 라우트는 둘, 표는 셋+1이라 감출 것이 없다(§2.1 Python 표). 표에 없는 것은 넣지 않는다 |
| PyPI 게시 | 설치 단위는 컨테이너 이미지 하나다(DESIGN §2.1 "아티팩트 하나"). 이미지 없이 돌릴 사람은 `uv pip install git+https://github.com/alteralab/harness-catalog`로 같은 패키지를 받는다. PyPI는 이름 등록·릴리스 절차·토큰을 더하는데 그것을 요구하는 소비자가 없다 |
| 카탈로그 스킬을 별도 저장소로 | 소비자 둘(`pin-skill`은 파일럿, `new-skill`은 저자)이고 저자가 한 사람이다. 이 저장소의 `skills/`에서 `publish_skill`로 올린다. 카탈로그 저장소의 사본이 정본이 되는 시점은 게시 순간이고, 그 뒤 `skills/`는 이력만 남는다 |

## 8. 리스크 대응표

| # | 리스크 | 대응 |
|---|---|---|
| R1 | Dex 장치 흐름이 공개 클라이언트로 안 된다(이슈 #3983, 문면) | P0에서 실측. 안 되면 브라우저 없는 샌드박스 경로를 v3.0에서 뺀다(설계가 이미 그렇게 정했다). 코드 변경 없음 — 그랜트는 Dex 설정이다 |
| R2 | 파일럿 하네스가 2026-07-28 무세션 개정판을 말하지 않는다 | SDK가 2025-11-25 세대를 함께 서빙한다(문면). P0에서 셋의 개정판을 실측하고 P1의 HTTP 시험을 그 개정판으로 한다 |
| R3 | Synology LDAP의 그룹 클레임이 Dex를 거쳐 평탄화되지 않는다 | P0 Dex 실측에 `groups` 클레임의 실물을 포함한다. 중첩 그룹은 만들지 않는다 |
| R4 | `skills-ref` 라이브러리 API가 문서와 다르다(`validate` 함수 시그니처) | service P1의 착수 조건이 실제 패키지의 API 실측이다. 포트(`SkillValidator`)가 라이브러리 호출과 CLI 서브프로세스 어느 쪽으로도 채워지도록 앱이 검증기를 모른다 |
| R5 | MCP Python SDK v2의 `TokenVerifier`·`AuthSettings`·RFC 9728 동작이 문면과 다르다 | P1 완료 조건이 HTTP 경유 401 챌린지 실물이다. SDK 판을 핀한다 |
| R6 | 한국어 설명에 트라이그램 검색이 쓸모없다 | P6(pilot Q7)이 측정 전에 적어 둔 문턱으로 잰다. 판정과 그 뒤의 설계 재검토는 실측 기록이 나온 뒤의 일이다 |
| R7 | 게시 경쟁·push 실패로 로컬 클론이 더러워진다 | 임시 작업 트리 + 클론 잠금 하나(§2). P3 시험이 non-fast-forward를 실제 원격 둘로 재현한다 |
| R8 | 설계가 초안이라 구현 중 계약이 흔들린다 | 계약 변경은 DESIGN §11 행이 먼저(§1 경계 규칙 ⑶). PLAN 판정으로 계약을 바꾸지 않는다 |

## 9. 시스템 검증 원장

구성 요소 안의 검증은 각 PLAN의 원장에 있다. 여기는 둘 이상을 가로지르는 것만이다.

| # | 검증 | 방법 | 통과 기준 | 상태 |
|---|---|---|---|---|
| V1 | 설치 1회 | 파일럿 하네스 셋에 URL 한 줄을 등록하고 로그인 한 번 뒤 `search_skills`가 답한다 | 셋 전부 URL 한 줄 + 로그인 한 번으로 성공. 추가 설정이 있으면 그 항목을 기록하고 불통과 | 대기 |
| V2 | 게시 즉시 검색 | 하네스 A에서 `publish_skill` → 하네스 B에서 `search_skills` | push 응답 뒤 B의 첫 검색에 나온다(60초 fetch를 기다리지 않는다) | 대기 |
| V3 | 우회 push 수용 | 레지스트리를 거치지 않고 git 호스트에 직접 push(PR 병합) | 설정된 `FETCH_INTERVAL_SECONDS`의 두 주기 안에 인덱스에 반영되고(허용오차의 정의는 이 행이 소유하고 distribution V8·service V19가 참조한다) CI가 validate를 돌렸다 | 대기 |
| V4 | 검증 fail-closed | validate 실패 스킬과 시크릿 든 스킬을 직접 push | 인덱스에서 빠지고 CI가 붉다. `publish_skill`로는 거부된다 | 대기 |
| V5 | 재기동 복구 | 새 VM에 compose를 올리고 기존 카탈로그 저장소를 가리킨다 | fetch만으로 인덱스가 다시 지어지고 `/readyz` 200. 은퇴한 이름이 `name_taken`으로 남아 있다 | 대기 |
| V6 | 내려받기 왕복 | `pin-skill`로 프로젝트·사용자 범위에 각각 내려받고 새 판 확인 | `PINNED` 형식 일치, 두 범위의 낡은 쪽 안내, 하네스 셋에서 한 번만 로드 | 대기 |
| V7 | 규칙 게이트 완주 | 네 축(common·python·bash·agent-skill)과 review가 선언되고 `pre-commit run --all-files` 통과 | 선언한 표면마다 그 게이트가 한 번 이상 실제로 **파일을 검사하며** 돌았다 | common·review 통과(2026-09-26). python은 선언·훅 설치까지(파일 0이라 미완주). bash·agent-skill 대기 |

## 10. 개정 규약

판정 변경은 해당 PLAN의 판정 원장에 행 추가(기존 행 유지, 후속 행이 우선). 설계 계약의 변경은 DESIGN §11에 먼저. 실측 기록은 `research/rN`에 증보. 진행은 각 PLAN의 진행 원장에, 단계 완료만 이 문서 §11에. 기록은 현재 상태만 적는다(REVIEW.md V-REC-1) — 재심 조건·트리거·이연 시점을 등록하지 않고, 기각에는 지금 아닌 이유를, 근거에는 등급을 붙인다.

## 11. 진행 원장

| 일자 | 항목 | 내용 | 근거 |
|---|---|---|---|
| 2026-09-26 | 저장소 신설 | `git init`, altera-rules rules-v0.10.0 설치(common·lang/python·review, 훅 declared·ruff·ast-grep). 게이트 완주: `--check` 일치, selftest 통과, census 0(파이썬 없음), `pre-commit run --all-files` 통과. lang/python은 사용자 결정으로 소스 0인 시점에 미리 선언했다 | §3-5, V7 |
| 2026-09-26 | 설계 개정 | 사용자 결정: 주기 fetch 간격을 설정값 `FETCH_INTERVAL_SECONDS`(기본 60초)로. DESIGN §2·§2.1·§11에 반영(설정값 일곱 = 필수 다섯 + 선택 둘) | DESIGN §11 |
| 2026-09-26 | 브랜치 보호 시도 | `alteralab/harness-catalog`(비공개)에 룰셋과 classic protection을 API로 걸어 봤으나 둘 다 403(Free 플랜 제약). §6-8로 등록. 카탈로그 저장소의 "보호된 main" 요건도 같은 제약이라 distribution 체크리스트 3·V7은 §6-8이 정해져야 통과 가능 | §6-8 |
| 2026-09-26 | 사용자 결정: 이미지 저장소 | GHCR 비공개 + 보존 규칙으로. Harbor·ECR·`registry:2`는 distribution 불채택 표에 사유와 함께 | distribution D11 |
| 2026-09-26 | 사용자 결정 §6-3~7 | TLS는 mini의 `tailscale serve`(URL `https://mini.tail2f9fe3.ts.net/{mcp,dex}`), 인가 서버 Dex, 실사용자 한 명 + 시험 계정, Apache-2.0, 이미지 ghcr, PyPI 미게시(§7), 코드 저장소 `main` + PR. §6 미결 0 | §6 |
| 2026-09-26 | 사용자 결정 §6-1·2 | 소유 GitHub org `alteralab`, 운영 호스트 `mini.altera.lab`, 개발은 로컬 compose. git 호스트 GitHub. PyPI `harness-catalog`·GitHub `alteralab/harness-catalog` 이름은 비어 있음(2026-09-26 실측). §6-7(브랜치 흐름) 추가 | §6 |
| 2026-09-26 | Codex 교차 검증 1회 | 17건 전부 반영. 치명 셋: P0↔distribution P1 순환 의존(distribution P0 신설), P4가 P5 산출물(두 스킬)을 요구(단계 순서를 스킬 작성→배포·게시로 바꿈), `pin-skill` 재다운로드가 기존 사본을 먼저 지움(백업 이름 바꾸기로). 중요 열둘: 도구 응답 `degraded` 필드 삭제, 도구 시그니처 사본 삭제, V3 허용오차를 설정값 기준으로, §9 항목 수 아홉으로 정정, 오류 코드 어휘를 DESIGN §3으로 이관, 미래 조건절 여섯 자리 삭제, 파일럿 표본 수 목표를 모집단 규칙으로, 시험용 토큰 취득 절차 추가, 마이그레이션 패키징 검증 추가, 이미지 태그 전략, 비밀 취급 절차, 마이그레이션 재시도를 fetch 루프에서 분리. 경미 둘: 교차 참조 오타, 배치 그림 | Codex 세션 01a0da1c |
| 2026-09-26 | 배치 결정 | 사용자 결정: 오픈소스 패키지로 낸다. 배치를 인용 프로젝트 여섯의 공통 골격으로 바꿨다(§3-8). 계획 문서는 `plans/`, 실측은 `research/`. DESIGN §2.1·§8·§11 반영 | §3-8 |
| 2026-09-26 | PLAN 초판 | 우산 + service·distribution·skills·pilot 넷. DESIGN v3.2를 원천으로, 설계 결정은 복제하지 않고 단계·완료 조건·검증만 적었다. Codex 교차 검증은 아직이다 | §3-6 |
