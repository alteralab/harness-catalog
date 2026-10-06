# 팀 규약 점검표 — 스킬 하나를 올리기 전에

이 파일이 팀 규약의 단일 소유자다. README와 `write-skill` 본문은 여기를 가리킨다. 항목마다 "예"라고 답할 수 있어야 한다.

## 1. 결정과 판단의 분리

- [ ] 결정적인 일(계산·변환·조회·파일 쓰기)은 `scripts/`의 스크립트가 한다. 본문은 판단(언제·무엇을·실패하면)만 적는다.
- [ ] 호출자가 이 스킬 하나뿐이고 열 줄 안에 끝나는 일은 스크립트가 아니라 본문의 지시다.

## 2. 스크립트

- [ ] 파이썬 스크립트는 PEP 723 머리를 단다:
  ```python
  # /// script
  # requires-python = ">=3.12"
  # dependencies = ["yt-dlp>=2026.1"]
  # ///
  ```
- [ ] 호출은 `uv run --script scripts/x.py <인자>`로 적는다. 실행 비트·shebang 직접 실행에 기대지 않는다.
- [ ] 종료 코드: `2` 입력 오류(인자·형식), `3` 대상 없음(URL·파일·레코드), `4` 시스템 도구 없음(설치 안내 한 줄을 표준 오류에). 그 밖의 실패는 `1`.
- [ ] 판을 고정하려면 `uv lock --script scripts/x.py`의 잠금 파일을 함께 두거나 `exclude-newer`를 쓴다(권고).

## 3. 종속성 두 자리

- [ ] 시스템 도구(바이너리)는 둘 다에 적는다: `metadata.requires-tools: "uv git gh"`(공백 구분, 토큰 문법 `[a-z0-9._+-]+`, 기계가 읽는다)와 `compatibility`(사람이 읽는 문장).
- [ ] 언어 패키지는 스크립트 안(PEP 723)에서 해결한다. frontmatter에 적지 않는다.

## 4. 공유 스크립트 — 여러 스킬이 같은 코드를 쓸 때

- [ ] 라이브러리 규모면 카탈로그 저장소의 `packages/<lib>/`(또는 별도 저장소)에 패키지로 두고, 각 스킬의 `scripts/x.py`는 PEP 723 `dependencies = ["<lib> @ git+<url>@<sha>#subdirectory=packages/<lib>"]`(SHA 고정)를 적은 얇은 진입점만 남긴다.
- [ ] 작으면 복사한다. `harness-catalog check` 항목 10이 복사본 사이의 드리프트를 경고한다(어느 둘인지 출력).
- [ ] 스킬 간 호출과 `${CLAUDE_PLUGIN_ROOT}` 같은 하네스 전용 경로는 쓰지 않는다.

## 5. SKILL.md

- [ ] frontmatter는 `name`(디렉토리명과 같다)·`description`·(있으면) `compatibility`·`metadata`뿐이다. `skills-ref validate`를 통과한다.
- [ ] description 첫 문장에 **핵심 용례와 발동 낱말**(사용자가 실제로 말할 표현)이 있다. 쓰지 말아야 할 상황이 한 줄 있다.
- [ ] 본문은 한국어. `name`·도구 이름·파일 경로는 영문 그대로.
- [ ] 본문 절: 언제 쓰는가 · 단계 · 실패 대응 표. 500줄 안.
- [ ] 크기: 파일 50개, 파일당 1 MB, 합계 5 MB 안. 심볼릭 링크 없음. 비밀 없음(gitleaks).

## 6. evals — 최소 쌍

- [ ] `evals/<case>/`가 둘 이상: 써야 하는 과제 하나, 쓰지 말아야 하는 과제 하나(`no-trigger-*`).
- [ ] 케이스마다 `task.toml`·`instruction.md`·`environment/Dockerfile`·`tests/test.sh`. 검증기는 결과 파일·상태를 검사해 `/logs/verifier/reward.txt`에 `1` 또는 `0`을 쓴다.
- [ ] 템플릿:
  ```toml
  # task.toml (Harbor 0.24, schema 1.4)
  schema_version = "1.4"

  [metadata]
  description = "<케이스 한 줄>"

  [environment]
  build_timeout_sec = 600.0
  skills_dir = "/skills"

  [agent]
  timeout_sec = 600.0

  [verifier]
  timeout_sec = 120.0
  ```
  ```dockerfile
  # environment/Dockerfile
  FROM python:3.12-slim
  RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
  COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
  WORKDIR /work
  ```
  ```sh
  # tests/test.sh — 결과를 보고 reward.txt에 0/1
  #!/bin/sh
  set -eu
  mkdir -p /logs/verifier
  if [ -f /work/result.txt ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
  ```
- [ ] 실행: `harbor run --dataset skills/<name>/evals --agent <하네스> --model <모델> --env docker --plugin harbor_langfuse:LangfusePlugin`. 스킬 있이·없이 두 잡. 둘 다 통과하면 스킬이 하는 일이 없는 것이고, 있이만 통과하면 값을 한 것이다.
- [ ] 음성 케이스는 궤적(스킬 로드 여부)을 봐야 판정되므로 검증기가 없으면 사람이 눈으로 판정해 Langfuse annotation으로 남긴다.
- [ ] 다시 돌리는 때 셋: 본문을 고쳤을 때, 주요 모델이 나왔을 때, 분기마다. 스킬 없이 2회 연속 전 케이스 통과면 폐기 심사 대상.

## 7. 은퇴와 대체

- [ ] 은퇴는 디렉토리 삭제다. 대체 스킬이 있으면 지우기 전 판의 `metadata.replaced-by: "<name>"`에 적는다(연쇄·순환 금지).
- [ ] 은퇴한 이름은 다시 쓰지 않는다(`check` 항목 5).
