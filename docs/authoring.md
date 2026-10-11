# 스킬 만들어 올리기

스킬 저자가 카탈로그 저장소에 스킬을 올리고, 고치고, 은퇴시키는 법입니다.

## 전제 조건

- 카탈로그 저장소의 로컬 clone과 write 권한(브랜치·PR).
- `uv`(스크립트 실행과 CLI 설치), `gitleaks`(검사 항목 4가 필요로 함), `git`·`gh`.
- evals를 돌리려면 `harbor`(0.24.0)와 Docker, 하네스의 모델 자격, Langfuse 키.
- 하네스에서 `write-skill`을 적재하면 아래 절차를 에이전트가 대신 밟습니다. 손으로 해도 같습니다.

## 1. 스킬의 모양

```
skills/<name>/
  SKILL.md            필수. frontmatter + 본문
  scripts/            선택. 결정적인 일(계산·변환·조회)
  references/         선택. 본문이 가리키는 긴 참고 문서
  assets/             선택. 템플릿·데이터
  evals/              선택이지만 팀 규약은 최소 한 쌍
    <case>/task.toml · instruction.md · environment/Dockerfile · tests/test.sh(진입점) · tests/test_outputs.py(pytest) · solution/solve.sh(Oracle)
```

최소 `SKILL.md`는 이렇습니다.

```markdown
---
name: yt-subs
description: YouTube 영상의 자동 자막을 받아 평문으로 저장한다. 사용자가 "자막 뽑아줘", "이 영상 자막 받아"라고 할 때 쓴다. 영상 다운로드나 번역은 하지 않는다.
compatibility: yt-dlp와 네트워크가 필요하다
metadata:
  requires-tools: "yt-dlp uv"
---

# yt-subs

## 언제 쓰는가
## 단계
1. `uv run --script scripts/fetch.py <url>`로 자막을 받는다 …
## 실패 대응
| 상황 | 대응 |
|---|---|
| 종료 4 | `brew install yt-dlp` 안내 |
```

형식은 agentskills.io 스펙입니다. `name`은 1~64자의 소문자·숫자·하이픈으로 디렉토리 이름과 같아야 하고 카탈로그 전체에서 유일합니다. 판은 따로 적지 않습니다. 그 디렉토리의 git 트리 `sha`가 판입니다.

## 2. 팀 규약

**description이 전부입니다.** 에이전트가 이 스킬을 고를지 판단하는 유일한 단서이고, 호스트가 긴 설명을 자를 수 있습니다. 첫 문장에 무엇을 하는지와 사용자가 실제로 입에 올릴 낱말을 넣고, 쓰지 말아야 할 상황을 한 줄 둡니다.

**종속성은 두 곳에.** 시스템 도구는 `compatibility`(사람이 읽는 문장)와 `metadata.requires-tools`(기계가 거르는 공백 구분 목록) 둘 다에 적습니다. 검색 결과에 둘 다 실립니다. 파이썬 패키지는 스크립트 머리의 PEP 723 `dependencies`에 `==`로 고정해 적습니다.

**결정적인 일은 스크립트로, 판단은 본문으로.** 파이썬은 `uv run --script scripts/x.py`로 부릅니다(실행 비트에 기대지 않습니다). 종료 코드는 2 입력 오류, 3 대상 없음, 4 시스템 도구 없음이고, 4일 때는 설치 명령을 함께 찍습니다.

**evals는 한 쌍부터.** 이 스킬을 써야 풀리는 과제 하나와, 비슷하지만 쓰면 안 되는 과제 하나(`no-trigger-*`). 전자는 스킬이 값을 하는지, 후자는 description이 과하게 발동하지 않는지 잽니다.

**여러 스킬이 같은 스크립트를 쓸 때.** 몇십 줄이면 복사합니다(어긋나면 검사 항목 10이 경고). 라이브러리 규모면 `packages/<lib>/`로 빼고 각 스킬의 스크립트는 PEP 723으로 그 패키지를 git 참조합니다.

규약의 정본은 카탈로그의 `write-skill/references/conventions.md`입니다.

## 3. 올리는 절차

1. `search_skills`로 같은 일을 하는 스킬이 없는지 봅니다. 있으면 새로 만들지 말고 고칩니다(§6).
2. `main`을 최신으로 하고 브랜치를 땁니다. `git switch -c skill/<name>`.
3. `skills/<name>/`을 §1의 모양대로 씁니다.
4. `pre-commit install`을 한 번 해 둡니다. 커밋마다 `harness-catalog check --rev INDEX --base HEAD`가 돕니다. 직접 돌리려면 `harness-catalog check . --rev HEAD --base main`.
5. evals를 스킬 있이·없이 두 번 돌립니다(§5).
6. 커밋하고 PR을 엽니다. 본문에 Langfuse run 링크를 적습니다.
7. CI의 `check`가 초록인지 봅니다. 붉으면 §4대로 고칩니다.
8. 병합은 사람이 git 호스트에서 합니다. 병합한 사람이 이 판의 인증자입니다.
9. 레지스트리가 한 주기(기본 60초) 안에 받아 색인합니다. `search_skills(<이름>)`에 나타나면 끝입니다.

`main`에 직접 push하거나 강제 push하지 않습니다. 브랜치 보호는 걸려 있지 않고 규율입니다.

## 4. 검사 항목

`harness-catalog check`의 종료 코드는 0 통과, 1 위반, 2 검사기 실패입니다.

| 항목 | 보는 것 | 붉으면 |
|---|---|---|
| 1 | 표지 `.harness-catalog`(`layout = 1`), `skills/`, CI 워크플로, pre-commit 설정, README | 저장소 초기화 문제. 운영자가 `init` |
| 2 | `skills/` 바로 아래는 디렉토리(와 `.gitkeep`)뿐, 각 디렉토리에 `SKILL.md` | 잘못 놓인 파일을 옮긴다 |
| 3 | `SKILL.md` 형식(agentskills.io 참조 검증기): `name` 문법·디렉토리 일치·frontmatter | 메시지대로 고친다 |
| 4 | gitleaks 비밀 검출 | 비밀을 지우고 그 비밀을 회전한다. 이력에 남은 것도 비밀이다 |
| 5 | 기준 커밋 대비 새 이름이 은퇴한 이름과 같음 | 다른 이름 |
| 6 | `metadata.replaced-by` 대상이 존재하고 연쇄·순환이 없음 | 최종 대상을 직접 가리킨다 |
| 7 | 파일 수·크기·합계 한도, 심볼릭 링크 금지 | 큰 데이터는 밖에 두고 받는 스크립트로 |
| 8 | `requires-tools` 토큰 문법(`[a-z0-9._+-]+`, 공백 구분) | 문법대로 |
| 9 (경고) | 스킬을 지우면서 `replaced-by`를 안 적음 | 대체가 있으면 적는다 |
| 10 (경고) | 다른 스킬과 같은 상대 경로의 스크립트 내용이 다름 | 맞추거나 의도적 분기임을 PR에 적는다 |

종료 2는 검사기 자체의 실패입니다. gitleaks가 없거나(항목 4는 fail-closed라 없으면 통과가 없습니다) 전체 이력을 못 읽는 얕은 clone이 흔한 원인입니다.

## 5. evals 돌리기

```sh
harbor run -p skills/<name>/evals -a oracle -e docker                                                                                   # 먼저: 모델 없이, solution/solve.sh로 태스크·검증기 자체를 확인
harbor run --path skills/<name>/evals --agent claude-code --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin   # 스킬 있이
harbor run --path skills/<name>/evals --agent claude-code --env docker --plugin harbor_langfuse:LangfusePlugin                           # 없이
```

둘 다 통과하면 모델이 이미 혼자 하는 일이라 스킬이 값을 하지 않는 것이고, 넣었을 때만 통과하면 값을 한 것입니다. 결과는 Langfuse 데이터셋 `<카탈로그>/<스킬>`에 run 둘로 남습니다. 음성 과제처럼 자동 판정이 어려우면 사람이 눈으로 보고 Langfuse에 주석(annotation)으로 남겨도 됩니다. Harbor가 없으면 PR 본문에 "evals 미실행"을 적습니다.

CI에서도 돌리려면 운영자가 git 호스트 변수 `HARNESS_EVALS=true`와 러너 자격을 둡니다([operations.md](operations.md)).

## 5.5 도구 올리기(toolbox)

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

뼈대는 `write-tool` 스킬이 만듭니다(`skills/write-tool/scripts/scaffold_tool.py`, 멱등). `tool.json`의 선택 키 `$schema`가 `schemas/tool.schema.json`을 가리키면 편집기가 타이핑 중에 검증합니다. 그 파일은 `harness-catalog init`이 core 모델에서 생성해 두고, 낡았으면 `harness-catalog schema tool > schemas/tool.schema.json`으로 다시 씁니다. 레지스트리는 `$schema`를 해석하지 않습니다. 계약의 저자용 문면은 `skills/write-tool/references/tool-contract.md`입니다.

규칙은 스킬과 같은 것이 많습니다. 이름은 **스킬과 합쳐 전역 유일**이고 은퇴한 이름은 다시 쓰지 않습니다(검사 5·11). 시크릿은 저장소에 없습니다 — `server.json`의 `isSecret: true` 항목은 `value`·`default`를 가질 수 없습니다(검사 12). `metadata.requires-tools`·`replaced-by`는 스킬 규칙 그대로입니다. 검사 항목은 11(도구)·12(서버)이고 `harness-catalog check`가 함께 봅니다.

## 6. 고치기, 은퇴시키기, 대체하기

**고치기**는 같은 디렉토리를 브랜치에서 바꿔 PR을 여는 것입니다. 병합되면 트리 `sha`가 바뀌고, pin해 둔 사람은 "새 판 있어?"로 압니다. 옛 판은 사라지지 않습니다. `load_skill(id, sha=<옛 sha>)`가 `main` 이력에서 찾아 돌려줍니다.

**은퇴**는 디렉토리를 지우는 PR입니다. 은퇴한 이름은 다시 쓸 수 없습니다(항목 5). 누군가의 `PINNED`가 그 이름을 가리킬 수 있기 때문입니다.

**대체**는 두 PR입니다. 먼저 옛 스킬의 `metadata.replaced-by: <새 이름>`을 적어 한 판 둡니다. 그동안 검색 결과의 `replaced_by`가 새 이름을 안내합니다. 그다음 옛 디렉토리를 지웁니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| 커밋 훅이 `checker failed: gitleaks` | `brew install gitleaks` |
| CI `check`가 `could not read Username` | 코드 저장소가 비공개인데 읽기 자격 시크릿이 없다. 운영자에게 |
| 이름이 `search_skills`에 없는데 항목 5가 거부 | 은퇴한 이름이다. 다른 이름 |
| `harbor run`이 자격 오류 | `CLAUDE_CODE_OAUTH_TOKEN`+`CLAUDE_FORCE_OAUTH=1` 또는 `ANTHROPIC_API_KEY`, Langfuse 키 셋 |
