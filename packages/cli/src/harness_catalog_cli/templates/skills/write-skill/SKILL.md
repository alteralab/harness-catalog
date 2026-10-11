---
name: write-skill
description: 팀 카탈로그(harness-catalog)에 올릴 새 스킬의 뼈대를 만들고 팀 규약대로 채운다. 사용자가 "스킬 새로 만들자", "이 절차를 스킬로 만들어", "SKILL.md 뼈대 잡아줘", "스킬 만들어서 카탈로그에 올리자"라고 할 때 쓴다. 먼저 search_skills로 같은 일을 하는 스킬이 있는지 확인하고, 카탈로그 클론의 브랜치에 SKILL.md·scripts/·evals/를 만들며, 종속성(metadata.requires-tools와 compatibility), PEP 723 + uv run --script, 종료 코드 2/3/4, 양성·음성 evals 한 쌍(Harbor 태스크), harbor run 결과를 Langfuse에, description 검수를 점검표로 지난다. 브랜치·커밋·PR은 사용자가 지시할 때만 만들고 병합은 사람이 git 호스트에서 한다. 기존 스킬의 한 줄 수정은 이 스킬이 아니다.
compatibility: 카탈로그 저장소의 로컬 클론과 git·gh(PR 생성), 스크립트가 있는 스킬이면 uv(uv run --script)가 필요하다
metadata:
  requires-tools: "uv git gh"
---

# write-skill — 새 스킬의 뼈대와 팀 규약

새 스킬의 뼈대를 카탈로그 클론의 **브랜치**(병합 전 = 비공개 초안)에 만들고, 팀 규약을 점검표로 통과시키고, evals 최소 쌍을 두고, `harbor run`으로 돌려 Langfuse에 남기는 데까지. PR은 사용자의 지시 뒤에만, 병합은 사람이 한다. 규약의 문장은 `references/conventions.md` 하나가 소유한다 — 본문은 그것을 가리킬 뿐 다시 쓰지 않는다.

## 언제 쓰는가

- 쓴다: "스킬 새로 만들자", "이 절차를 스킬로 만들어", "SKILL.md 뼈대 잡아줘", "스킬 만들어서 카탈로그에 올리자".
- 쓰지 않는다: 기존 스킬의 한 줄 수정은 갱신이다 — 카탈로그 클론에서 `main` 기준 브랜치 → `skills/<name>/` 수정 → 커밋 → PR. 이 스킬의 뼈대 절차가 아니다.

## 단계

1. 사용자의 한 문장에서 스킬이 **하는 일**과 **발동 상황**을 받아 적는다. `search_skills`로 같은 일을 하는 스킬이 있는지 확인한다. 있으면 갱신 경로(위 "쓰지 않는다")를 안내하고 멈춘다.
2. 이름을 정한다. `name` 문법은 1~64자, 소문자·숫자·하이픈이고 `search_skills(<이름>)`에 없어야 한다. 은퇴한 이름은 `harness-catalog check`(항목 5)가 거부하니 그때 바꾼다.
3. 카탈로그 저장소의 로컬 클론(없으면 사용자에게 경로를 묻고 clone)에서 `main`을 최신으로 한 뒤 브랜치 `skill/<name>`을 따고 뼈대는 `uv run --script <이 스킬>/scripts/scaffold.py <name> --description "<한 문장>" --positive <케이스> --negative <케이스> [--script <x.py>]`로 만든다(멱등). 그 결과의 TODO 자리를 채운다 — `SKILL.md` 본문(언제 쓰는가·단계·실패 대응 표), 스크립트 본문, evals의 과제 문장과 검증 조건.
4. `references/conventions.md`의 점검표를 하나씩 지난다. 요지: 결정적인 일(계산·변환·조회)은 스크립트로, 판단은 본문 지시로. 파이썬 스크립트는 PEP 723 머리 + `uv run --script scripts/x.py`. 시스템 도구는 `metadata.requires-tools`(기계용)와 `compatibility`(사람용 문장) 둘 다에. 종료 코드 2 입력 오류·3 대상 없음·4 시스템 도구 없음.
5. evals 최소 쌍은 3의 스크립트가 Harbor 태스크 여섯 파일(`task.toml`·`instruction.md`·`environment/Dockerfile`·`tests/test.sh`·`tests/test_outputs.py`·`solution/solve.sh`)씩 만들어 둔다. 써야 하는 과제 하나와 쓰지 말아야 하는 과제 하나(`no-trigger-*`). `instruction.md`·`tests/test_outputs.py`(pytest 단언)·`solve.sh`의 TODO를 채우고, 모델 없이 `harbor run -p skills/<name>/evals -a oracle -e docker`로 넷이 reward 1인지 먼저 본다.
6. description을 검수한다: 무엇을·언제 쓰는지, 사용자가 실제로 말할 낱말이 들었는지, 쓰지 말아야 할 상황이 한 줄 있는지, **핵심 용례와 발동 낱말이 첫 문장에 있는지**(호스트가 설명을 자를 수 있고 모델은 첫머리를 더 잘 쓴다).
7. `harness-catalog check`를 돌린다(pre-commit 훅이 커밋 때 다시 돌리고 CI가 PR에서 또 돌린다). 위반 항목을 고친다.
8. `harbor run --path skills/<name>/evals --agent <하네스> --model <모델> --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin`을 스킬 있이(`--skill`)·없이 두 번 돌린다. 결과는 Langfuse에 run 둘로 남고 PR 본문에 그 run 링크를 적는다. Harbor가 없거나 음성 케이스처럼 검증기가 아직 없으면 사람이 눈으로 판정해 Langfuse annotation으로 남긴다.
9. 사용자에게 브랜치·점검표 결과를 보고하고 **멈춘다**. 사용자가 "올려"라고 할 때만 커밋하고 push해 `gh pr create`(GitLab이면 `glab mr create`)로 PR을 연다. 병합은 사람이 git 호스트에서 한다. 클라우드 샌드박스 세션(git 자격 없음)이면 여기서 멈추고 로컬 세션에서 하라고 알린다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 같은 일을 하는 스킬이 이미 있다 | 갱신 경로를 안내하고 멈춘다 |
| 이름이 `search_skills`에 있거나 `check` 항목 5가 거부 | 다른 이름 |
| `harness-catalog check`가 붉다 | 항목 번호대로 고친다. 검사기 자체 실패(종료 2)는 gitleaks 설치·전체 이력 클론을 확인 |
| Harbor가 없다 | 8을 건너뛰고 PR 본문에 "evals 미실행"을 적는다. 음성 케이스는 사람이 판정 |
| 클라우드 샌드박스 세션 | 9에서 멈춘다 |
