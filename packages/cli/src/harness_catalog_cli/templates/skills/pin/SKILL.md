---
name: pin
description: 카탈로그(harness-catalog)의 스킬이나 도구를 내 하네스 옆에 내려받아(pin) 두고, 내려받은 사본의 새 판을 확인한다. 사용자가 "이 스킬 내려받아", "pin 해줘", "곁에 둬", "매일 쓰니까 설치해 둬", "이 도구 설치해", "새 판 있어?", "내려받은 것 갱신해줘"라고 할 때 쓴다. 범위(프로젝트 또는 사용자)만 묻고, 레지스트리에서 받은 응답을 그대로 hc pin에 넘긴다 — 받기·대조·교체·링크는 그 명령이 한 번에 한다. 세션에 스킬을 잠깐 넣는 것(get_skill)은 이 스킬이 아니다.
---

# pin — 카탈로그의 스킬·도구를 곁에 두기

카탈로그의 한 판을 로컬 하네스 디렉토리에 **원자적으로** 놓고, 나중에 새 판이 있는지 확인한다. 판단(무엇을, 어느 범위에)은 이 산문이 대화로 정하고, 결정적인 일(받기·크기와 sha256 대조·풀기·파일 목록 대조·PINNED·교체·링크)은 CLI `hc pin`이 한 번에 한다. 파일 내용은 모델을 지나지 않는다.

## 언제 쓰는가

- 쓴다: "이 스킬 내려받아", "pin 해줘", "곁에 둬", "매일 쓰니까 설치해 둬", "이 도구 설치해", "새 판 있어?", "내려받은 것 갱신해줘".
- 쓰지 않는다: "이 스킬 세션에 넣어줘"처럼 지금 한 번 쓰려는 것은 `get_skill`이다. 내려받지 않는다.

## 놓이는 자리

| 받는 것 | 자리(프로젝트 범위) | 자리(사용자 범위) | 그 뒤 |
|---|---|---|---|
| 스킬 | `.agents/skills/<name>/` | `~/.agents/skills/<name>/` | `.claude/skills/<name>`(또는 `~/.claude/skills/<name>`)이 그곳을 가리키는 심볼릭 링크. 하네스가 시작 시 이름·설명을 읽어 스스로 발견한다 |
| 도구(`kind: script`) | `.agents/tools/<name>/` | `~/.agents/tools/<name>/` | `.mcp.json`(사용자 범위는 `~/.agents/mcp.json`)에 `toolbox` 항목(`hc toolbox .agents/tools`)이 생겨 도구가 MCP로 뜬다. 승인 패턴은 `mcp__toolbox__<name>` |
| 도구(`kind: mcp`) | 내려받을 파일이 없다 | | `get_tool`이 준 `server`(server.json)대로 그 서버를 하네스 설정의 `mcpServers`에 붙인다. 시크릿은 사용자가 환경 변수로 |

하네스별 디렉토리는 `.agents/`가 공용 경로이고(Codex·Cursor·Gemini CLI·VS Code가 읽는다) Claude Code만 `.claude/`를 읽어 링크를 둔다. Claude Code는 같은 이름이 두 범위에 있으면 사용자 범위가 이기고, Codex는 둘 다 선택기에 보인다. Cursor는 `.agents/skills/`·`.cursor/skills/`와 호환 경로 `.claude/skills/`·`.codex/skills/`를, Gemini CLI는 `.gemini/skills/` 또는 `.agents/skills/`를, VS Code/Copilot은 `.github/skills/`·`.claude/skills/`·`.agents/skills/`를 읽는다. 에이전트 종류는 묻지 않는다.

## 내려받기 — 단계

1. 이 세션이 클라우드 샌드박스(홈 디렉토리를 읽지 않는 세션)면 멈추고 알린다: "여기서는 라이브(`get_skill`)만 된다."
2. 사용자에게 **범위 하나만** 묻는다: 프로젝트(저장소에 커밋, 팀원과 공유) 또는 사용자(홈, 나만).
3. `search_skills(<이름>)` 또는 `search_tools(<이름>)`으로 `<name>`과 현재 `sha`를 확인한다. 검색에 없으면 은퇴한 이름이다 — 알리고 멈춘다. 같은 이름의 사본이 이미 있으면 멈추고 알린다(재다운로드는 사용자가 명시했을 때만, 그때 `hc pin --force`).
4. 응답 하나를 받는다. 스킬은 `get_skill(<name>, sha=<3의 sha>, archive=true)`, script 도구는 `get_tool(<name>, sha=<3의 sha>, archive=true)`. `sha`를 명시하므로 받는 도중 `main`이 바뀌어도 한 판만 받는다. mcp 도구는 `get_tool(<name>)`의 `server`를 읽고 위 표의 셋째 줄대로 하고 끝난다.
5. 그 응답(structuredContent)을 그대로 파일에 쓰거나 표준 입력으로 넘겨 **셸에서** 한 번 부른다:
   ```sh
   hc pin --scope project --response response.json          # 또는 --scope user; 저장소 루트가 아니면 --project-root <경로>
   ```
   이 명령이 받고(헤더의 5분 토큰), 크기와 sha256을 대조하고, 임시 디렉토리에 풀고, 풀린 파일 집합을 응답의 `files`와 대조하고, `PINNED` 한 줄(`<name> <sha 40자> <ISO 8601 UTC 시각>`)을 쓰고, 한 번에 이름을 바꾸고, 링크(스킬) 또는 `.mcp.json`의 `toolbox` 항목(도구)을 둔다. 어느 단계에서 실패해도 기존 사본은 남는다. `hc`가 없으면 `uvx --from "harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v<판>#subdirectory=packages/cli" hc pin …`.
6. 보고한다: 명령의 출력(경로, sha, 파일 수)과 "이 사본은 이 시점의 판이고 새 판은 다시 받아야 한다". 도구를 받았으면 하네스를 다시 열어야 `toolbox` 항목이 뜬다고 덧붙인다.

## 새 판 확인 — "새 판 있어?", "갱신해줘"

1. 프로젝트·사용자 **두 범위의** `PINNED`를 모두 읽는다(`.agents/skills/*/PINNED`, `.agents/tools/*/PINNED`, `~/.agents/skills/*/PINNED`, `~/.agents/tools/*/PINNED`).
2. 이름마다 `search_skills(<name>)`(도구는 `search_tools`)을 불러 `sha`와 견준다. sha가 다르면 새 판이다. **받기 전에 description을 보여 같은 것인지 사용자가 확인하게 한다** — 은퇴한 이름이 다른 스킬로 다시 쓰였을 수 있다. 검색에 나오지 않는 이름은 은퇴한 것이다 — 알린다.
3. 같은 이름이 두 범위에 다 있으면 낡은 쪽을 알리고 하나로 합치기를 권한다. 두 sha가 같으면 어느 쪽이 이겨도 결과가 같다.
4. 새 판을 받기로 하면 "내려받기"의 4~6을 `hc pin --force`로 다시 한다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 클라우드 샌드박스 세션 | 멈춘다. 라이브(`get_skill`)만 안내 |
| 같은 이름의 사본이 이미 있다 | 멈추고 알린다. 덮어쓰기는 사용자의 명시 뒤에만 `--force`(기존은 `.pin-old`로 비켜 두었다가 성공 뒤 지운다). 고친 사본을 지키려면 이름을 바꿔 두라고 알린다 |
| `hc pin`이 "sha256 mismatch"·"size mismatch" | 전송이 깨졌다. 응답을 다시 받아 한 번 더. 두 번째도 다르면 알린다(프록시가 본문을 바꾸는 중) |
| `hc pin`이 "file list mismatch" | 판이 어긋났다. 4부터 다시(같은 `sha`로) |
| `hc pin`이 "download failed" 또는 403 | 토큰 만료(5분) 또는 레지스트리 재기동. 4부터 다시 받아 한 번 더. 두 번째도 같으면 멈추고 알린다 |
| `get_skill`·`get_tool`이 `unknown_version` | `main`이 바뀌어 그 판이 이력에서 풀리지 않는다 — 3부터 다시 |
| `get_skill`·`get_tool`이 `input_limit` | 그 판의 tar가 20 MB를 넘는다 — 저자에게 알린다(파일을 줄여야 한다) |
| `.claude/skills/<name>`이 실제 디렉토리 | 링크를 만들지 않고 알린다 |
| `hc`가 없다 | 5의 `uvx` 한 줄로 부른다 |
