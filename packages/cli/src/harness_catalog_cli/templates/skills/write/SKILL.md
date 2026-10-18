---
name: write
description: 팀 카탈로그(harness-catalog)에 올릴 새 스킬이나 새 도구의 뼈대를 만들고 팀 규약대로 채운다. 사용자가 "스킬 새로 만들자", "이 절차를 스킬로 만들어", "도구 새로 만들자", "이 스크립트를 도구로 등록해", "MCP 서버의 이 도구를 카탈로그에 올리자"라고 할 때 쓴다. 첫 단계는 절차를 결정적인 부분과 판단으로 가르는 것이다 — 판단은 본문 산문으로, 결정적 부분은 도구(tools/<name>/tool.json)로. 도구가 이미 있으면 이름으로 엮고 없으면 새로 만든다(세션과 루프가 함께 쓰는 기본형). 뼈대는 도구 scaffold가 만들고, 규약 점검표와 hc check를 지나 브랜치까지. 브랜치·커밋·PR은 사용자가 지시할 때만, 병합은 사람이 git 호스트에서. 기존 스킬·도구의 한 줄 수정은 이 스킬이 아니다.
compatibility: 카탈로그 저장소의 로컬 클론과 git·gh(PR 생성), uv(도구 스크립트 실행)가 필요하다
---

# write — 새 스킬·도구의 뼈대와 팀 규약

카탈로그에 올릴 것은 둘뿐이다. **스킬**(에이전트가 읽는 절차, `skills/<name>/SKILL.md`)과 **도구**(스키마로 부르는 코드, `tools/<name>/tool.json`). 이 스킬은 절차를 판단(본문)과 결정적 부분(도구)으로 가르고, 결정적 부분마다 있는 도구를 엮거나 새 도구를 만들고, 뼈대를 도구 `scaffold`로 만들고, 규약(`references/conventions.md`, `references/tool-contract.md`)을 점검표로 통과시키고, `hc check`로 검증해 브랜치에 두는 데까지다. PR은 사용자의 지시 뒤에만, 병합은 사람이 한다. 규약의 문장은 두 references 파일이 소유한다 — 본문은 가리킬 뿐 다시 쓰지 않는다.

## 언제 쓰는가

- 쓴다: "스킬 새로 만들자", "이 절차를 스킬로 만들어", "도구 새로 만들자", "이 스크립트를 도구로 등록해", "MCP 서버의 이 도구를 카탈로그에 올리자".
- 쓰지 않는다: 기존 스킬·도구의 한 줄 수정은 갱신이다 — 카탈로그 클론에서 `main` 기준 브랜치 → `skills/<name>/` 또는 `tools/<name>/` 수정 → 커밋 → PR. 이 뼈대 절차가 아니다.

## 단계

1. **가른다.** 사용자의 한 문장에서 하는 일과 발동 상황을 받아 적고, 절차를 두 종류로 가른다. **판단**(언제 쓰는가, 무엇을 고르는가, 어디서 멈추는가)과 **결정적 부분**(입력과 출력을 스키마로 적을 수 있고 모델 판단 없이 도는 연산). 판단은 본문 산문이 되고, 결정적 부분은 하나씩 **도구**다. 스킬은 도구를 이름으로 부른다 — 세션과 루프가 같은 스킬을 쓰는 기본형이고, 루프는 `scripts/`를 품은 스킬을 후보에서 뺀다.
   - 결정적 부분이 없다 → 스킬만. 판단이 없다 → 도구만(스킬 없음).
   - 팀 MCP 서버가 이미 내는 도구 하나를 카탈로그에서 찾게 하려면 **도구(mcp 런타임)**.
   `search_skills`로 같은 일을 하는 스킬이 있는지 확인한다. 있으면 갱신 경로(위 "쓰지 않는다")를 안내하고 멈춘다.
2. **결정적 부분마다 있는 도구를 찾는다.** `search_tools(<하는 일>)`로 찾고, 후보가 있으면 `get_tool(<name>)`의 `description`과 `inputSchema`가 이 자리에 맞는지 본다. 맞으면 그 이름으로 엮는다(새로 만들지 않는다). 없으면 새 도구의 이름을 정한다. 도구는 여러 스킬이 다른 조합으로 쓰는 것이 정상이다.
3. 이름을 정한다. 스킬과 새 도구 모두 1~64자 소문자·숫자·하이픈이고 **스킬과 도구를 합쳐 전역 유일**이다(`search_skills(<이름>)`·`search_tools(<이름>)`에 없어야 한다). 같은 이름으로 다른 내용을 올리고 싶으면 그것은 은퇴가 아니라 갱신이다.
4. 카탈로그 클론(없으면 경로를 묻고 clone)에서 `main`을 최신으로 하고 브랜치 `skill/<name>` 또는 `tool/<name>`을 딴다. 뼈대는 도구 **`scaffold`**로 만든다(멱등, 있는 파일은 건드리지 않는다). 카탈로그 클론의 `.mcp.json`이 `hc toolbox ./tools`를 등록해 두므로 이 클론 안에서 `scaffold`는 MCP 도구로 떠 있다.
   - 스킬: `scaffold {"kind": "skill", "name": "<name>", "description": "<한 문장>", "positive": "<케이스>", "negative": "<케이스>", "tools": ["<있는 도구>", "<새 도구>"]}`. 2의 결과를 `tools`에 전부 적는다. 있는 이름은 그 `tool.json`을 읽어 본문 단계에 호출 줄("도구 `x`를 `{…}`로 부른다 — 설명. 결과: 키")을 미리 적고, 없는 이름은 `tools/<x>/` 뼈대를 함께 만든다.
   - 도구(script): `scaffold {"kind": "tool", "name": "<name>", "description": "<한 문장>", "script": "<x.py>"}`.
   - 도구(mcp): `scaffold {"kind": "tool", "name": "<name>", "description": "<한 문장>", "runtime": "mcp", "server": "<server>", "mcp_tool": "<그 서버의 도구 이름>"}`. `mcp-servers/<server>/server.json`이 없으면 골격도 만든다.
   결과의 `todo` 목록이 채울 자리다.
5. TODO를 채운다. 스킬은 `SKILL.md` 본문 세 절(언제 쓰는가·단계·실패 대응)과 evals 쌍의 과제 문장·검증 조건·solve. 도구는 `tool.json`의 `inputSchema`(인자마다 `description` 한 줄)·`outputSchema`(코드가 읽을 결과; 사람만 읽는 텍스트 도구면 키를 지운다)·`description`(무엇을 돌려주는지와 쓰지 말 상황 한 줄), 그리고 스크립트 본문(stdin JSON → 일 → stdout JSON). 스킬 본문에서 도구는 **이름으로** 부른다: "도구 `x`를 `{...}`로 부른다". 참조 파일은 스킬 루트 기준 상대 경로·마크다운 링크·한 단계 깊이로 적는다.
6. 점검표를 지난다. 스킬은 `references/conventions.md`, 도구는 `references/tool-contract.md`. 요지: 의존성은 스크립트 안에만(PEP 723 머리, 바이너리는 없을 때 종료 4), `command`는 셸 없는 argv이고 `path`는 그 원소 하나, 결과는 stdout의 JSON 하나·종료 0은 "결과를 냈다", 판정은 결과 필드로. `compatibility`는 네트워크·특정 제품 같은 조건이 있을 때만.
7. 도구는 한 번 돌려 본다. `scaffold`가 떠 있는 것과 같은 toolbox가 새 도구도 띄우므로(toolbox를 다시 시작하면 새 `tool.json`을 읽는다) MCP로 부르거나, 터미널에서 `echo '{...}' | uv run --script tools/<name>/scripts/<x.py>`로 친다.
8. `hc check`를 돌린다(pre-commit 훅이 커밋 때 다시 돌리고 CI가 PR에서 또 돌린다). 위반 항목(3 SKILL.md 스펙, 4 시크릿, 7 크기, 11 tool.json, 12 server.json)을 고친다.
9. 스킬이면 evals를 모델 없이 먼저 돌린다: `harbor run -p skills/<name>/evals -a oracle -e docker`로 전 케이스 reward 1. 그다음 `harbor run --path skills/<name>/evals --agent <하네스> --model <모델> --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin`을 스킬 있이·없이 두 번. Harbor가 없으면 건너뛰고 PR 본문에 "evals 미실행"을 적는다.
10. 사용자에게 브랜치·점검표 결과를 보고하고 **멈춘다.** 사람 승인 전까지는 되돌릴 수 있는 일만 한다. "올려"라고 할 때만 커밋·push·`gh pr create`(GitLab이면 `glab mr create`). 병합은 사람이 git 호스트에서 한다. 클라우드 샌드박스 세션(git 자격 없음)이면 여기서 멈추고 로컬 세션에서 하라고 알린다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 같은 일을 하는 스킬·도구가 이미 있다 | 갱신 경로를 안내하고 멈춘다 |
| 이름이 `search_skills`·`search_tools`에 있거나 `check` 항목 11이 "이름이 스킬로도 있다"고 거부 | 다른 이름 |
| `scaffold`가 MCP에 없다 | 카탈로그 클론 루트에 `.mcp.json`이 있는지, 하네스를 그 디렉토리에서 열었는지 본다. 없으면 `hc init <repo-url>`이 둔 파일을 받거나 `hc toolbox ./tools`를 설정에 더한다 |
| `hc`가 없어 toolbox를 못 띄우는 환경 | 같은 도구를 터미널에서 친다: `echo '{"kind": "skill", …}' \| uv run --script tools/scaffold/scripts/scaffold.py`. 입력과 결과는 MCP로 부를 때와 같다 |
| 입출력이 스키마로 안 떨어진다(판단이 필요하다) | 도구가 아니라 스킬이다 — 판단은 산문으로, 결정적 부분만 도구로 |
| 있는 도구가 거의 맞는데 인자 하나가 모자란다 | 그 도구를 갱신한다(인자는 더하기만, 기존 스킬이 깨지지 않게). 복사해서 새 도구를 만들지 않는다 |
| `scaffold`가 `tools/<x>/tool.json unreadable` | 있는 도구의 tool.json이 깨져 있다. 그 도구부터 고친다(`hc check` 항목 11) |
| 세션에서만 뜻이 있는 보조 코드(사람이 읽을 보고서 찍기 등) | 예외로 `skills/<name>/scripts/`에 두되 SKILL.md에 왜 세션 전용인지 한 줄을 적는다. 그 스킬은 루프가 집지 않는다 |
| `check` 항목 11: `runtime.path`가 `command`에 정확히 한 번 없다 | `command`는 argv 배열이고 `path`가 그 원소여야 한다. `sh -c`로 감싸지 않는다 |
| `check` 항목 11: `runtime.server`가 없다 | `mcp-servers/<server>/server.json`을 먼저 만든다(3의 골격) |
| `check` 항목 12: `isSecret: true` 항목에 `value`·`default` | 값을 지운다. 시크릿은 저장소에 없다 |
| `check`가 "schemas/tool.schema.json differs"를 경고 | 편집기용 스키마가 낡았다. 운영자가 `hc init <repo-url> --refresh`를 돌린다(검사 결과에는 영향 없음) |
| `hc check`가 붉다 | 항목 번호대로 고친다. 검사기 자체 실패(종료 2)는 gitleaks 설치를 확인 |
| Harbor가 없다 | 9를 건너뛰고 PR 본문에 "evals 미실행"을 적는다 |
| 클라우드 샌드박스 세션 | 10에서 멈춘다 |
