---
title: 도구 올리기
description: 도구 계약, runtime 두 갈래, 스킬과의 이름 유일성.
audience: 스킬 저자
---

# 도구 올리기

입출력이 정해진 것을 스킬이 아니라 도구로 올립니다. 올리는 차례는 스킬과 같아 [올리는 절차](submit.md)를 따르고, 검사 항목은 [검사 통과시키기](checks.md)의 11·12입니다.

스킬이 "어떻게 하는가"의 산문이라면 도구는 "무엇을 부를 수 있는가"의 스키마입니다. 자주 쓰이고 입출력이 정해진 것은 도구로 올립니다(DESIGN §11 2026-10-11).

```
tools/<name>/tool.json          # 필수. $schema(선택) · name(= 디렉토리명, 스킬과 같은 문법) · description(≤1024자) · inputSchema(type: object) · outputSchema(선택, MCP와 같은 이름) · runtime · metadata(선택)
tools/<name>/scripts/x.py       # kind: script면 runtime.path가 가리키는 파일
mcp-servers/<name>/server.json  # kind: mcp 도구가 참조하는 배선 레코드(MCP Registry 형식: name·version·packages|remotes)
```

`runtime`은 둘 중 하나입니다.

| kind | 필드 | 규칙 |
|---|---|---|
| `script` | `path`, `command` | `command`는 셸을 거치지 않는 argv 배열이고 `path`는 그 원소 정확히 하나. `path`는 디렉토리 안의 일반 파일(링크 금지) |
| `mcp` | `server`, `tool` | `server`는 `mcp-servers/<server>/`가 있어야 하고 `tool`은 그 서버가 내는 도구 이름 |

뼈대는 `write` 스킬이 도구 `scaffold`(`tools/scaffold/`, 카탈로그 클론의 `.mcp.json`으로 MCP에 떠 있음)로 만듭니다(멱등). `tool.json`의 선택 키 `$schema`가 `schemas/tool.schema.json`을 가리키면 편집기가 타이핑 중에 검증합니다. 그 파일은 `harness-catalog init`이 core 모델에서 생성해 두고, 낡았으면 `hc check`가 경고하고 운영자가 `hc init <repo-url> --refresh`로 다시 씁니다. 레지스트리는 `$schema`를 해석하지 않습니다. 계약의 저자용 문면은 `skills/write/references/tool-contract.md`입니다.

규칙은 스킬과 같은 것이 많습니다. 이름은 **스킬과 합쳐 전역 유일**입니다(검사 11). 시크릿은 저장소에 없습니다 — `server.json`의 `isSecret: true` 항목은 `value`·`default`를 가질 수 없습니다(검사 12). `metadata`는 자유 맵이고 팀 규약 키는 없습니다 — 의존성은 스크립트 안에만, 은퇴는 디렉토리 삭제뿐입니다(스킬과 같다). 검사 항목은 11(도구)·12(서버)이고 `hc check`가 함께 봅니다.
