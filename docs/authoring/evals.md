---
title: evals 돌리기
description: Oracle·있이·없이 세 번 돌리기, Langfuse 기록, CI 의 몫.
audience: 스킬 저자
---

# evals 돌리기

스킬의 evals를 Harbor로 돌려 스킬이 값을 하는지 잽니다. PR을 열기 전 단계이고, [올리는 절차](submit.md) 5항이 이 쪽을 가리킵니다.

```sh
harbor run -p skills/<name>/evals -a oracle -e docker                                                                                   # 먼저: 모델 없이, solution/solve.sh로 태스크·검증기 자체를 확인
harbor run --path skills/<name>/evals --agent claude-code --env docker --skill ./skills/<name> --plugin harbor_langfuse:LangfusePlugin   # 스킬 있이
harbor run --path skills/<name>/evals --agent claude-code --env docker --plugin harbor_langfuse:LangfusePlugin                           # 없이
```

둘 다 통과하면 모델이 이미 혼자 하는 일이라 스킬이 값을 하지 않는 것이고, 넣었을 때만 통과하면 값을 한 것입니다. 결과는 Langfuse 데이터셋 `<카탈로그>/<스킬>`에 run 둘로 남습니다. 음성 과제처럼 자동 판정이 어려우면 사람이 눈으로 보고 Langfuse에 주석(annotation)으로 남겨도 됩니다. Harbor가 없으면 PR 본문에 "evals 미실행"을 적습니다.

CI는 Oracle만 돌립니다(`harness-catalog evals`, 바뀐 스킬의 `-a oracle`) — 과제가 풀리고 검증기가 끝 상태를 받는지를 PR마다 확인하는 것이고, 모델 측정은 위 두 명령으로 저자가 자기 자격으로 합니다. 결과는 Langfuse에 남습니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| `harbor run`이 자격 오류 | `CLAUDE_CODE_OAUTH_TOKEN`+`CLAUDE_FORCE_OAUTH=1` 또는 `ANTHROPIC_API_KEY`, Langfuse 키 셋 |
