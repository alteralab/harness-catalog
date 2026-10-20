---
title: 개발
description: 저장소 배치, 개발 환경, 설계 문서와 원장.
audience: 개발자
---

# 개발

이 코드 저장소를 고치는 사람을 위한 안내입니다.

## 배치

uv 워크스페이스에 배포물 넷이 있습니다. 의존 방향은 `cli → core`, `server → core`이고 `cli`와 `server`는 서로 import하지 못합니다.

| 패키지 | 배포물 | 내용 |
|---|---|---|
| `packages/core` | `harness-catalog-core` | 모델, 카탈로그 앱(`Catalog`), 검사 항목(`check.py`), 인가(`authz.py`), git·skills-ref 어댑터, 설정(`settings.py`) |
| `packages/server` | `harness-catalog-server` | MCP 서버(Streamable HTTP), OIDC 검증, PostgreSQL 어댑터와 브레이커, 스케줄러, 마이그레이션, `/healthz`·`/readyz` |
| `packages/cli` | `harness-catalog-cli` | `check`·`init`·`config`, 카탈로그 저장소 템플릿(`templates/`) |
| `packages/harbor-langfuse` | `harbor-langfuse` | Harbor 플러그인: 잡 결과를 Langfuse 데이터셋 실험으로 |

앱 층(`core`)은 git·PostgreSQL·OIDC를 모릅니다. 포트는 ContentStore·SkillValidator·FactStore 셋이고 어댑터가 꽂힙니다. 시험은 가짜 어댑터로 앱을 직접 부릅니다.

## 환경

자주 치는 명령은 `make help`에 이름이 있습니다(`make quickstart`·`dev-up`·`serve`·`test`·`typecheck`·`gates`·`check`·`image`). 아래는 그 풀이입니다.

```sh
uv sync -p 3.12
cp docker/.env.example docker/.env                                  # 비밀은 openssl rand -base64 32
docker compose -f docker/compose.dev.yml up -d        # postgres + dex (호스트 127.0.0.1 바인딩)
set -a; . ./.env; set +a
uv run harness-catalog-server serve --port 8000
```

개발 compose는 postgres와 dex만 띄우고 레지스트리는 호스트에서 돌립니다. 카탈로그는 `HC__CATALOG_REPO_URL=file:///…`로 로컬 저장소를 가리켜도 되고 그때 `HC__GIT_DEPLOY_KEY`는 빈 문자열입니다. Dex 설정은 gomplate `{{ getenv }}`로 환경 변수를 읽습니다(Dex 자체의 `$VAR` 확장은 저장소·커넥터 설정에서만 됩니다).

기계 계정 토큰은 `scripts/dev-token.sh`, 사람 토큰(PKCE·장치 흐름)과 Dex 그랜트 실측은 `tools/pilot/dex_grants.py`, 하네스 첫 접촉 캡처는 `tools/pilot/capture_stub.py`입니다.

## 과제별 쪽

| 쪽 | 무엇을 끝내나 |
|---|---|
| [시험과 게이트 돌리기](testing.md) | 시험·타입 검사·커밋 훅 게이트를 돌리고, 검색을 바꿀 때 벤치마크를 잰다 |
| [판 내고 배포하기](release.md) | 판을 올려 태그를 내고 운영 호스트에 배포한다 |
| [Trail 과 OpenWiki](tooling.md) | 코드 지도와 위키를 세워 두고 세션에서 쓴다 |
| [문서 사이트 짓기](docs-site.md) | `docs/`를 사이트로 미리보고, 짓고, 점검한다 |

## 설계 문서와 원장

설계 계약을 바꾸는 변경은 코드보다 DESIGN.md §11의 결정 행이 먼저입니다. 실행 계획은 PLAN.md(우산)와 `plans/{service,distribution,pilot,skills}.md`이고, 각 문서의 원장 절에 날짜·내용·근거를 남깁니다. 측정 결과(Dex 그랜트, LDAP, 하네스 첫 접촉)는 `plans/pilot/r1~r3.md`에 있습니다. 구현 단계마다 Codex 적대 리뷰를 걸어 반영했고 그 기록도 원장에 있습니다.
