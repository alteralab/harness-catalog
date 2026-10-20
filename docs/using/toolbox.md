---
title: 도구 찾아 쓰기
description: 도구 검색, script 와 mcp 두 갈래, 하네스에 붙이기.
audience: 팀원
---

# 도구 찾아 쓰기

카탈로그에서 도구를 찾아 하네스에 붙이는 쪽입니다. 스킬 쪽은 [스킬 찾아 세션에 넣기](find.md)입니다.

카탈로그는 스킬 말고 **도구**도 싣습니다(DESIGN §11 2026-10-11). 도구는 스키마가 있는 호출 가능한 것이고, 구현은 둘 중 하나입니다.

- `script` — 카탈로그 안의 스크립트. `get_tool(archive=true)` 응답을 `hc pin --scope project`에 넘겨 `.agents/tools/<name>/`에 놓으면 같은 명령이 `.mcp.json`에 `toolbox` 항목을 써 두고, `hc toolbox .agents/tools`가 그 디렉토리의 도구를 MCP 도구로 띄웁니다. 호출마다 어댑터가 `runtime.command`를 **셸 없이 argv로** 실행합니다. 입력은 `inputSchema`에 맞는 JSON 객체 하나를 stdin으로, 결과는 stdout이고, `tool.json`에 `outputSchema`가 있으면 그 스키마에 맞는 JSON 객체 하나입니다. 종료 코드 0은 결과를 냈다는 뜻이고 0이 아니면 실행 실패(사유는 stderr)입니다. 통과·불통과 같은 판정은 결과 객체의 필드에 있고 종료 코드로는 말하지 않습니다. cwd는 받은 디렉토리입니다. 부르는 쪽은 종료 코드·stdout·stderr를 구분된 관측으로 모델에 돌려줍니다.
- `mcp` — 팀 MCP 서버의 도구 하나. `get_tool`이 `server`에 그 서버의 `server.json`(MCP Registry 형식)을 함께 싣습니다. 하네스 설정(`.mcp.json`·`mcpServers`)에 그 서버를 붙이는 것은 사용자의 일이고, 레지스트리는 도구를 부르지 않습니다.

```
search_tools(query, limit=10)       → name·description·sha·kind·server
get_tool(id, sha?, archive?)        → tool.json 전체 + sha·commit·files + server(kind=mcp); archive=true면 다운로드 명세(kind=script)
```

어느 턴에 어느 도구를 문맥에 넣을지는 하네스가 정합니다(Claude Code의 지연 적재·ToolSearch). 레지스트리는 "무엇이 있는가"까지입니다.
