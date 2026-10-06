# harness-catalog

팀이 만든 에이전트 스킬을 한 곳에 모아 두고, 각자의 하네스(Claude Code·Codex·Cursor 등)에서 찾아 쓰고 곁에 두게 하는 플랫폼입니다. 이 문서는 사용자 가이드입니다. 왜 이렇게 설계했는지는 [DESIGN.md](DESIGN.md)에, 무엇을 어떤 순서로 만들었고 무엇이 남았는지는 [PLAN.md](PLAN.md)와 `plans/`에 있습니다.

## 한눈에 보는 그림

스킬 하나는 git 저장소의 디렉토리 하나입니다. `skills/<name>/` 아래에 `SKILL.md`가 있고, 필요하면 스크립트와 참고 파일, 평가 과제가 따라옵니다. 그 저장소를 **카탈로그 저장소**라고 부릅니다. 스킬을 만들고 고치고 지우는 일은 전부 이 저장소에서 브랜치를 따고 PR을 열고 `main`에 병합하는 일이고, `main`에 있는 것이 곧 게시된 것입니다. 병합한 사람이 그 판을 인증한 사람입니다.

**레지스트리**는 그 `main`을 주기적으로 받아 검사하고 색인해 두었다가, 하네스가 MCP로 물으면 답하는 서버입니다. 검색하고, 본문을 주고, 파일을 주는 도구 넷이 전부이고 쓰기 도구는 없습니다. 저장소에는 읽기 전용 deploy key로만 닿습니다. 그래서 레지스트리가 뚫려도 카탈로그는 바뀌지 않고, 레지스트리가 죽어도 카탈로그는 git에 그대로 있습니다.

로그인은 팀 LDAP 계정으로 한 번 합니다. 레지스트리 앞의 Dex가 LDAP을 OIDC로 감싸고, LDAP 그룹 `harness-readers`에 든 사람만 도구를 부를 수 있습니다. 저장소의 읽기 권한 명단과 이 그룹을 같게 유지하는 것이 운영자의 일입니다.

이 저장소(`alteralab/harness-catalog`)는 레지스트리와 CLI, 컨테이너 이미지, 카탈로그 저장소 템플릿을 담은 **코드 저장소**입니다. 카탈로그 저장소(우리 팀은 `alteralab/catalog`)와는 별개입니다.

누구인지에 따라 읽을 곳이 다릅니다. 스킬을 쓰려는 팀원은 §1, 스킬을 만들어 올리려는 저자는 §2, 레지스트리와 저장소를 세우는 운영자는 §3, 이 코드를 고치려는 개발자는 §4를 읽으면 됩니다.

## 1. 하네스에서 스킬 쓰기

### 등록과 첫 로그인

필요한 것은 레지스트리의 공개 URL과 하네스의 클라이언트 ID 둘뿐입니다. 레지스트리는 동적 클라이언트 등록을 쓰지 않고 하네스마다 ID를 미리 등록해 두었기 때문에, 그 ID를 설정에 적어야 합니다. Claude Code는 `claude-code`, Codex는 `codex`, Cursor는 `cursor`입니다.

Claude Code라면 명령 하나로 서버를 더하고,

```sh
claude mcp add --transport http --scope user harness-catalog https://<레지스트리 호스트>/mcp
```

`~/.claude.json`(프로젝트에만 두려면 `.mcp.json`)의 그 항목에 클라이언트 ID를 더합니다.

```json
"harness-catalog": {
  "type": "http",
  "url": "https://<레지스트리 호스트>/mcp",
  "oauth": { "clientId": "claude-code" }
}
```

Claude Code를 새로 시작해 `/mcp`에서 harness-catalog를 고르면 브라우저가 열립니다. 팀 LDAP 계정으로 로그인하면 "Authentication successful"이 뜨고 그 뒤로는 묻지 않습니다. 로그인은 되는데 도구 호출이 거부된다면 계정이 `harness-readers` 그룹에 없는 것이니 운영자에게 말하면 됩니다. Codex와 Cursor는 같은 방식으로 ID가 등록되어 있지만 아직 실제로 붙여 보지는 않았습니다.

### 일상의 사용

등록이 끝나면 하네스에게 말로 시키면 됩니다. "카탈로그에 어떤 스킬 있어?"라고 하면 에이전트가 `list_skills`를 불러 이름과 설명을 보여 주고, "자막 뽑는 스킬 있어?"처럼 물으면 `search_skills`로 찾습니다. 마음에 드는 것을 "그거 불러와"라고 하면 `load_skill`로 본문을 받아 이번 세션의 지식으로 삼습니다. 스킬에 스크립트가 딸려 있으면 에이전트가 `get_skill_file`로 받아 돌립니다. 적재는 세션 단위입니다. 다음 세션에서는 다시 부르면 됩니다.

매일 쓰는 스킬은 곁에 두는 편이 낫습니다. 카탈로그에 든 `pin-skill`이 그 절차를 압니다. 먼저 `pin-skill`을 적재하고 "yt-subs 스킬 pin 해줘"라고 하면 에이전트가 범위 하나를 묻습니다. 프로젝트에 두면 `.agents/skills/<name>/`에 들어가 저장소에 커밋되고 팀원과 공유되며, 사용자에게 두면 `~/.agents/skills/<name>/`에 들어가 나만 씁니다. 에이전트는 스킬의 파일 전부를 한 판(`sha`)으로 받아 임시 디렉토리에서 대조한 뒤 한 번에 제자리로 옮기고, `.claude/skills/<name>`에는 그곳을 가리키는 링크를 둡니다. 그래서 Claude Code든 Codex든 같은 사본을 봅니다. 옆에 남는 `PINNED` 한 줄이 받은 판의 기록입니다.

내려받은 사본은 그 시점의 판입니다. 카탈로그가 바뀌어도 저절로 따라오지 않습니다. "새 판 있어?"라고 하면 에이전트가 `PINNED`의 `sha`와 `list_skills`의 `sha`를 견줘 알려 주고, "갱신해줘"라고 하면 같은 절차로 다시 받습니다. 목록에서 사라진 스킬은 은퇴한 것입니다.

한 가지만 지켜 주세요. `search_skills`의 검색어는 팀 Langfuse의 호출 기록에 남습니다. 토큰이나 비밀번호, 개인 정보를 검색어에 적지 않습니다.

### 사람 없이 쓰기

CI나 자동화 루프처럼 사람이 로그인할 수 없는 자리에는 LDAP 기계 계정을 씁니다. 운영자가 LDAP에 계정(우리 팀은 `svc-harness`)을 만들어 `harness-readers`에 넣어 두면, 기밀 클라이언트 `ci-runner`의 비밀번호 그랜트로 토큰을 받을 수 있습니다.

```sh
TOKEN=$(scripts/dev-token.sh https://<호스트>/dex https://<호스트>/mcp ci-runner "$CI_RUNNER_SECRET" svc-harness "$SVC_PASSWORD")
```

이 토큰을 `Authorization: Bearer`로 붙여 같은 MCP 엔드포인트를 부르면 됩니다. 권한은 사람과 똑같이 읽기뿐입니다.

## 2. 스킬 만들어 올리기

### 스킬의 모양

스킬은 agentskills.io 형식을 따릅니다. `skills/<name>/SKILL.md` 하나가 필수이고, frontmatter의 `name`은 1~64자의 소문자·숫자·하이픈으로 디렉토리 이름과 같아야 합니다. `description`은 에이전트가 이 스킬을 고를지 판단하는 유일한 단서입니다. 그래서 첫 문장에 무엇을 하는지와 사용자가 실제로 입에 올릴 낱말이 들어가야 하고, 쓰지 말아야 할 상황도 한 줄 있으면 좋습니다. 호스트가 긴 설명을 자를 수 있어 뒤쪽은 읽히지 않을 수 있습니다.

스킬이 시스템 도구를 요구하면 두 곳에 적습니다. `compatibility`에는 사람이 읽을 문장("yt-dlp와 ffmpeg이 필요합니다")을, `metadata.requires-tools`에는 기계가 거를 공백 구분 목록(`"yt-dlp ffmpeg uv"`)을 둡니다. 검색 결과에 둘 다 실리므로 적재하기 전에 알 수 있습니다.

결정적인 일, 즉 계산·변환·조회는 `scripts/`의 스크립트로 두고 판단만 본문 지시로 남기는 것이 팀 규약입니다. 파이썬 스크립트는 맨 위 PEP 723 주석에 의존성을 적고 `uv run --script scripts/x.py`로 부릅니다. 실행 비트에 기대지 않고, 의존성 판은 `==`로 고정합니다. 실패할 때의 종료 코드도 정해져 있습니다. 2는 입력 오류, 3은 대상 없음, 4는 시스템 도구 없음입니다. 4일 때는 설치 명령을 함께 찍어 줍니다.

`evals/`에는 Harbor 태스크를 둡니다. 최소한 한 쌍입니다. 이 스킬을 써야 풀리는 과제 하나와, 비슷해 보이지만 쓰면 안 되는 과제 하나(`no-trigger-*`). 전자는 스킬이 값을 하는지, 후자는 description이 과하게 발동하지 않는지 잽니다.

### 올리는 흐름

카탈로그 저장소를 clone해 두고, 하네스 세션에서 카탈로그의 `write-skill`을 적재한 뒤 "이 절차를 스킬로 만들자"라고 하면 에이전트가 위 규약대로 뼈대를 잡아 줍니다. 손으로 해도 같습니다.

먼저 같은 일을 하는 스킬이 이미 있는지 `search_skills`로 봅니다. 있으면 새로 만들지 말고 그 스킬을 고칩니다. 없으면 `main`을 최신으로 하고 브랜치 `skill/<name>`을 따서 `skills/<name>/`을 씁니다. 커밋하기 전에 `pre-commit install`을 한 번 해 두면 커밋마다 `harness-catalog check`가 돌아 규약 위반을 그 자리에서 잡습니다. 직접 돌리려면 저장소 루트에서 `harness-catalog check . --rev HEAD --base main`입니다.

evals는 스킬을 넣고 한 번, 빼고 한 번 돌립니다.

```sh
harbor run --path skills/<name>/evals --agent claude-code --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin
harbor run --path skills/<name>/evals --agent claude-code --env docker --plugin harbor_langfuse:LangfusePlugin
```

둘 다 통과하면 모델이 이미 혼자 하는 일이라 스킬이 값을 하지 않는 것이고, 넣었을 때만 통과하면 스킬이 값을 한 것입니다. 결과는 Langfuse 데이터셋 `<카탈로그>/<스킬>`에 run 둘로 남고, PR 본문에 그 링크를 적습니다. Harbor가 없거나 음성 과제처럼 자동 판정이 어려우면 사람이 눈으로 보고 Langfuse에 주석으로 남겨도 됩니다.

PR을 열면 CI가 같은 `check`를 돌립니다. 붉으면 병합하지 않습니다. 병합은 사람이 git 호스트에서 하고, 그 사람이 이 판의 인증자입니다. 병합되면 레지스트리가 다음 주기(기본 60초)에 받아 색인하므로 곧 `list_skills`에 나타납니다. `main`에 직접 push하거나 강제 push하지 않는 것은 설정이 아니라 규율입니다.

### 게이트가 거부하는 것

`harness-catalog check`는 열 가지를 봅니다. 저장소에 표지 파일(`.harness-catalog`)과 필수 파일이 있는지, `skills/` 바로 아래가 스킬 디렉토리뿐인지, 각 `SKILL.md`가 형식에 맞는지(agentskills.io의 참조 검증기로), gitleaks가 비밀을 찾지 못했는지, 은퇴한 이름을 다시 쓰지 않았는지, `replaced-by`가 실재하는 스킬을 가리키고 연쇄나 순환이 없는지, 파일 수와 크기가 한도 안이고 심볼릭 링크가 없는지, `requires-tools` 문법이 맞는지. 여기까지가 오류이고 종료 코드 1입니다. 스킬을 지우면서 `replaced-by`를 안 적은 것과, 여러 스킬이 같은 상대 경로의 스크립트를 갖는데 내용이 어긋난 것은 경고로만 냅니다. gitleaks가 설치되어 있지 않거나 이력을 못 읽으면 검사기 자체가 실패해 종료 코드 2입니다. 비밀 검출은 fail-closed라 gitleaks 없이는 통과가 없습니다.

### 고치기, 은퇴시키기, 대체하기

고치는 것은 같은 디렉토리를 브랜치에서 바꿔 PR을 여는 것입니다. 병합되면 트리 `sha`가 바뀌고, pin해 둔 사람은 "새 판 있어?"로 압니다. 옛 판이 사라지지는 않습니다. `load_skill(id, sha=<옛 sha>)`는 `main` 이력에서 그 판을 찾아 돌려주므로, 어떤 세션이 어느 판을 썼는지 기록된 `sha`로 언제든 되짚을 수 있습니다.

은퇴는 디렉토리를 지우는 PR입니다. 대체 스킬이 있으면 지우기 전에 옛 스킬의 `metadata.replaced-by`에 새 이름을 적어 한 판 두었다가 지웁니다. 그러면 옛 이름을 찾는 사람에게 검색 결과의 `replaced_by`가 새 이름을 안내합니다. 은퇴한 이름은 다시 쓸 수 없습니다. 누군가의 `PINNED`가 그 이름을 가리키고 있을 수 있기 때문입니다.

## 3. 운영

### 전체 구성

운영 호스트 한 대에 compose로 컨테이너 셋을 띄웁니다. `registry`(이 저장소의 이미지), `postgres`(색인과 Dex 저장소), `dex`(LDAP을 OIDC로 감싸는 인가 서버). TLS와 라우팅은 앞의 리버스 프록시가 맡고, 우리 팀은 mini의 `tailscale serve`를 씁니다. 프록시는 경로 셋을 열어야 합니다. `/mcp`와 `/.well-known/oauth-protected-resource`는 registry로, `/dex`는 dex로. 마지막 경로를 빠뜨리면 첫 접촉의 401 응답이 가리키는 메타데이터가 404가 되어 하네스가 로그인 절차를 시작하지 못합니다.

레지스트리가 아는 설정값은 여섯입니다. 카탈로그 저장소 URL, 읽기 전용 deploy key, OIDC issuer, 레지스트리 공개 URL, PostgreSQL 접속, 그리고 fetch 주기(기본 60초). 환경 변수 `HC__*`로 받고 비밀 둘은 `*_FILE`로 파일에서 읽습니다. 이름과 뜻은 [docs/configuration.md](docs/configuration.md)에 있습니다. 공개 URL(예: `https://<호스트>/mcp`)은 토큰의 audience이자 RFC 9728의 resource라 Dex 설정의 audience 클라이언트 ID와 글자까지 같아야 합니다.

### 카탈로그 저장소 세우기

git 호스트에 빈 저장소를 만듭니다. 이름은 자유이고 비공개가 좋습니다. 그다음 CLI로 초기화합니다.

```sh
uvx --from "harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v0.1.0#subdirectory=packages/cli" \
  harness-catalog init https://github.com/<org>/<catalog>.git
```

`init`은 운영자의 git 자격으로 저장소를 받아 표지 파일, `skills/.gitkeep`, README, pre-commit 설정, 호스트(GitHub 또는 GitLab)에 맞는 CI 워크플로를 없는 것만 쓰고 커밋·push합니다. 두 번 돌리면 아무것도 하지 않습니다. 워크플로와 pre-commit 설정에는 CLI 자기 판의 태그가 박히므로 코드 저장소에 그 태그가 있어야 하고, 없으면 멈춥니다.

레지스트리가 읽을 **읽기 전용 deploy key**를 만들어 등록하고 개인 키를 운영 비밀에 넣습니다. 저자에게는 저장소 write를, 병합할 사람에게는 admin을 줍니다. 저장소를 읽을 수 있는 사람의 명단과 LDAP 그룹 `harness-readers`를 같게 유지하는 것이 접근 통제의 전부입니다.

코드 저장소가 비공개인 동안은 카탈로그의 CI가 `harness-catalog check`를 설치하려고 코드 저장소를 읽어야 합니다. 가장 간단한 길은 코드 저장소에 읽기 전용 deploy key를 하나 더 등록하고 그 개인 키를 카탈로그 저장소 시크릿 `HARNESS_CATALOG_DEPLOY_KEY`에 넣는 것입니다.

```sh
ssh-keygen -t ed25519 -N '' -f hc-ci-deploy
gh repo deploy-key add hc-ci-deploy.pub --repo alteralab/harness-catalog --title "catalog CI (read)"
gh secret set HARNESS_CATALOG_DEPLOY_KEY --repo <org>/<catalog> < hc-ci-deploy
```

fine-grained PAT(Contents: Read)를 `HARNESS_CATALOG_READ_TOKEN`으로 넣어도 되지만 GitHub 웹에서만 만들 수 있고 만료가 있습니다. 코드 저장소를 공개하면 둘 다 필요 없습니다.

CI에서 evals까지 돌리려면 git 호스트 변수 `HARNESS_EVALS=true`를 두고 self-hosted 러너의 `.env`에 하네스의 모델 자격과 Langfuse 키를 넣습니다. 변수가 없으면 evals 잡은 만들어지지 않고 `check`만 돕니다. 하네스 목록은 `HARNESS_EVALS_AGENTS`(기본 `claude-code codex`)로 바꿉니다.

### 레지스트리 띄우기

```sh
git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
cp .env.example .env && chmod 600 .env
scripts/make-secrets.sh secrets ~/.ssh/catalog-deploy-key
docker compose up -d
curl -fsS http://127.0.0.1:8000/readyz
```

`.env`에는 이미지 태그(`REGISTRY_IMAGE`), 레지스트리 설정값, Dex의 issuer와 공개 URL을 적습니다. `make-secrets.sh`는 비밀 파일 여섯을 만듭니다. DB 비밀번호 셋과 `ci-runner` 시크릿은 무작위로 만들고, deploy key는 둘째 인자로 받은 파일을 복사하며, DB 접속 문자열은 조립합니다. 이미 있는 파일은 건드리지 않습니다. 이미지는 `main` 병합마다 self-hosted 러너가 빌드해 `ghcr.io/alteralab/harness-catalog:<짧은 SHA>`로 올리는 것을 쓰거나, 같은 호스트에서 `docker build -t harness-catalog:current .`로 만든 로컬 태그를 씁니다.

`/healthz`는 프로세스가 살아 있는지, `/readyz`는 섬길 준비가 됐는지입니다. `/readyz`가 503이면 본문에 이유가 있습니다. `repo_unreachable`이면 URL이나 deploy key를, `no_main_branch`면 `init`을 아직 안 돌린 빈 저장소를, `not_a_catalog`·`unsupported_layout`·`layout_mismatch`면 표지 파일을 봅니다.

기본 Dex 설정(`docker/dex/config.yaml`)은 빠른 시작용 정적 사용자입니다. 팀 LDAP으로 바꾸려면 오버레이를 겹칩니다.

```sh
docker compose -f docker-compose.yml -f examples/synology-ldap/docker-compose.override.yml up -d
```

LDAP 호스트·바인드 DN·베이스 DN은 `.env`의 `LDAP_*`에, 바인드 비밀번호는 `secrets/ldap_bind_pw`에 둡니다. 그룹 `harness-readers`와 기계 계정은 LDAP 쪽에서 만듭니다. 나중에 사내 IdP로 옮기면 Dex는 빠지고 `HC__OIDC_ISSUER`만 바뀝니다.

### 운영 중에 생기는 일

`main`이 되감기면(강제 push 등) 레지스트리는 색인을 멈추고 `/readyz`에 알립니다. 의도한 것이면 받아들이고 재기동합니다.

```sh
docker compose exec registry harness-catalog-server reindex --accept-rewind && docker compose restart registry
```

이미지를 올리는 것은 `.env`의 `REGISTRY_IMAGE`를 바꾸고 `docker compose up -d`입니다. 몇 초 끊깁니다. 백업 대상은 없습니다. 색인은 `main`에서 언제든 다시 지을 수 있고, 사용 기록과 평가 결과는 Langfuse에 있습니다. 도구 호출은 OpenTelemetry 스팬으로 나가며 `OTEL_EXPORTER_OTLP_*` 변수로 켭니다.

## 4. 개발

네 패키지가 uv 워크스페이스에 함께 있습니다. `core`는 모델·카탈로그 앱·검사 항목과 git/검증 어댑터, `server`는 MCP 서버와 OIDC 검증·PostgreSQL·스케줄러, `cli`는 `check`·`init`과 카탈로그 템플릿, `harbor-langfuse`는 Harbor 결과를 Langfuse로 보내는 플러그인입니다. 넷은 같은 판으로 함께 태그됩니다. 이미지에는 `server`만 들어가고, 카탈로그 저장소의 훅과 CI는 `core`와 `cli`를 git 태그로 설치합니다. 의존성 판은 전부 `==`로 고정하며 올리는 것은 명시 행위입니다.

```sh
uv sync -p 3.12
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d      # postgres + dex
set -a; . ./.env; set +a
uv run harness-catalog-server serve --port 8000
```

개발 compose는 postgres와 dex만 띄우고 레지스트리는 호스트에서 돌립니다. 카탈로그는 `HC__CATALOG_REPO_URL=file:///…`로 로컬 저장소를 가리켜도 되고 그때 deploy key는 빈 문자열입니다. 시험은 `uv run pytest -q tests`이고, `pg` 표시 시험은 docker(testcontainers)를, `http` 표시 시험은 개발 compose의 Dex와 토큰을 필요로 합니다. 타입은 `uv run pyright packages tests tools`, 규칙 게이트(altera-rules)는 `pre-commit install` 뒤 커밋마다 돕니다. 새 판을 내는 것은 네 `pyproject.toml`의 version을 함께 올리고 `vX.Y.Z` 태그를 push하는 것이고, `main` 병합마다 이미지가 빌드됩니다.

## 부록: 명령과 도구

CLI `harness-catalog`는 셋입니다. `check [repo] --rev INDEX|HEAD|<commit> --base <commit>`은 저장소와 스킬을 판정해 0·1·2로 끝나고, `init <repo-url> [--pin vX.Y.Z] [--host github|gitlab]`은 카탈로그 저장소를 세우며, `config list`와 `config docs`는 레지스트리 설정값을 보여 주고 문서로 씁니다.

MCP 도구는 넷입니다. `list_skills()`는 게시된 스킬 전체를 이름·설명·`sha`·`replaced_by`·`requires_tools`·`compatibility`와 함께 주고, `search_skills(query, limit=10)`은 같은 모양으로 검색 결과를 줍니다. `load_skill(id, sha=None)`은 `SKILL.md` 본문과 `sha`·`commit`·`metadata`·파일 목록을, `get_skill_file(id, path, sha=None)`은 파일 하나를 텍스트(`text`) 또는 바이너리(`base64`)로 줍니다. `sha`를 주면 `main` 이력에서 그 판을 찾고, 이력에서 풀리지 않으면 `unknown_version`을 돌려줍니다.
