---
title: 런북
description: 새 판 올리기, /readyz 진단, 비밀 회전, 관측, 온보딩.
audience: 운영자
---

# 런북

떠 있는 레지스트리를 돌보는 쪽입니다. 설치는 [레지스트리 설치하기](install.md)에 있습니다.

**새 판 올리기.** 코드 저장소에서 `make release VERSION=X.Y.Z`(태그·이미지), CI가 끝나면 `make deploy HOST=mini TAG=<짧은 SHA>`. 둘 다 스크립트 하나이고 손으로 하지 않습니다(plans/distribution.md D25). 배포 스크립트는 `/readyz`가 ready이고 `db_unavailable`이 없을 때까지 기다린 뒤 적용된 마이그레이션을 찍습니다.

**`/readyz`가 503일 때.** 본문의 `reasons`를 봅니다.

| 사유 | 뜻 | 조치 |
|---|---|---|
| `repo_unreachable` | 저장소를 받지 못함 | URL, deploy key, 네트워크 |
| `no_main_branch` | 커밋 0인 빈 저장소 | `hc init` |
| `not_a_catalog` | 표지 파일 없음 | `init` |
| `unsupported_layout` | 표지의 `layout`이 지원하지 않는 값 | 레지스트리 판을 올리거나 표지를 맞춘다 |
| `layout_mismatch` | 표지와 실제 배치가 다름 | 저장소 구조를 본다 |

`degraded`는 준비는 됐지만 온전하지 않은 상태입니다. `db_unavailable`이면 PostgreSQL이 끊긴 것이고 레지스트리는 메모리 사본으로 계속 섬기며 브레이커가 30초 뒤 재시도합니다. `main_rewound`는 아래 되감기입니다. `rebuild_failed:…`는 새 커밋의 색인 빌드가 실패해 이전 색인으로 섬기는 중입니다. `embedding_unavailable`이면 임베딩 서비스(`HC__EMBED_URL`)에 닿지 못했거나 그 값이 비어 어휘(BM25)만으로 답하는 중입니다 — Ollama 가 떠 있고 모델이 내려받아져 있는지(`curl -s http://127.0.0.1:11434/api/tags`) 본 뒤 다음 재빌드(fetch 간격)에서 사유가 사라집니다.

**0.9.0 으로 올린 뒤(선택).** 마이그레이션 0005 가 어휘 검색의 열·인덱스·함수를 지웁니다. `pg_trgm` 확장만 슈퍼유저 소유라 남는데 쓰는 곳이 없으니 원하면 한 번 지웁니다: `docker compose -f docker/compose.yml exec postgres psql -U postgres -d harness_catalog -c 'DROP EXTENSION IF EXISTS pg_trgm'`. 새로 세우는 DB 에는 처음부터 없습니다.

**`main`이 되감겼을 때**(강제 push 등). 레지스트리는 색인을 멈추고 `/readyz`에 알립니다. 의도한 것이면 받아들이고 재기동합니다.

```sh
docker compose -f docker/compose.yml exec registry harness-catalog-server reindex --accept-rewind && docker compose -f docker/compose.yml restart registry
```

**이미지 올리기.** `.env`의 `REGISTRY_IMAGE`를 바꾸고 `docker compose -f docker/compose.yml up -d`. 몇 초 끊깁니다. 마이그레이션은 기동 때 자동으로 적용됩니다.

**비밀 회전.** 값을 새로 만들어 `secrets/`의 파일을 바꾸고 그 값을 쓰는 컨테이너만 재기동합니다. 옛 값은 발급처에서 지웁니다. deploy key는 git 호스트에서, `ci-runner` 시크릿은 Dex 설정에서, DB 비밀번호는 PostgreSQL 역할에서. `docker compose -f docker/compose.yml config`의 출력은 비밀을 담으니 기록에 남기지 않습니다.

**관측(Langfuse).** 레지스트리가 Langfuse를 직접 알지는 않습니다. 도구 호출마다 OpenTelemetry 스팬(`tools/call <tool>`, 속성 `langfuse.user.id`·`langfuse.observation.metadata.skill`·`sha`·`query`·`result_count`)을 내고, 표준 OTLP 환경 변수가 있을 때만 내보냅니다. 수신처는 **기본값이 비어 있습니다** — 모든 배포에 맞는 수집기 주소는 없으므로 운영자가 자기 주소를 `.env`에 적습니다(§11 2026-10-20).

**0.10.0 이행 한 줄.** 0.9.x까지는 compose가 팀 Langfuse Cloud US를 기본값으로 넣었습니다. 0.10.0을 배포하기 **전에** 운영 호스트의 `docker/.env`에 `OTEL_EXPORTER_OTLP_ENDPOINT`를 넣지 않으면 배포 즉시 트레이스가 끊깁니다(DB 마이그레이션은 없습니다).

```sh
# .env 에 수신처를 적는다: OTEL_EXPORTER_OTLP_ENDPOINT=https://us.cloud.langfuse.com/api/public/otel  (EU 는 https://cloud.langfuse.com/..., 셀프호스팅은 https://<host>/api/public/otel)
LANGFUSE_PUBLIC_KEY=$(gopass show -o nas/langfuse-public) LANGFUSE_SECRET_KEY=$(gopass show -o nas/langfuse-secret) scripts/make-secrets.sh ./secrets   # otlp_headers 에 Basic 헤더(D10). 이미 채워져 있으면 그대로
# 배포 뒤 deploy.sh 가 'tracing: on -> <수신처>' 또는 'tracing: off (OTEL_EXPORTER_OTLP_ENDPOINT 비어 있음)' 를 찍는다 — 끈 것과 못 보낸 것을 가른다
```

`.env`에서 `ENDPOINT`를 비우면(또는 적지 않으면) 스팬은 no-op이고 아무 데도 가지 않습니다(`secrets/otlp_headers`가 비어 있어도 됩니다). 셀프호스팅으로 옮기는 것은 수신처와 헤더 파일만 바꾸는 일이고 과거 trace 는 옮겨지지 않습니다(Langfuse 는 export API 만). 평가 결과는 다른 경로입니다. `harbor run`의 플러그인이 러너 환경의 `LANGFUSE_PUBLIC_KEY`·`LANGFUSE_SECRET_KEY`·`LANGFUSE_HOST`로 Langfuse에 직접 씁니다. 같은 Langfuse 프로젝트의 키 한 쌍이면 둘 다 됩니다.

**팀원 온보딩.** LDAP 계정을 읽기 그룹(`HC__READER_GROUP`, 기본 `harness-readers`)에 넣고, 카탈로그 저장소 read를 줍니다. 두 명단은 같아야 합니다. 그다음 [using.md](../using/index.md)를 건넵니다.
