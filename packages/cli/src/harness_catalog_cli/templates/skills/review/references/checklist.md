# 스킬 심사 점검표

항목마다 출처를 붙였다. [스펙] agentskills.io/specification · [Anthropic] Skill authoring best practices(platform.claude.com, 2026-10-18 열람) · [Codex] Build skills(developers.openai.com/codex/skills, 2026-10-18 열람) · [팀] write의 conventions.md. 판정은 통과 · 수정 · 해당 없음 · 판단 필요 넷이고, 근거는 본문 인용 한 줄이다.

## A. 발견 — description과 name

- [ ] A1 description이 **무엇을 하는지와 언제 쓰는지**를 둘 다 말한다. [스펙] "Should describe both what the skill does and when to use it." [Anthropic] 나쁜 예 "Helps with documents".
- [ ] A2 **3인칭**이다. "I can…", "You can use this…"가 아니다. [Anthropic] "Always write in third person. The description is injected into the system prompt."
- [ ] A3 **발동 낱말**(사용자가 실제로 말하는 표현)이 들어 있고 **앞쪽**에 있다. [스펙] "Should include specific keywords". [Codex] "Front-load the key use case and trigger words so a host can still match the skill if descriptions are shortened." [팀] 쓰지 말아야 할 상황 한 줄.
- [ ] A4 길이: 1~1024자. [스펙] name은 1~64자 소문자·숫자·하이픈, 디렉토리명과 같다, 연속 하이픈 없음. [Anthropic] name에 "anthropic"·"claude" 금지, XML 태그 금지.
- [ ] A5 name이 **무엇을 하는지** 드러낸다(`helper`·`utils`·`tools`·`documents` 같은 막연한 이름 아님). [Anthropic] Naming conventions.

## B. 구조 — 읽히는가

- [ ] B1 SKILL.md 본문이 **500줄 안**이다. 넘으면 참조 파일로 나눈다. [Anthropic] "Keep SKILL.md body under 500 lines."
- [ ] B2 참조 파일은 SKILL.md에서 **한 단계**다(참조 파일이 또 참조하지 않는다). [Anthropic] "Keep references one level deep from SKILL.md." [팀] 스킬 루트 기준 상대 경로·마크다운 링크.
- [ ] B3 100줄 넘는 참조 파일은 머리에 **목차**가 있다. [Anthropic] "For reference files longer than 100 lines, include a table of contents."
- [ ] B4 경로는 슬래시다(`scripts/x.py`). [Anthropic] Avoid Windows-style paths.
- [ ] B5 본문 절이 셋이다: 언제 쓰는가 · 단계 · 실패 대응. frontmatter는 name·description(+조건이 있을 때만 compatibility). [팀] conventions §4.

## C. 본문 — 따를 수 있는가

- [ ] C1 **간결**하다. 모델이 이미 아는 것(라이브러리가 무엇인지, 일반 개념)을 설명하지 않는다. [Anthropic] "Default assumption: Claude is already very smart… Does this paragraph justify its token cost?"
- [ ] C2 **자유도**가 과제에 맞다. 여러 길이 다 되는 일(코드 리뷰)은 산문·휴리스틱(높은 자유도), 깨지기 쉽고 순서가 정해진 일(마이그레이션)은 정확한 명령 하나(낮은 자유도). [Anthropic] "Match the level of specificity to the task's fragility and variability."
- [ ] C3 선택지를 늘어놓지 않는다. **기본 하나 + 예외 하나**. [Anthropic] "Provide a default (with escape hatch)."
- [ ] C4 **시간에 묶인 정보**가 없다("2025년 8월 전에는…"). 옛 방식은 "옛 패턴" 절로 접는다. [Anthropic] Avoid time-sensitive information.
- [ ] C5 **용어가 일관**된다. 같은 것을 두 낱말로 부르지 않는다. [Anthropic] Use consistent terminology.
- [ ] C6 절차는 **순서 있는 단계**이고, 길면 복사해 체크할 수 있는 목록이다. 결정점은 분기로 적는다. [Anthropic] Use workflows for complex tasks · Conditional workflow pattern.
- [ ] C7 **되먹임 고리**가 있다: 검증 → 고침 → 다시 검증. 검증기는 스크립트일 수도 참조 문서일 수도 있다. [Anthropic] Implement feedback loops.
- [ ] C8 출력 형식이 중요하면 **본보기**(입력·출력 쌍)나 틀이 있다. [Anthropic] Template pattern · Examples pattern.

## D. 팀 규약 — 세션·루프 공용 기본형

- [ ] D1 **결정적 연산은 도구**다. 본문이 "이 명령을 이렇게 쳐라"로 계산·변환·조회를 시키고 있으면 `tools/<x>/`로 빼고 이름으로 부르라고 제안한다. [팀] conventions §1.
- [ ] D2 `scripts/`가 있으면 **왜 세션 전용인지 한 줄**이 있다. 없으면 수정. 그 스킬은 루프가 집지 않는다(`has_scripts`). [팀] conventions §1.
- [ ] D3 도구는 **이름으로** 부른다("도구 `x`를 `{…}`로 부른다"). 선언 키·플래그 없음. [팀] conventions §4.
- [ ] D4 사람 승인이 전제인 단계에 "사람 승인 전까지는 되돌릴 수 있는 일만"이 있다. [팀] conventions §1.
- [ ] D5 비밀 없음, 심볼릭 링크 없음, 파일 50개·1 MB·합 5 MB 안(`hc check` 4·7). [팀]

## E. 검증 — 측정되었는가

- [ ] E1 evals가 있다. 팀의 **최소**는 쌍(써야 하는 과제 하나, `no-trigger-*` 하나)이고 [팀 conventions §5], Anthropic은 **셋 이상**을 권한다 [Anthropic "At least three evaluations created"]. 둘뿐이면 "통과(최소)"로 적고 셋째 케이스(두 번째 양성 또는 경계 사례)를 제안한다. 둘 미만이면 수정.
- [ ] E2 Oracle이 전 케이스 reward 1이다(`harbor run -a oracle`). [팀]
- [ ] E3 스킬 **있이·없이** 결과가 있다. 없이도 통과하면 스킬이 하는 일이 없다 — 2회 연속이면 폐기 심사. [팀] conventions §5. [Anthropic] "Establish baseline: Measure Claude's performance without the Skill."
- [ ] E4 쓰려는 모델 전부로 돌려 봤다. [Anthropic] "Test with all models you plan to use."
