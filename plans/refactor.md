# 리팩토링 원장 — 어디서든 설치되는 오픈소스 모양으로 (2026-10-20)

사용자 요구(2026-10-20): "harness-catalog 를 특정 환경에서만 쓰지 않고 오픈소스처럼 **설정값으로 원하는 환경에 맞게 설치**하게 하고 싶다. Langfuse 는 우리는 SaaS 를 쓰지만 누구는 온프레미스에 올릴 수 있으니 URL 설정값 하나로 자기 것을 쓰면 된다(Langfuse 를 우리가 띄운다는 뜻이 아니다). 하드코딩·강결합된 값 중 사용자가 제어해야 할 값은 설정으로. `packages/cli` 안의 템플릿은 관리가 용이해 보이지 않으니 다른 오픈소스는 어떻게 하는지 확인. PEP·간결함·추상화·깔끔함도 점검(syntopicon). 리팩토링은 Opus 에이전트가 하고 Codex 가 리뷰. docs 를 구성해 서빙하고 `llms.txt` 도 제공(cocoindex 는 깔끔하나 누런 테마는 싫고, LangChain docs 스타일이 좋다)."

리서치 셋은 `plans/research/2026-10-20-{config-management,init-templates,docs-site}.md`(출처 URL 전수). 이 문서는 그 셋과 KB 를 근거로 한 **결정과 실행 원장**이다. 계약을 바꾸는 항목은 DESIGN §11 2026-10-20 행이 정본이고 여기는 그 행을 푼 것이다.

## 1. 판단 기준 — 무엇을 설정으로 빼고 무엇을 빼지 않는가

하나의 기준으로 간다(메모리 `feedback-right-design-over-min-cost`·`feedback-simplicity-over-branching`).

- `[it]` 외부 설정(thomas2020 Topic 32) — 설정으로 뺄 것의 목록: **외부 서비스의 자격 증명, 로깅 목적지, 앱이 쓰는 포트·IP·기계·클러스터 이름, 환경별 매개변수, 사이트별 서식, 라이선스 키.** 판별 규칙 — "바뀌어야 할 것을 알고 있으면서 코드 본체 밖에 표현할 수 있는 것".
- 같은 페이지의 정정 "Don't Overdo It" — ① 모든 필드를 설정으로 만든 고객은 4만 개의 설정 변수와 코딩의 악몽을 얻었다. ② **게을러서 결정을 설정으로 밀지 마라** — 진짜 논쟁이 있으면 한쪽으로 해 보고 피드백을 받아라. 설정 항목 하나하나는 미룬 결정이고, 사용자와 운영자에게 넘어간다.
- `[it]` ousterhout2021 §8.2 — 설정 매개변수는 복잡성을 **위로** 옮긴다. 내보내기 전에 자문하라: **"사용자가 여기서 우리가 정할 수 있는 것보다 더 나은 값을 정할 수 있는가?"**
- `[it]` 설정과 코드를 가르는 선(hohpe2020 11장) — 복잡한 설정은 도구도 문서도 없는 형편없는 언어로 하는 프로그래밍이다. 설정이라 이름 붙인 것도 설계·테스트·버전 관리·배포 관리를 거치게 하라.
- 사례 공통 규칙(리서치 config §5): **파일 하나가 기본값 정본, 환경 변수는 override; 비밀은 `_FILE`·외부 백엔드·secretRef; 수집기(OTLP) endpoint 는 비우거나 localhost — 벤더 URL 을 기본값으로 박는 것은 자기 제품 텔레메트리뿐이고 그것도 끄는 플래그가 있다(Polaris: "no collector endpoint that works for all deployments"); 환경 특정 값(URL·그룹·클라이언트 ID·이미지)은 전부 설정 키로 노출하고 compose 는 `${VAR:-dev-default}`.**

따라서 이 리팩토링에서 설정이 되는 것은 **"운영자의 환경이 정하는 값"** 뿐이다 — 주소·이름·자격·이미지. 알고리즘의 매개변수(검색 α·k, 브레이커 시간, 보존 기간)는 그대로 상수다(DESIGN §11 2026-10-19 검색 행의 결정과 같다).

## 2. 현황 감사 — 환경 특정 값이 박힌 자리

`grep` 전수(2026-10-20, plans·DESIGN·README 제외). 열 "처분"이 결정이다.

| 자리 | 값 | 종류 | 처분 |
|---|---|---|---|
| `docker/compose.yml` `OTEL_EXPORTER_OTLP_ENDPOINT` 기본값 | `https://us.cloud.langfuse.com/api/public/otel` | 외부 서비스 주소(벤더 SaaS) | **비운다**(R1). 우리 값은 mini 의 `.env` 로 |
| `docker/compose.yml` `HC__EMBED_URL` 기본값 | `http://host.docker.internal:11434/api/embed` | 로컬 관례(호스트 Ollama) | 둔다 — 벤더 주소가 아니고 비우면 BM25 만. 문서에 "호스트 Ollama 관례" 명시 |
| `core/model.py` `HARNESS_READERS` + `authz.py` + Dex 설정 둘 + 템플릿·docs | `harness-readers` | 디렉터리의 그룹 이름(환경) | **설정 `HC__READER_GROUP`**(기본값 그대로)(R2) |
| `docker/.env.example` `REGISTRY_IMAGE`, `compose.yml` 오류 문구, `.github/workflows/ci.yml` | `ds923plus.tail2f9fe3.ts.net:9443/alteralab/…` | 이미지 레지스트리(환경) | compose 는 지금도 필수값(기본값 없음) — 문구만 중립으로. CI 는 저장소 변수 `IMAGE_REGISTRY`·`IMAGE_REPOSITORY` + 시크릿으로(R3) |
| `docker/.env.example` LDAP 절 | `192.168.3.95`, `dc=gyojunan,dc=synology,dc=me` | 개인 환경 값 | 자리표시자로(R3) |
| `docker/dex/config.yaml` 정적 클라이언트 | `claude-code`·`codex`·`cursor`·`ci-runner` | 에이전트 제품 관례 | 둔다 — 배포 설정 파일이고 제품마다 하나(§2 Dex 결정). `ci-runner` 시크릿은 이미 파일 |
| `docker/synology-ldap/` | 우리 팀의 LDAP 연합 오버레이 — 그 안의 개인 LDAP 주소·hairpin 기본값 | 팀 변형 + 개인 값 | 오버레이는 둔다("우리 팀 변형"). 개인 값은 `.env` 변수로 끌어올리고 예시는 자리표시자(R3, Codex #1 보완) |
| `scripts/deploy.sh` 의 mini 전용 기본값 | 호스트·경로 기본값 | 운영 스크립트의 환경값 | 인자·환경 변수로(기본값은 중립 또는 없음)(R3, Codex #1 보완) |
| `cli/init.py` `CODE_REPO_URL`, `core/toolbox.py` `TOOL_SCHEMA_ID` | `https://github.com/alteralab/harness-catalog` | 코드 저장소 주소 | **패키지 메타데이터(`[project.urls]`)에서 읽는다** — 포크가 자기 주소를 얻는다(R4). 스키마 `$id` 는 그 주소에서 조립 |
| `cli/templates/**` Dockerfile 9·README·pin SKILL.md·scaffold.py | `https://ds923plus…:8443/repository/pypi-public/simple/` | 사내 PyPI 인덱스 | **템플릿 재배치(B)와 함께** — starter 저장소의 Dockerfile 은 `ARG PIP_INDEX_URL`(기본 공개 PyPI)(R6, 결정 대기) |
| `.github/workflows/ci.yml` altera-rules 비공개 체크아웃·self-hosted 러너 라벨 | `alteralab/altera-rules`, `[self-hosted, harness-catalog]` | 이 코드 저장소의 CI | 둔다 — 코드 저장소 자신의 CI 이지 배포물의 설정이 아니다. 공개 전환 때 규칙 저장소 공개 여부와 함께 |
| `docs/*.md` 의 tailnet 호스트 이름 | `alteraui-macmini…`, `ds923plus…` | 운영 문서의 실제 값 | 둔다(사내 문서) — 공개 전환 때 자리표시자(리서치 docs §4.5) |

코드 품질 감사(ruff `--select ALL` 통계, radon): E501 923(줄 길이 — 프로젝트 규약은 altera-rules 가 정한다), I001 미정렬 import 18, TC00x 타입 전용 import 57, N818 예외 이름 4, FBT 불리언 위치 인자 24, PLR0913 인자 6+ 8, RUF105/100 noqa 정리 34. 복잡도: `catalog.py` MI 10.3(B), `_build` CC 20, `_embed_missing` 17, `_rebuild` 14; `check.inspect_tool` 18; `search.tokenize` 17; `git.archive_tree` 14; `pg.replace_index` 13; `embed._one` 14. `catalog.py` 523줄이 유지·읽기·아카이브 셋을 한 클래스에 든다.

## 3. 결정

### R1. OTLP endpoint 기본값을 비운다 (compose)
`OTEL_EXPORTER_OTLP_ENDPOINT: ${OTEL_EXPORTER_OTLP_ENDPOINT-}` — 비면 꺼짐(0.7.1 의 규칙 그대로). `.env.example` 에 Langfuse Cloud US/EU·셀프호스트 세 값을 **예시**로, "모든 배포에 맞는 수집기 주소는 없다"(Polaris) 한 줄과 함께. 우리 팀 값은 mini 의 `docker/.env` 에 적는다 — **이행 단계**: 0.10.0 배포 **전에** mini 의 `.env` 에 `OTEL_EXPORTER_OTLP_ENDPOINT` 를 넣지 않으면 배포 즉시 트레이스가 끊긴다(Codex #2). `deploy.sh` 의 `tracing:` 출력은 "off(값 없음)" 과 endpoint 를 구분해 찍는다. DB 마이그레이션은 없다. 2026-10-19 의 "compose 기본값 = Langfuse US" 결정을 **거둔다** — 그때 기준은 "우리 팀의 설치 편의"였고 지금 기준은 "어느 환경이든"이다.

### R2. 읽기 그룹 이름을 설정으로 — `HC__READER_GROUP` (기본 `harness-readers`)
Ousterhout 의 물음에 "예"다: 디렉터리에 이미 있는 그룹을 쓰려는 운영자가 우리보다 더 나은 값을 안다. 외부 설정 목록의 "기계·클러스터 이름" 부류. `authz.authorize(principal, tool, *, reader_group)` 가 값을 받고, 인가가 실제로 일어나는 자리인 MCP 어댑터 `ToolBindings._principal` 이 부트스트랩에서 받은 설정값을 넘긴다(`Catalog` 는 인가를 모른다 — Codex 계획 검토 #1 정정). 상수 `HARNESS_READERS` 는 **기본값**으로만 남는다. Dex 설정·템플릿·docs 의 문자열은 "기본값 `harness-readers`"로 읽히게 고친다. DESIGN §7 "그룹→역할 매핑 설정 없음"은 그대로다 — 역할은 하나고 이름만 설정이다.

### R3. 레지스트리·개인 값의 중립화 (compose·.env.example·CI)
`REGISTRY_IMAGE` 는 지금도 필수값이다(기본값 없음) — 오류 문구와 `.env.example` 의 예시를 `ghcr.io/<org>/harness-catalog:<tag>` 꼴로. LDAP 예시는 `ldap.example.com:636`, `dc=example,dc=com`. CI 의 이미지 주소는 저장소 변수 `IMAGE_REGISTRY`(`ds923plus…:9443`)·`IMAGE_REPOSITORY`(`alteralab/harness-catalog`)로 올리고 로그인은 지금처럼 시크릿. `scripts/deploy.sh`·`release.py` 가 같은 변수를 읽는다. 우리 값은 GitHub 저장소 변수에 둔다(설정의 정본이 코드 밖으로).

### R4. 코드 저장소 주소를 패키지 메타데이터에서
**정본은 하나** — `packages/core/pyproject.toml` 의 `[project.urls] Repository` 만이고, cli·server 는 core 에 의존하므로 코드는 언제나 `metadata("harness-catalog-core")` 를 읽는다(Codex #3: 배포물마다 두면 정본이 둘이 된다). cli·server 의 pyproject 에 같은 URL 을 적는 것은 PyPI 표시용이지 코드가 읽는 자리가 아니다. `init.py` 의 `CODE_REPO_URL` 상수와 `toolbox.TOOL_SCHEMA_ID` 의 조립 근거가 그것이 된다. 포크는 core 의 pyproject 한 줄을 고쳐 자기 주소를 얻는다(고치지 않으면 상류 주소가 남는다 — 자동이 아니다).

### R5. 코드 정리 (계약 불변)
1. **`catalog.py` 분할** — 한 파일에 유지(`_rebuild`·`_resync`·`_rewound`·`_build`·`_indexes`·`_embed_missing`)·읽기(검색·get)·아카이브(발급·캐시·퇴거)가 있다. `Catalog` 의 공개 인터페이스(시험이 보는 것)는 그대로 두고 안쪽을 둘로 뗀다: `indexing.py`(재구축 상태 기계 + 벡터 캐시 `VectorCache`)와 `archives.py`(tar 발급·캐시). `[it]` 깊은 모듈 — 인터페이스는 그대로, 구현만 나눈다. 분할의 기준은 "변경 이유가 다른가"(재구축 규칙 vs 아카이브 보존)이지 줄 수가 아니다. **보존 계약**(Codex #4): `_lock` 의 소유와 범위(fetch→빌드→교체가 한 잠금 안), `_live = (snapshot, indexes)` 의 원자 교체, 검색이 잠금 없이 `_live` 하나를 읽는 것 — 셋은 분할 뒤에도 글자 그대로 유지한다.
2. **스킬·도구 쌍의 중복** — core 의 `search_skills`/`search_tools` 와 `_resolve`/`_resolve_tool` 처럼 **이름만 다른 쌍**은 한 함수로 접는다. MCP 어댑터의 `search_skills`/`search_tools` 는 응답 모델과 스팬 속성이 달라 이름만 다른 쌍이 **아니다** — 접지 않는다(Codex #4). `get_skill`/`get_tool` 처럼 모양이 다른 쌍(path·archive vs kind·server)은 **접지 않는다** — 메모리 "분기보다 규칙 하나": 공통 추상을 만들어 분기를 안에 숨기는 것이 더 나쁘다.
3. **복잡도 상위 함수** — `_build`(CC 20)·`_embed_missing`(17)·`inspect_tool`(18)·`tokenize`(17)·`archive_tree`(14)·`replace_index`(13)·`embed._one`(14): 각각 "한 단계 내려가는 보조 함수 하나"로 10 아래로. 동작·시험 불변.
4. **PEP 정합** — PEP 8 import 정렬(I001 18), 예외 이름 `…Error`(N818: `GitleaksUnavailable`·scaffold `Input`), 타입 전용 import 를 `TYPE_CHECKING` 아래로(TC00x 57 — 런타임 import 비용 제거), 불리언 위치 인자를 키워드 전용으로(FBT 24), `noqa` 정리(RUF100/105 34). **ruff 규칙 집합은 늘리지 않는다** — 이 저장소의 린트 정책은 altera-rules 가 조항으로 정한다(`pyproject.toml` 주석). 조항으로 올릴 만한 것(I·TC·N818)은 altera-rules 저장소에 제안으로 남긴다(사용자 결정).
5. 긴 줄(E501 923)은 **손대지 않는다** — 줄 길이는 규칙 저장소의 결정이고, 이 코드의 긴 줄은 한 줄 주석(근거 인용)이 대부분이다.

### R6. `hc init` 템플릿 — (B) 구조는 내장, 스킬·도구는 starter 카탈로그 저장소 (결정 대기)
리서치(templates §3) 권고 (B): 구조 파일(README·pre-commit·워크플로·`.gitignore`·표지·`.mcp.json`·생성 스키마)은 CLI 계약과 함께 가므로 패키지에 남기고, `skills/`·`tools/`(324K, 템플릿 커밋 46 vs 릴리스 8)는 **그 자체가 `layout = 1` 카탈로그인 별도 저장소**를 태그+SHA 로 핀해 받는다. 이득: 스킬 수정이 CLI 릴리스에서 분리, starter 저장소 CI 가 `hc check`+Oracle evals 를 그대로 돌려 시험이 공짜(지금은 템플릿 evals 를 CLI CI 가 못 돌린다), Dockerfile 의 사내 인덱스는 `ARG PIP_INDEX_URL`(공개 PyPI 기본)로 — 치환 변수를 늘리지 않는다. 오프라인·에어갭은 `--starter <로컬 경로>` — 단 `resolve_pin()` 의 `git ls-remote` 가 남아 완전 오프라인은 아니다(Codex #6, R6 설계 때 함께). Harbor 는 build-arg 유틸이 있으나 `hc evals` 가 `PIP_INDEX_URL` 을 넘기지 않는다 — R6 구현 범위에 포함.
선례: Harbor(뼈대는 패키지, 데이터셋 메타는 저장소), Astro(embed + 원격 템플릿), create-next-app(내장 + `--example`), anthropics/skills(스킬은 git 저장소 + ref/sha 핀), copier(태그 핀).
**사용자 결정이 필요한 것 둘**: (a) starter 저장소(`alteralab/harness-catalog-starter`)를 만들 것인가, 공개로 둘 것인가(공개면 Nexus 의존이 사라지고 외부 사용자도 `hc init` 이 된다); (b) 판 번호를 CLI 와 같이 갈지 독립으로 갈지. 결정 전에는 이 항목을 **시작하지 않는다**(반쯤 옮긴 상태를 두지 않는다 — DESIGN 2026-10-10 "기본 스킬은 패키지 데이터에서" 행은 결정 뒤 §11 행으로 개정).

### R7. 문서 사이트 + `llms.txt`
리서치(docs §5) 권고대로: **MkDocs + Material**(Zensical 호환 부분집합 — search·include-markdown·mkdocstrings·llmstxt·superfences), `mkdocs-llmstxt` 가 `llms.txt`·`llms-full.txt` 를 생성, `docs/` 를 그대로 소스로(`docs/index.md` 가 README 를, `docs/design.md` 가 DESIGN 을 include). 테마는 흰 바탕 + 파란 액센트(LangChain `docs.json` 의 `#161F34`/`#006DDD`), Inter + Noto Sans KR, 누런 토큰 금지. 서빙은 **mini compose 의 nginx 정적 컨테이너를 `tailscale serve` 뒤에**(비용 0, 사내 호스트 이름 노출 문제 없음, 기존 러너·Harbor 그대로); CI 가 `mkdocs build --strict` 로 링크 깨짐을 막고 이미지로 올린다. 공개 전환 때 같은 `site/` 를 Cloudflare Pages 로. Material 이 유지보수 모드(2027-05 까지 치명 버그만)라 **CI 에 `zensical build` 를 비차단으로 함께 돌려** 0.1.0(2026-11-05) 뒤 전환할 때 무엇이 안 맞는지 미리 본다(호환성 게이트는 아니다 — 전환 때 따로 검증한다, Codex #5). `site_url` 은 지금 mini 의 tailnet 주소이고 공개 전환 때 바꾼다.
`[it]` 문서를 코드처럼(winters2020) — 소스 관리·리뷰·소유자·정본 지정은 이미 있고(docs/ + DESIGN + 원장), 이 항목이 더하는 것은 **배포(서빙)와 주기적 평가(strict 빌드)** 둘이다.

### R8. 실행 방식 — Opus 가 고치고 Codex 가 본다
단위마다: (1) Opus 에이전트가 worktree 에서 구현 + 시험 + 게이트(`make check`), (2) Codex 적대적 리뷰(원문은 `~/workspace/loop-engineering/codex-review-refactor-<단위>.md`), (3) 지적 반영 뒤 main 에 병합. 단위는 서로 파일이 겹치지 않게 나눈다. 릴리스는 전부 모아 **0.10.0** 하나(계약 변경: R1·R2·R4 설정/기본값; 마이그레이션 없음).

| 단위 | 범위 | 겹치는 파일 |
|---|---|---|
| U1 설정·중립화 | R1·R2·R3·R4 — compose·.env.example·CI·settings·authz·bootstrap·init·toolbox·docs(configuration·operations) | docker/, .github/, settings.py, authz.py, model.py, bootstrap.py, init.py, toolbox.py, pyproject 둘 |
| U2 코드 정리 | R5 — catalog.py 분할·중복·복잡도·PEP | core/catalog.py(+indexing.py·archives.py), check.py, search.py, git.py, pg.py, embed.py, cli/*.py(import 정렬·FBT) |
| U3 문서 사이트 | R7 — mkdocs.yml, docs/index.md·design.md, stylesheets, docs 그룹 의존성, docker/docs.Dockerfile, compose docs 서비스, CI docs 잡, deploy.sh | 새 파일 + compose.yml(서비스 추가 — U1 과 같은 파일이라 **U1 뒤에**) + ci.yml(잡 추가 — U1 뒤에) |
| U4 템플릿 (B) | R6 | 결정 뒤 |

U1·U2 는 동시에 돌리되 **실제 겹침**(Codex #7)은 다음과 같고 병합 때 손으로 푼다: U2 의 PEP 정합이 `cli/*.py` 를 건드리므로 U1 의 `init.py`·`toolbox.py` 는 U2 범위에서 뺐다; `mcp_tools.py` 는 U1 이 `_principal`, U2 가 search 쌍(접지 않기로 함)이라 사실상 U1 만. U3 는 U1 병합 뒤(compose·ci·deploy.sh). 각 단위의 끝 조건: 시험 전부 통과, pyright 0, 게이트 통과, Codex 리뷰 반영, 이 원장 §4 에 행.

## 4. 진행 원장

| 일자 | 단위 | 내용 | 근거 |
|---|---|---|---|
| 2026-10-20 | 계획 | 리서치 셋(plans/research/)·KB·코드 감사로 §1~3 작성; DESIGN §11 2026-10-20 행 | 이 문서 |
| 2026-10-20 | 계획 검토 | Codex 적대 검토 7건 반영: R2 배선 자리(`_principal`), R1 이행 단계(mini `.env`)와 `tracing:` 출력 구분, R4 정본 하나(core), R5 보존 계약·MCP search 쌍 제외, R7 Zensical 비차단의 뜻, R6 오프라인·build-arg 메모, 단위 겹침 명시, 감사표에 오버레이·deploy.sh 추가 | `~/workspace/loop-engineering/codex-review-refactor-plan.md` |
| 2026-10-20 | U1 설정·중립화 | R1~R4 구현. **R1** compose `OTEL_EXPORTER_OTLP_ENDPOINT` 기본값 비움(`telemetry.configure_tracing`이 이미 빈 값 = no-op), `.env.example` 관측 절에 US·EU·셀프호스트 예시 셋 + "모든 배포에 맞는 수집기 주소는 없다", `deploy.sh`가 `tracing: on -> <endpoint>` / `tracing: off (… 비어 있음)`을 가려 찍는다, docs/operations.md 에 0.10.0 이행 한 줄. **R2** 설정 `HC__READER_GROUP`(기본 `harness-readers`, 설정값 아홉), `authorize(…, *, reader_group=)`가 인자로 받고 `bootstrap → build_server → ToolBindings._principal`이 넘긴다(core 는 설정을 모른다), compose 가 변수 전달, Dex 설정 둘·템플릿 README·docs 문구를 "기본값"으로. **R3** `REGISTRY_IMAGE` 예시·오류 문구를 `ghcr.io/<org>/harness-catalog:<tag>` 꼴로, LDAP 예시를 `ldap.example.com:636`·`dc=example,dc=com`로, 오버레이의 개인 LDAP·hairpin 기본값을 없애고 `:?` 필수로, CI 이미지 주소를 저장소 변수 `IMAGE_REGISTRY`·`IMAGE_REPOSITORY`로(기본값 없음 — 없으면 잡이 그 자리에서 실패), `deploy.sh`·`release.py`가 같은 이름을 읽되 기본값이 우리 값이라 동작 불변, `deploy.sh`의 경로·오버레이도 `DEPLOY_REPO_PATH`·`DEPLOY_OVERLAY`로. **R4** `core/pyproject.toml`의 `[project.urls] Repository` 한 줄이 정본, `core/distribution.py:code_repo_url()`이 `importlib.metadata`로 읽고 `init.resolve_pin`·`toolbox.tool_schema_id`가 그것을 쓴다(실패는 `DistributionMetadataError`). 시험: `test_authz` 다른 그룹 이름 케이스, `tests/http` `test_reader_group_follows_the_setting`(설정값을 바꾼 프로세스), 설정 개수 8→9. 실측: 메타데이터 읽기가 uv 워크스페이스·editable·휠 셋에서 같은 주소, `docker compose config`가 `.env` 없이도 원래의 `:?`에서만 멈춤, `gh variable list`에 변수 둘, pytest 191 통과·pyright 0·게이트 넷 통과 | DESIGN §11 2026-10-20; 이 문서 §3 R1~R4 |
