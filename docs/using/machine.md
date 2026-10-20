---
title: 사람 없이 쓰기
description: CI·자동화 루프의 기계 계정과 비밀번호 그랜트.
audience: 팀원
---

# 사람 없이 쓰기

브라우저 로그인 없이 CI나 자동화 루프에서 레지스트리를 부르는 쪽입니다. 사람이 쓰는 등록·로그인은 [등록하고 로그인하기](connect.md)입니다.

CI나 자동화 루프에는 LDAP 기계 계정을 씁니다. 운영자가 계정(우리 팀은 `svc-harness`)을 `harness-readers`에 넣어 두면, 기밀 클라이언트 `ci-runner`의 비밀번호 그랜트로 토큰을 받습니다.

```sh
TOKEN=$(scripts/dev-token.sh https://<호스트>/dex https://<호스트>/mcp ci-runner "$CI_RUNNER_SECRET" svc-harness "$SVC_PASSWORD")
```

이 토큰을 `Authorization: Bearer`로 붙여 같은 MCP 엔드포인트(Streamable HTTP)를 부릅니다. 권한은 사람과 같은 읽기뿐입니다.
