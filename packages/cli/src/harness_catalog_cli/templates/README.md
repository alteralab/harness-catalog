# 스킬 카탈로그

이 저장소는 팀의 스킬 카탈로그입니다. `skills/<name>/`마다 agentskills.io 형식의 스킬 하나가 있고, `main`에 병합된 것이 곧 게시·인증된 판입니다.

## 사용자 안내

1. **등록 한 줄, 로그인 한 번.** 하네스(Claude Code·Codex·Cursor)의 MCP 설정에 레지스트리 URL `<REGISTRY_URL>` 한 줄을 넣습니다. 첫 호출에서 로그인 창이 열리고, 팀 LDAP 계정으로 한 번 로그인하면 됩니다.
2. **스킬 둘을 먼저 보세요.** `pin-skill`은 매일 쓰는 스킬을 내 하네스 옆에 내려받아 두는 절차이고, `write-skill`은 새 스킬의 뼈대와 팀 규약입니다. 내려받은 사본이 낡았는지는 `list_skills`의 `sha`와 사본의 `PINNED`를 견주면 압니다.
3. **검색어에 비밀을 넣지 마세요.** `search_skills`의 검색어는 팀 Langfuse의 도구 호출 기록에 남습니다. 토큰·비밀번호·개인 정보를 검색어에 적지 않습니다.

## 게시 — 브랜치·PR·병합

- `main`에 직접 push하지 않습니다. 브랜치를 따서 `skills/<name>/`을 만들거나 고치고 PR을 엽니다. 강제 push는 하지 않습니다(규율입니다 — 브랜치 보호는 걸려 있지 않습니다).
- PR마다 CI가 `harness-catalog check`를 돌립니다. 붉으면 병합하지 않습니다. 병합한 사람이 그 판의 인증자입니다.
- 커밋 전에 같은 검사를 돌리려면 `pre-commit install`을 한 번 하세요(`.pre-commit-config.yaml`이 `harness-catalog check`를 부릅니다).
- 이름은 카탈로그 전체에서 유일하고, 은퇴한 이름은 다시 쓰지 않습니다. 은퇴는 디렉토리 삭제이고, 대체 스킬이 있으면 지우기 전 판의 `metadata.replaced-by`에 적습니다.

## 운영자 체크리스트

1. git 호스트에 빈 저장소를 만들고 `harness-catalog init <repo-url>`을 돌립니다(이 파일들이 그 결과입니다). 두 번 돌려도 변경이 없습니다.
2. 읽기 전용 deploy key를 등록하고 레지스트리 `.env`에 개인 키를 넣습니다. 확인: 레지스트리 컨테이너에서 `git fetch`는 되고 `git push --dry-run`은 거부됩니다.
3. 저자에게 저장소 write, 병합·설정을 할 사람에게 admin을 줍니다. 저장소 read 이상 명단과 LDAP 그룹 `skills-readers`를 같게 유지합니다.
4. Dex에 하네스 제품의 정적 클라이언트가 있는지, 첫 팀원이 `skills-readers`에 있는지 확인합니다(로그인 한 번으로 확인).
5. 레지스트리를 띄우고 `/readyz`가 200인지 봅니다. 503이면 본문의 사유(`not_a_catalog`·`no_main_branch`·`repo_unreachable`·`layout_mismatch`)대로 1·2를 다시 봅니다.
6. CI evals(선택): git 호스트 변수 `HARNESS_EVALS=true`와 러너 `.env`의 자격으로 켜고, `false`로 끕니다. 하네스 목록은 `HARNESS_EVALS_AGENTS`(기본 `claude-code codex`).

GitLab용 워크플로(`.gitlab-ci.yml`)는 문면대로 작성만 되어 있고 아직 실제로 돌린 적이 없습니다. GitHub Actions가 먼저입니다.
