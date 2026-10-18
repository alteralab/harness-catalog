# skills 계획 — 카탈로그에 실리는 절차 스킬 둘

**상태: 초안 · 작성 2026-09-26.** 이 PLAN은 `~/workspace/harness-catalog/packages/cli/src/harness_catalog_cli/templates/skills/`(2026-10-10까지는 루트 `skills/`)의 정본이다. 카탈로그 자체가 스킬로 실어 나르는 절차 둘 — `pin-skill`(사람의 내려받기)과 `write-skill`(스킬 뼈대와 팀 규약) — 그리고 카탈로그 README의 **사용자 안내** 절 내용을 관할한다. 설계의 정본은 `../DESIGN.md`(v3.3)이고 이 PLAN은 설계를 복제하지 않는다. 우산은 `../PLAN.md`이며 이 PLAN은 그 §4 P5 한 행을 편다.

## 0. 한 장 요약

카탈로그는 서버 도구 넷 밖에 CLI도 서버 기능도 더하지 않는다(DESIGN §3). 사람이 매일 쓰는 스킬을 곁에 두는 절차와 새 스킬의 뼈대를 만드는 절차는 **스킬 하나씩**으로 카탈로그에 실린다. 그래서 어느 하네스에서든 같은 지시를 따르게 된다. 이 PLAN이 만드는 것은 SKILL.md 둘, 그 참조 파일, 각자의 evals 최소 쌍이다. 스크립트는 하나도 없다 — 내려받기의 쓰기는 도구 응답을 받은 에이전트가 하고, 뼈대는 파일 넷을 쓰는 일이라 에이전트가 직접 한다(§3 D2·D3). 두 스킬은 이 저장소의 `skills/`에서 저작되고 카탈로그 저장소에 PR로 병합된 순간부터 그쪽이 정본이다(우산 §7). 게시는 service P3와 distribution P3 뒤이고, 파일럿 하네스 셋에서의 관찰은 pilot의 몫이다.

```
skills/                            # 계획 정본은 plans/skills.md
  pin-skill/
    SKILL.md                     # 내려받기·새 판 확인 절차. 참조 없음, 스크립트 없음
    evals/                       # Harbor 태스크 둘(DESIGN §5.1)
      pin-project/               #   양성: instruction.md "yt-subs 내려받아줘" · tests/test.sh가 .agents/skills/yt-subs/PINNED 형식을 검사
      no-trigger-load/           #   음성: "yt-subs 스킬 이 세션에 넣어줘"(load_skill이지 pin 아님) · 검증기는 PINNED가 생기지 않았는지
  write-skill/
    SKILL.md                     # 뼈대 생성 → 규약 점검표 → evals(Harbor→Langfuse) → 게시 인계
    references/conventions.md    # 팀 규약의 단일 소유자(종료 코드·PEP 723·requires-tools·evals 배치·공유 스크립트)
    evals/                       # Harbor 태스크 둘
      scaffold/                  #   양성: "유튜브 자막 뽑는 스킬 새로 만들자" · 검증기는 브랜치에 skills/<name>/SKILL.md·evals/가 생기고 check가 통과하는지
      no-trigger-edit/           #   음성: "yt-subs description 한 줄만 고쳐줘" · 검증기는 새 디렉토리가 생기지 않았는지
```

## 1. 관할과 경계

**이 PLAN이 소유하는 것.** 기본 스킬 셋(`pin-skill`·`write-skill`·`write-tool`, 2026-10-11)의 frontmatter·본문·참조·evals, 그리고 `packages/cli/src/harness_catalog_cli/templates/README.md`의 "사용자 안내" 절의 **문장**(검색어에 비밀을 넣지 말라는 안내, 두 스킬의 이름과 한 줄 용도, `list_skills`의 sha로 새 판을 확인한다는 것). README 파일 자체와 운영자 체크리스트(브랜치 보호·deploy key·CI 선택)는 `plans/distribution.md`가 소유한다. 안내 절은 README에 한 번만 있고 이 PLAN은 그 절의 내용을 정한다 — 같은 문장을 SKILL.md에 다시 쓰지 않는다.

**이 PLAN이 구현하는 DESIGN의 계약.** 아래 넷은 DESIGN이 정한 것이고 이 PLAN은 그것을 지시문으로 옮길 뿐이다.

| 계약 | 요지 | 자리 |
|---|---|---|
| 내려받기 절차와 `PINNED` | 사람이 범위(프로젝트·사용자) 하나만 고른다. `.agents/skills/`에 쓰고 `.claude/skills/`는 심볼릭 링크. 임시 디렉토리 → `load_skill` 파일 목록 대조 → 이름 바꾸기. `PINNED`는 한 줄 `<name> <tree sha 40자> <ISO 8601 UTC>`. 새 판은 `list_skills`의 sha와 견준다. 사본은 그 시점의 판이고 갱신은 사용자가 다시 받는다 | DESIGN §4 "내려받기", 규칙 넷 |
| 하네스별 스킬 디렉토리 | Claude Code만 `.claude/skills/`, Codex·Cursor·Gemini CLI·VS Code는 `.agents/skills/`. 같은 이름 둘일 때의 우선순위가 하네스마다 다르다 | DESIGN §4 하네스 표 |
| 팀 규약 | 종속성은 둘로 가른다(`metadata.requires-tools` 공백 구분·`compatibility` 문장). 파이썬은 PEP 723 + `uv run --script`. 종료 코드 2 입력 오류·3 대상 없음·4 시스템 도구 없음. evals는 써야 하는 과제 하나 + 쓰지 말아야 하는 과제 하나가 최소. 결과는 `harbor run --plugin harbor_langfuse`로 Langfuse에 | DESIGN §5.1 ②·③ |
| 부르는 도구 | 읽기 넷. 게시·갱신·은퇴는 도구가 아니라 git 워크플로(브랜치·커밋·PR·병합)이고 `write-skill`이 그 절차를 안내한다 | DESIGN §3, §5.1 ③ |

**소유하지 않는 것.** 도구 넷의 동작(service), 템플릿 저장소의 구조와 CI(distribution), 파일럿 하네스에서의 관찰(pilot). 설계 계약을 바꿔야 하면 DESIGN §11 행이 먼저다(우산 §1 경계 규칙 ⑶).

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
3. `search_skills(이름)`으로 `<name>`과 현재 `sha`를 확인한다. `replaced-by`가 있으면 대체 대상을 알리고 어느 쪽을 받을지 묻는다.
4. 대상 디렉토리를 정한다. 프로젝트 범위는 `.agents/skills/<name>/`, 사용자 범위는 `~/.agents/skills/<name>/`. 그 이름의 디렉토리가 **이미 있으면 멈추고 알린다**(카탈로그 밖 개인 스킬과의 충돌은 여기서만 잡힌다). 재다운로드(새 판 받기)는 사용자가 명시했을 때만 덮어쓰고, 고친 사본을 지키려면 이름을 바꿔 두라고 알린다.
5. `load_skill(<name>)`으로 본문·`sha`·`commit`·파일 목록을 받는다. 이 목록이 대조의 기준이고, 이후 `get_skill_file`은 같은 `sha`를 명시해 부른다(받는 도중 `main`이 바뀌어도 한 판만 받는다).
6. 같은 범위 디렉토리 아래 임시 디렉토리 `.<name>.pin-tmp/`를 만들고 `SKILL.md`를 쓴다. 목록의 나머지 파일을 `get_skill_file(<name>, path, sha=<5의 sha>)`로 하나씩 받아 같은 상대 경로에 쓴다. 바이너리는 base64로 받아 그대로 쓴다. 빈 디렉토리는 만들지 않는다(git에 없다).
7. 임시 디렉토리의 파일 집합과 5의 목록을 대조한다. 하나라도 빠지거나 남으면 임시 디렉토리를 지우고 멈춘다. 기존 사본은 그대로다.
8. `PINNED` 파일을 임시 디렉토리 안에 쓴다. 한 줄, `<name> <sha 40자> <ISO 8601 UTC 시각>`, UTF-8, 끝에 개행.
9. 임시 디렉토리를 `<name>/`으로 한 번에 이름을 바꾼다. 재다운로드(기존 사본이 있는 경우)는 셋으로 한다: 기존 `<name>/`을 같은 디렉토리 안의 `.<name>.pin-old/`로 이름을 바꾸고 → 임시 디렉토리를 `<name>/`으로 바꾸고 → 성공하면 `.pin-old`를 지운다. 둘째 이름 바꾸기가 실패하면 `.pin-old`를 `<name>/`으로 되돌린다. 어느 단계에서 멈춰도 기존 사본은 남는다.
10. `.claude/skills/`(또는 `~/.claude/skills/`)가 없으면 만들고, `.claude/skills/<name>`이 `../../.agents/skills/<name>`을 가리키는 심볼릭 링크를 둔다. 이미 실제 디렉토리가 있으면 링크를 만들지 않고 알린다.
11. 사용자에게 보고한다. 경로, sha, 파일 수, 그리고 "이 사본은 이 시점의 판이고 새 판은 다시 받아야 한다".

**새 판 확인(같은 스킬의 둘째 지시).** "새 판 있어?"·"갱신해줘"에는 프로젝트·사용자 **두 범위의** `PINNED`를 모두 읽고 이름마다 `search_skills(<name>)`의 `sha`와 견준다. 은퇴한 이름은 재사용되지 않으므로 sha가 다르면 새 판이다. 같은 스킬이 두 범위에 다 있으면 낡은 쪽을 알리고 하나로 합치기를 권한다(두 sha가 같으면 어느 쪽이 이겨도 결과가 같다). 새 판을 받기로 하면 4~11을 다시 한다. 병합이 반영되는 주기는 레지스트리의 fetch 주기(운영 설정)라 이 스킬은 시간을 말하지 않고 sha만 견준다.

**번들 파일.** 없다. 하네스 디렉토리 표는 본문에 표 하나로 넣는다(§3 D1). 스크립트는 없다(§3 D2).

### 2.2 `write-skill`

**목적.** 새 스킬의 뼈대를 카탈로그 **밖**의 개인 디렉토리에 만들고, 팀 규약을 점검표로 통과시키고, evals 최소 쌍을 두고, `harbor run`으로 돌려 Langfuse에 남기는 데까지의 절차. PR은 사람의 지시 뒤에만 만들고 병합은 사람이 한다. Anthropic `skill-creator`·Codex `$skill-creator`와 같은 일을 하되 이 팀의 규약을 뼈대에 넣는다.

**frontmatter.**

- `name: write-skill`
- `description`(초안):

  > 팀 카탈로그(harness-catalog)에 올릴 새 스킬의 뼈대를 만들고 팀 규약대로 채운다. 사용자가 "스킬 새로 만들자", "이 절차를 스킬로 만들어", "SKILL.md 뼈대 잡아줘", "스킬 만들어서 카탈로그에 올리자"라고 할 때 쓴다. 먼저 search_skills로 같은 일을 하는 스킬이 있는지 확인하고, 개인 디렉토리에 SKILL.md·scripts/·evals/를 만들며, 종속성(metadata.requires-tools와 compatibility), PEP 723 + uv run --script, 종료 코드 2/3/4, 양성·음성 evals 한 쌍(Harbor 태스크), harbor run 결과를 Langfuse에, description 검수를 점검표로 지난다. 브랜치·커밋·PR은 사용자가 지시할 때만 만들고 병합은 사람이 git 호스트에서 한다. 기존 스킬의 한 줄 수정은 이 스킬이 아니다.

- `compatibility: "카탈로그 저장소의 로컬 클론과 git·gh(PR 생성), 스크립트가 있는 스킬이면 uv(uv run --script)가 필요하다"`
- `metadata.requires-tools: "uv git gh"`(공백 구분, 토큰 문법 `[a-z0-9._+-]+`). 검사는 `harness-catalog check`(pre-commit 훅이 부른다)라 별도 도구가 아니다.

**본문 — 에이전트가 따르는 단계.**

1. 사용자의 한 문장에서 스킬이 하는 일과 발동 상황을 받아 적는다. `search_skills`로 같은 일을 하는 스킬이 있는지 확인하고, 있으면 갱신 경로(카탈로그 클론에서 `main` 기준 브랜치 → `skills/<name>/` 수정 → 커밋 → PR)를 안내하고 멈춘다.
2. 이름을 정한다. `name` 문법(1–64자, 소문자·숫자·하이픈)이고 `search_skills(<이름>)`에 없어야 한다. 은퇴한 이름은 `harness-catalog check`(항목 5)가 거부하니 그때 바꾼다.
3. 카탈로그 저장소의 로컬 클론(없으면 사용자에게 경로를 묻고 clone)에서 `main`을 최신으로 한 뒤 브랜치 `skill/<name>`을 따고 `skills/<name>/`에 뼈대를 쓴다. 병합 전의 브랜치가 곧 비공개 초안이다(DESIGN §5 비공개). `SKILL.md`(frontmatter + 본문 절: 언제 쓰는가·단계·실패 대응 표), 스크립트가 있으면 `scripts/`, `evals/`.
4. `references/conventions.md`의 점검표를 하나씩 지난다. 결정적인 일(계산·변환·조회)은 스크립트로, 판단은 본문 지시로 가른다. 파이썬 스크립트는 PEP 723 머리와 `uv run --script scripts/x.py` 호출로 적고 실행 비트에 기대지 않는다. 시스템 도구는 `metadata.requires-tools`(기계용)와 `compatibility`(사람용 문장) 둘 다에. 스크립트의 종료 코드는 2 입력 오류·3 대상 없음·4 시스템 도구 없음(설치 안내 한 줄과 함께).
5. evals 최소 쌍을 Harbor 태스크로 둔다(DESIGN §5.1). 케이스마다 `evals/<case>/{task.toml, instruction.md, environment/Dockerfile, tests/test.sh}`. 써야 하는 과제 하나와 쓰지 말아야 하는 과제 하나(`no-trigger-*`). Dockerfile은 팀 베이스 이미지 한 줄, `task.toml`은 `references/conventions.md`의 템플릿을 복사. 검증기는 결과 파일·상태를 검사하고 `/logs/verifier/reward.txt`에 0/1을 쓴다.
6. description을 검수한다. 무엇을·언제 쓰는지, 검색될 낱말(사용자가 실제로 말할 표현)이 들었는지, 쓰지 말아야 할 상황이 한 줄 있는지, **핵심 용례와 발동 낱말이 첫 문장에 있는지**(호스트가 설명을 자를 수 있고 모델은 첫머리를 더 잘 쓴다 — DESIGN §5.1).
7. `harness-catalog check`를 돌린다(pre-commit 훅이 커밋 때 다시 돌리고 CI가 PR에서 또 돌린다). 위반 항목을 고친다.
8. `harbor run --dataset skills/<name>/evals --agent <하네스> --model <모델> --env docker --plugin harbor_langfuse:LangfusePlugin`을 스킬 있이(`skills` 원천에 이 브랜치)·없이 두 번 돌린다. 결과는 Langfuse에 run 둘로 남고(메타데이터 `sha`는 브랜치 판) PR 본문에는 그 run 링크를 적는다(리뷰의 재료). 레지스트리에는 아무것도 붙이지 않는다. 병합 뒤 `main` push의 CI가 병합된 판으로 다시 돌리도록 팀이 정할 수 있다. Harbor가 없거나 음성 케이스처럼 검증기가 아직 없으면 사람이 눈으로 판정해 Langfuse annotation으로 남긴다(권고의 하한).
9. 사용자에게 브랜치·점검표 결과를 보고하고 멈춘다. **사용자가 "올려"라고 할 때만** 커밋하고 push해 `gh pr create`(GitLab이면 `glab mr create`)로 PR을 연다. 병합은 사람이 git 호스트에서 한다. 클라우드 샌드박스 세션(git 자격 없음)이면 여기서 멈추고 로컬 세션에서 하라고 알린다.

**번들 파일.** `references/conventions.md` 하나 — 팀 규약의 단일 소유자(§3 D4). 점검표 형식이고 DESIGN §5.1 ②·③의 규약을 실행 가능한 문장으로 옮긴 것이다. 스크립트는 없다(§3 D3).

### 2.3 README 사용자 안내 절 (packages/cli/src/harness_catalog_cli/templates/README.md 안)

문단 셋. ⑴ 등록 한 줄과 로그인 한 번(레지스트리 URL은 distribution가 채운다). ⑵ 두 스킬의 이름과 한 줄 용도, 새 판 확인은 `search_skills(<name>)`의 sha. ⑶ 검색어는 팀 Langfuse의 도구 호출 스팬에 남는다 — 검색어에 비밀·개인 정보를 넣지 말 것. 팀 규약의 본문은 여기 다시 쓰지 않고 `write-skill`의 `references/conventions.md`를 가리킨다.

## 3. 판정 원장

DESIGN이 정하지 않은 구현 선택만 적는다. 근거 등급은 우산 §3-1의 넷(실측·문면·설계 판단·휴리스틱).

| # | 물음 | 판정 | 근거 |
|---|---|---|---|
| D1 | 하네스 디렉토리 표를 `references/`로 번들하는가 본문에 넣는가 | **본문에 표 하나.** 행 다섯이고 `pin-skill`의 4·10단계가 이 표 없이는 성립하지 않는다. 활성화 시 본문과 함께 읽혀야 하는 정보라 필요 시 파일(3단계)이 아니다 | 설계 판단(DESIGN §1.4 점진적 공개의 층 구분). 본문 500줄 권고 안에 든다(휴리스틱, 표 6줄) |
| D2 | `pin-skill`에 스크립트를 두는가 | **두지 않는다.** 쓰는 내용은 MCP 도구 응답(`load_skill`·`get_skill_file`)이고 그것을 가진 것은 에이전트뿐이다. 스크립트는 레지스트리에 다시 붙어야 해서 토큰·URL을 인자로 받게 되고 그것이 곧 CLI다(DESIGN §7 "내려받기 CLI" 기각) | 설계 판단(DESIGN §3 "서버 도구는 없다", §7). 원자성은 임시 디렉토리 → 대조 → 이름 바꾸기의 지시로 확보하고 준수 여부는 pilot이 잰다 |
| D3 | `write-skill`에 뼈대 스크립트를 두는가 | **개정 2026-10-10(사용자 결정): 둔다.** `scripts/scaffold.py <name> --description … [--positive] [--negative] [--script]`(PEP 723 Python, 종속성 없음, `uv run --script`, 멱등; conventions §1의 "파이썬 스크립트는 PEP 723" 규약 그대로)가 SKILL.md frontmatter·evals 쌍의 Harbor 다섯 파일·PEP 723 머리를 쓴다. 에이전트는 TODO 자리(설명·과제 문장·검증 조건·절차)만 채운다. 이전 판 "두지 않는다. 뼈대 쓰기는 계산이 아니다"는 conventions §1("파일 쓰기도 스크립트가 한다")과 모순이었고, Oracle solve.sh를 쓰면서 규약 문면(schema 1.4·skills_dir·타임아웃·no-trigger-·reward.txt)이 세 곳(conventions 템플릿·본문·solve.sh)에 복제되는 것이 드러났다 | 사용자 결정. 스크립트는 코드 저장소 `tests/cli/test_scaffold.py`가 검사한다. Oracle은 `--skill`을 받지 않아(Harbor 0.24 실측) solve.sh는 스크립트에 기대지 않는 참조 해답이다 |
| D4 | 팀 규약의 단일 소유자 | **`write-skill/references/conventions.md`.** README와 `write-skill` 본문은 그 파일을 가리키고 규약 문장을 다시 쓰지 않는다. DESIGN §5.1은 설계의 서술이고 실행 가능한 점검표는 이 파일 하나다 | 설계 판단(C-DUP-2: 세 벌째가 되기 전에 소유자 하나). DESIGN·README·SKILL.md 셋에 같은 규약이 있으면 정확히 그 실패다 |
| D5 | 본문 언어 | **한국어.** 이 팀의 하네스 세션이 한국어이고 description의 발동 표현이 사용자의 실제 발화여야 한다. `name`·도구 이름·파일 경로는 그대로 영문 | 실측(이 세션과 `~/workspace`의 스킬 전부가 한국어 본문). 어휘 검색이 description을 대상으로 하므로 한국어 낱말이 검색어와 맞아야 한다(설계 판단) |
| D6 | 레지스트리의 fetch 주기를 에이전트가 알아야 하는가 | **몰라도 된다.** 새 판 판정은 `PINNED`의 sha와 `search_skills(<name>)`의 sha 비교뿐이다. 주기는 운영 설정(`FETCH_INTERVAL_SECONDS`)이라 스킬 본문에 시간을 적으면 낡는다 | 설계 판단(DESIGN §2 사용자 결정 2026-09-26). C-COMMENT-2와 같은 이유 |
| D7 | Cursor가 호환 경로를 함께 읽어 같은 스킬이 두 번 보이는 문제 | **현재 규칙은 심볼릭 링크 하나다.** Claude Code·Codex는 문서로 확인됐고 Cursor·Gemini CLI·VS Code는 실측 전이다. 이 PLAN은 그 결과를 예측하지 않는다. 실측은 pilot P0의 항목이고 결과가 갈리면 DESIGN §4의 "링크 대신 사본 하나를 더 둔다"가 그때의 지시다 | 문면(DESIGN §4 하네스 표, **가정:** 표시). 실측은 pilot |
| D8 | 두 스킬 자신의 evals | **각자 양성 하나·음성 하나, Harbor 태스크 형식.** 자기 규약을 자기가 지킨다. `pin-skill`의 음성은 "세션에 넣어줘"(`load_skill`이지 pin이 아님), `write-skill`의 음성은 "한 줄만 고쳐줘"(갱신이지 뼈대가 아님). 검증기는 파일 시스템 상태(PINNED·브랜치의 디렉토리)를 본다 — 두 스킬 다 결과가 파일이라 궤적 없이 판정된다. 결과는 Langfuse run | 설계 판단(DESIGN §5.1 evals 행, `[altera-skills]` 양성·음성 각 1 규약은 문면) |
| D9 | 뼈대의 기본 위치 | **현재 저장소 밖 `~/skills-draft/<name>/`, 사용자가 다른 곳을 말하면 그곳.** 카탈로그 밖이 곧 비공개다(DESIGN §5). 현재 저장소 안에 두면 그 저장소에 스킬이 섞여 커밋된다 | 설계 판단. 경로 이름은 휴리스틱 |
| D11 | 공유 스크립트 규약 | `conventions.md`에 한 절: 라이브러리 규모면 카탈로그 저장소 `packages/<lib>/` + PEP 723 `dependencies = ["<lib> @ git+<url>@<sha>#subdirectory=packages/<lib>"]`(SHA 고정), 작으면 복사(`check` 10이 드리프트 경고), 스킬 간 호출·`${CLAUDE_PLUGIN_ROOT}` 금지. 뼈대의 예시 스크립트는 복사형(의존 없음) | DESIGN §5.1(사용자 결정 2026-09-27). 실측: uv 0.11.8 git 직접 참조 실행 |
| D10 | 이름 | `pin-skill`·`write-skill` 고정 | 설계 판단(DESIGN §4·§5.1, 3차 리뷰에서 `platform/pin-skill` → `pin-skill`) |
| D11 | evals 검증기의 모양 | **검증기의 인터페이스·보고 형식은 Harbor 공식 뼈대(`harbor tasks init`)를 따른다(사용자 결정 2026-10-10; 보정 2026-10-11).** bash 진입점 `tests/test.sh` + pytest `tests/test_outputs.py` + CTRF 보고 `/logs/verifier/ctrf.json`, reward는 pytest 종료 코드. 검사 논리는 pytest 단언에만 둔다. 공유 검증기(`[verifier] environment_mode = "shared"`)를 명시한다 — 에이전트 컨테이너의 끝 상태(`.agents/skills/`·`PINNED`·링크)를 직접 보기 위해; 분리 모드는 artifacts 선언·`tests/Dockerfile`이 필요해 비용이 크고 대가(에이전트에 pytest 노출)는 무해. 이미지는 공식 뼈대(`ubuntu:24.04` 두 줄, 검증 때 apt·curl·uvx로 pytest 설치)와 다르다: `python:3.12-slim`+git, uv(스킬 스크립트 규약 `uv run --script`), pytest 8.4.1·pytest-json-ctrf 0.3.5 미리 설치, `/skills`, `WORKDIR /work`. 미리 넣는 이유는 검증 중 PyPI 내려받기를 없애 검증 예산·결정성을 지키는 것(Harbor PR #2596이 같은 방향; Terminal-Bench `check-verifier-tooling-baked`·`check-trial-network-fetch`) — `network_mode`는 기본 `public`이다. uv·pytest는 PyPI `pip install`(GHCR `COPY --from`은 self-hosted 러너에서 pull denied 실측 — 루트 Dockerfile과 같은 이유). 문면은 scaffold.py `DOCKERFILE_HEAD`·`TEST_SH`가 소유하고 실린 네 케이스는 그 머리로 시작한다(`tests/cli/test_scaffold.py::test_shipped_base_evals_match_scaffold`) | 사용자 결정. 이전 판의 근거 "검증 때 네트워크 없음"은 틀렸다(기본 public) — 2026-10-11 보정 행. Terminal-Bench의 digest 핀·canonical pytest 9.1.1은 그 저장소 규칙이라 채택하지 않음 |

## 4. 단계

**skills P1 작성.** (우산 P4. service P1 뒤 언제든 시작할 수 있다)

1. `pin-skill/SKILL.md` — §2.1의 frontmatter와 단계 11 + 새 판 확인. 하네스 표는 본문에.
2. `write-skill/SKILL.md`와 `references/conventions.md` — §2.2. 점검표는 DESIGN §5.1 ②·③에서 옮기되 문장은 실행형으로.
3. 각자 evals 양성·음성 한 쌍(§3 D8).
4. `skills-ref validate packages/cli/src/harness_catalog_cli/templates/skills/pin-skill …/write-skill` 로컬 통과.
5. `altera-rules.yml`에 `purpose/agent-skill` 선언, 재실체화, `pre-commit run --all-files`로 그 축의 게이트를 한 번 완주(우산 §3-5, V9).
6. Codex 독립 리뷰 한 번(우산 §3-6). 발견의 반영·기각을 §9에.
7. README 사용자 안내 절 문장을 distribution에 넘긴다(§2.3). 파일은 distribution가 쓴다.

**skills P2 게시.** (우산 P5. distribution P3의 첫 카탈로그 저장소가 생긴 뒤. 게시는 PR이었고 이 두 스킬이 그 저장소의 첫 PR이었다. 2026-10-10부터 새 카탈로그에는 `init`이 함께 쓰고(distribution D14 개정), 갱신만 PR이다)

1. 첫 카탈로그 저장소(distribution P3)에 두 스킬을 PR로 올려 병합한다. 병합 커밋과 tree SHA를 §9에 적는다.
2. `search_skills("내려받아")`·`search_skills("스킬 만들자")`가 각각을 첫 후보로 낸다.
3. 두 스킬의 evals를 스킬 있이·없이 `harbor run --plugin harbor_langfuse`로 돌린다(자기 Langfuse 키). Langfuse에 dataset 둘·run 넷이 보인다.
4. 파일럿 하네스 셋에서의 `pin-skill` 관찰은 pilot의 몫이다(우산 §9 V6 "내려받기 왕복").

**완료 조건.** skills P1은 우산 §4 P4 그대로: "두 스킬이 `skills-ref validate`를 통과하고 각자 양성·음성 evals 한 쌍이 있으며 `purpose/agent-skill` 게이트가 SKILL.md 둘을 검사하며 한 번 돌았다". skills P2는 우산 §4 P5의 게시 몫: "두 스킬을 PR로 올려 병합하고 `list_skills`에 보이게 한다". 하네스 셋에서의 `pin-skill` 관찰은 우산 P6(pilot Q11)의 완료 조건이다.

## 5. 불채택 표

기각 사유는 현재형으로만 적는다.

| 항목 | 기각 근거 (왜 지금 아닌가) |
|---|---|
| 내려받기 CLI | 하네스 밖(CI·스크립트)에서 내려받는 수요가 없다. 읽기는 도구 둘로 충분하고 절차는 스킬 하나다(DESIGN §3·§7) |
| 서버 쪽 pin 도구 | 내려받기는 클라이언트 쪽 쓰기라 MCP 서버가 할 수 없다(DESIGN §3) |
| 에이전트 종류를 묻는 선택지 | `.agents/skills/` + `.claude/skills/` 링크로 파일럿 하네스 셋이 덮인다(문면). 물을 것이 늘면 인터페이스가 얕아진다 |
| 내려받은 사본의 자동 갱신 | 사본의 뜻이 point-in-time이다(DESIGN §4). 자동 갱신은 사용자가 고친 사본을 덮어쓴다 |
| 게시 전용 셋째 스킬 | 게시는 브랜치·커밋·PR이고 `write-skill`의 마지막 단계가 그것이다. 절차가 없는 스킬은 이름만 늘린다 |
| DESIGN 전문을 `references/`로 번들 | 스킬이 필요로 하는 것은 규약 점검표(`conventions.md`)뿐이다. 설계 문서를 실으면 게시 상한(5 MB)과 무관하게 활성화 시 읽을 것이 늘고 설계 개정마다 스킬이 낡는다 |
| 자체 evals 러너·판정자 | 러너는 Harbor(DESIGN §5.1), 판정자는 케이스의 `tests/test.sh`다. 이 저장소는 둘 다 만들지 않는다 |
| 영어 본문 | 발동 표현이 사용자의 실제 발화(한국어)여야 어휘 검색과 description 매칭이 된다(§3 D5) |
| `pin-skill`의 무결성 검사(파일별 해시 대조) | `get_skill_file`이 SHA를 돌려주지만 그것은 blob 식별이지 전송 오류 검출이 아니다. 대조는 파일 목록으로 충분하고, 사본이 맞는지는 `PINNED`의 tree sha와 `search_skills(<name>)`가 답한다 |

## 6. 리스크 대응표

| # | 리스크 | 대응 |
|---|---|---|
| R1 | 에이전트가 원자적 절차(임시 디렉토리 → 대조 → 이름 바꾸기)를 건너뛰고 대상 디렉토리에 바로 쓴다 | 본문의 단계 6~9를 번호로 강제하고 7에 "빠지거나 남으면 지우고 멈춘다"를 명시. pilot Q11이 하네스 셋에서 명령 순서를 원문으로 관찰한다 |
| R2 | 하네스가 링크와 실체를 둘 다 읽어 같은 스킬이 두 번 보인다 | 현재 규칙은 링크 하나(§3 D7). 실측은 pilot P0. 본문은 "두 번 보이면 알려 달라"를 사용자에게 요청하는 문장을 둔다 |
| R3 | description이 과잉 발동한다(모든 "스킬" 발화에 `write-skill`이 뜬다) | 음성 evals(§3 D8)가 잡는다. description 끝에 "~는 이 스킬이 아니다" 한 줄 |
| R4 | README 안내 절과 `conventions.md`의 규약 문장이 어긋난다 | README는 규약 문장을 갖지 않고 가리키기만 한다(§3 D4). 어긋날 문장이 없다 |
| R5 | `skills-ref validate`가 한국어 description을 거부하거나 길이 계산이 바이트 기준이다 | V1·V2가 실물로 잰다. 길이 계산 기준은 검증기 소스에서 읽어 §9에 적는다 |

## 7. 검증 원장

| # | 검증 | 방법 | 통과 기준 | 상태 |
|---|---|---|---|---|
| V1 | 스펙 준수 | `skills-ref validate` 두 디렉토리 | 둘 다 오류 0 | 대기 |
| V2 | frontmatter 한도 | `name` 문법 `^[a-z0-9-]{1,64}$`·디렉토리명 일치, description 1–1024자 | 둘 다 통과 | 대기 |
| V3 | `PINNED` 형식 | 하네스 하나에서 `pin-skill`로 프로젝트 범위 내려받기 | 파일이 정확히 한 줄 `<name> <sha40> <ISO8601Z>` + 개행이고 sha가 `search_skills(<name>)`와 같다 | 대기 |
| V4 | 실패 시 원자성 | 세 지점에서 실패를 주입한다: (a) 6단계 도중 `get_skill_file` 실패(없는 경로를 목록에 끼움), (b) 재다운로드의 둘째 이름 바꾸기 실패(대상 이름에 쓰기 불가 파일을 둠), (c) 첫 이름 바꾸기 뒤 중단 | (a) `.<name>.pin-tmp/`가 남지 않고 기존 사본 그대로. (b) `.pin-old`가 `<name>/`으로 되돌아온다. (c) `<name>/`이 기존 사본 또는 새 사본 중 하나로 온전하고 반쪽이 없다 | 대기 |
| V5 | 기존 디렉토리 거부 | 같은 이름의 개인 스킬을 먼저 두고 내려받기 지시 | 쓰지 않고 멈추며 충돌을 알린다 | 대기 |
| V6 | 두 범위 낡음 감지 | 프로젝트·사용자 범위에 sha가 다른 두 사본을 두고 "새 판 있어?" | 낡은 쪽을 지목하고 합치기를 권한다 | 대기 |
| V7 | 뼈대의 규약 | `write-skill`로 만든 뼈대가 V1을 통과하고, 생성된 예시 스크립트가 종료 코드 2·3·4를 각각 낸다(입력 없음·대상 없음·`PATH`에서 도구 제거) | 셋 다 관찰 | 대기 |
| V8 | evals 쌍 | 두 스킬 디렉토리에 양성·음성 각 1의 Harbor 태스크 | `evals/*/{task.toml,instruction.md,environment/Dockerfile,tests/test.sh}` 넷씩, 음성은 `no-trigger-*`. `harbor run --env docker`로 넷이 돌고 양성은 스킬 있이 reward 1·없이 0, 음성은 있이·없이 둘 다 1 | **부분 통과(2026-10-10)**: `-a oracle -e docker`로 넷 모두 reward 1.0·예외 0(solution/solve.sh 추가, Harbor 0.24.0, Docker Desktop 25). 태스크가 풀리고 검증기가 끝 상태를 받는다는 것까지. 모델 하네스(claude-code) 있이·없이 비교는 대기 |
| V11 | 공유 규약 문장 | `conventions.md`의 공유 스크립트 절대로 만든 두 스킬 표본(패키지 참조형·복사형)에 `check` | 패키지 참조형은 `uv run --script`가 git 참조를 설치해 돌고, 복사형 둘의 내용이 다르면 `check`가 항목 10 경고를 내고 종료 0 | 대기 |
| V9 | Langfuse 왕복 | 병합 뒤 두 스킬의 evals를 `harbor run --plugin harbor_langfuse`로 스킬 있이·없이(service P3 플러그인 뒤) | Langfuse에 dataset `<catalog>/pin-skill`·`<catalog>/write-skill`, 각 run 둘, 메타데이터 `sha`가 `list_skills`의 `sha`와 같고 `passed` score가 V8의 기대와 같다 | 대기 |
| V10 | 규칙 게이트 | `purpose/agent-skill` 선언 뒤 `pre-commit run --all-files` | 그 축의 게이트가 SKILL.md 둘을 검사하며 한 번 돌았다 | 대기 |

## 8. 개정 규약

판정 변경은 §3에 행 추가(기존 행 유지, 후속 행이 우선). 설계 계약(`PINNED` 형식·하네스 표·팀 규약)의 변경은 DESIGN §11이 먼저. 게시된 뒤의 스킬 수정은 카탈로그 저장소가 정본이므로 그 저장소에 PR로 하고, 이 저장소의 `skills/`는 같은 내용을 따라 적어 이력만 남긴다. 기록은 현재 상태만(REVIEW.md V-REC-1).

## 9. 진행 원장

| 일자 | 항목 | 내용 | 근거 |
|---|---|---|---|
| 2026-10-07 | P1 작성 1~5 | `skills/pin-skill/SKILL.md`(§2.1 단계 11 + 새 판 확인 + 하네스 표 본문), `skills/write-skill/SKILL.md` + `references/conventions.md`(점검표 7절: 결정/판단·스크립트·종속성 두 자리·공유 스크립트·SKILL.md·evals·은퇴), 각자 evals 양성·음성(Harbor schema 1.4 실측: `harbor/cli/template-task/task.toml`; 검증기는 파일 시스템 상태 — PINNED 형식·심볼릭 링크 / 브랜치의 SKILL.md·evals 쌍·main 불변). `skills-ref validate` 둘 통과, 임시 카탈로그에서 `harness-catalog check`(gitleaks 포함) 종료 0. `lang/bash`·`purpose/agent-skill` 선언·재실체화, `altera-shellcheck` 훅 추가 → 셸 게이트가 스크립트 5개를 검사하며 완주(SC2010 하나 참 → 수정). agent-skill 표면에는 rules-v0.10.0에 커밋 훅이 없다(선언은 에이전트가 읽는 텍스트). 6(Codex 리뷰)·7(README 문장 → 템플릿에 이미 반영) | 우산 §4 P4 |
| 2026-09-27 | 설계 개정 반영 | `new-skill`→`write-skill`(전부), 공유 스크립트 규약 D11·V11 | DESIGN §11 |
| 2026-09-27 | 설계 개정 반영 | v3.5: README 문단 ⑶(검색어는 Langfuse 스팬) | DESIGN §11 |
| 2026-09-27 | 설계 개정 반영 | v3.4: 결과를 `record_eval`에서 Langfuse 플러그인으로(트리·단계 8·D8·V9·description·부르는 도구) | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | evals를 Harbor 태스크 형식으로(트리·단계 5·8·D8·V8·불채택). `conventions.md`에 `task.toml`·`Dockerfile`·`test.sh` 템플릿 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | description 검수에 "핵심을 앞에" 추가(단계 6). `list_skills` 필드 최소화는 pin 절차에 영향 없음(`sha`만 본다) | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | v3.3: 게시는 PR — `write-skill` 단계 1·3·7·8·9 재작성(클론·브랜치·`check`·`gh pr create`·샌드박스 멈춤), pin은 현재 판 `sha`로, P2는 첫 PR | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 8차 리뷰: pin·새 판 확인은 유효 판 `sha`, 편집은 `latest_sha`에서, `unavailable`이면 멈춤 | DESIGN §11 |
| 2026-09-26 | 설계 개정 반영 | 인증된 판: `pin-skill`의 기본은 인증 판(단계 3·5), 새 판 확인은 `certified_sha` 기준, 받는 동안 `sha`를 고정 | DESIGN §11 |
| 2026-09-26 | Codex 교차 검증 1회 | 반영: 재다운로드 절차를 백업 이름 바꾸기로(단계 9, V4 세 지점), 도구 시그니처 사본 삭제(§1 표), 단계 번호를 우산 P4(작성)·P5(게시)로, R1·R5의 미래 조건절 삭제, 배치 그림의 PLAN.md 제거. 기각 없음 | 우산 §11 |
| 2026-09-26 | PLAN 초판 | 스킬 둘의 사양(description 초안·단계)·판정 D1~D10·검증 V1~V10. 파일은 아직 없다 | 우산 §4 P4·P5 |
| 2026-10-10 | evals에 `solution/solve.sh` + Oracle 실측 | 사용자 지적("Harbor를 대충 확인하고 구조를 잡은 것 아닌가"). 형식은 Harbor 0.24 문서·소스와 대조해 전부 일치했으나(schema 1.4·skills_dir·tests/test.sh·reward.txt·`--skill`), 한 번도 돌린 적이 없었고 Harbor가 권장하는 `solution/`이 없었다. 네 케이스에 solve.sh를 쓰고 `harbor run -a oracle -e docker`로 넷 reward 1.0(0 예외, 21s+14s). conventions.md §6에 solve.sh와 Oracle 선행 실행을 항목으로. dbt-agent-skills의 `scenario.md`는 Harbor 표준이 아니라 그쪽 자체 도구 파일이어서 들이지 않는다 | Harbor docs-mintlify/tasks/{overview,solution,skills}.mdx, src/harbor/models/task/config.py; 로컬 실측 |
| 2026-10-10 | D3 개정: scaffold.sh | 사용자 질문("write-skill에는 기본 구조를 잡는 결정적 스크립트가 필요한 것 아닌가"). `scripts/scaffold.py`(처음 sh로 썼다가 사용자 지적 "결정적 스크립트는 Python이 이점"으로 PEP 723 Python으로 — conventions §1과도 일치) 추가, conventions §6의 템플릿 문면을 스크립트 소유로 옮김, SKILL.md 단계 3·5 갱신, `tests/cli/test_scaffold.py`(생성 12 파일·멱등·이름 거부·toml 파싱). Oracle에 `--skill`을 주면 `Agent 'oracle' does not support skills` ValueError(실측) — solve.sh는 스크립트에 기대지 않게 유지. 참고: `harbor tasks init`이 Harbor 공식 뼈대이고 그 검증기는 bash 진입점 + pytest(`tests/test_outputs.py`, CTRF 보고)다 — 우리는 이미지에 uv를 미리 넣고 sh 검증기를 쓰는 점이 다르다(검증 때 네트워크 없음) | 로컬 실측(pyright·ruff 통과), Harbor Oracle(아래 행) |
| 2026-10-10 | D11: 검증기를 Harbor 공식 뼈대로 | 사용자 결정("검증기를 harbor 공식 뼈대로 가라"). 네 케이스의 `tests/test.sh`를 공식 진입점으로, 검사 논리를 `tests/test_outputs.py`(pytest)로 옮김. Dockerfile에 pytest 미리 설치. scaffold.py 템플릿·`test_scaffold.py`(14 파일) 갱신. ruff·pyright strict·shellcheck 통과. Oracle 재실측: pin-skill 2/2(17s)·write-skill 2/2(15s) reward 1.0, 트라이얼마다 `verifier/ctrf.json`(예: new-skill-skeleton tests 4 passed)·`test-stdout.txt` 수집됨 | `harbor tasks init` 실측 출력, 로컬 게이트, Harbor Oracle |
| 2026-10-11 | D11 보정: evals Dockerfile의 근거와 문면 | 사용자 질문("harbor의 dockerfile 이렇게 작성하는 것이 맞아?"). Harbor 0.24 `tasks init` 생성물·소스·문서, Terminal-Bench CONTRIBUTING·TASK_REVIEW_AUTOMATION, Harbor PR #2596, LangChain의 Harbor 활용 글을 대조. 틀린 것 셋: (1) "검증 때 네트워크 없음" — `network_mode` 기본 `public`; 굽는 이유는 검증 예산·결정성이다. (2) "공식 뼈대 그대로, 차이 하나" — 이미지·WORKDIR·uv·`/skills` 등 차이가 여럿이라 "인터페이스·보고 형식만"으로 정정. (3) `COPY --from=ghcr.io/astral-sh/uv` — 루트 Dockerfile이 mini에서 denied를 실측해 pip로 바꾼 패턴을 eval Dockerfile이 그대로 썼다(CI evals는 mini 러너에서 빌드). 고친 것: Dockerfile 머리를 scaffold.py `DOCKERFILE_HEAD`로 모으고 `pip install uv pytest pytest-json-ctrf`, `RUN mkdir -p /skills`(문서 준수; Harbor가 주입 때 만들기도 함), `[verifier] environment_mode = "shared"` 명시, 실린 네 케이스가 그 머리로 시작함을 시험으로 고정. Codex 리뷰 1회(사실 7건 소스 대조, 공유 모드 명시·범위 축소 문구·"보정" 어휘 채택; digest 핀은 Harbor 요구가 아니라 미채택). LangChain 사례는 작성 규약이 아니라 연결(Deep Agents·LangSmith Sandboxes·Observability)과 운용(반복 실행·lite 부분집합·점수+트레이스)이라 D11에는 영향 없음 | 계약은 그대로(보정). Oracle 네 케이스 재실측·mini 빌드 실측은 이 행 아래 결과 행 |
| 2026-10-11 | `list_skills` 제거 반영 | pin-skill 단계 3·새 판 확인, write-skill 이름 확인을 `search_skills(<name>)`로. D6·V3·완료 조건 2 문면 수정 | DESIGN §11 2026-10-11 `list_skills` 제거 |
| 2026-10-18 | evals 구멍 셋 정리(0.7.0) | (1) 컨테이너에 hc: DOCKERFILE_HEAD 가 NAS Nexus `pypi-public` 에서 `harness-catalog-cli==<판>` 설치, task.toml `[[environment.mcp_servers]]` stdio 로 `hc toolbox /work/catalog/tools`; write 의 시험용 카탈로그는 scaffold 사본 대신 `hc init --host github --pin v<판> file:///fixture.git`(베어 저장소는 `-b main` — 기본 master 라 clone 이 체크아웃 못 함, 실측) + yt-subs, 검증기 기준은 main(`/work/main.sha`). (2) pin 에 레지스트리: 진짜 레지스트리(OAuth·tailnet) 대신 stdio MCP 스텁 `registry_stub.py`(PEP 723, mcp==2.3.0; 네 도구의 응답 모양 = 서버 pydantic 모델; 아카이브는 127.0.0.1 HTTP + 5분 토큰) — 검증 대상은 레지스트리가 아니라 pin 스킬. 코드 저장소 시험 `test_pin_eval_stub.py` 가 스텁→get_skill(archive)→`hc pin` 설치까지 고정. (3) 모델 자격: CI 는 Oracle, 모델 측정은 저자 로컬(DESIGN §5.1 개정). mini(tailnet, Docker)에서 실측: write 5/5 · pin 2/2 · review 2/2 reward 1.0 | DESIGN §11 2026-10-18 행들, tests/cli/test_pin_eval_stub.py |
| 2026-10-18 | 셋째 기본 스킬 `review` | 사용자 질문("write 뒤 저작 지침의 최적 형태인지 검증·리팩토링하는 스킬은 안 필요한가"). 출처 셋을 원문에서 읽어 점검표(A 발견·B 구조·C 본문·D 팀 규약·E 검증) 작성: agentskills.io/specification(name·description·compatibility 규칙), Anthropic best-practices(간결·자유도·3인칭·500줄·한 단계 참조·목차·시간 정보·용어·워크플로·되먹임·evals 먼저), Codex Build skills(발동 낱말 앞쪽, 2% 문맥 예산). evals 쌍: review-vague-skill(A1·B2·C4·D2를 어긴 yt-subs를 고쳐 브랜치에; 검증기는 description ≥ 40자·시간 문장 없음·참조 한 단계·main 그대로), no-trigger-new-skill(yt-subs 불변·review/ 브랜치 없음) | DESIGN §11 2026-10-18 행, Oracle 2/2 |
| 2026-10-18 | write evals를 모델이 풀 수 있는 환경으로 | 사용자 질문("evals가 모두 맞게 구성되고 테스트됐나"). 실측: Oracle만 통과했고 모델 실행은 성립하지 않았다 — 시험용 카탈로그에 tools/scaffold·.mcp.json이 없어 스킬 4단계가 불가능. 고침: 양성 케이스 넷의 `environment/catalog/tools/scaffold/`에 사본(Harbor 빌드 컨텍스트가 environment/뿐이고 두 저장소가 비공개라 이미지에서 받을 수 없다; 코드 저장소 시험 `test_eval_environment_scaffold_copies_match_the_tool`이 드리프트를 고정), Dockerfile이 `.mcp.json`도 둔다. `no-trigger-skill-request`는 통합 write에서는 양성이라 `skill-not-tool`로 이름을 바꾸고 검증기를 "새 스킬이 생겼고 도구는 scaffold뿐"으로. 새 케이스 `compose-existing-tool`(있는 도구 changelog-diff를 이름으로 엮고 복사·scripts/ 없음). write 실패 대응에 "hc가 없어 toolbox를 못 띄우면 터미널에서 scaffold" 한 줄. 파일 41/50. **남은 구멍:** 이미지에 `hc`가 없어 MCP 경로(task.toml `[[environment.mcp_servers]]` stdio)는 못 돌린다 — 코드 저장소 공개 또는 러너 GHCR 로그인 뒤; pin 케이스는 레지스트리 URL 주입(tailnet 러너)이 있어야 모델이 풀 수 있다; 모델 실행(스킬 있이·없이)은 자격(`CLAUDE_CODE_OAUTH_TOKEN`)이 있는 곳에서 아직 안 돌렸다 | Oracle write 5/5·pin 2/2 reward 1.0(2026-10-18), 이미지 안에서 changelog-diff·scaffold tools[] 실측 |
| 2026-10-18 | write의 첫 단계를 "가른다"로, scaffold `tools[]` | 사용자 지적(결정적/비결정적 분리가 먼저, 있는 도구를 엮는 방향). `scaffold`의 `tool`→`tools`(있는 도구는 tool.json을 읽어 호출 줄, 없는 도구는 뼈대), write 1·2단계(가르기, `search_tools`로 있는 도구 찾기), conventions §1·§5, 템플릿 README, docs/authoring | DESIGN §11 2026-10-18 행, tests/cli/test_scaffold.py::test_skill_composes_existing_tools_and_scaffolds_missing_ones |
| 2026-10-11 | 셋째 기본 스킬 `write-tool` | 사용자 결정. SKILL.md·`references/tool-contract.md`(D18 ABI의 저자용 문면)·`scripts/scaffold_tool.py`(tool.json·ABI 골격·server.json 골격, 멱등; 검사 10 때문에 write-skill과 다른 이름)·evals 쌍(`new-script-tool`·`no-trigger-skill-request`). 도구에는 evals를 두지 않는다 | DESIGN §11 2026-10-11 도구 저작 행 |
\n| 2026-10-11 | D11 보정 실측 | Mac: `harbor run -a oracle -e docker` pin-skill 2/2·write-skill 2/2 reward 1.0(17초·14초, 이미지 재빌드 포함). mini(self-hosted 러너, `/opt/homebrew/bin/docker`): 새 Dockerfile을 stdin으로 빌드 성공 — uv 0.11.8·pytest 8.4.1·`/skills` 확인, GHCR 접근 없음. 부수 발견: 시험이 scaffold.py를 import하면 패키지 데이터에 `__pycache__`가 생겨 `init`이 .pyc를 텍스트로 읽어 실패 → 시험은 소스 exec로, `template_files`는 `__pycache__`를 건너뛰게 고침 | tests/cli/test_scaffold.py::test_shipped_base_evals_match_scaffold, init.py template_files |\n