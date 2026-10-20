---
title: 카탈로그 저장소 세우기
description: 빈 저장소 초기화, deploy key, CI 러너.
audience: 운영자
---

# 카탈로그 저장소 세우기

레지스트리가 읽을 카탈로그 저장소를 만드는 쪽입니다. 전제 조건은 [레지스트리 운영](index.md)에 있습니다.

1. git 호스트에 빈 저장소를 만듭니다. 이름은 자유이고 비공개가 좋습니다.
2. CLI로 초기화합니다. 운영자의 git 자격으로 clone해 표지 파일·기본 스킬 둘(`skills/pin`·`skills/write`)과 기본 도구 하나(`tools/scaffold`)·README·pre-commit 설정·호스트별 CI 워크플로를 없는 것만 쓰고 커밋·push합니다. 두 번 돌리면 변경이 없습니다.

   ```sh
   uvx --from "harness-catalog-cli @ git+https://github.com/alteralab/harness-catalog@v0.1.0#subdirectory=packages/cli" \
     hc init https://github.com/<org>/<catalog>.git
   ```

   템플릿에는 CLI 자기 판의 태그가 박힙니다. 코드 저장소에 그 태그가 없으면 멈춥니다(`--pin`으로 다른 ref를 줄 수 있습니다).
3. 레지스트리용 **읽기 전용 deploy key**를 만들어 등록합니다. 개인 키는 [레지스트리 설치하기](install.md)의 비밀 디렉토리에 넣습니다.

   ```sh
   ssh-keygen -t ed25519 -N '' -f ~/.ssh/catalog-deploy-key
   gh repo deploy-key add ~/.ssh/catalog-deploy-key.pub --repo <org>/<catalog> --title "registry (read)"
   ```
4. 저자에게 write, 병합할 사람에게 admin을 줍니다. 저장소를 읽을 수 있는 명단과 읽기 그룹(`HC__READER_GROUP`, 기본 `harness-readers`)을 같게 유지합니다. 이것이 접근 통제의 전부입니다.
5. 코드 저장소가 비공개인 동안 카탈로그 CI가 `harness-catalog check`를 설치하려면 읽기 자격이 필요합니다. 코드 저장소에 읽기 전용 deploy key를 하나 더 등록하고 개인 키를 카탈로그 시크릿 `HARNESS_CATALOG_DEPLOY_KEY`에 넣습니다.

   ```sh
   ssh-keygen -t ed25519 -N '' -f hc-ci-deploy
   gh repo deploy-key add hc-ci-deploy.pub --repo alteralab/harness-catalog --title "catalog CI (read)"
   gh secret set HARNESS_CATALOG_DEPLOY_KEY --repo <org>/<catalog> < hc-ci-deploy
   ```

   자격 경로는 deploy key 하나입니다(PAT 경로는 2026-10-10에 뺐습니다 — 웹에서만 만들 수 있고 만료가 있어 자동화가 끊깁니다). 코드 저장소를 공개하면 이 시크릿도 필요 없습니다.
6. CI evals는 Oracle입니다(모델·자격 없이, 바뀐 스킬의 참조 해답으로 과제와 검증기를 확인). PR마다·`main` push마다 self-hosted 러너에서 돕니다. 켜고 끄는 변수는 없습니다. self-hosted 러너는 **저장소 단위로 등록**하므로 카탈로그 저장소에도 라벨 `harness-catalog`의 러너가 있어야 합니다(없으면 잡이 영원히 queued — 2026-10-18 실측). mini에는 `~/actions-runner-catalog`(`mini-catalog`)가 그것입니다. 러너 디렉토리를 복사해 만들 때 `bin`·`externals`가 원본을 가리키는 절대 심볼릭 링크라 그대로 두면 원본 러너로 동작합니다 — 복사본 안의 판으로 다시 겁니다. 그리고 러너 루트의 `.path`에 `/opt/homebrew/bin`이 있어야 잡이 docker를 찾습니다(없으면 Harbor가 "Docker is not installed" — 2026-10-18 실측). `.path`는 서비스 스크립트가 읽으므로 ssh에서 `nohup ./run.sh`로 띄울 때는 `export PATH="$(cat .path)"`를 먼저 합니다. 모델로 돌리는 측정은 저자가 자기 클론에서 합니다([evals 돌리기](../authoring/evals.md)).
