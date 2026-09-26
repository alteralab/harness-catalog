# skills 계획 — 카탈로그에 실리는 절차 스킬 둘

**상태: 초안 · 작성 2026-09-26.** 이 PLAN은 `~/workspace/harness-catalog/skills/`의 정본이다. 카탈로그 자체가 스킬로 실어 나르는 절차 둘 — `pin-skill`(사람의 내려받기)과 `new-skill`(스킬 뼈대와 팀 규약) — 그리고 카탈로그 README의 **사용자 안내** 절 내용을 관할한다. 설계의 정본은 `../DESIGN.md`(v3.2)이고 이 PLAN은 설계를 복제하지 않는다. 우산은 `../PLAN.md`이며 이 PLAN은 그 §4 P5 한 행을 편다.

## 0. 한 장 요약

카탈로그는 서버 도구 일곱 밖에 CLI도 서버 기능도 더하지 않는다(DESIGN §3). 사람이 매일 쓰는 스킬을 곁에 두는 절차와 새 스킬의 뼈대를 만드는 절차는 **스킬 하나씩**으로 카탈로그에 실린다. 그래서 어느 하네스에서든 같은 지시를 따르게 된다. 이 PLAN이 만드는 것은 SKILL.md 둘, 그 참조 파일, 각자의 evals 최소 쌍이다. 스크립트는 하나도 없다 — 내려받기의 쓰기는 도구 응답을 받은 에이전트가 하고, 뼈대는 파일 넷을 쓰는 일이라 에이전트가 직접 한다(§3 D2·D3). 두 스킬은 이 저장소의 `skills/`에서 저작되고 `publish_skill`로 카탈로그에 게시된 순간부터 카탈로그 저장소의 사본이 정본이다(우산 §7). 게시는 service P3와 distribution P3 뒤이고, 파일럿 하네스 셋에서의 관찰은 pilot의 몫이다.

```
skills/                            # 계획 정본은 plans/skills.md
  pin-skill/
    SKILL.md                     # 내려받기·새 판 확인 절차. 참조 없음, 스크립트 없음
    evals/
      pin-project/prompt.txt · expected.md        # 양성: "yt-subs 내려받아줘"
      no-trigger-load/prompt.txt · expected.md    # 음성: "yt-subs 스킬 이 세션에 넣어줘"(load_skill 이지 pin 아님)
  new-skill/
    SKILL.md                     # 뼈대 생성 → 규약 점검표 → evals → record_eval → 게시 인계
    references/conventions.md    # 팀 규약의 단일 소유자(종료 코드·PEP 723·requires-tools·evals 배치)
    evals/
      scaffold/prompt.txt · expected.md           # 양성: "유튜브 자막 뽑는 스킬 새로 만들자"
      no-trigger-edit/prompt.txt · expected.md    # 음성: "yt-subs description 한 줄만 고쳐줘"
```

## 1. 관할과 경계

**이 PLAN이 소유하는 것.** 두 스킬의 frontmatter·본문·참조·evals, 그리고 `examples/catalog-template/README.md`의 "사용자 안내" 절의 **문장**(검색어에 비밀을 넣지 말라는 안내, 두 스킬의 이름과 한 줄 용도, `list_skills`의 sha로 새 판을 확인한다는 것). README 파일 자체와 운영자 체크리스트(브랜치 보호·deploy key·CI 선택)는 `plans/distribution.md`가 소유한다. 안내 절은 README에 한 번만 있고 이 PLAN은 그 절의 내용을 정한다 — 같은 문장을 SKILL.md에 다시 쓰지 않는다.

**이 PLAN이 구현하는 DESIGN의 계약.** 아래 넷은 DESIGN이 정한 것이고 이 PLAN은 그것을 지시문으로 옮길 뿐이다.

| 계약 | 요지 | 자리 |
|---|---|---|
| 내려받기 절차와 `PINNED` | 사람이 범위(프로젝트·사용자) 하나만 고른다. `.agents/skills/`에 쓰고 `.claude/skills/`는 심볼릭 링크. 임시 디렉토리 → `load_skill` 파일 목록 대조 → 이름 바꾸기. `PINNED`는 한 줄 `<name> <tree sha 40자> <ISO 8601 UTC>`. 새 판은 `list_skills`의 sha와 견준다. 사본은 그 시점의 판이고 갱신은 사용자가 다시 받는다 | DESIGN §4 "내려받기", 규칙 넷 |
| 하네스별 스킬 디렉토리 | Claude Code만 `.claude/skills/`, Codex·Cursor·Gemini CLI·VS Code는 `.agents/skills/`. 같은 이름 둘일 때의 우선순위가 하네스마다 다르다 | DESIGN §4 하네스 표 |
| 팀 규약 | 종속성은 둘로 가른다(`metadata.requires-tools` 공백 구분·`compatibility` 문장). 파이썬은 PEP 723 + `uv run --script`. 종료 코드 2 입력 오류·3 대상 없음·4 시스템 도구 없음. evals는 써야 하는 과제 하나 + 쓰지 말아야 하는 과제 하나가 최소. 결과는 `record_eval`로 | DESIGN §5.1 ②·③ |
| 부르는 도구 | 읽기 넷·`record_eval`·`publish_skill`. 시그니처·기본값·오류는 DESIGN §3 도구 표가 소유하고 여기 다시 적지 않는다 | DESIGN §3 |

**소유하지 않는 것.** 도구 일곱의 동작(service), 템플릿 저장소의 구조와 CI(distribution), 파일럿 하네스에서의 관찰(pilot). 설계 계약을 바꿔야 하면 DESIGN §11 행이 먼저다(우산 §1 경계 규칙 ⑶).

## 2. 스킬 둘의 사양

### 2.1 `pin-skill`

**목적.** "이 스킬 내려받아"라는 사람의 지시를 받은 에이전트가 카탈로그의 스킬 디렉토리 전체를 로컬 하네스 디렉토리에 원자적으로 쓰고, 나중에 새 판이 있는지 확인하게 하는 절차. UC의 `ug skills add`에 해당하는 사람 쪽 절차이고 서버 도구가 아니다.

**frontmatter.**

- `name: pin-skill`
- `description`(초안, 한국어, 검색어 포함):

  > 카탈로그(harness-catalog)의 스킬을 내 하네스의 스킬 디렉토리에 내려받아(pin) 두고, 내려받은 사본의 새 판을 확인한다. 사용자가 "이 스킬 내려받아", "pin 해줘", "곁에 둬", "매일 쓰니까 설치해 둬", "새 판 있어?", "내려받은 스킬 갱신해줘"라고 할 때 쓴다. 범위(프로젝트 또는 사용자)만 묻고, .agents/skills/에 쓰고 .claude/skills/는 심볼릭 링크로 둔다. 임시 디렉토리에 전부 받아 load_skill의 파일 목록과 대조한 뒤 한 번에 이름을 바꾸며, 옆에 PINNED 한 줄을 남긴다. 세션에 스킬을 잠깐 넣는 것(load_skill)은 이 스킬이 아니다.

- `compatibility` 없음(파일 쓰기와 심볼릭 링크뿐이고 시스템 도구가 없다).
- `metadata` 없음.

**본문 — 에이전트가 따르는 단계.**

1. 이 세션이 클라우드 샌드박스(홈 디렉토리를 읽지 않는 세션)면 멈추고 "여기서는 라이브(`load_skill`)만 된다"고 알린다.
2. 사용자에게 **범위 하나만** 묻는다. 프로젝트(저장소에 커밋, 팀원과 공유) 또는 사용자(홈, 나만). 에이전트 종류는 묻지 않는다.
3. `list_skills()` 또는 `search_skills(이름)`으로 `<name>`과 `sha`(유효 판)·`latest_sha`·`certified_sha`를 확인한다. 기본은 유효 판이고, 사용자가 미인증 최신 판을 원할 때만 `latest_sha`를 `sha`로 준다. `unavailable`이 있으면 멈추고 알린다(인증 판을 읽을 수 없는 상태). `replaced-by`가 있으면 대체 대상을 알리고 어느 쪽을 받을지 묻는다.
4. 대상 디렉토리를 정한다. 프로젝트 범위는 `.agents/skills/<name>/`, 사용자 범위는 `~/.agents/skills/<name>/`. 그 이름의 디렉토리가 **이미 있으면 멈추고 알린다**(카탈로그 밖 개인 스킬과의 충돌은 여기서만 잡힌다). 재다운로드(새 판 받기)는 사용자가 명시했을 때만 덮어쓰고, 고친 사본을 지키려면 이름을 바꿔 두라고 알린다.
5. `load_skill(<name>)`(기본은 `sha` 없이 → 유효 판)으로 본문·`sha`·`commit`·`certified`·파일 목록을 받는다. 이 목록이 대조의 기준이고, 이후 `get_skill_file`은 같은 `sha`를 명시해 부른다(인증이 도중에 바뀌어도 한 판만 받는다).
6. 같은 범위 디렉토리 아래 임시 디렉토리 `.<name>.pin-tmp/`를 만들고 `SKILL.md`를 쓴다. 목록의 나머지 파일을 `get_skill_file(<name>, path)`로 하나씩 받아 같은 상대 경로에 쓴다. 바이너리는 base64로 받아 그대로 쓴다. 빈 디렉토리는 만들지 않는다(git에 없다).
7. 임시 디렉토리의 파일 집합과 5의 목록을 대조한다. 하나라도 빠지거나 남으면 임시 디렉토리를 지우고 멈춘다. 기존 사본은 그대로다.
8. `PINNED` 파일을 임시 디렉토리 안에 쓴다. 한 줄, `<name> <sha 40자> <ISO 8601 UTC 시각>`, UTF-8, 끝에 개행.
9. 임시 디렉토리를 `<name>/`으로 한 번에 이름을 바꾼다. 재다운로드(기존 사본이 있는 경우)는 셋으로 한다: 기존 `<name>/`을 같은 디렉토리 안의 `.<name>.pin-old/`로 이름을 바꾸고 → 임시 디렉토리를 `<name>/`으로 바꾸고 → 성공하면 `.pin-old`를 지운다. 둘째 이름 바꾸기가 실패하면 `.pin-old`를 `<name>/`으로 되돌린다. 어느 단계에서 멈춰도 기존 사본은 남는다.
10. `.claude/skills/`(또는 `~/.claude/skills/`)가 없으면 만들고, `.claude/skills/<name>`이 `../../.agents/skills/<name>`을 가리키는 심볼릭 링크를 둔다. 이미 실제 디렉토리가 있으면 링크를 만들지 않고 알린다.
11. 사용자에게 보고한다. 경로, sha, 파일 수, 그리고 "이 사본은 이 시점의 판이고 새 판은 다시 받아야 한다".

**새 판 확인(같은 스킬의 둘째 지시).** "새 판 있어?"·"갱신해줘"에는 프로젝트·사용자 **두 범위의** `PINNED`를 모두 읽고 `list_skills()`의 `sha`(유효 판)와 견준다. 은퇴한 이름은 재사용되지 않으므로 sha가 다르면 새 판이다. 같은 스킬이 두 범위에 다 있으면 낡은 쪽을 알리고 하나로 합치기를 권한다(두 sha가 같으면 어느 쪽이 이겨도 결과가 같다). 새 판을 받기로 하면 4~11을 다시 한다. 판이 새로 나오는 주기는 레지스트리의 fetch 주기(운영 설정)라 이 스킬은 시간을 말하지 않고 sha만 견준다.

**번들 파일.** 없다. 하네스 디렉토리 표는 본문에 표 하나로 넣는다(§3 D1). 스크립트는 없다(§3 D2).

### 2.2 `new-skill`

**목적.** 새 스킬의 뼈대를 카탈로그 **밖**의 개인 디렉토리에 만들고, 팀 규약을 점검표로 통과시키고, evals 최소 쌍을 두고, 결과를 `record_eval`로 붙이는 데까지의 절차. 게시 자체는 사람의 지시 뒤에만 `publish_skill`로 인계한다. Anthropic `skill-creator`·Codex `$skill-creator`와 같은 일을 하되 이 팀의 규약을 뼈대에 넣는다.

**frontmatter.**

- `name: new-skill`
- `description`(초안):

  > 팀 카탈로그(harness-catalog)에 올릴 새 스킬의 뼈대를 만들고 팀 규약대로 채운다. 사용자가 "스킬 새로 만들자", "이 절차를 스킬로 만들어", "SKILL.md 뼈대 잡아줘", "스킬 만들어서 카탈로그에 올리자"라고 할 때 쓴다. 먼저 search_skills로 같은 일을 하는 스킬이 있는지 확인하고, 개인 디렉토리에 SKILL.md·scripts/·evals/를 만들며, 종속성(metadata.requires-tools와 compatibility), PEP 723 + uv run --script, 종료 코드 2/3/4, 양성·음성 evals 한 쌍, record_eval 기록, description 검수를 점검표로 지난다. 게시(publish_skill)는 사용자가 지시할 때만 한다. 기존 스킬의 한 줄 수정은 이 스킬이 아니다.

- `compatibility: "스크립트가 있는 스킬을 만들 때 uv가 필요하다(uv run --script). 검증에 skills-ref validate를 쓴다"`
- `metadata.requires-tools: "uv skills-ref"`(공백 구분, 토큰 문법 `[a-z0-9._+-]+`).

**본문 — 에이전트가 따르는 단계.**

1. 사용자의 한 문장에서 스킬이 하는 일과 발동 상황을 받아 적는다. `search_skills`로 같은 일을 하는 스킬이 있는지 확인하고, 있으면 갱신 경로(`list_skills`의 `latest_sha` → `load_skill(id, sha=latest_sha)` → 고치기 → `publish_skill(expected_sha=latest_sha)`. 유효 판이 아니라 latest에서 시작한다)를 안내하고 멈춘다.
2. 이름을 정한다. `name` 문법(1–64자, 소문자·숫자·하이픈)이고 `list_skills`에 없어야 한다. 은퇴한 이름은 게시 시 `name_taken`으로 거부되니 그때 바꾼다.
3. 카탈로그 밖의 개인 디렉토리(사용자가 지정, 기본은 현재 저장소 밖의 `~/skills-draft/<name>/`)에 뼈대를 쓴다. `SKILL.md`(frontmatter + 본문 절: 언제 쓰는가·단계·실패 대응 표), 스크립트가 있으면 `scripts/`, `evals/`.
4. `references/conventions.md`의 점검표를 하나씩 지난다. 결정적인 일(계산·변환·조회)은 스크립트로, 판단은 본문 지시로 가른다. 파이썬 스크립트는 PEP 723 머리와 `uv run --script scripts/x.py` 호출로 적고 실행 비트에 기대지 않는다. 시스템 도구는 `metadata.requires-tools`(기계용)와 `compatibility`(사람용 문장) 둘 다에. 스크립트의 종료 코드는 2 입력 오류·3 대상 없음·4 시스템 도구 없음(설치 안내 한 줄과 함께).
5. evals 최소 쌍을 둔다. 써야 하는 과제 하나(`<name>/evals/<case>/prompt.txt`·`expected.md`)와 쓰지 말아야 하는 과제 하나(`no-trigger-*`).
6. description을 검수한다. 무엇을·언제 쓰는지, 검색될 낱말(사용자가 실제로 말할 표현)이 들었는지, 쓰지 말아야 할 상황이 한 줄 있는지.
7. `skills-ref validate <dir>`를 돌린다(권고. 서버가 어차피 다시 한다).
8. 두 프롬프트를 스킬 있이·없이 돌려 `expected.md`와 견준다. 결과를 `record_eval(run_id=새 UUID, id, sha, model, harness, passed, baseline_passed)`로 붙인다 — 단, sha는 게시 뒤에야 생기므로 이 단계는 게시 뒤에 한 번 더 안내한다.
9. 사용자에게 뼈대의 경로와 점검표 결과를 보고하고 멈춘다. **게시는 사용자가 "올려"라고 할 때만** `publish_skill(name, files)`를 부른다.

**번들 파일.** `references/conventions.md` 하나 — 팀 규약의 단일 소유자(§3 D4). 점검표 형식이고 DESIGN §5.1 ②·③의 규약을 실행 가능한 문장으로 옮긴 것이다. 스크립트는 없다(§3 D3).

### 2.3 README 사용자 안내 절 (examples/catalog-template/README.md 안)

문단 셋. ⑴ 등록 한 줄과 로그인 한 번(레지스트리 URL은 distribution가 채운다). ⑵ 두 스킬의 이름과 한 줄 용도, 새 판 확인은 `list_skills`의 sha. ⑶ 검색어는 저장된다(보존 일수 뒤 삭제) — 검색어에 비밀·개인 정보를 넣지 말 것. 팀 규약의 본문은 여기 다시 쓰지 않고 `new-skill`의 `references/conventions.md`를 가리킨다.

## 3. 판정 원장

DESIGN이 정하지 않은 구현 선택만 적는다. 근거 등급은 우산 §3-1의 넷(실측·문면·설계 판단·휴리스틱).

| # | 물음 | 판정 | 근거 |
|---|---|---|---|
| D1 | 하네스 디렉토리 표를 `references/`로 번들하는가 본문에 넣는가 | **본문에 표 하나.** 행 다섯이고 `pin-skill`의 4·10단계가 이 표 없이는 성립하지 않는다. 활성화 시 본문과 함께 읽혀야 하는 정보라 필요 시 파일(3단계)이 아니다 | 설계 판단(DESIGN §1.4 점진적 공개의 층 구분). 본문 500줄 권고 안에 든다(휴리스틱, 표 6줄) |
| D2 | `pin-skill`에 스크립트를 두는가 | **두지 않는다.** 쓰는 내용은 MCP 도구 응답(`load_skill`·`get_skill_file`)이고 그것을 가진 것은 에이전트뿐이다. 스크립트는 레지스트리에 다시 붙어야 해서 토큰·URL을 인자로 받게 되고 그것이 곧 CLI다(DESIGN §7 "내려받기 CLI" 기각) | 설계 판단(DESIGN §3 "서버 도구는 없다", §7). 원자성은 임시 디렉토리 → 대조 → 이름 바꾸기의 지시로 확보하고 준수 여부는 pilot이 잰다 |
| D3 | `new-skill`에 `scripts/init_skill.py`를 두는가 | **두지 않는다.** 뼈대는 파일 넷(SKILL.md·`scripts/.gitkeep` 없음·evals 파일 넷)을 쓰는 일이고 에이전트가 직접 쓰는 것이 더 짧다. 호출자가 에이전트 하나뿐인 스크립트는 C-SPEC-1의 대상이다. Anthropic `init_skill.py`는 선례이지 우리 규약(PEP 723·종료 코드·evals 쌍)을 모른다 | 설계 판단. Anthropic 선례는 문면(DESIGN §5.1 ①). C-SPEC-1·C-LIB-1은 "표준이 있는 계산"에 위임하라는 것인데 뼈대 쓰기는 계산이 아니다 |
| D4 | 팀 규약의 단일 소유자 | **`new-skill/references/conventions.md`.** README와 `new-skill` 본문은 그 파일을 가리키고 규약 문장을 다시 쓰지 않는다. DESIGN §5.1은 설계의 서술이고 실행 가능한 점검표는 이 파일 하나다 | 설계 판단(C-DUP-2: 세 벌째가 되기 전에 소유자 하나). DESIGN·README·SKILL.md 셋에 같은 규약이 있으면 정확히 그 실패다 |
| D5 | 본문 언어 | **한국어.** 이 팀의 하네스 세션이 한국어이고 description의 발동 표현이 사용자의 실제 발화여야 한다. `name`·도구 이름·파일 경로는 그대로 영문 | 실측(이 세션과 `~/workspace`의 스킬 전부가 한국어 본문). 어휘 검색이 description을 대상으로 하므로 한국어 낱말이 검색어와 맞아야 한다(설계 판단) |
| D6 | 레지스트리의 fetch 주기를 에이전트가 알아야 하는가 | **몰라도 된다.** 새 판 판정은 `PINNED`의 sha와 `list_skills`의 sha 비교뿐이다. 주기는 운영 설정(`FETCH_INTERVAL_SECONDS`)이라 스킬 본문에 시간을 적으면 낡는다 | 설계 판단(DESIGN §2 사용자 결정 2026-09-26). C-COMMENT-2와 같은 이유 |
| D7 | Cursor가 호환 경로를 함께 읽어 같은 스킬이 두 번 보이는 문제 | **현재 규칙은 심볼릭 링크 하나다.** Claude Code·Codex는 문서로 확인됐고 Cursor·Gemini CLI·VS Code는 실측 전이다. 이 PLAN은 그 결과를 예측하지 않는다. 실측은 pilot P0의 항목이고 결과가 갈리면 DESIGN §4의 "링크 대신 사본 하나를 더 둔다"가 그때의 지시다 | 문면(DESIGN §4 하네스 표, **가정:** 표시). 실측은 pilot |
| D8 | 두 스킬 자신의 evals | **각자 양성 하나·음성 하나.** 자기 규약을 자기가 지킨다. `pin-skill`의 음성은 "세션에 넣어줘"(`load_skill`이지 pin이 아님), `new-skill`의 음성은 "한 줄만 고쳐줘"(갱신이지 뼈대가 아님). 판정은 사람이 눈으로, 결과는 게시 뒤 `record_eval` | 설계 판단(DESIGN §5.1 evals 행, `[altera-skills]` 양성·음성 각 1 규약은 문면) |
| D9 | 뼈대의 기본 위치 | **현재 저장소 밖 `~/skills-draft/<name>/`, 사용자가 다른 곳을 말하면 그곳.** 카탈로그 밖이 곧 비공개다(DESIGN §5). 현재 저장소 안에 두면 그 저장소에 스킬이 섞여 커밋된다 | 설계 판단. 경로 이름은 휴리스틱 |
| D10 | 이름 | `pin-skill`·`new-skill` 고정 | 설계 판단(DESIGN §4·§5.1, 3차 리뷰에서 `platform/pin-skill` → `pin-skill`) |

## 4. 단계

**skills P1 작성.** (우산 P4. service P1 뒤 언제든 시작할 수 있다)

1. `pin-skill/SKILL.md` — §2.1의 frontmatter와 단계 11 + 새 판 확인. 하네스 표는 본문에.
2. `new-skill/SKILL.md`와 `references/conventions.md` — §2.2. 점검표는 DESIGN §5.1 ②·③에서 옮기되 문장은 실행형으로.
3. 각자 evals 양성·음성 한 쌍(§3 D8).
4. `skills-ref validate skills/pin-skill skills/new-skill` 로컬 통과.
5. `altera-rules.yml`에 `purpose/agent-skill` 선언, 재실체화, `pre-commit run --all-files`로 그 축의 게이트를 한 번 완주(우산 §3-5, V9).
6. Codex 독립 리뷰 한 번(우산 §3-6). 발견의 반영·기각을 §9에.
7. README 사용자 안내 절 문장을 distribution에 넘긴다(§2.3). 파일은 distribution가 쓴다.

**skills P2 게시.** (우산 P5. service P3와 distribution P3 완료 뒤 — distribution P3의 첫 카탈로그 저장소가 P1의 두 스킬을 첫 커밋에 넣고, 이 단계는 그 뒤 `publish_skill`로 같은 내용을 게시한다. 내용이 같으면 tree SHA 멱등으로 커밋이 생기지 않는다)

1. 사람의 세션에서 `publish_skill("pin-skill", files)`, `publish_skill("new-skill", files)`. 응답의 sha를 §9에 적는다.
2. `list_skills()`에 둘이 보이고 `search_skills("내려받아")`·`search_skills("스킬 만들자")`가 각각을 첫 후보로 낸다.
3. 두 스킬의 evals를 스킬 있이·없이 돌려 `record_eval`로 붙인다. `list_skills`의 `evals`에 나온다.
4. 파일럿 하네스 셋에서의 `pin-skill` 관찰은 pilot의 몫이다(우산 §9 V6 "내려받기 왕복").

**완료 조건.** skills P1은 우산 §4 P4 그대로: "두 스킬이 `skills-ref validate`를 통과하고 각자 양성·음성 evals 한 쌍이 있으며 `purpose/agent-skill` 게이트가 SKILL.md 둘을 검사하며 한 번 돌았다". skills P2는 우산 §4 P5의 게시 몫: "두 스킬을 `publish_skill`로 게시해 `list_skills`에 보이게 한다". 하네스 셋에서의 `pin-skill` 관찰은 우산 P6(pilot Q11)의 완료 조건이다.

## 5. 불채택 표

기각 사유는 현재형으로만 적는다.

| 항목 | 기각 근거 (왜 지금 아닌가) |
|---|---|
| 내려받기 CLI | 하네스 밖(CI·스크립트)에서 내려받는 수요가 없다. 읽기는 도구 둘로 충분하고 절차는 스킬 하나다(DESIGN §3·§7) |
| 서버 쪽 pin 도구 | 내려받기는 클라이언트 쪽 쓰기라 MCP 서버가 할 수 없다(DESIGN §3) |
| 에이전트 종류를 묻는 선택지 | `.agents/skills/` + `.claude/skills/` 링크로 파일럿 하네스 셋이 덮인다(문면). 물을 것이 늘면 인터페이스가 얕아진다 |
| 내려받은 사본의 자동 갱신 | 사본의 뜻이 point-in-time이다(DESIGN §4). 자동 갱신은 사용자가 고친 사본을 덮어쓴다 |
| 게시 전용 셋째 스킬 | 게시는 `publish_skill` 한 번이고 `new-skill`의 마지막 단계가 그 인계다. 절차가 없는 스킬은 이름만 늘린다 |
| DESIGN 전문을 `references/`로 번들 | 스킬이 필요로 하는 것은 규약 점검표(`conventions.md`)뿐이다. 설계 문서를 실으면 게시 상한(5 MB)과 무관하게 활성화 시 읽을 것이 늘고 설계 개정마다 스킬이 낡는다 |
| evals 러너·판정자·기록 대장 | DESIGN §5.1이 "팀이 원할 때 그 위에 얹는다"로 두었고 지금 스킬은 둘이다. 눈으로 보는 것이 러너보다 싸다 |
| 영어 본문 | 발동 표현이 사용자의 실제 발화(한국어)여야 어휘 검색과 description 매칭이 된다(§3 D5) |
| `pin-skill`의 무결성 검사(파일별 해시 대조) | `get_skill_file`이 SHA를 돌려주지만 그것은 blob 식별이지 전송 오류 검출이 아니다. 대조는 파일 목록으로 충분하고, 사본이 맞는지는 `PINNED`의 tree sha와 `list_skills`가 답한다 |

## 6. 리스크 대응표

| # | 리스크 | 대응 |
|---|---|---|
| R1 | 에이전트가 원자적 절차(임시 디렉토리 → 대조 → 이름 바꾸기)를 건너뛰고 대상 디렉토리에 바로 쓴다 | 본문의 단계 6~9를 번호로 강제하고 7에 "빠지거나 남으면 지우고 멈춘다"를 명시. pilot Q11이 하네스 셋에서 명령 순서를 원문으로 관찰한다 |
| R2 | 하네스가 링크와 실체를 둘 다 읽어 같은 스킬이 두 번 보인다 | 현재 규칙은 링크 하나(§3 D7). 실측은 pilot P0. 본문은 "두 번 보이면 알려 달라"를 사용자에게 요청하는 문장을 둔다 |
| R3 | description이 과잉 발동한다(모든 "스킬" 발화에 `new-skill`이 뜬다) | 음성 evals(§3 D8)가 잡는다. description 끝에 "~는 이 스킬이 아니다" 한 줄 |
| R4 | README 안내 절과 `conventions.md`의 규약 문장이 어긋난다 | README는 규약 문장을 갖지 않고 가리키기만 한다(§3 D4). 어긋날 문장이 없다 |
| R5 | `skills-ref validate`가 한국어 description을 거부하거나 길이 계산이 바이트 기준이다 | V1·V2가 실물로 잰다. 길이 계산 기준은 검증기 소스에서 읽어 §9에 적는다 |

## 7. 검증 원장

| # | 검증 | 방법 | 통과 기준 | 상태 |
|---|---|---|---|---|
| V1 | 스펙 준수 | `skills-ref validate` 두 디렉토리 | 둘 다 오류 0 | 대기 |
| V2 | frontmatter 한도 | `name` 문법 `^[a-z0-9-]{1,64}$`·디렉토리명 일치, description 1–1024자 | 둘 다 통과 | 대기 |
| V3 | `PINNED` 형식 | 하네스 하나에서 `pin-skill`로 프로젝트 범위 내려받기 | 파일이 정확히 한 줄 `<name> <sha40> <ISO8601Z>` + 개행이고 sha가 `list_skills`와 같다 | 대기 |
| V4 | 실패 시 원자성 | 세 지점에서 실패를 주입한다: (a) 6단계 도중 `get_skill_file` 실패(없는 경로를 목록에 끼움), (b) 재다운로드의 둘째 이름 바꾸기 실패(대상 이름에 쓰기 불가 파일을 둠), (c) 첫 이름 바꾸기 뒤 중단 | (a) `.<name>.pin-tmp/`가 남지 않고 기존 사본 그대로. (b) `.pin-old`가 `<name>/`으로 되돌아온다. (c) `<name>/`이 기존 사본 또는 새 사본 중 하나로 온전하고 반쪽이 없다 | 대기 |
| V5 | 기존 디렉토리 거부 | 같은 이름의 개인 스킬을 먼저 두고 내려받기 지시 | 쓰지 않고 멈추며 충돌을 알린다 | 대기 |
| V6 | 두 범위 낡음 감지 | 프로젝트·사용자 범위에 sha가 다른 두 사본을 두고 "새 판 있어?" | 낡은 쪽을 지목하고 합치기를 권한다 | 대기 |
| V7 | 뼈대의 규약 | `new-skill`로 만든 뼈대가 V1을 통과하고, 생성된 예시 스크립트가 종료 코드 2·3·4를 각각 낸다(입력 없음·대상 없음·`PATH`에서 도구 제거) | 셋 다 관찰 | 대기 |
| V8 | evals 쌍 | 두 스킬 디렉토리에 양성·음성 각 1 | `evals/*/prompt.txt`·`expected.md` 넷 존재, 음성은 `no-trigger-*` | 대기 |
| V9 | `record_eval` 왕복 | 게시 뒤 사람 토큰으로 두 스킬의 결과를 붙인다(service P3 뒤) | `list_skills`의 `evals`에 `(model, harness)`별 최근 행이 보인다 | 대기 |
| V10 | 규칙 게이트 | `purpose/agent-skill` 선언 뒤 `pre-commit run --all-files` | 그 축의 게이트가 SKILL.md 둘을 검사하며 한 번 돌았다 | 대기 |

## 8. 개정 규약

판정 변경은 §3에 행 추가(기존 행 유지, 후속 행이 우선). 설계 계약(`PINNED` 형식·하네스 표·팀 규약)의 변경은 DESIGN §11이 먼저. 게시된 뒤의 스킬 수정은 카탈로그 저장소가 정본이므로 `publish_skill(expected_sha)`로 하고, 이 저장소의 `skills/`는 같은 내용을 따라 적어 이력만 남긴다. 기록은 현재 상태만(REVIEW.md V-REC-1).

## 9. 진행 원장

| 일자 | 항목 | 내용 | 근거 |
|---|---|---|---|
| 2026-09-26 | 설계 개정 반영 | 8차 리뷰: pin·새 판 확인은 유효 판 `sha`, 편집은 `latest_sha`에서, `unavailable`이면 멈춤 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 인증된 판: `pin-skill`의 기본은 인증 판(단계 3·5), 새 판 확인은 `certified_sha` 기준, 받는 동안 `sha`를 고정 | DESIGN §11 |
| 2026-09-26 | Codex 교차 검증 1회 | 반영: 재다운로드 절차를 백업 이름 바꾸기로(단계 9, V4 세 지점), 도구 시그니처 사본 삭제(§1 표), 단계 번호를 우산 P4(작성)·P5(게시)로, R1·R5의 미래 조건절 삭제, 배치 그림의 PLAN.md 제거. 기각 없음 | 우산 §11 |
| 2026-09-26 | PLAN 초판 | 스킬 둘의 사양(description 초안·단계)·판정 D1~D10·검증 V1~V10. 파일은 아직 없다 | 우산 §4 P4·P5 |
