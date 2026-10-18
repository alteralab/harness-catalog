---
name: write-tool
description: 팀 카탈로그(harness-catalog)의 toolbox에 올릴 새 도구의 tool.json을 스키마대로 만들고 검사까지 통과시킨다. 사용자가 "도구 새로 만들자", "이 스크립트를 도구로 등록해", "tool.json 뼈대 잡아줘", "MCP 서버의 이 도구를 카탈로그에 올리자"라고 할 때 쓴다. 먼저 search_tools·search_skills로 같은 것이 있는지와 이름 충돌을 확인하고, 카탈로그 클론의 브랜치에 tools/<name>/tool.json(과 kind가 script면 ABI를 지키는 스크립트, mcp면 mcp-servers/<server>/server.json)을 뼈대 스크립트로 만들며, $schema가 schemas/tool.schema.json을 가리키게 하고 harness-catalog check 항목 11·12로 검증한다. 브랜치·커밋·PR은 사용자가 지시할 때만. 절차·판단을 적는 것은 스킬이라 write-skill이고, 이 스킬이 아니다.
compatibility: 카탈로그 저장소의 로컬 클론과 git·gh(PR 생성), kind가 script인 도구면 uv(uv run --script)가 필요하다
metadata:
  requires-tools: "uv git gh"
---

# write-tool — 새 도구의 tool.json과 계약

도구는 **스키마가 있는 호출 가능한 것**이다(`name`·`description`·`inputSchema`·`runtime`). 이 스킬은 그 정의를 카탈로그 클론의 **브랜치**에 뼈대로 만들고, 계약(`references/tool-contract.md`)을 점검표로 통과시키고, `harness-catalog check`로 검증하는 데까지다. PR은 사용자의 지시 뒤에만, 병합은 사람이 한다. 계약의 문장은 `references/tool-contract.md` 하나가 소유한다.

## 언제 쓰는가

- 쓴다: "도구 새로 만들자", "이 스크립트를 도구로 등록해", "tool.json 뼈대 잡아줘", "MCP 서버의 이 도구를 카탈로그에 올리자".
- 쓰지 않는다: "이 절차를 스킬로 만들어"는 `write-skill`이다. 도구인가 스킬인가의 기준은 하나다 — **입출력이 스키마로 정해지고 모델의 판단 없이 부를 수 있는가.** 그렇지 않으면 스킬이다. 기존 도구의 한 줄 수정은 갱신이다(브랜치 → `tools/<name>/` 수정 → 커밋 → PR).

## 단계

1. 사용자의 한 문장에서 도구가 **받는 것**(입력 필드)과 **돌려주는 것**을 받아 적는다. `search_tools`로 같은 것이 있는지, `search_skills(<이름>)`과 `search_tools(<이름>)`으로 이름이 비었는지 확인한다. 이름은 **스킬과 도구를 합쳐 전역 유일**이다.
2. 종류를 정한다. 카탈로그 안에 둘 스크립트면 `script`, 팀 MCP 서버가 이미 내는 도구 하나를 카탈로그에서 찾게 하려면 `mcp`.
3. 카탈로그 클론(없으면 경로를 묻고 clone)에서 `main`을 최신으로 한 뒤 브랜치 `tool/<name>`을 따고 뼈대를 만든다(멱등, 있는 파일은 건드리지 않는다):
   - `script`: `uv run --script skills/write-tool/scripts/scaffold_tool.py <name> --description "<한 문장>" --kind script --script <x.py>` → `tools/<name>/tool.json`과 `tools/<name>/scripts/<x.py>`(ABI 골격).
   - `mcp`: `uv run --script skills/write-tool/scripts/scaffold_tool.py <name> --description "<한 문장>" --kind mcp --server <server> --tool <그 서버의 도구 이름>` → `tools/<name>/tool.json`. `mcp-servers/<server>/server.json`이 없으면 MCP Registry 형식의 골격도 만든다.
4. TODO 자리를 채운다. `inputSchema.properties`와 `required`(인자마다 `description` 한 줄 — 검색 색인은 설명을 본다), `outputSchema`(결과를 코드가 읽는 도구면 유지하고 필드를 채운다; 사람만 읽는 텍스트 도구면 키를 지운다), `description`(무엇을 돌려주는지와 쓰지 말 상황 한 줄), `script`면 스크립트 본문(stdin JSON → 일 → stdout), `mcp`면 `server.json`의 `version`·`packages` 또는 `remotes`(시크릿 값은 적지 않는다).
5. `tool.json`의 `$schema`는 뼈대가 `../../schemas/tool.schema.json`으로 넣어 둔다. 편집기가 타이핑 중에 검증한다. 그 파일이 카탈로그에 없거나 낡았으면 `harness-catalog schema tool > schemas/tool.schema.json`으로 다시 쓴다(CLI 판은 `.pre-commit-config.yaml`의 핀과 같다).
6. `references/tool-contract.md`의 점검표를 하나씩 지난다. 요지: `command`는 셸 없는 argv이고 `path`는 그 원소 정확히 하나, 입력은 stdin의 JSON 객체 하나, 결과는 stdout(`outputSchema`를 선언했으면 그 스키마의 JSON 객체 하나만), 종료 0 = 결과를 냈다·0 아님 = 실행 실패(사유는 stderr). 판정은 종료 코드가 아니라 결과 객체의 필드로. 조용히 끝나지 않는다. `inputSchema`는 `type: object`, 32 KiB·깊이 16 안. 시스템 도구는 `metadata.requires-tools`.
7. `script`면 ABI대로 한 번 돌려 본다: `echo '{...}' | uv run --script tools/<name>/scripts/<x.py>`. 종료 코드와 stdout이 설명과 맞아야 한다.
8. `hc check`를 돌린다(pre-commit 훅이 커밋 때, CI가 PR에서 다시 돈다). 항목 11(도구)·12(서버) 위반을 고친다.
9. 사용자에게 브랜치·점검표 결과를 보고하고 **멈춘다**. "올려"라고 할 때만 커밋·push·`gh pr create`. 병합은 사람이 git 호스트에서 한다. 클라우드 샌드박스 세션(git 자격 없음)이면 여기서 멈추고 로컬 세션에서 하라고 알린다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 같은 일을 하는 도구가 이미 있다 | 갱신 경로를 안내하고 멈춘다 |
| 이름이 `search_skills`·`search_tools`에 있거나 `check` 항목 5·11이 거부 | 다른 이름. 은퇴한 이름은 다시 쓰지 않는다 |
| 입출력이 스키마로 안 떨어진다(판단이 필요하다) | 도구가 아니라 스킬이다 — `write-skill`로 안내 |
| `check` 항목 11: `runtime.path`가 `command`에 정확히 한 번 없다 | `command`는 argv 배열이고 `path`가 그 원소여야 한다. `sh -c`로 감싸지 않는다 |
| `check` 항목 11: `runtime.server`가 없다 | `mcp-servers/<server>/server.json`을 먼저 만든다(3의 골격) |
| `check` 항목 12: `isSecret: true` 항목에 `value`·`default` | 값을 지운다. 시크릿은 저장소에 없다 |
| `schemas/tool.schema.json`이 없거나 편집기가 `$schema`를 못 푼다 | `hc schema tool > schemas/tool.schema.json`으로 다시 쓴다 |
| 클라우드 샌드박스 세션 | 9에서 멈춘다 |
