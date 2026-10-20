---
title: Dex와 LDAP 붙이기
description: LDAP 오버레이, Dex 클라이언트, 읽기 그룹 인가.
audience: 운영자
---

# Dex와 LDAP 붙이기

로그인을 팀 디렉터리로 옮기는 쪽입니다. [프록시 붙이기](proxy.md)가 끝나 있어야 합니다.

기본 `docker/dex/config.yaml`은 정적 사용자(`dev`·`outsider`)로 빠른 시작용입니다. 팀 LDAP으로 바꾸려면 오버레이를 겹칩니다.

```sh
docker compose -f docker/compose.yml -f docker/synology-ldap/compose.override.yml up -d
```

`.env`의 `LDAP_HOST`(LDAPS면 `<host>:636`)·`LDAP_BIND_DN`·`LDAP_USER_BASE_DN`·`LDAP_GROUP_BASE_DN`과 hairpin 둘(`HC_PUBLIC_HOSTNAME`·`HC_HOST_TAILSCALE_IP`)을 채우고, 바인드 비밀번호는 `secrets/ldap_bind_pw`에 둡니다. 이 여섯은 **기본값이 없습니다** — 한 팀의 디렉터리 주소가 다른 팀의 기본값일 수 없어, 비면 `docker compose`가 그 자리에서 어느 변수가 비었는지 말하고 멈춥니다(§11 2026-10-20). 예시 값은 `docker/.env.example`의 자리표시자입니다. LDAP Server의 인증서를 신뢰하지 않으면 `LDAP_INSECURE_SKIP_VERIFY=true`(기본)입니다.

Dex에 등록된 클라이언트는 다음과 같습니다. 바꾸려면 설정 파일을 고치고 `dex`를 재기동합니다.

| ID | 종류 | 용도 |
|---|---|---|
| `claude-code`, `codex`, `cursor` | 공개 | 하네스. 브라우저 로그인(PKCE) |
| `ci-runner` | 기밀(시크릿 `secrets/dex_ci_runner_secret`) | 기계 계정의 비밀번호 그랜트 |
| `<HC_PUBLIC_URL>` | 공개, `trustedPeers`에 위 넷 | 토큰의 `aud`에 레지스트리 URL이 실리게 하는 audience 등록 |

인가는 레지스트리 안에서 토큰의 `groups`에 읽기 그룹(`HC__READER_GROUP`, 기본 `harness-readers`)이 있는지로만 판정합니다. 스코프는 보지 않습니다. 기계 계정(우리 팀은 `svc-harness`)도 같은 그룹에 넣습니다.

사내 IdP로 옮기면 Dex와 이 쪽이 사라지고 `HC__OIDC_ISSUER`만 바뀝니다.
