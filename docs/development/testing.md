---
title: 시험과 게이트 돌리기
description: 시험·타입 검사·게이트 넷, 검색 벤치마크.
audience: 개발자
---

# 시험과 게이트 돌리기

고친 것을 시험·타입 검사·게이트로 거르는 쪽입니다. 먼저 [개발 환경](index.md)을 갖춥니다.

```sh
uv run pytest -q tests                      # 65
uv run pyright packages tests tools         # strict, 0
pre-commit install && pre-commit run --all-files
```

`pg` 표시 시험은 docker(testcontainers PostgreSQL)가 필요합니다. macOS Docker Desktop은 `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`이 필요하고 시험이 setdefault로 넣습니다. `http` 표시 시험은 실제 uvicorn 프로세스와 가짜 issuer(JWKS, `tests/http/fake_issuer.py`)로 돌며 Dex가 필요 없습니다. 실제 Dex·LDAP까지의 끝에서 끝은 빠른 시작 스택에서 손으로 확인합니다.

커밋 훅은 altera-rules 게이트 넷(ruff·ast-grep·shellcheck·표면 선언 드리프트)을 돌립니다. 선언은 `altera-rules.yml`, 리뷰 루브릭은 `REVIEW.md`입니다. CI(`.github/workflows/ci.yml`)는 ubuntu에서 게이트(비공개 altera-rules를 읽을 `ALTERALAB_READ_TOKEN`이 있을 때만)·pyright·pytest를 돌리고, `main` 병합이면 self-hosted 러너(mini)가 이미지를 빌드해 저장소 변수 `IMAGE_REGISTRY`·`IMAGE_REPOSITORY`가 가리키는 레지스트리로 올립니다(우리 값은 NAS Harbor. 변수가 없으면 그 잡이 명확히 실패합니다 — `gh variable list`로 봅니다).

## 검색 벤치마크

`bench/search/`(로컬 전용, .gitignore)는 합성 말뭉치로 `search_skills`·`search_tools` 의 recall@k·MRR·지연을 잰다. 의존성은 `uv sync --group bench`(sentence-transformers·rank_bm25·kiwipiepy). 검색을 바꾸는 PR 의 게이트는 서버 모듈을 그대로 꽂는 다음 명령이고, 그 표를 `plans/search.md` §2 에 적는다(DESIGN §11 2026-10-19; 기대 app-hybrid R@3 ≈ 0.98, app-bm25 ≈ 0.94):

```sh
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock uv run --group bench python -m bench.search --n 720 --app --expanded --good-only --alphas 0.85
```

모델·리랭커·토크나이저 변형은 `--models`·`--rerank`·`--jev`·`--kiwi`·`--late`·`--ollama`. 방법과 한계는 `bench/search/README.md`.
