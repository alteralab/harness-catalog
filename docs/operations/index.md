---
title: 레지스트리 운영
description: 구성, 전제 조건, 과제별 쪽 안내.
audience: 운영자
---

# 레지스트리 운영

운영자가 카탈로그 저장소를 세우고, 레지스트리를 띄우고, 돌보는 법입니다. 먼저 한번 돌려 보고 싶으면 [quickstart.md](../quickstart.md)가 명령 둘로 전체를 로컬에 띄웁니다.

## 구성

호스트 한 대에 compose로 컨테이너 셋을 띄웁니다.

| 서비스 | 이미지 | 역할 |
|---|---|---|
| `registry` | `<registry>/<org>/harness-catalog:<판 태그>` (`.env`의 `REGISTRY_IMAGE`. 우리 팀은 NAS Harbor) | MCP 서버 + 주기 fetch·색인 |
| `postgres` | `postgres:17-alpine` | 색인(`harness_catalog`)과 Dex 저장소(별도 DB·역할) |
| `dex` | `ghcr.io/dexidp/dex:v2.45.1` | LDAP을 OIDC로 감싸는 인가 서버 |

TLS와 라우팅은 앞의 리버스 프록시가 맡습니다. 우리 팀은 mini의 `tailscale serve`이고 접근 통제는 tailnet ACL입니다. 백업 대상은 없습니다. 색인은 `main`에서 언제든 다시 짓고, 사용·평가 기록은 Langfuse에 있습니다.

## 전제 조건

- Docker와 compose v2. 컨테이너가 git 호스트와 LDAP에 닿을 것(macOS는 colima가 LAN에 닿았고 Docker Desktop은 닿지 않았습니다).
- 리버스 프록시(TLS 종단). 경로 셋을 열 수 있어야 합니다([프록시 붙이기](proxy.md)).
- LDAP: 읽기 그룹 하나(설정 `HC__READER_GROUP`, 기본 `harness-readers`), 기계 계정 하나, 바인드 DN. 없으면 `docker/dex/config.yaml`의 정적 사용자로 시작할 수 있습니다.
- 카탈로그 저장소와 읽기 전용 deploy key.
- 임베딩 서비스(검색의 dense 쪽, DESIGN §11 2026-10-19). 호스트의 Ollama 에 `ollama pull hf.co/mykor/KURE-v1-gguf:BF16` 한 번이면 됩니다(1.2 GB; Mac 에서는 컨테이너가 GPU 에 닿지 못하므로 호스트 앱). compose 기본값 `HC__EMBED_URL=http://host.docker.internal:11434/api/embed` 가 그것을 가리킵니다. 없어도 레지스트리는 뜨되 `/readyz` 가 `degraded: embedding_unavailable` 로 BM25 만 씁니다.

## 과제별 쪽

차례대로 밟습니다.

| 쪽 | 무엇을 끝내나 |
|---|---|
| [카탈로그 저장소 세우기](catalog-repo.md) | 빈 git 저장소를 `hc init`으로 초기화하고, deploy key와 CI 러너를 붙인다 |
| [레지스트리 설치하기](install.md) | `.env`와 비밀 파일을 만들고 compose로 컨테이너 셋을 띄워 `/readyz`를 확인한다 |
| [프록시 붙이기](proxy.md) | 리버스 프록시에 경로 셋을 열고 issuer hairpin을 맞춘다 |
| [Dex와 LDAP 붙이기](identity.md) | 정적 사용자 대신 팀 LDAP을 붙이고 읽기 그룹으로 인가한다 |
| [런북](runbook.md) | 새 판 올리기, `/readyz` 진단, 비밀 회전, 관측, 온보딩 |
