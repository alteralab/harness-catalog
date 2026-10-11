---
name: pin-skill
description: 카탈로그(harness-catalog)의 스킬을 내 하네스의 스킬 디렉토리에 내려받아(pin) 두고, 내려받은 사본의 새 판을 확인한다. 사용자가 "이 스킬 내려받아", "pin 해줘", "곁에 둬", "매일 쓰니까 설치해 둬", "새 판 있어?", "내려받은 스킬 갱신해줘"라고 할 때 쓴다. 범위(프로젝트 또는 사용자)만 묻고, .agents/skills/에 쓰고 .claude/skills/는 심볼릭 링크로 둔다. 임시 디렉토리에 전부 받아 load_skill의 파일 목록과 대조한 뒤 한 번에 이름을 바꾸며, 옆에 PINNED 한 줄을 남긴다. 세션에 스킬을 잠깐 넣는 것(load_skill)은 이 스킬이 아니다.
---

# pin-skill — 카탈로그 스킬 내려받기

카탈로그의 스킬 디렉토리 전체를 로컬 하네스 디렉토리에 **원자적으로** 쓰고, 나중에 새 판이 있는지 확인한다. 서버 도구도 CLI도 없다 — 레지스트리는 읽기 도구만 내므로 쓰기는 이 세션의 에이전트(셸)가 한다. 파일 내용은 `get_skill_archive`의 tar로 모델을 거치지 않고 디스크로 간다.

## 언제 쓰는가

- 쓴다: "이 스킬 내려받아", "pin 해줘", "곁에 둬", "매일 쓰니까 설치해 둬", "새 판 있어?", "내려받은 스킬 갱신해줘".
- 쓰지 않는다: "이 스킬 세션에 넣어줘"처럼 지금 한 번 쓰려는 것은 `load_skill`이다. 내려받지 않는다.

## 하네스별 스킬 디렉토리

| 하네스 | 프로젝트 범위 | 사용자 범위 | 같은 이름이 둘일 때 |
|---|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | 사용자 범위가 이긴다 |
| Codex | `.agents/skills/` | `~/.agents/skills/` | 둘 다 선택기에 보인다 |
| Cursor | `.agents/skills/`, `.cursor/skills/` (호환: `.claude/skills/`) | `~/.agents/skills/`, `~/.cursor/skills/` | 문서에 규칙 없음 |
| Gemini CLI | `.gemini/skills/` 또는 `.agents/skills/` | `~/.gemini/skills/` 또는 `~/.agents/skills/` | 같은 층에서는 `.agents/skills/` 우선 |
| VS Code / Copilot | `.github/skills/`, `.claude/skills/`, `.agents/skills/` | `~/.copilot/skills/`, `~/.claude/skills/`, `~/.agents/skills/` | 문서에 규칙 없음 |

그래서 쓰는 자리는 하나다: `.agents/skills/<name>/`(프로젝트) 또는 `~/.agents/skills/<name>/`(사용자). `.claude/skills/<name>`은 그곳을 가리키는 심볼릭 링크다. 에이전트 종류는 묻지 않는다.

## 내려받기 — 단계

1. 이 세션이 클라우드 샌드박스(홈 디렉토리를 읽지 않는 세션)면 멈추고 알린다: "여기서는 라이브(`load_skill`)만 된다."
2. 사용자에게 **범위 하나만** 묻는다: 프로젝트(저장소에 커밋, 팀원과 공유) 또는 사용자(홈, 나만).
3. `search_skills(<이름>)`으로 `<name>`과 현재 `sha`를 확인한다. `replaced_by`가 있으면 대체 대상을 알리고 어느 쪽을 받을지 묻는다.
4. 대상 디렉토리를 정한다. 프로젝트 범위는 `.agents/skills/<name>/`, 사용자 범위는 `~/.agents/skills/<name>/`. 그 이름의 디렉토리가 **이미 있으면 멈추고 알린다** — 카탈로그 밖의 개인 스킬과 이름이 겹치는 것은 여기서만 잡힌다. 재다운로드(새 판 받기)는 사용자가 명시했을 때만 덮어쓰고, 고친 사본을 지키려면 이름을 바꿔 두라고 알린다.
5. `load_skill(<name>)`으로 `sha`·`commit`·파일 목록을 받는다. 이 목록이 대조의 기준이다. 이후 호출은 **같은 `sha`를 명시**한다 — 받는 도중 `main`이 바뀌어도 한 판만 받는다.
6. `get_skill_archive(<name>, sha=<5의 sha>)`로 다운로드 명세(`uri`·`headers`·`size`·`sha256`)를 받는다. 같은 범위 디렉토리 아래 임시 디렉토리 `.<name>.pin-tmp/`를 만들고 **셸에서** 받아 검증하고 푼다 — 파일 내용은 모델을 지나지 않는다:
   ```sh
   curl -fsS -H "X-Harness-Archive-Token: <headers의 값>" -o .<name>.pin-tmp.tar "<uri>"
   # 크기와 sha256이 명세와 같아야 다음으로 간다(다르면 파일을 지우고 멈춘다)
   wc -c < .<name>.pin-tmp.tar ; shasum -a 256 .<name>.pin-tmp.tar   # Linux는 sha256sum
   tar -xf .<name>.pin-tmp.tar -C .<name>.pin-tmp/ && rm .<name>.pin-tmp.tar
   ```
   토큰은 5분짜리다. 403이면 명세를 **한 번** 다시 받아 재시도한다(레지스트리가 재기동되면 옛 토큰은 전부 403이다). `curl`이 없으면 `python3 -c 'import urllib.request,sys; …'` 한 줄로 같은 헤더를 붙여 받는다.
7. 풀린 파일 집합과 5의 목록을 대조한다. 하나라도 빠지거나 남으면 임시 디렉토리를 지우고 멈춘다. 기존 사본은 그대로다. (sha256은 전송을, 이 대조는 판을 보증한다.)
8. `PINNED` 파일을 임시 디렉토리 안에 쓴다. 한 줄, `<name> <sha 40자> <ISO 8601 UTC 시각>`, UTF-8, 끝에 개행. 예: `yt-subs 3f2a…(40자) 2026-10-07T09:12:00Z`.
9. 임시 디렉토리를 `<name>/`으로 **한 번에** 이름을 바꾼다. 재다운로드(기존 사본이 있을 때)는 셋으로: 기존 `<name>/`을 같은 디렉토리 안의 `.<name>.pin-old/`로 바꾸고 → 임시 디렉토리를 `<name>/`으로 바꾸고 → 성공하면 `.pin-old`를 지운다. 둘째 이름 바꾸기가 실패하면 `.pin-old`를 `<name>/`으로 되돌린다. 어느 단계에서 멈춰도 기존 사본은 남는다.
10. `.claude/skills/`(또는 `~/.claude/skills/`)가 없으면 만들고, `.claude/skills/<name>`이 `../../.agents/skills/<name>`(사용자 범위는 `../.agents/skills/<name>`)을 가리키는 심볼릭 링크를 둔다. 그 자리에 이미 실제 디렉토리가 있으면 링크를 만들지 않고 알린다.
11. 보고한다: 경로, `sha`, 파일 수, 그리고 "이 사본은 이 시점의 판이고 새 판은 다시 받아야 한다".

## 새 판 확인 — "새 판 있어?", "갱신해줘"

1. 프로젝트·사용자 **두 범위의** `PINNED`를 모두 읽는다(`.agents/skills/*/PINNED`, `~/.agents/skills/*/PINNED`).
2. 이름마다 `search_skills(<name>)`을 불러 `sha`와 견준다. 은퇴한 이름은 다시 쓰이지 않으므로 sha가 다르면 새 판이다. 검색에 나오지 않는 이름은 은퇴한 것이다 — 알린다.
3. 같은 스킬이 두 범위에 다 있으면 낡은 쪽을 알리고 하나로 합치기를 권한다. 두 sha가 같으면 어느 쪽이 이겨도 결과가 같다.
4. 새 판을 받기로 하면 "내려받기"의 4~11을 다시 한다. 반영 주기는 레지스트리의 운영 설정이라 이 스킬은 시간을 말하지 않고 sha만 견준다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 클라우드 샌드박스 세션 | 멈춘다. 라이브(`load_skill`)만 안내 |
| 같은 이름의 디렉토리가 이미 있다 | 멈추고 알린다. 덮어쓰기는 사용자의 명시 뒤에만, `.pin-old` 절차로 |
| 파일 대조가 어긋난다 | 임시 디렉토리를 지우고 멈춘다. 기존 사본 유지 |
| `get_skill_archive`가 `unknown_version` | `main`이 바뀌어 그 판이 이력에서 풀리지 않는다 — 5부터 다시 |
| 다운로드가 403 | 토큰 만료(5분) 또는 레지스트리 재기동. 명세를 한 번 다시 받는다. 두 번째도 403이면 멈추고 알린다 |
| 크기·sha256이 명세와 다르다 | 받은 파일을 지우고 멈춘다. 다시 받아도 다르면 알린다(프록시가 본문을 바꾸는 중) |
| `get_skill_archive`가 `input_limit` | 그 판의 tar가 20 MB를 넘는다 — 스킬 저자에게 알린다(파일을 줄여야 한다) |
| `.claude/skills/<name>`이 실제 디렉토리 | 링크를 만들지 않고 알린다 |
| `replaced_by`가 있다 | 대체 대상을 알리고 선택을 묻는다 |
