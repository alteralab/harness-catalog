# harness-catalog

팀의 에이전트 스킬을 git 저장소에 두고, 각자의 하네스(Claude Code·Codex·Cursor)에서 MCP로 찾아 쓰게 하는 스킬 카탈로그입니다.

상태: **운영 중** (v0.9.0). Claude Code + Synology LDAP Server 조합으로 등록 → 로그인 → 검색 → PR → 병합 → 색인까지 끝에서 끝까지 실측했고, 팀 레지스트리가 그 구성으로 돌고 있습니다. 검색은 BM25 와 한국어 임베딩(KURE-v1)의 하이브리드이고 도구 호출은 Langfuse 로 갑니다. Codex·Cursor는 클라이언트만 등록되어 있고 아직 붙여 보지 않았습니다.

## 목차

- [무엇인가](#무엇인가)
- [빠른 시작](#빠른-시작)
  - [먼저 돌려 보기](#먼저-돌려-보기)
  - [팀원: 하네스에서 쓰기](#팀원-하네스에서-쓰기)
  - [저자: 스킬 올리기](#저자-스킬-올리기)
  - [운영자: 레지스트리 띄우기](#운영자-레지스트리-띄우기)
- [문서](#문서)
- [저장소 구성](#저장소-구성)
- [판과 호환](#판과-호환)
- [기여](#기여)
- [라이선스](#라이선스)

## 무엇인가

스킬 하나는 git 저장소의 디렉토리 하나입니다. `skills/<name>/SKILL.md`와, 필요하면 스크립트·참고 파일·평가 과제가 함께 있습니다. 이 저장소를 **카탈로그 저장소**라 부르고, `main`에 병합된 것이 곧 게시된 판입니다. 스킬을 만들고 고치고 지우는 일은 전부 브랜치 → PR → 병합이며, 병합한 사람이 그 판을 인증한 사람입니다.

**레지스트리**는 `main`을 주기적으로 받아 검사·색인하고, 하네스가 MCP로 물으면 답하는 서버입니다. 도구는 넷(스킬 둘 `search_skills`·`get_skill`, 도구 둘 `search_tools`·`get_tool`)이고 전부 읽기이며 쓰기 도구도 전체 목록 도구도 없습니다. 저장소에는 읽기 전용 deploy key로만 닿습니다. 레지스트리가 뚫려도 카탈로그는 바뀌지 않고, 레지스트리가 죽어도 카탈로그는 git에 그대로 있습니다.

로그인은 팀 LDAP 계정으로 한 번 합니다. 레지스트리 앞의 Dex가 LDAP을 OIDC로 감싸고, LDAP 그룹 `harness-readers`에 든 사람만 도구를 부를 수 있습니다.

검색은 레지스트리 프로세스 메모리에서 합니다. 이름·설명의 BM25(한글 2-gram)와 설명 임베딩(KURE-v1, 호스트의 Ollama 가 만든다)의 코사인을 섞어 "캡션 가져와"로 자막 스킬을 찾습니다. 임베딩 서비스가 없으면 BM25 만으로 돌고 `/readyz`가 그 사실을 알립니다. 벡터는 PostgreSQL 에 캐시되어 재기동 때 다시 만들지 않습니다.

```mermaid
flowchart LR
    subgraph team["팀원"]
        H["하네스<br/>(Claude Code · Codex · Cursor)"]
    end

    subgraph host["운영 호스트 (compose)"]
        P["프록시 (TLS)"]
        R["registry<br/>MCP 서버 · 색인"]
        D["dex<br/>OIDC"]
        PG[("postgres<br/>색인")]
    end

    L["LDAP<br/>harness-readers"]

    subgraph git["git 호스트"]
        C["카탈로그 저장소<br/>skills/&lt;name&gt;/"]
        CI["CI: harness-catalog check"]
    end

    LF["Langfuse<br/>평가 · 사용 기록"]

    H -- "MCP (OAuth 토큰)" --> P
    P -- "/mcp" --> R
    P -- "/dex" --> D
    H -. "브라우저 로그인" .-> D
    D -- "인증 · groups" --> L
    R --> PG
    R -- "fetch main<br/>(deploy key, 읽기 전용)" --> C
    H -- "브랜치 · PR · 병합" --> C
    C -- "PR마다" --> CI
    CI -- "harbor run" --> LF
    R -. "도구 호출 스팬" .-> LF
```

이 저장소(`alteralab/harness-catalog`)는 레지스트리·CLI·이미지·템플릿을 담은 **코드 저장소**입니다. 카탈로그 저장소(우리 팀은 `alteralab/catalog`)와는 별개입니다. 설계의 근거는 [DESIGN.md](DESIGN.md), 진행과 결정의 원장은 [PLAN.md](PLAN.md)와 `plans/`에 있습니다.

## 빠른 시작

### 먼저 돌려 보기

Docker만 있으면 명령 둘로 전체(레지스트리·Dex·PostgreSQL·심은 카탈로그)가 내 머신에 뜹니다. 편집할 파일도 환경 변수도 없습니다. 평가·데모 전용이고 비밀번호는 공개된 값입니다.

```sh
git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
docker compose -f docker/compose.quickstart.yml up -d --build --wait    # 또는 make quickstart
```

끝나면 `docker compose -f docker/compose.quickstart.yml logs welcome`이 접속 방법을 찍습니다. 레지스트리는 `http://localhost:8000/mcp`, 로그인은 `dev@example.com` / `password`. 다음은 [docs/quickstart.md](docs/quickstart.md).

### 팀원: 하네스에서 쓰기

필요한 것: Claude Code 2.1 이상, 레지스트리 URL, LDAP 계정이 `harness-readers` 그룹에 있을 것.

```sh
claude mcp add --transport http --scope user harness-catalog https://<레지스트리 호스트>/mcp
```

`~/.claude.json`의 그 항목에 `"oauth": { "clientId": "claude-code" }`를 더하고 Claude Code를 새로 시작합니다. `/mcp`에서 harness-catalog를 고르면 브라우저가 열리고, LDAP 계정으로 한 번 로그인하면 끝입니다. 이제 "카탈로그에 어떤 스킬 있어?"라고 물으면 됩니다. 자세한 것은 [docs/using.md](docs/using.md).

### 저자: 스킬 올리기

필요한 것: 카탈로그 저장소 clone, `uv`, `gitleaks`, (evals를 돌리려면) `harbor`.

```sh
git switch -c skill/<name>
mkdir -p skills/<name> && $EDITOR skills/<name>/SKILL.md
pre-commit install                                   # 커밋마다 harness-catalog check
hc check . --rev HEAD                                # 직접 돌릴 때 (hc = harness-catalog의 짧은 이름)
gh pr create
```

PR의 CI가 같은 검사를 돌리고, 사람이 병합하면 레지스트리가 한 주기(기본 60초) 안에 색인합니다. 하네스에서 `write` 스킬을 불러 "이 절차를 스킬로 만들자"나 "도구 새로 만들자"라고 하면 뼈대를 잡아 줍니다. 규약과 검사 항목은 [docs/authoring.md](docs/authoring.md).

### 운영자: 레지스트리 띄우기

운영 경로입니다. 필요한 것: Docker(compose v2), TLS를 맡을 리버스 프록시, LDAP(또는 정적 사용자), git 호스트의 카탈로그 저장소와 읽기 전용 deploy key, 그리고 검색의 임베딩을 만들 호스트의 Ollama(`ollama pull hf.co/mykor/KURE-v1-gguf:BF16`. 없어도 뜨되 BM25 만).

```sh
git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
cp docker/.env.example docker/.env && chmod 600 docker/.env             # REGISTRY_IMAGE, HC__*
scripts/make-secrets.sh secrets ~/.ssh/catalog-deploy-key
docker compose -f docker/compose.yml up -d
curl -fsS http://127.0.0.1:8000/readyz
```

카탈로그 저장소가 아직 없으면 `hc init <repo-url>`이 세웁니다(`hc`와 `harness-catalog`는 같은 명령입니다. 사람이 치는 자리는 `hc`, pre-commit·CI 설정 같은 기계가 읽는 자리는 긴 이름을 씁니다). 프록시 경로·LDAP 연동·런북은 [docs/operations.md](docs/operations.md).

## 문서

아래 전부가 문서 사이트로도 만들어집니다(`mkdocs`, 워크플로 `docs.yml`): **<https://ds923plus.tail2f9fe3.ts.net:9810/harness-catalog/>** (tailnet 안에서만). 에이전트용 목차는 `llms.txt`, 전체 본문은 `llms-full.txt`.

| 문서 | 누구에게 | 내용 |
|---|---|---|
| [docs/quickstart.md](docs/quickstart.md) | 처음 보는 사람 | 명령 둘로 로컬에 전체 띄우기, 로그인, 지우기 |
| [docs/using.md](docs/using.md) | 팀원 | 등록, 로그인, 찾기·적재, 곁에 두기(pin), 기계 계정, 문제 해결 |
| [docs/authoring.md](docs/authoring.md) | 스킬 저자 | 스킬의 모양, 팀 규약, 올리는 절차, 검사 항목, evals, 갱신·은퇴 |
| [docs/operations.md](docs/operations.md) | 운영자 | 구성, 카탈로그 저장소 신설, 설치, 프록시, Dex·LDAP, 런북 |
| [docs/configuration.md](docs/configuration.md) | 운영자 | 설정 표면 전체의 참조: 레지스트리 설정값(생성), 관측, compose 변수·비밀 파일, Dex·LDAP, CI·러너 |
| [docs/development.md](docs/development.md) | 개발자 | 배치, 개발 환경, 시험, 게이트, 릴리스 |
| [DESIGN.md](DESIGN.md) | 모두 | 설계와 결정의 근거 |
| [PLAN.md](PLAN.md), `plans/` | 개발자 | 실행 계획, 측정 결과, 결정 원장 |

## 저장소 구성

`tree -L 2 --dirsfirst` 출력에 역할을 달았습니다.

```
.
├── docker/                      # compose 셋과 지원 파일. compose의 상대 경로·.env는 이 디렉토리 기준
│   ├── compose.yml              #   운영: registry · postgres · dex (docker secrets). 프로젝트 이름 harness-catalog 고정
│   ├── compose.dev.yml          #   개발: postgres · dex만
│   ├── compose.quickstart.yml   #   빠른 시작: 전체를 기본값으로, 편집 없이
│   ├── .env.example             #   설정값 견본 → docker/.env
│   ├── synology-ldap/           #   우리 팀 변형: LDAP 연합 compose 오버레이 + Dex 설정 (운영은 compose.yml 위에 겹친다)
│   ├── dex/                     #   Dex 설정 (gomplate, 정적 사용자)
│   ├── postgres/                #   PostgreSQL 초기화 (DB·역할 둘. 표는 레지스트리의 마이그레이션 0001~0005가 만든다)
│   └── quickstart/              #   빠른 시작의 카탈로그 심기 스크립트
├── docs/                        # 독자별 안내
│   ├── quickstart.md            #   처음: 명령 둘로 전체 띄우기
│   ├── using.md                 #   팀원: 등록·로그인·찾기·pin
│   ├── authoring.md             #   저자: 규약·절차·검사 항목·evals
│   ├── operations.md            #   운영자: 설치·프록시·Dex/LDAP·런북
│   ├── configuration.md         #   설정값 참조 (harness-catalog config docs 생성)
│   └── development.md           #   개발자: 배치·시험·게이트·릴리스
├── packages/                    # uv 워크스페이스, lockstep 배포물 넷
│   ├── core/                    #   harness-catalog-core: 모델·카탈로그 앱·검사 항목·git/검증 어댑터
│   ├── server/                  #   harness-catalog-server: MCP 서버·OIDC·PostgreSQL·스케줄러·마이그레이션
│   ├── cli/                     #   harness-catalog-cli: check·init·config, 카탈로그 저장소 템플릿
│   │   └── templates/           #     카탈로그 저장소 템플릿 + 기본 스킬 셋(skills/pin·write·review, 각자 evals)·기본 도구 하나(tools/scaffold)와 생성되는 schemas/tool.schema.json. init이 새 카탈로그에 함께 쓴다
│   └── harbor-langfuse/         #   harbor-langfuse: Harbor 플러그인 → Langfuse
├── plans/                       # 실행 계획과 원장 (PLAN.md가 우산)
│   ├── pilot/                   #   측정 결과 r1~r3 (Dex 그랜트, LDAP, 하네스 첫 접촉)
│   ├── service.md
│   ├── distribution.md
│   ├── pilot.md
│   ├── skills.md
│   └── search.md                #   검색 리서치·벤치마크·결정(0.8.0 하이브리드)
├── scripts/
│   ├── make-secrets.sh          #   운영 비밀 파일 생성 (멱등; Langfuse OTLP 헤더 포함)
│   ├── dev-token.sh             #   기계 계정 토큰 (비밀번호 그랜트)
│   ├── release.py               #   make release — 판 올리기·태그·push (CI가 이미지), Nexus 휠 업로드
│   └── deploy.sh                #   make deploy — 호스트에 compose 적용, readyz·마이그레이션 확인
├── tests/                       # pytest (core는 가짜 어댑터, adapters는 testcontainers, http는 실제 서버)
├── tools/
│   └── pilot/                   #   Dex 그랜트 실측 · 하네스 첫 접촉 캡처 stub
├── Dockerfile                   # registry 이미지 (python:3.12-slim + git + gitleaks)
├── Makefile                     # make help — 자주 치는 명령의 이름
├── package.json                 # 개발 도구 고정(Trail Code 0.23.0 · OpenWiki 0.6.1). 배포물 아님, 이미지에 안 들어감
├── .mcp.json · .claude/ · .trail/  # Trail(코드 지도 + 세션 학습)·OpenWiki의 Claude Code 배선(훅·skill·MCP). docs/development.md
├── CLAUDE.md                    # 에이전트 지시: Trail(위치)·OpenWiki(이유) 역할 분담
├── openwiki/                    # 설계 이유 위키(한국어, claim에 file:line 증거). 커밋됨
├── pyproject.toml               # 워크스페이스 루트 (배포물 아님)
├── uv.lock
├── altera-rules.yml             # 규칙 게이트 표면 선언
├── REVIEW.md                    # 리뷰 루브릭 (altera-rules review 표면)
├── DESIGN.md                    # 설계와 결정의 근거
└── PLAN.md                      # 실행 계획 우산
```

## 판과 호환

네 패키지는 uv 워크스페이스의 lockstep 배포물이라 판이 같고 태그 `vX.Y.Z` 하나로 함께 나갑니다. 이미지에는 `server`만 들어가고, 카탈로그 저장소의 훅과 CI는 `core`와 `cli`를 그 태그로 설치합니다. 의존성은 전부 `==`로 고정합니다.

실측한 조합은 Python 3.12, uv 0.11.8, gitleaks 8.30.1, Harbor 0.24.0, Dex v2.45.1, PostgreSQL 17, Ollama 0.18.0(KURE-v1 GGUF BF16), Langfuse Cloud, Claude Code 2.1.258, Synology DSM LDAP Server입니다.

## 기여

브랜치를 따고 PR을 엽니다. 커밋 훅(`pre-commit install`)이 altera-rules 게이트(ruff·ast-grep·shellcheck·선언 드리프트)를 돌리고, CI가 pyright와 pytest를 돌립니다. 설계 계약을 바꾸는 변경은 코드보다 DESIGN.md §11의 결정 행이 먼저입니다. 개발 환경은 [docs/development.md](docs/development.md).

## 라이선스

미정입니다. 저장소 공개 전환과 함께 정합니다.
