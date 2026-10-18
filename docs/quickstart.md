# 빠른 시작

명령 둘로 레지스트리 전체를 내 머신에 띄우고, 하네스에서 로그인해 스킬을 찾아보는 10분 코스입니다. **평가·데모 전용**입니다. 비밀번호가 공개된 값이고 TLS가 없습니다. 운영 설치는 [operations.md](operations.md)입니다.

## 필요한 것

- Docker와 compose v2 (`docker compose version`)
- git
- Claude Code 2.1 이상 (다른 하네스는 [using.md](using.md)의 클라이언트 ID 표)

## 1. 띄우기

```sh
git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
docker compose -f docker/compose.quickstart.yml up -d --build --wait
```

첫 실행은 이미지를 빌드하므로 몇 분 걸립니다. `--wait`는 모든 컨테이너가 healthy가 될 때까지 기다립니다. 끝나면 `welcome` 컨테이너가 접속 방법을 찍습니다.

```sh
docker compose -f docker/compose.quickstart.yml logs welcome
```

편집할 파일도 내보낼 환경 변수도 없습니다. 모든 값에 기본값이 있고(`${VAR:-default}`), 바꾸고 싶으면 같은 이름의 환경 변수로 덮습니다(`REGISTRY_PORT=8010 docker compose …`). 같은 디렉토리에 `.env`가 있으면 compose가 그 값을 먼저 씁니다(개발용 `.env`와 변수 이름이 같습니다).

| 무엇 | 어디 |
|---|---|
| 레지스트리(MCP) | `http://localhost:8000/mcp` |
| OIDC issuer(Dex) | `http://localhost:5556/dex` |
| 읽을 수 있는 사용자 | `dev@example.com` / `password` (그룹 `harness-readers`) |
| 읽을 수 없는 사용자 | `outsider@example.com` / `password` (그룹 없음 — 로그인은 되고 도구 호출은 거부) |
| 기계 계정용 클라이언트 | `ci-runner` / `quickstart` |

카탈로그는 이 저장소의 `skills/`(`pin`·`write`)와 `tools/`(`scaffold`)를 bare git 저장소로 심은 것입니다. 실제 git 호스트가 없어도 레지스트리는 똑같이 fetch·검사·색인을 합니다.

## 2. 하네스에서 로그인

```sh
claude mcp add --transport http harness-catalog http://localhost:8000/mcp
```

`.mcp.json`의 그 항목에 `"oauth": { "clientId": "claude-code" }`를 더하고 Claude Code를 새로 시작합니다. `/mcp`에서 harness-catalog를 고르면 브라우저가 열리고, `dev@example.com` / `password`로 로그인합니다(Dex의 로컬 사용자는 이메일로 로그인합니다). 그다음 "카탈로그에 어떤 스킬 있어?"라고 물으면 두 스킬이 나옵니다.

`outsider@example.com`으로 로그인해 보면 인가의 경계가 보입니다. 로그인은 되지만 도구 호출이 거부됩니다.

## 3. 사람 없이 불러 보기

기계 계정 흐름(비밀번호 그랜트)은 터미널에서 바로 확인할 수 있습니다.

```sh
TOKEN=$(scripts/dev-token.sh http://localhost:5556/dex http://localhost:8000/mcp ci-runner quickstart dev@example.com password)
curl -s http://localhost:8000/mcp -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' -i | grep -i mcp-session-id
```

## 4. 스킬을 바꿔 보기

심은 카탈로그는 볼륨 안의 bare 저장소라 PR 대신 push로 바꿉니다.

```sh
docker compose -f docker/compose.quickstart.yml cp catalog-init:/catalog/catalog.git /tmp/catalog.git   # 꺼내서
git clone /tmp/catalog.git /tmp/catalog && cd /tmp/catalog                                                # 작업하고
# skills/<name>/ 을 고친 뒤 commit, 그리고 되돌려 넣는다:
docker compose -f docker/compose.quickstart.yml cp /tmp/catalog.git catalog-init:/catalog/catalog.git
```

레지스트리는 10초마다(`HC__FETCH_INTERVAL_SECONDS`) 받아 색인합니다. 진짜 흐름(브랜치·PR·CI·병합)은 git 호스트의 카탈로그 저장소에서 하며 [authoring.md](authoring.md)에 있습니다.

## 5. 지우기

```sh
docker compose -f docker/compose.quickstart.yml down -v
```

`-v`가 볼륨(색인 DB, 심은 카탈로그, 클론)을 지웁니다. 빼면 다음 `up`에서 그대로 이어집니다.

## 안에서 벌어지는 일

| 서비스 | 역할 |
|---|---|
| `postgres` | 색인과 Dex 저장소 |
| `dex` | 정적 사용자 둘과 클라이언트(`claude-code`·`codex`·`cursor`·`ci-runner`)를 가진 OIDC 서버 |
| `catalog-init` | 한 번 돌고 끝. `skills/`와 init 템플릿으로 bare 저장소를 심는다(멱등) |
| `registry` | 이 저장소에서 빌드한 이미지. `file:///catalog/catalog.git`을 받아 검사·색인하고 MCP로 섬긴다 |
| `welcome` | 준비가 끝나면 접속 안내를 로그에 찍는다 |

레지스트리가 Dex의 네트워크 네임스페이스를 공유하는(`network_mode: service:dex`) 이유는 issuer URL 하나(`http://localhost:5556/dex`)가 브라우저와 레지스트리 컨테이너 양쪽에서 같은 곳을 가리켜야 하기 때문입니다. 운영 compose는 프록시 뒤의 공개 호스트 이름으로 이 문제를 풀어 이 트릭이 없습니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| `Ports are not available: … 8000` 또는 `5556` | 그 포트를 쓰는 프로세스를 멈추거나 `REGISTRY_PORT=`·`DEX_PORT=`로 바꾼다 |
| `registry-1 is unhealthy` | `docker compose -f docker/compose.quickstart.yml logs registry`와 `curl -s localhost:8000/readyz`의 `reasons` |
| `/readyz`가 `repo_unreachable` | `catalog-init` 로그. 볼륨을 지우고(`down -v`) 다시 |
| 브라우저 로그인 뒤 "동적 등록을 지원하지 않는다" | `.mcp.json`에 `oauth.clientId`가 없다 |
