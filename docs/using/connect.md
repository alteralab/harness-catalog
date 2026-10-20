---
title: 등록하고 로그인하기
description: 하네스 등록, 클라이언트 ID, 첫 로그인.
audience: 팀원
---

# 등록하고 로그인하기

하네스에 레지스트리를 더하고 한 번 로그인해 두는 쪽입니다. 먼저 [전제 조건](index.md)을 갖춥니다.

## 등록

레지스트리는 동적 클라이언트 등록을 쓰지 않고 하네스마다 ID를 미리 등록해 두었습니다. 그래서 URL과 함께 ID를 적어야 합니다.

| 하네스 | 클라이언트 ID |
|---|---|
| Claude Code | `claude-code` |
| Codex | `codex` |
| Cursor | `cursor` |

**Claude Code.** 사용자 범위(모든 프로젝트)로 더합니다.

```sh
claude mcp add --transport http --scope user harness-catalog https://<레지스트리 호스트>/mcp
```

그다음 `~/.claude.json`(프로젝트에만 두려면 `.mcp.json`)의 그 항목에 `oauth.clientId`를 더합니다.

```json
"harness-catalog": {
  "type": "http",
  "url": "https://<레지스트리 호스트>/mcp",
  "oauth": { "clientId": "claude-code" }
}
```

이미 떠 있는 세션은 새 서버를 모릅니다. Claude Code를 새로 시작합니다.

## 첫 로그인

`/mcp`에서 harness-catalog를 고르면 브라우저가 열립니다. Dex 로그인 화면에서 LDAP 계정으로 로그인하면 터미널에 "Authentication successful. Connected to harness-catalog."가 뜹니다. 그 뒤로는 묻지 않습니다(토큰이 하네스에 저장되고 갱신됩니다).

로그인이 끝나면 [스킬 찾아 세션에 넣기](find.md)로 갑니다.

## 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `claude mcp get`이 `ENOTFOUND` | tailnet 이름이 풀리지 않음 | Tailscale을 켠다 |
| `/mcp`에 harness-catalog가 없다 | 세션이 설정을 기동 때 읽음 | Claude Code 재시작 |
| 로그인 뒤 "인증 서버가 동적 등록을 지원하지 않는다" | `oauth.clientId`가 없음 | 설정에 클라이언트 ID를 더한다 |
| 로그인은 되는데 도구 호출이 거부 | `harness-readers`에 없음 | 운영자에게 그룹 추가 요청 |
