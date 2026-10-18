# 하네스에서 스킬 쓰기

팀원이 자기 하네스에서 카탈로그의 스킬을 찾고, 세션에 넣고, 곁에 두는 법입니다.

## 전제 조건

- 레지스트리 공개 URL. 우리 팀은 `https://alteraui-macmini.tail2f9fe3.ts.net/mcp`이고 tailnet 안에서만 닿습니다(Tailscale을 켭니다).
- LDAP 계정이 그룹 `harness-readers`에 있을 것. 없으면 로그인은 되지만 도구 호출이 거부됩니다. 운영자에게 요청합니다.
- 하네스. Claude Code 2.1 이상은 실측했습니다. Codex·Cursor는 클라이언트 ID가 등록되어 있지만 아직 붙여 보지 않았습니다.

## 1. 등록

레지스트리는 동적 클라이언트 등록을 쓰지 않고 하네스마다 ID를 미리 등록해 두었습니다. 그래서 URL과 함께 ID를 적어야 합니다.

| 하네스 | 클라이언트 ID |
|---|---|
| Claude Code | `claude-code` |
| Codex | `codex` |
| Cursor | `cursor` |

**Claude Code.** 사용자 범위(모든 프로젝트)로 더합니다.

```sh
claude mcp add --transport http --scope user harness-catalog https://<레지스트리 호스트>/mcp
```

그다음 `~/.claude.json`(프로젝트에만 두려면 `.mcp.json`)의 그 항목에 `oauth.clientId`를 더합니다.

```json
"harness-catalog": {
  "type": "http",
  "url": "https://<레지스트리 호스트>/mcp",
  "oauth": { "clientId": "claude-code" }
}
```

이미 떠 있는 세션은 새 서버를 모릅니다. Claude Code를 새로 시작합니다.

## 2. 첫 로그인

`/mcp`에서 harness-catalog를 고르면 브라우저가 열립니다. Dex 로그인 화면에서 LDAP 계정으로 로그인하면 터미널에 "Authentication successful. Connected to harness-catalog."가 뜹니다. 그 뒤로는 묻지 않습니다(토큰이 하네스에 저장되고 갱신됩니다).

## 3. 찾고 적재하기

레지스트리가 내는 도구는 넷이고 전부 읽기입니다. 전체 목록을 돌려주는 도구는 없습니다. 주제로 좁혀 검색합니다. 동사는 `get` 하나입니다. 넷 다 식별자를 받아 정의를 돌려주고, 받은 것을 문맥에 넣는 것은 받아 간 쪽의 일입니다.

| 도구 | 하는 일 |
|---|---|
| `search_skills(query, limit?)` | 스킬 어휘 검색(기본 10, 상한 20): 이름·설명·`sha`(판)·`compatibility`·`has_scripts` |
| `get_skill(id, sha?, path?, archive?)` | 기본은 SKILL.md 본문과 메타데이터·파일 목록. `path`를 주면 그 파일 하나(1 MB, 본문은 null). `archive=true`면 한 판 전체를 tar로 받는 다운로드 명세(URI + 5분 헤더 토큰 + sha256)를 함께 — 파일은 모델을 지나지 않습니다. §4 pin이 씁니다. `sha`를 주면 그 판 |
| `search_tools(query, limit?)` | 도구 어휘 검색: 이름·설명·`sha`·`kind`·`server`. §5.5 |
| `get_tool(id, sha?)` | `tool.json` 전체. `kind: mcp`면 참조하는 `server.json`을, `kind: script`면 다운로드 명세를 함께. §5.5 |

네 도구 모두 `tools/list`에 `outputSchema`를 싣습니다. 성공 응답의 `structuredContent`는 그 스키마에 맞고, `content[0].text`에 같은 JSON이 있습니다. 오류는 `isError`와 `{code, detail}`입니다. 스키마의 정본은 서버의 `driving/responses.py`입니다.

하네스에게 말로 시킵니다. 에이전트가 적절한 도구를 고릅니다.

| 말 | 에이전트가 부르는 도구 |
|---|---|
| "카탈로그에 어떤 스킬 있어?" | 전체 목록 도구는 없습니다. 주제를 붙여 `search_skills("…")` |
| "유튜브 자막 뽑는 스킬 있어?" | `search_skills("유튜브 자막")` |
| "yt-subs 불러와" | `get_skill("yt-subs")` |
| (본문이 참조 파일을 가리킬 때) | `get_skill("yt-subs", path="references/x.md", sha=…)` |
| "yt-subs 내려받아" | `get_skill("yt-subs", sha=…, archive=true)` → 명세로 셸에서 `curl`로 받기(§4) |

`search_skills`의 응답은 이런 모양입니다(줄임).

```json
{"skills": [
  {"name": "pin", "description": "카탈로그(harness-catalog)의 스킬이나 도구를 내 하네스 옆에 내려받아(pin) 두고 …",
   "sha": "c8991b7e1bcd40ea1cf397ecec58fb1f21702b33", "compatibility": null, "has_scripts": false},
  {"name": "write", "description": "팀 카탈로그(harness-catalog)에 올릴 새 스킬이나 새 도구의 뼈대를 만들고 …",
   "sha": "…", "compatibility": "카탈로그 저장소의 로컬 클론과 git·gh(PR 생성) …", "has_scripts": true}
]}
```

`sha`는 그 스킬 디렉토리의 git 트리 해시이고 곧 판입니다. `compatibility`는 그 스킬이 환경에 요구하는 것을 사람이 읽는 문장이고(대부분 없음), `has_scripts`는 스킬 안에 `scripts/`가 있다는 표시입니다 — 루프는 그런 스킬을 후보에서 뺍니다(세션 전용). 검색에 더 나오지 않는 이름은 은퇴한 스킬입니다.

적재는 **세션 단위**입니다. `get_skill`로 받은 본문은 이번 세션의 지식이고, 다음 세션에서는 다시 부릅니다.

## 4. 곁에 두기(pin)

매일 쓰는 스킬은 내려받아 둡니다. 서버에는 내려받기 도구가 없고, 카탈로그의 `pin` 스킬이 판단을, CLI `hc pin`이 결정적인 받기·대조·교체를 맡습니다.

1. `pin`을 적재합니다. "pin 불러와".
2. "yt-subs 스킬 pin 해줘"라고 합니다.
3. 에이전트가 범위 하나만 묻습니다. **프로젝트**면 `.agents/skills/<name>/`에 들어가 저장소에 커밋되고 팀원과 공유됩니다. **사용자**면 `~/.agents/skills/<name>/`에 들어가 나만 씁니다.
4. 에이전트가 파일 전부를 한 판(`sha`)으로 받아 임시 디렉토리에서 대조한 뒤 한 번에 제자리로 옮기고, `.claude/skills/<name>`에 그곳을 가리키는 심볼릭 링크를 둡니다. Claude Code·Codex·Cursor가 같은 사본을 봅니다.
5. 디렉토리 안의 `PINNED` 한 줄(`<name> <sha> <시각>`)이 받은 판의 기록입니다.

같은 이름의 디렉토리가 이미 있으면 에이전트가 멈추고 알립니다. 카탈로그 밖의 개인 스킬과 이름이 겹치는 경우입니다. 덮어쓰기는 명시해야 합니다.

## 5. 새 판과 은퇴

내려받은 사본은 그 시점의 판이고 저절로 바뀌지 않습니다. "새 판 있어?"라고 하면 에이전트가 두 범위의 `PINNED`를 읽어 이름마다 `search_skills(<이름>)`의 `sha`와 견줍니다. "갱신해줘"라고 하면 같은 절차로 다시 받되, 기존 사본은 새 사본이 제자리에 들어갈 때까지 남겨 둡니다. 검색에 더 나오지 않는 이름은 은퇴한 스킬입니다.

## 5.5 도구 찾기(toolbox)

카탈로그는 스킬 말고 **도구**도 싣습니다(DESIGN §11 2026-10-11). 도구는 스키마가 있는 호출 가능한 것이고, 구현은 둘 중 하나입니다.

- `script` — 카탈로그 안의 스크립트. `get_tool(archive=true)` 응답을 `hc pin --scope project`에 넘겨 `.agents/tools/<name>/`에 놓으면 같은 명령이 `.mcp.json`에 `toolbox` 항목을 써 두고, `hc toolbox .agents/tools`가 그 디렉토리의 도구를 MCP 도구로 띄웁니다. 호출마다 어댑터가 `runtime.command`를 **셸 없이 argv로** 실행합니다. 입력은 `inputSchema`에 맞는 JSON 객체 하나를 stdin으로, 결과는 stdout이고, `tool.json`에 `outputSchema`가 있으면 그 스키마에 맞는 JSON 객체 하나입니다. 종료 코드 0은 결과를 냈다는 뜻이고 0이 아니면 실행 실패(사유는 stderr)입니다. 통과·불통과 같은 판정은 결과 객체의 필드에 있고 종료 코드로는 말하지 않습니다. cwd는 받은 디렉토리입니다. 부르는 쪽은 종료 코드·stdout·stderr를 구분된 관측으로 모델에 돌려줍니다.
- `mcp` — 팀 MCP 서버의 도구 하나. `get_tool`이 `server`에 그 서버의 `server.json`(MCP Registry 형식)을 함께 싣습니다. 하네스 설정(`.mcp.json`·`mcpServers`)에 그 서버를 붙이는 것은 사용자의 일이고, 레지스트리는 도구를 부르지 않습니다.

```
search_tools(query, limit=10)       → name·description·sha·kind·server
get_tool(id, sha?, archive?)        → tool.json 전체 + sha·commit·files + server(kind=mcp); archive=true면 다운로드 명세(kind=script)
```

어느 턴에 어느 도구를 문맥에 넣을지는 하네스가 정합니다(Claude Code의 지연 적재·ToolSearch). 레지스트리는 "무엇이 있는가"까지입니다.

## 6. 사람 없이 쓰기

CI나 자동화 루프에는 LDAP 기계 계정을 씁니다. 운영자가 계정(우리 팀은 `svc-harness`)을 `harness-readers`에 넣어 두면, 기밀 클라이언트 `ci-runner`의 비밀번호 그랜트로 토큰을 받습니다.

```sh
TOKEN=$(scripts/dev-token.sh https://<호스트>/dex https://<호스트>/mcp ci-runner "$CI_RUNNER_SECRET" svc-harness "$SVC_PASSWORD")
```

이 토큰을 `Authorization: Bearer`로 붙여 같은 MCP 엔드포인트(Streamable HTTP)를 부릅니다. 권한은 사람과 같은 읽기뿐입니다.

## 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `claude mcp get`이 `ENOTFOUND` | tailnet 이름이 풀리지 않음 | Tailscale을 켠다 |
| `/mcp`에 harness-catalog가 없다 | 세션이 설정을 기동 때 읽음 | Claude Code 재시작 |
| 로그인 뒤 "인증 서버가 동적 등록을 지원하지 않는다" | `oauth.clientId`가 없음 | 설정에 클라이언트 ID를 더한다 |
| 로그인은 되는데 도구 호출이 거부 | `harness-readers`에 없음 | 운영자에게 그룹 추가 요청 |
| `get_skill`이 `unknown_version` | 받는 사이 `main`이 바뀌어 그 판이 이력에서 풀리지 않음 | `sha` 없이 다시 불러 현재 판부터 |
| 검색 결과가 비어 있다 | 아직 색인 전(병합 뒤 한 주기) 또는 없는 스킬 | 잠시 뒤 다시, 또는 다른 낱말로 검색 |

## 비밀을 검색어에 넣지 않기

`search_skills`의 검색어와 도구 호출은 팀 Langfuse의 기록에 남습니다. 토큰·비밀번호·개인 정보를 검색어에 적지 않습니다.
