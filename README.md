# harness-catalog

팀의 에이전트 스킬 카탈로그를 git 저장소에 두고, 하네스(Claude Code·Codex·Cursor 등)가 MCP로 검색·적재하게 하는 레지스트리입니다. 스킬의 게시는 git의 PR → `main` 병합이고, 레지스트리는 `main`을 읽어 검사·색인만 합니다. 로그인은 팀 LDAP 계정(Dex가 OIDC로 연합), 인가는 LDAP 그룹 `harness-readers`입니다.

저장소는 둘입니다.

| 저장소 | 역할 |
|---|---|
| **코드 저장소** (이 저장소, `alteralab/harness-catalog`) | 레지스트리 서버, CLI, Harbor 플러그인, 컨테이너 이미지, compose, 템플릿 |
| **카탈로그 저장소** (예: `alteralab/catalog`) | `skills/<name>/` 디렉토리들. `main`에 병합된 것이 게시된 판 |

설계의 근거와 결정은 [DESIGN.md](DESIGN.md), 실행 계획과 원장은 [PLAN.md](PLAN.md)·`plans/`에 있습니다. 이 문서는 "어떻게 쓰나"만 적습니다.

## 1. 하네스에서 쓰기 (팀원)

필요한 것은 레지스트리 공개 URL과 사전 등록된 클라이언트 ID 둘입니다. 동적 클라이언트 등록(DCR)을 쓰지 않으므로 ID를 적어야 합니다.

| 하네스 | 클라이언트 ID |
|---|---|
| Claude Code | `claude-code` |
| Codex | `codex` |
| Cursor | `cursor` |

**Claude Code**

```sh
claude mcp add --transport http harness-catalog https://<레지스트리 호스트>/mcp
```

그 다음 `.mcp.json`(프로젝트) 또는 사용자 설정의 그 항목에 클라이언트 ID를 더합니다.

```json
{
  "mcpServers": {
    "harness-catalog": {
      "type": "http",
      "url": "https://<레지스트리 호스트>/mcp",
      "oauth": { "clientId": "claude-code" }
    }
  }
}
```

첫 도구 호출에서 브라우저 로그인 창이 열립니다. 팀 LDAP 계정으로 한 번 로그인하면 됩니다. `harness-readers` 그룹에 없는 계정은 로그인은 되지만 도구 호출이 거부됩니다.

**도구 넷**

| 도구 | 하는 일 |
|---|---|
| `list_skills` | 게시된 스킬 전체(이름·설명·`sha`) |
| `search_skills(query, limit)` | 이름·설명 검색. 검색어는 팀 Langfuse의 호출 기록에 남으니 비밀을 넣지 않습니다 |
| `load_skill(id, sha?)` | 스킬 본문(`SKILL.md`)과 파일 목록 |
| `get_skill_file(id, path, sha?)` | 스킬 디렉토리 안의 파일 하나 |

카탈로그에는 메타 스킬 둘이 먼저 있습니다. `pin-skill`은 매일 쓰는 스킬을 내 하네스 옆에 내려받아 두는 절차이고, `write-skill`은 새 스킬의 뼈대와 팀 규약입니다. 둘 다 `load_skill`로 세션에 넣어 씁니다.

**무인 읽기(CI·루프)** 는 LDAP 기계 계정 + 비밀번호 그랜트입니다. 기밀 클라이언트 `ci-runner`로 토큰을 받습니다.

```sh
TOKEN=$(scripts/dev-token.sh https://<호스트>/dex https://<호스트>/mcp ci-runner "$CI_RUNNER_SECRET" svc-harness "$SVC_PASSWORD")
```

## 2. 카탈로그 저장소 만들기 (운영자, 최초 1회)

1. git 호스트에 빈 저장소를 만듭니다(비공개 권장). 이름은 자유이고, Harbor·Langfuse에는 `org/repo`·`repo/<skill>`로 보입니다.
2. CLI로 초기화합니다. 운영자의 git 자격으로 clone → 파일 다섯(표지 `.harness-catalog`, `skills/.gitkeep`, README, pre-commit 설정, 호스트별 CI 워크플로)을 없는 것만 쓰고 → 커밋·push 합니다. 두 번 돌리면 변경 0입니다.

   ```sh
   uvx --from "harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v0.1.0#subdirectory=packages/cli" \
     harness-catalog init https://github.com/<org>/<catalog>.git
   ```

   템플릿에는 CLI 자기 판의 태그(`@v0.1.0`)가 박힙니다. 코드 저장소에 그 태그가 없으면 멈춥니다.
3. 레지스트리용 **읽기 전용 deploy key**를 등록하고 개인 키를 운영 비밀(§3)에 넣습니다. 확인: 컨테이너 안에서 `git fetch`는 되고 `git push --dry-run`은 거부됩니다.
4. 저자에게 저장소 write, 병합할 사람에게 admin을 줍니다. 저장소 read 이상 명단과 LDAP 그룹 `harness-readers`를 같게 유지합니다.
5. 코드 저장소가 비공개인 동안 카탈로그 CI가 `harness-catalog check`를 설치할 수 있게 읽기 자격을 시크릿으로 넣습니다. 둘 중 하나입니다.
   - `HARNESS_CATALOG_DEPLOY_KEY`: 코드 저장소에 등록한 읽기 전용 deploy key의 개인 키. 터미널에서 끝나고 만료가 없습니다.

     ```sh
     ssh-keygen -t ed25519 -N '' -f hc-ci-deploy
     gh repo deploy-key add hc-ci-deploy.pub --repo alteralab/harness-catalog --title "catalog CI (read)"
     gh secret set HARNESS_CATALOG_DEPLOY_KEY --repo <org>/<catalog> < hc-ci-deploy
     ```
   - `HARNESS_CATALOG_READ_TOKEN`: fine-grained PAT(대상 코드 저장소, Contents: Read). GitHub 웹에서만 만들 수 있습니다.
6. CI evals(선택)는 git 호스트 변수 `HARNESS_EVALS=true`와 self-hosted 러너의 `.env`(모델 자격 + Langfuse 키)로 켭니다. 하네스 목록은 `HARNESS_EVALS_AGENTS`(기본 `claude-code codex`).

스킬을 올리는 절차는 카탈로그 저장소의 README(템플릿: `packages/cli/src/harness_catalog_cli/templates/README.md`)에 있습니다. 요약하면 브랜치 → `skills/<name>/` → PR → CI `check` 초록 → 병합이고, `main` 직접 push와 강제 push는 하지 않습니다.

## 3. 레지스트리 설치 (운영자)

호스트 한 대에 compose로 셋을 띄웁니다: `registry`(이 이미지), `postgres`, `dex`. TLS와 라우팅은 앞의 리버스 프록시가 합니다(우리 팀은 `tailscale serve`).

```sh
git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
cp .env.example .env && chmod 600 .env          # REGISTRY_IMAGE, HC__*, DEX_ISSUER, HC_PUBLIC_URL …
scripts/make-secrets.sh secrets ~/.ssh/catalog-deploy-key   # 비밀 파일 여섯(멱등). 둘째 인자 = 카탈로그 deploy key 개인 키
docker compose up -d
curl -fsS http://127.0.0.1:8000/readyz
```

- 이미지는 `ghcr.io/alteralab/harness-catalog:<짧은 SHA>`(`main` 병합마다 self-hosted 러너가 빌드)이거나, 같은 호스트에서 `docker build -t harness-catalog:current .` 한 로컬 태그입니다. `.env`의 `REGISTRY_IMAGE`에 적습니다.
- 레지스트리 설정값은 다섯 + 선택 하나이고 환경 변수 `HC__*`로 받습니다. 비밀 둘(deploy key, DB 접속)은 `*_FILE`로 파일에서 읽습니다. 목록은 [docs/configuration.md](docs/configuration.md).
- `/healthz`는 살아 있음, `/readyz`는 준비됨입니다. 503이면 본문의 사유(`not_a_catalog`·`no_main_branch`·`repo_unreachable`·`layout_mismatch`)대로 §2의 1·3을 다시 봅니다.
- 프록시는 경로 셋을 열어야 합니다: `/mcp` → registry, `/dex` → dex, `/.well-known/oauth-protected-resource` → registry. 마지막을 안 열면 401 챌린지의 메타데이터 링크가 404가 됩니다.
- `HC__PUBLIC_URL`(예: `https://<호스트>/mcp`)이 토큰의 audience이자 RFC 9728 `resource`입니다. Dex 설정의 audience 클라이언트 ID와 같아야 합니다.

**Dex와 LDAP.** 기본 `docker/dex/config.yaml`은 빠른 시작용 정적 사용자입니다. 팀 LDAP(Synology LDAP Server)으로 바꾸려면 오버레이를 겹칩니다.

```sh
docker compose -f docker-compose.yml -f examples/synology-ldap/docker-compose.override.yml up -d
```

LDAP 호스트·바인드 DN·베이스 DN은 `.env`의 `LDAP_*`, 바인드 비밀번호는 `secrets/ldap_bind_pw`입니다. 그룹 `harness-readers`와 기계 계정(예: `svc-harness`)은 LDAP 쪽에서 만듭니다. 다른 IdP로 옮기면 Dex는 빠지고 `HC__OIDC_ISSUER`만 바뀝니다.

**운영 명령.** `main`이 되감겼을 때(강제 push 등) 레지스트리는 색인을 멈추고 `/readyz`에 사유를 냅니다. 받아들이려면:

```sh
docker compose exec registry harness-catalog-server reindex --accept-rewind && docker compose restart registry
```

## 4. CLI

```sh
harness-catalog check [repo] --rev INDEX|HEAD|<commit> --base <commit>   # 저장소 구조와 스킬 규칙 판정. 종료 0 통과 / 1 위반 / 2 검사기 실패
harness-catalog init <repo-url> [--pin vX.Y.Z] [--host github|gitlab]
harness-catalog config list        # 실효 설정값
harness-catalog config docs        # docs/configuration.md 생성
```

`check`는 카탈로그 저장소의 pre-commit 훅과 CI가 부르는 그 명령입니다. 항목 열 가지(표지와 필수 파일, `skills/` 배치, 스킬 형식, 비밀 검출(gitleaks), 은퇴 이름 재사용, `replaced-by` 연쇄, 파일 수·크기, `requires-tools` 문법, 그리고 경고 둘인 대체 권고와 공유 스크립트 어긋남)를 판정하고, gitleaks가 없으면 검사기 실패(2)로 멈춥니다.

## 5. 개발

```sh
uv sync -p 3.12
cp .env.example .env                     # 비밀은 openssl rand -base64 32
docker compose -f docker-compose.dev.yml up -d        # postgres + dex만. 레지스트리는 호스트에서
set -a; . ./.env; set +a
uv run harness-catalog-server serve --port 8000       # HC__CATALOG_REPO_URL=file:///path/to/catalog 도 됩니다(deploy key 빈 문자열)
```

- 시험: `uv run pytest -q tests`. `pg` 표시 시험은 docker(testcontainers), `http` 표시 시험은 개발 compose의 Dex와 토큰(`HC_TEST_TOKEN`)이 필요합니다. macOS Docker Desktop은 `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`이 필요합니다.
- 타입: `uv run pyright packages tests tools`. 게이트: `pre-commit install` 뒤 커밋마다 altera-rules(ruff·ast-grep·shellcheck·선언)가 돕니다.
- 기계 계정 토큰: `scripts/dev-token.sh <issuer> <public-url> ci-runner <secret> <user> <password>`. 사람 토큰(PKCE·장치 흐름) 실측은 `tools/pilot/dex_grants.py`.
- Dex 비밀 등 환경 변수는 `docker/dex/config.yaml`이 gomplate `{{ getenv }}`로 읽습니다. Dex 자체 `$VAR` 확장은 저장소·커넥터 설정에서만 됩니다.

## 6. 배치

```
packages/core/            harness-catalog-core    모델·카탈로그 앱·검사 항목·git/검증 어댑터 (hexagonal, 포트 셋)
packages/server/          harness-catalog-server  MCP 서버(Streamable HTTP)·OIDC 검증·PostgreSQL·스케줄러·마이그레이션
packages/cli/             harness-catalog-cli     check·init·config, 카탈로그 저장소 템플릿
packages/harbor-langfuse/ harbor-langfuse         Harbor 플러그인: evals 결과를 Langfuse 데이터셋 실험으로
skills/                   pin-skill·write-skill   첫 카탈로그에 올리는 메타 스킬 둘(+ evals)
docker/, examples/        Dex 설정·PostgreSQL 초기화, Synology LDAP 오버레이, 카탈로그 템플릿
scripts/, tools/pilot/    비밀 생성·토큰, Dex/하네스 실측 도구
```

네 패키지는 uv 워크스페이스의 lockstep 배포물이고 판이 같습니다(태그 `vX.Y.Z`). 이미지는 `server`만 담고, 카탈로그 저장소의 훅·CI는 `core`+`cli`를 git 태그로 설치합니다.
