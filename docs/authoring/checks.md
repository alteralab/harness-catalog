---
title: 검사 통과시키기
description: 검사 항목 일곱과 종료 코드, 붉을 때 고치는 법.
audience: 스킬 저자
---

# 검사 통과시키기

커밋 훅과 CI의 `check`가 보는 항목입니다. 붉은 항목을 찾아 고칩니다. 훅을 걸어 두는 자리는 [올리는 절차](submit.md) 4항입니다.

## 검사 항목

`hc check`(`harness-catalog check`와 같은 명령)의 종료 코드는 0 통과, 1 위반, 2 검사기 실패입니다.

| 항목 | 보는 것 | 붉으면 |
|---|---|---|
| 1 | 표지 `.harness-catalog`(`layout = 1`), `skills/`, CI 워크플로, pre-commit 설정, README | 저장소 초기화 문제. 운영자가 `init` |
| 2 | `skills/` 바로 아래는 디렉토리(와 `.gitkeep`)뿐, 각 디렉토리에 `SKILL.md` | 잘못 놓인 파일을 옮긴다 |
| 3 | `SKILL.md` 형식(agentskills.io 참조 검증기): `name` 문법·디렉토리 일치·frontmatter | 메시지대로 고친다 |
| 4 | gitleaks 비밀 검출 | 비밀을 지우고 그 비밀을 회전한다. 이력에 남은 것도 비밀이다 |
| 7 | 파일 수·크기·합계 한도, 심볼릭 링크 금지 | 큰 데이터는 밖에 두고 받는 스크립트로 |
| 11 | `tools/<name>/tool.json`의 모양·이름·`runtime.path`·참조 서버·스킬과의 이름 충돌 | [도구 계약](tool.md)대로 |
| 12 | `mcp-servers/<name>/server.json`의 MCP Registry 형식·시크릿 리터럴 | 값을 지우고 형식을 맞춘다 |

종료 2는 검사기 자체의 실패입니다. gitleaks가 없는 것(항목 4는 fail-closed라 없으면 통과가 없습니다)이 흔한 원인입니다. 검사는 커밋 하나의 트리만 보므로 얕은 clone에서도 같습니다. 번호 5·6·8·9·10은 뺀 규칙의 자리라 비어 있습니다(은퇴 이름 재사용 금지, replaced-by, requires-tools, 복사 스크립트 드리프트 — 은퇴는 삭제뿐, 의존성은 스크립트 안에만, 공유 코드는 도구).

## 문제 해결

| 증상 | 조치 |
|---|---|
| 커밋 훅이 `checker failed: gitleaks` | `brew install gitleaks` |
| CI `check`가 `could not read Username` | 코드 저장소가 비공개인데 읽기 자격 시크릿이 없다. 운영자에게 |
