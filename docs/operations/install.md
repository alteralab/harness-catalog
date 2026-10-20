---
title: 레지스트리 설치하기
description: .env 와 비밀 파일, compose 기동, /readyz 확인.
audience: 운영자
---

# 레지스트리 설치하기

레지스트리를 호스트에 띄우는 쪽입니다. [카탈로그 저장소 세우기](catalog-repo.md)가 끝나 있어야 합니다.

1. 코드 저장소를 받고 `.env`를 만듭니다.

   ```sh
   git clone https://github.com/alteralab/harness-catalog && cd harness-catalog
   cp docker/.env.example docker/.env && chmod 600 docker/.env
   ```

   채울 것: `REGISTRY_IMAGE`(NAS Harbor 태그 또는 로컬 태그), `HC__CATALOG_REPO_URL`(deploy key로 받을 ssh URL), `HC__OIDC_ISSUER`(`https://<호스트>/dex`), `HC__PUBLIC_URL`(`https://<호스트>/mcp`). Dex의 issuer와 audience 클라이언트 ID는 compose가 이 두 값에서 그대로 건네므로 따로 적을 것이 없습니다. 끝에 `/`를 붙이면 레지스트리가 기동을 거부합니다. 설정값의 뜻은 [configuration.md](../configuration.md).
2. 비밀 파일을 만듭니다. DB 비밀번호 셋과 `ci-runner` 시크릿은 무작위로 만들고, deploy key는 둘째 인자의 파일을 복사하며, DB 접속 문자열은 조립합니다. 있는 파일은 건드리지 않습니다.

   ```sh
   scripts/make-secrets.sh secrets ~/.ssh/catalog-deploy-key
   ```
3. 띄우고 확인합니다.

   ```sh
   docker compose -f docker/compose.yml up -d
   # 매번 -f를 치기 싫으면 운영 사용자의 셸에 export COMPOSE_FILE=docker/compose.yml 을 두면 아래 명령에서 -f를 뺄 수 있다
   curl -fsS http://127.0.0.1:8000/readyz
   ```

   `/healthz`는 프로세스가 살아 있는지, `/readyz`는 섬길 준비가 됐는지입니다. 준비되면 본문에 색인한 `commit`과 거부된 스킬 목록이 실립니다.
4. 이미지는 `main` 병합마다 self-hosted 러너가 빌드해 **저장소 변수** `IMAGE_REGISTRY`·`IMAGE_REPOSITORY`가 가리키는 레지스트리에 올립니다(짧은 SHA 태그와 판 태그). 둘 중 하나가 없으면 그 잡이 그 자리에서 실패합니다 — 빈 주소로 push하지 않습니다. 우리 팀 값은 NAS Harbor(`ds923plus.tail2f9fe3.ts.net:9443` · `alteralab/harness-catalog`, portainer 저장소 `stacks/harbor`)이고 보존은 그 프로젝트의 태그 보존 규칙입니다. 프로젝트가 public이라 pull에는 로그인이 필요 없고, push는 robot 계정(GitHub 시크릿 `HARBOR_ROBOT_NAME`·`HARBOR_ROBOT_SECRET`)입니다. `scripts/deploy.sh`·`scripts/release.py`도 같은 이름의 환경 변수를 읽습니다(없으면 우리 팀 값). 같은 호스트에서 `docker build -t harness-catalog:current .`로 만들어 써도 됩니다.

`HC__PUBLIC_URL`은 토큰의 audience이자 RFC 9728의 resource이고, Dex 설정의 audience 클라이언트 ID도 같은 값입니다. compose가 한 값에서 둘을 채우므로 어긋날 길이 없습니다.
