---
title: 프록시 붙이기
description: 열어야 할 경로 셋, TLS 종단, issuer hairpin.
audience: 운영자
---

# 프록시 붙이기

TLS를 종단하는 리버스 프록시를 레지스트리 앞에 붙이는 쪽입니다. [레지스트리 설치하기](install.md)가 끝나 있어야 합니다.

경로 셋을 엽니다.

| 경로 | 대상 | 이유 |
|---|---|---|
| `/mcp` | registry :8000 | MCP 엔드포인트 |
| `/.well-known/oauth-protected-resource` | registry :8000 | 401 응답이 가리키는 보호 자원 메타데이터. 안 열면 하네스가 로그인 절차를 시작하지 못한다 |
| `/dex` | dex :5556 | OIDC issuer |

`tailscale serve`면 이렇습니다.

```sh
tailscale serve --bg --set-path /mcp http://127.0.0.1:8000/mcp
tailscale serve --bg --set-path /.well-known/oauth-protected-resource http://127.0.0.1:8000/.well-known/oauth-protected-resource
tailscale serve --bg --set-path /dex http://127.0.0.1:5556/dex
```

레지스트리 컨테이너는 토큰 검증 때 issuer(자기 공개 호스트 이름)에 닿아야 합니다. 프록시가 같은 호스트면 hairpin이 필요하고, Synology 오버레이의 `extra_hosts`가 그 이름을 호스트의 IP로 풉니다.
