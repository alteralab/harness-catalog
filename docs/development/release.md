---
title: 판 내고 배포하기
description: 의존성과 판, lockstep 태그, 운영 호스트 배포.
audience: 개발자
---

# 판 내고 배포하기

새 판을 내고 운영 호스트에 올리는 쪽입니다. 태그 전에 [시험과 게이트](testing.md)가 통과해 있어야 합니다.

## 의존성과 판

### 판 내기와 배포 — 스크립트 하나씩

```sh
make release VERSION=0.3.2          # 판 넷+내부 핀 → uv lock → pip 경로 설치 실측 → make check → 커밋·태그·원자 push
make deploy HOST=mini TAG=<짧은 SHA>   # 운영 호스트에서 pull → REGISTRY_IMAGE 교체 → registry up -d → readyz 대기 → 마이그레이션 출력
```

손으로 하지 않습니다. 태그 전에 워크스페이스 밖의 새 venv에 네 패키지를 **pip**로 설치해 보는 단계가 핵심입니다(uv pip는 로컬 디렉토리를 핀보다 우선해 이 어긋남을 잡지 못합니다 — 실측) — 카탈로그 저장소의 pre-commit·CI는 uv 워크스페이스가 아니라 태그에서 pip로 설치하므로, 내부 핀(`harness-catalog-core==<판>`)이 어긋나면 그 길에서만 깨집니다(v0.3.0 실측). `--dry-run`은 파일을 고치고 설치 실측까지만 합니다. 배포 스크립트의 기본값(저장소 경로·docker 경로·LDAP 오버레이·이미지 주소)은 우리 운영 호스트 값이고 인자 또는 환경 변수(`DEPLOY_REPO_PATH`·`DEPLOY_OVERLAY`·`IMAGE_REGISTRY`·`IMAGE_REPOSITORY`)로 바꿉니다(plans/distribution.md D25, §11 2026-10-20).

의존성은 `pyproject.toml` 다섯과 PEP 723 스크립트 머리 모두 `==`로 고정합니다. 올리는 것은 값을 바꾸고 `uv lock`을 돌리는 명시 행위입니다.

새 판을 내는 절차는 다음과 같습니다.

1. 네 `pyproject.toml`의 `version`을 같은 값으로 올립니다(lockstep).
2. `uv lock`, 시험·게이트 통과, 커밋.
3. 태그 `vX.Y.Z`를 push합니다. 이어서 `core`·`cli` 휠을 NAS Nexus `pypi-internal`에 올립니다(`UV_PUBLISH_USERNAME`·`UV_PUBLISH_PASSWORD` — gopass `nas/nexus-publish`; 없으면 건너뛰고 `release.py --publish-only <판>`으로 나중에). 받는 쪽은 인덱스 `https://ds923plus.tail2f9fe3.ts.net:8443/repository/pypi-public/simple/`(tailnet)로 `uvx --default-index … --from harness-catalog-cli==<판> hc …`. 카탈로그 저장소의 훅과 CI가 이 태그로 `core`·`cli`를 설치하고, `init`은 자기 판의 태그를 템플릿에 박습니다. CI가 이미지를 `$IMAGE_REGISTRY/$IMAGE_REPOSITORY:<태그>`로도 올립니다(저장소 변수 둘. 판 태그는 보존 정리에서 제외).
4. `main` 병합마다는 짧은 SHA 태그로 빌드됩니다. 운영 호스트에서는 `REGISTRY_IMAGE`에 판 태그를 적어 올립니다.

템플릿(`packages/cli/.../templates/`)을 바꾸면 이미 만들어진 카탈로그 저장소에는 반영되지 않습니다. `init`은 없는 파일만 쓰기 때문입니다. 그 저장소의 워크플로 파일은 손으로 갱신합니다.

**코드 저장소 주소.** `hc init`이 템플릿에 박는 핀 URL과 도구 스키마의 `$id`는 `packages/core/pyproject.toml`의 `[project.urls] Repository` 한 줄에서 옵니다(`harness_catalog_core.distribution.code_repo_url()`이 설치된 배포물의 메타데이터를 읽습니다). 정본은 그 한 줄뿐이고 `cli`·`server`의 `pyproject.toml`에는 적지 않습니다 — 적으면 정본이 둘이 됩니다. **이 저장소를 포크하면 그 한 줄을 자기 주소로 고칩니다**(자동이 아닙니다 — 고치지 않으면 상류 주소가 템플릿과 `$id`에 그대로 남습니다). 메타데이터를 읽을 수 없으면 조용히 기본값으로 떨어지지 않고 `DistributionMetadataError`로 멈춥니다.
