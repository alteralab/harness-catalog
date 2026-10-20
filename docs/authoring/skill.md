---
title: 스킬의 모양과 팀 규약
description: 디렉토리 모양, SKILL.md 형식, 팀 규약 다섯.
audience: 스킬 저자
---

# 스킬의 모양과 팀 규약

스킬 하나의 디렉토리 모양과, 카탈로그에 올릴 때 지키는 팀 규약입니다. 다 쓰면 [올리는 절차](submit.md)로 갑니다.

## 스킬의 모양

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

## 팀 규약

**description이 전부입니다.** 에이전트가 이 스킬을 고를지 판단하는 유일한 단서이고, 호스트가 긴 설명을 자를 수 있습니다. 첫 문장에 무엇을 하는지와 사용자가 실제로 입에 올릴 낱말을 넣고, 쓰지 말아야 할 상황을 한 줄 둡니다.

**의존성은 스크립트 안에만.** 파이썬 패키지는 스크립트의 PEP 723 머리에 적고(`uv run --script`가 실행 때마다 맞춥니다), 바이너리는 없을 때 스크립트가 종료 4와 설치 안내 한 줄로 말합니다. 바깥에 베껴 적는 필드(`metadata.requires-tools`)는 없습니다. `compatibility`는 네트워크나 특정 제품 같은 조건이 있을 때만 사람이 읽는 자유 문장이고 대부분의 스킬에는 없습니다.

**결정적인 일은 스크립트로, 판단은 본문으로.** 파이썬은 `uv run --script scripts/x.py`로 부릅니다(실행 비트에 기대지 않습니다). 종료 코드는 2 입력 오류, 3 대상 없음, 4 시스템 도구 없음이고, 4일 때는 설치 명령을 함께 찍습니다.

**evals는 한 쌍부터.** 이 스킬을 써야 풀리는 과제 하나와, 비슷하지만 쓰면 안 되는 과제 하나(`no-trigger-*`). 전자는 스킬이 값을 하는지, 후자는 description이 과하게 발동하지 않는지 잽니다.

**여러 스킬이 같은 코드를 쓸 때.** 그 코드는 도구입니다. `tools/<name>/`에 한 번 두고 스킬들은 이름으로 참조합니다. 라이브러리 규모면 `packages/<lib>/`로 빼고 도구의 스크립트가 PEP 723으로 그 패키지를 git 참조합니다.

규약의 정본은 카탈로그의 `skills/write/references/conventions.md`(스킬)와 `references/tool-contract.md`(도구)입니다.
