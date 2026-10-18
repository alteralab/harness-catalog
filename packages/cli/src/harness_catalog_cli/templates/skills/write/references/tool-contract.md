# 도구 계약 점검표 — tool.json 하나를 올리기 전에

이 파일이 도구 계약의 저자용 문면을 소유한다. 계약의 정본은 코드 저장소 `DESIGN.md` §4·§11(2026-10-11 toolbox, 2026-10-18 toolbox 어댑터)과 `plans/service.md` D18이고, 기계가 보는 모양은 `schemas/tool.schema.json`(core `ToolSpec`에서 생성)이다. 항목마다 "예"라고 답할 수 있어야 한다.

## 1. 도구인가

- [ ] 입력과 출력이 스키마로 정해지고, 모델의 판단 없이 부를 수 있다. 아니면 스킬이다(`write`). 여러 스킬이 쓰는 코드도 도구다 — 복사하지 않는다.
- [ ] 이름은 1~64자 소문자·숫자·하이픈이고 디렉토리명과 같다. **스킬과 도구를 합쳐 살아 있는 이름 사이에서 유일**이다(검사 11).

## 2. tool.json

- [ ] 최상위 키는 `$schema`(선택)·`name`·`description`·`inputSchema`·`outputSchema`(선택)·`runtime`·`metadata`(선택, 자유 맵)뿐이다. 모르는 키는 검사 11이 거부한다.
- [ ] `$schema`는 `../../schemas/tool.schema.json`을 가리킨다(편집기 검증용. 레지스트리는 이 값을 해석하지 않는다).
- [ ] `description`은 1~1024자. 첫 문장에 무엇을 돌려주는지와 사용자가 실제로 말할 낱말이 있고, 쓰지 말아야 할 상황이 한 줄 있다. 검색 색인은 이름·설명·`metadata` 값을 본다.
- [ ] `inputSchema`는 `type: object`, 직렬화 32 KiB 안, 중첩 깊이 16 안, Draft 2020-12로 유효한 스키마, `$ref`는 문서 안(`#…`)만. 인자마다 `description` 한 줄. `additionalProperties: false`를 권한다.
- [ ] 결과를 코드가 읽어야 하는 도구(채점기·조회)는 **`outputSchema`**(MCP `Tool.outputSchema`와 같은 이름)를 선언한다. 규칙은 `inputSchema`와 같다. 사람이 읽을 설명이 필요하면 `summary`·`message` 같은 필드를 그 스키마에 선언한다 — 모든 도구에 공통 필드를 강제하지 않는다.
- [ ] **의존성은 스크립트 안에만.** 파이썬 패키지는 PEP 723 머리, 바이너리는 없을 때 스크립트가 종료 4와 설치 안내 한 줄로 말한다. `metadata`에 베껴 적지 않는다.

## 3. kind: script — 실행 ABI

- [ ] `runtime.path`는 디렉토리 안의 일반 파일(링크 금지, `..` 금지)이고, `runtime.command`는 **셸을 거치지 않는 argv 배열**이며 `path`가 그 원소 **정확히 하나**다. `sh -c "..."`로 감싸지 않는다 — 셸 주입면이고 하네스가 사전 승인(`Bash(<경로> *)`)을 걸 수 없다.
- [ ] 파이썬이면 `["uv", "run", "--script", "scripts/x.py"]`와 PEP 723 머리. 실행 비트·shebang 직접 실행에 기대지 않는다.
- [ ] 호출하는 쪽은 어디서나 `hc toolbox <dir>`(세션은 pin이 `.mcp.json`에, 카탈로그 클론은 `init`의 `.mcp.json`이, 루프는 조립기가 등록)이고 `command`를 argv 그대로 실행하며, cwd는 도구 디렉토리(아카이브를 푼 곳), 입력은 `inputSchema`에 맞는 **JSON 객체 하나를 stdin**으로, 결과는 **stdout**, 종료 코드는 **0 = 신뢰할 결과를 냈다 · 0 아님 = 결과를 만들지 못한 실행 실패**다. 환경은 하네스가 준 그대로. 샌드박스·시간 초과·권한 확인은 하네스의 몫.
- [ ] `outputSchema`를 선언했으면 정상 완료 시 stdout에 **그 스키마에 맞는 UTF-8 JSON 객체 하나만** 낸다. 로그·진행 표시·별도 PASS/FAIL 줄을 섞지 않는다. 통과·불통과 같은 판정은 그 객체의 필드로만 말한다 — **종료 1을 "결과가 부정"의 뜻으로 쓰지 않는다**(pytest식 mirror도 금지: 소비자마다 정본이 둘이 된다). 선언하지 않았으면 stdout은 텍스트다.
- [ ] 0이 아닌 종료는 사유를 stderr에 적고 stdout에 부분 결과를 두지 않는다. stdin이 JSON 객체가 아니거나 `required` 키가 빠졌으면 어느 키가 왜 틀렸는지 적는다 — 모델이 입력을 고칠 유일한 단서다. 조용히 끝나지 않는다.
- [ ] toolbox는 종료 코드·stdout·stderr를 **구분된 관측**으로 모델에 되돌리되 크기 상한과 잘림 표시를 두고, 실행물의 해시를 고정하며(바뀌면 재시작 전까지 거부), 최소 환경과 시간 상한으로 돌린다. 구조화 결과는 JSON 파싱과 `outputSchema` 검증을 통과해야만 코드가 쓰고, 실패하면 정상 판정이 아니라 계약 오류 관측이다. 사전 승인 거부는 종료 코드가 아니라 `not_executed` 관측이다. 회차를 멈출지는 소비자의 예산이 정한다(DESIGN §11 2026-10-12 보정).
- [ ] 레지스트리는 도구를 부르지 않는다. `get_tool`이 정의와 다운로드 명세를 주고, 받아서 실행하는 것은 소비자다.

## 4. kind: mcp — 서버 배선

- [ ] `runtime.server`는 `mcp-servers/<server>/`가 있어야 하고, `runtime.tool`은 그 서버가 실제로 내는 도구 이름이다(`tools/list`로 확인).
- [ ] `mcp-servers/<server>/server.json`은 MCP Registry 형식: `$schema`(공식 URL)·`name`(디렉토리명 또는 `<ns>/<디렉토리명>`)·`version` 필수, `packages` 또는 `remotes` 하나 이상. 최상위에 그 밖의 키는 검사 12가 거부한다.
- [ ] `isSecret: true` 항목(`environmentVariables`·`headers`·`packageArguments`·`runtimeArguments`)에는 `value`·`default`를 적지 않는다. 시크릿은 저장소에 없다(검사 4 gitleaks도 본다).
- [ ] `get_tool`은 `server.json`을 그대로 돌려줄 뿐이다. 하네스 설정(`.mcp.json`·`mcpServers`)에 서버를 붙이는 것은 소비자의 일이다.

## 5. 올리기

- [ ] 브랜치 `tool/<name>` → `hc check`(항목 11·12 포함) → PR → 사람이 병합. 병합한 사람이 그 판의 인증자다. 레지스트리는 다음 fetch(기본 60초)에 `search_tools`·`get_tool`로 낸다. 뼈대는 도구 `scaffold`(`{"kind": "tool", …}`)가 만든다.
- [ ] 판은 디렉토리의 tree SHA다. 과거 판은 `get_tool(id, sha)`.
- [ ] 도구에는 Harbor evals를 두지 않는다. 결정적 호출이라 스크립트의 자체 시험(있다면)과 검사 11이 검증이다.
