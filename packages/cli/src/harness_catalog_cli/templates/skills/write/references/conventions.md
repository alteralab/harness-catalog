# 팀 규약 점검표 — 스킬 하나를 올리기 전에

이 파일이 스킬 규약의 단일 소유자다(도구 쪽은 `tool-contract.md`). README와 `write` 본문은 여기를 가리킨다. 항목마다 "예"라고 답할 수 있어야 한다.

## 1. 결정과 판단의 분리 — 기본형은 세션·루프 공용

- [ ] 결정적인 일(계산·변환·조회·파일 쓰기)은 **도구**(`tools/<name>/tool.json` + 스크립트)이고 스킬 본문은 그 도구를 **이름으로** 부른다("도구 `x`를 `{...}`로 부른다"). 판단(언제·무엇을·실패하면)만 본문에 적는다.
- [ ] `skills/<name>/scripts/`는 두지 않는다. 예외는 세션에서만 뜻이 있는 보조(호출자가 이 스킬 하나뿐이고 열 줄 안, 사람이 읽을 보고서 찍기)이고, 그때는 SKILL.md에 왜 세션 전용인지 한 줄을 적는다. 그 스킬은 루프가 후보에서 뺀다(`has_scripts`).
- [ ] 호출자가 이 스킬 하나뿐이고 열 줄 안에 끝나는 일은 스크립트가 아니라 본문의 지시다.
- [ ] 참조 파일은 스킬 루트 기준 **상대 경로·마크다운 링크·한 단계 깊이**로 적는다(agentskills 스펙 File references). `@` 포함은 스펙 밖이라 쓰지 않는다.
- [ ] 사람 승인이 전제인 단계는 본문에 "사람 승인 전까지는 되돌릴 수 있는 일만"이라고 적는다. 루프는 그 줄에 오면 멈춘다(needs_human). 플래그나 선언 키는 없다.

## 2. 스크립트(예외로 둘 때)와 의존성

- [ ] 파이썬 스크립트는 PEP 723 머리를 단다:
  ```python
  # /// script
  # requires-python = ">=3.12"
  # dependencies = ["yt-dlp>=2026.1"]
  # ///
  ```
- [ ] 호출은 `uv run --script scripts/x.py <인자>`로 적는다. 실행 비트·shebang 직접 실행에 기대지 않는다.
- [ ] **의존성은 스크립트 안에만 적는다.** 파이썬 패키지는 위 머리에, 바이너리(git·yt-dlp 같은 시스템 도구)는 없을 때 스크립트가 종료 `4`와 설치 안내 한 줄(표준 오류)로 말한다. frontmatter에 베껴 적는 필드는 없다.
- [ ] 종료 코드: `2` 입력 오류(인자·형식), `3` 대상 없음(URL·파일·레코드), `4` 시스템 도구 없음. 그 밖의 실패는 `1`. 도구 스크립트의 ABI(0 = 결과를 냈다, 그 밖 = 실행 실패)와 어긋나지 않는다 — 2·3·4는 "왜 실패했나"의 세부 분류다.
- [ ] 판을 고정하려면 `uv lock --script scripts/x.py`의 잠금 파일을 함께 두거나 `exclude-newer`를 쓴다(권고).

## 3. 공유 코드 — 여러 스킬이 같은 코드를 쓸 때

- [ ] 그 코드는 도구다. `tools/<name>/`에 한 번 두고 스킬들은 이름으로 부른다. 복사하지 않는다.
- [ ] 라이브러리 규모면 카탈로그 저장소의 `packages/<lib>/`(또는 별도 저장소)에 패키지로 두고, 도구의 스크립트는 PEP 723 `dependencies = ["<lib> @ git+<url>@<sha>#subdirectory=packages/<lib>"]`(SHA 고정)를 적은 얇은 진입점만 남긴다.
- [ ] 스킬 간 호출과 `${CLAUDE_PLUGIN_ROOT}` 같은 하네스 전용 경로는 쓰지 않는다.

## 4. SKILL.md

- [ ] frontmatter는 `name`(디렉토리명과 같다)·`description`뿐이다. `compatibility`는 네트워크·특정 제품 같은 조건이 있을 때만 사람이 읽는 한 문장(대부분 없다). `metadata`는 쓰지 않는다. `skills-ref validate`를 통과한다.
- [ ] description 첫 문장에 **핵심 용례와 발동 낱말**(사용자가 실제로 말할 표현)이 있다. 쓰지 말아야 할 상황이 한 줄 있다.
- [ ] 본문은 한국어. `name`·도구 이름·파일 경로는 영문 그대로. 도구는 이름으로만 참조한다(선언 키 없음).
- [ ] 본문 절: 언제 쓰는가 · 단계 · 실패 대응 표. 500줄 안.
- [ ] 크기: 파일 50개, 파일당 1 MB, 합계 5 MB 안. 심볼릭 링크 없음. 비밀 없음(gitleaks).

## 5. evals — 최소 쌍

- [ ] `evals/<case>/`가 둘 이상: 써야 하는 과제 하나, 쓰지 말아야 하는 과제 하나(`no-trigger-*`).
- [ ] 케이스마다 `task.toml`·`instruction.md`·`environment/Dockerfile`·`tests/test.sh`·`tests/test_outputs.py`·`solution/solve.sh`. 검증기의 인터페이스와 보고 형식은 Harbor 공식 뼈대(`harbor tasks init`)를 따른다 — bash 진입점 `tests/test.sh`가 `tests/test_outputs.py`를 pytest로 돌려 CTRF 보고(`/logs/verifier/ctrf.json`)와 함께 종료 코드로 `/logs/verifier/reward.txt`에 `1`/`0`을 쓴다. 검사 논리는 전부 pytest 단언에 둔다(셸 조건문 아님). 이미지는 공식 뼈대(`ubuntu:24.04` 두 줄)와 다르다: `python:3.12-slim` + git + uv(스킬 스크립트 규약) + pytest·pytest-json-ctrf 미리 설치 + `/skills` + `WORKDIR /work`. 미리 넣는 이유는 검증 중 PyPI 내려받기를 없애 검증 예산과 결정성을 지키는 것이다(Harbor PR #2596, Terminal-Bench `check-verifier-tooling-baked`) — `network_mode`는 기본 `public`이라 네트워크가 없어서가 아니다. uv는 PyPI에서 받는다(GHCR `COPY --from`은 self-hosted 러너에서 pull denied 실측). 검증기는 공유 모드(`[verifier] environment_mode = "shared"`)를 명시한다 — 에이전트 컨테이너의 끝 상태(`.agents/skills/`·`PINNED`·심볼릭 링크)를 직접 보기 위해서다; 분리 모드는 artifacts 선언과 `tests/Dockerfile`이 필요해 스킬 eval에는 비용이 크고, 대가(에이전트에 pytest 노출)는 무해하다. `solve.sh`는 검증기가 참으로 보는 끝 상태를 직접 만드는 Oracle용 스크립트다(Harbor 표준의 선택 디렉토리). 음성 케이스의 solve.sh는 `exit 0`이다.
- [ ] 모델 없이 먼저 돈다: `harbor run -p skills/<name>/evals -a oracle -e docker` 로 전 케이스 reward 1(태스크가 풀리는 태스크인지, 검증기가 끝 상태를 받아들이는지). 2026-10-10 실측: 기본 스킬 둘의 넷이 각 1.0, 두 데이터셋 35초. Oracle은 잡 스킬(`--skill`)을 받지 않으므로(Harbor 0.24 `capabilities.skills`) solve.sh는 카탈로그의 도구에 기대지 않는 참조 해답이어야 한다.
- [ ] 뼈대는 도구 `scaffold`(`tools/scaffold/`, 카탈로그 클론의 `.mcp.json`으로 MCP에 떠 있다)가 `{"kind": "skill", "name": …, "description": …, "positive": …, "negative": …, "tool": …}`로 만든다(멱등, 있는 파일은 건드리지 않음). task.toml(schema 1.4·`skills_dir`·타임아웃)·Dockerfile 머리·test.sh/solve.sh 골격의 문면은 그 도구가 소유한다 — 여기 다시 적지 않는다. 에이전트는 TODO 자리(description·instruction·검증 조건·solve 본문·절차)만 채운다.
- [ ] 실행: `harbor run --path skills/<name>/evals --agent <하네스> --model <모델> --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin`(스킬 있이)과 `--skill`을 뺀 같은 명령(없이) 두 잡. `--dataset`은 Harbor 레지스트리의 `name@version`용이라 로컬 경로에는 `--path`다. 둘 다 통과하면 스킬이 하는 일이 없는 것이고, 있이만 통과하면 값을 한 것이다.
- [ ] 음성 케이스는 궤적(스킬 로드 여부)을 봐야 판정되므로 검증기가 없으면 사람이 눈으로 판정해 Langfuse annotation으로 남긴다.
- [ ] 다시 돌리는 때 셋: 본문을 고쳤을 때, 주요 모델이 나왔을 때, 분기마다. 스킬 없이 2회 연속 전 케이스 통과면 폐기 심사 대상.

## 6. 은퇴

- [ ] 은퇴는 디렉토리 삭제다. 그것뿐이다. 검색에 더 나오지 않으면 은퇴한 것이고 후속은 검색으로 찾는다. 같은 이름으로 다른 내용을 올리고 싶으면 그것은 은퇴가 아니라 갱신이다(디렉토리를 고쳐 병합).
