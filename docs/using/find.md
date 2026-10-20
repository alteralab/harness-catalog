---
title: 스킬 찾아 세션에 넣기
description: 도구 넷, 검색과 세션 적재, 검색어 주의.
audience: 팀원
---

# 스킬 찾아 세션에 넣기

하네스에게 말로 시켜 스킬을 찾고 이번 세션에 적재하는 쪽입니다. 먼저 [등록하고 로그인하기](connect.md)를 마칩니다.

## 찾고 적재하기

레지스트리가 내는 도구는 넷이고 전부 읽기입니다. 전체 목록을 돌려주는 도구는 없습니다. 주제로 좁혀 검색합니다. 동사는 `get` 하나입니다. 넷 다 식별자를 받아 정의를 돌려주고, 받은 것을 문맥에 넣는 것은 받아 간 쪽의 일입니다.

| 도구 | 하는 일 |
|---|---|
| `search_skills(query, limit?)` | 스킬 검색 — 이름·설명·metadata 의 BM25 와 설명 임베딩(KURE-v1)의 결합이라 바꿔 말한 질의("캡션" → 자막)도 잡힌다(기본 10, 상한 20): 이름·설명·`sha`(판)·`compatibility`·`has_scripts` |
| `get_skill(id, sha?, path?, archive?)` | 기본은 SKILL.md 본문과 메타데이터·파일 목록. `path`를 주면 그 파일 하나(1 MB, 본문은 null). `archive=true`면 한 판 전체를 tar로 받는 다운로드 명세(URI + 5분 헤더 토큰 + sha256)를 함께 — 파일은 모델을 지나지 않습니다. [pin.md](pin.md)가 씁니다. `sha`를 주면 그 판 |
| `search_tools(query, limit?)` | 도구 검색(엔진은 스킬과 같다): 이름·설명·`sha`·`kind`·`server`. [toolbox.md](toolbox.md) |
| `get_tool(id, sha?)` | `tool.json` 전체. `kind: mcp`면 참조하는 `server.json`을, `kind: script`면 다운로드 명세를 함께. [toolbox.md](toolbox.md) |

네 도구 모두 `tools/list`에 `outputSchema`를 싣습니다. 성공 응답의 `structuredContent`는 그 스키마에 맞고, `content[0].text`에 같은 JSON이 있습니다. 오류는 `isError`와 `{code, detail}`입니다. 스키마의 정본은 서버의 `driving/responses.py`입니다.

하네스에게 말로 시킵니다. 에이전트가 적절한 도구를 고릅니다.

| 말 | 에이전트가 부르는 도구 |
|---|---|
| "카탈로그에 어떤 스킬 있어?" | 전체 목록 도구는 없습니다. 주제를 붙여 `search_skills("…")` |
| "유튜브 자막 뽑는 스킬 있어?" | `search_skills("유튜브 자막")` |
| "yt-subs 불러와" | `get_skill("yt-subs")` |
| (본문이 참조 파일을 가리킬 때) | `get_skill("yt-subs", path="references/x.md", sha=…)` |
| "yt-subs 내려받아" | `get_skill("yt-subs", sha=…, archive=true)` → 명세로 셸에서 `curl`로 받기([pin.md](pin.md)) |

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

## 비밀을 검색어에 넣지 않기

`search_skills`의 검색어와 도구 호출은 팀 Langfuse의 기록에 남습니다. 토큰·비밀번호·개인 정보를 검색어에 적지 않습니다.

## 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `get_skill`이 `unknown_version` | 받는 사이 `main`이 바뀌어 그 판이 이력에서 풀리지 않음 | `sha` 없이 다시 불러 현재 판부터 |
| 검색 결과가 비어 있다 | 아직 색인 전(병합 뒤 한 주기) 또는 없는 스킬 | 잠시 뒤 다시, 또는 다른 낱말로 검색 |
