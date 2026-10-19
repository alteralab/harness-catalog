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

## 시험과 게이트

```sh
uv run pytest -q tests                      # 65
uv run pyright packages tests tools         # strict, 0
pre-commit install && pre-commit run --all-files
```

`pg` 표시 시험은 docker(testcontainers PostgreSQL)가 필요합니다. macOS Docker Desktop은 `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`이 필요하고 시험이 setdefault로 넣습니다. `http` 표시 시험은 실제 uvicorn 프로세스와 가짜 issuer(JWKS, `tests/http/fake_issuer.py`)로 돌며 Dex가 필요 없습니다. 실제 Dex·LDAP까지의 끝에서 끝은 빠른 시작 스택에서 손으로 확인합니다.

커밋 훅은 altera-rules 게이트 넷(ruff·ast-grep·shellcheck·표면 선언 드리프트)을 돌립니다. 선언은 `altera-rules.yml`, 리뷰 루브릭은 `REVIEW.md`입니다. CI(`.github/workflows/ci.yml`)는 ubuntu에서 게이트(비공개 altera-rules를 읽을 `ALTERALAB_READ_TOKEN`이 있을 때만)·pyright·pytest를 돌리고, `main` 병합이면 self-hosted 러너(mini)가 이미지를 빌드해 저장소 변수 `IMAGE_REGISTRY`·`IMAGE_REPOSITORY`가 가리키는 레지스트리로 올립니다(우리 값은 NAS Harbor. 변수가 없으면 그 잡이 명확히 실패합니다 — `gh variable list`로 봅니다).

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

## Trail — 코드 지도와 세션 학습

이 저장소는 [Trail Code](https://github.com/trailhq/Trail-Code)(npm `@trailhq/trail-code`, 2026-10 에 `@nanonets/graft`에서 이름이 바뀜 — `graft` 명령도 그대로 돈다)를 Claude Code에 연결해 둡니다. tree-sitter로 심볼·호출 그래프(코드 지도, `graft/`)를 만들어 세션 시작에 저장소 지도를, 프롬프트마다 관련 심볼을 넣고, 편집 뒤 영향 범위를 알리며, 질의 때마다 그래프를 작업 트리에 맞춥니다. 여기에 `.trail/learnings/`(세션이 알아낸 것을 짧은 마크다운으로 — `trail note`, 커밋 대상)가 더해졌습니다. **구조 계층만** 씁니다. 모델 호출이 없고 키가 필요 없습니다. "왜 이렇게 만들었나"는 DESIGN.md와 원장이 답하고, Trail은 "어디 있고 누가 부르나"와 "지난 세션이 무엇을 알아냈나"를 답합니다.

판은 `package.json`에 정확히 고정됩니다(`"@trailhq/trail-code": "0.23.0"`, lockfile 포함). 저장소의 `node_modules`가 기준이고, `.mcp.json`의 MCP 서버(도구 이름 `trail_*`)도 `npx -y @trailhq/trail-code@0.23.0 mcp`로 같은 판을 가리킵니다. 올리는 것은 `package.json`의 판을 바꾸고 `npm install`로 lockfile을 갱신한 뒤 `make mcp-pin`을 돌리는 명시 행위입니다.

```sh
make trail            # npm ci + trail build — 처음 clone한 뒤 한 번(지도는 graft/ 에, git 무시)
make trail-init       # Trail 의 배선(.trail/hook.cjs, settings.json 의 session-start)을 다시 쓸 때. 뒤에 git diff 로 확인
npx trail ask "where is the token audience verified"   # CLI로 바로 물을 때
npx trail build --check                                # 지도가 코드와 어긋났는지(훅이 자동으로 맞추므로 보통 OK)
npx trail note                                         # 이번 세션이 알아낸 것을 .trail/learnings/ 에 남길 때
```

커밋되는 것은 배선과 학습뿐입니다: `.claude/settings.json`(훅 전부 — 저장소 수준에 둡니다, 아래)·`.claude/helpers/trail-ensure.sh`·`.claude/skills/trail/SKILL.md`·`.trail/{hook.cjs,README.md,.gitignore,learnings/}`·`.mcp.json`·`.ignore`·`package.json`·`package-lock.json`. `graft/`(지도 캐시)·`.trail/cache/`·`node_modules/`는 git에도 Docker 빌드 컨텍스트에도 들어가지 않습니다. 레지스트리 이미지는 python 기반이라 node 자체가 없습니다.

Trail 0.23 의 `trail init`은 session-start 훅만 저장소에 두고 나머지 훅·skill 은 `~/.claude`(사용자 전역)에 씁니다. 이 저장소는 그 반대로 **전역에 아무것도 쓰지 않고** 훅 전부와 skill 을 저장소에 커밋합니다 — 팀원이 clone 만 하면 같은 배선을 얻고, 각자의 `~/.claude`는 건드리지 않습니다. 모든 훅은 `.trail/hook.cjs`(저장소 `node_modules`와 전역 설치 중 더 새 판을 고르는 shim)를 거칩니다. 그래서 전역에는 같은 판의 `@trailhq/trail-code`를 두거나 아예 두지 않습니다 — 전역에 옛 `@nanonets/graft`만 있으면 trail 의 session-start 가 `~/.claude.json`의 이 폴더 항목에 `graft mcp`(판 없음)를 써 넣어 고정된 `.mcp.json`을 가립니다(실측 2026-10-20). 그래프가 없을 때 trail 의 훅이 만들어 주지 않으므로 `.claude/helpers/trail-ensure.sh`가 SessionStart 첫 자리에서 매 세션 `trail build`를 돌리고(캐시 재생 0.2초), `node_modules/`가 없으면 `make trail`을 돌리라는 한 줄을 세션에 넣습니다. 텔레메트리는 `DO_NOT_TRACK=1`.

## OpenWiki — 설계 이유를 읽는 위키

Trail과 짝으로 [OpenWiki](https://github.com/langchain-ai/openwiki)를 씁니다. Trail은 찾는 색인, OpenWiki는 읽는 문서입니다. 위키는 `openwiki/` 아래 영어 마크다운이고 **커밋됩니다**. 각 문장(claim)은 `file:line` 증거를 들고, update가 그 증거의 지문을 검사해 낡은 claim만 다시 씁니다. 판은 `package.json`에 `openwiki@0.6.1`로 고정되고 `.mcp.json`도 같은 판을 가리킵니다(최신 0.7.2는 node ≥ 22.22가 필요해 보류).

- **읽기**는 당기기(pull)입니다. 에이전트가 필요할 때 `openwiki_search` → `openwiki_read`를 부릅니다. CLAUDE.md의 두 줄이 역할을 가릅니다. 위치·시그니처는 Trail이나 소스, 이유·흐름은 OpenWiki.
- **갱신**은 CI가 하루 한 번(04:00 KST) 합니다. `.github/workflows/openwiki-update.yml`이 `openwiki code --update`를 돌려 `openwiki/update` 브랜치로 PR을 올리고, 그 PR을 병합해야 다음 실행의 기준(`.last-update.json`)이 됩니다. 기준 커밋 이후 소스 변경이 없는 날은 모델을 부르지 않고 몇 초에 끝납니다(실측 7초). 병합마다 돌리지 않는 이유는 run당 고정 비용(계획·마무리)과 취소 낭비, PR 수 때문이고, 신선도는 SessionStart 훅과 "그 사이 바뀐 파일은 소스를 본다"는 규약이 맡습니다. 공급자는 Anthropic(`ANTHROPIC_API_KEY` 시크릿), 모델은 저장소 변수 `OPENWIKI_MODEL_ID`(기본 `claude-opus-5`). 당장 맞추고 싶으면 `gh workflow run "OpenWiki Update"`(변경이 없어도 돌리려면 `-f force=true`). AGENTS.md와 CLAUDE.md의 `OPENWIKI` 블록은 OpenWiki가 매 실행마다 다시 쓰는 생성물이라 손으로 고쳐도 되돌아가며, 변경 검사에서도 제외됩니다. MR 안에서 손으로 돌리지 않습니다(사이드카와 기준 커밋이 갈립니다). CI가 막혔을 때만 깨끗한 `main`에서 Claude Code로 "Update this repository's OpenWiki for changes since its last successful run".
- **신선도 신호**는 OpenWiki가 주지 않으므로 `.claude/helpers/openwiki-age.sh`(SessionStart)가 기준 커밋 대비 커밋 수를 한 줄 찍습니다.
- MR을 올리기 전 `make wiki-claims`로 바꾼 파일을 인용하는 페이지를 봅니다(모델 없음, 몇 초).

```sh
make wiki-install     # 배선(.claude/skills/openwiki, .mcp.json)을 다시 쓸 때
make wiki-claims      # 바꾼 파일을 인용하는 claim 페이지
```

## 설계 문서와 원장

설계 계약을 바꾸는 변경은 코드보다 DESIGN.md §11의 결정 행이 먼저입니다. 실행 계획은 PLAN.md(우산)와 `plans/{service,distribution,pilot,skills}.md`이고, 각 문서의 원장 절에 날짜·내용·근거를 남깁니다. 측정 결과(Dex 그랜트, LDAP, 하네스 첫 접촉)는 `plans/pilot/r1~r3.md`에 있습니다. 구현 단계마다 Codex 적대 리뷰를 걸어 반영했고 그 기록도 원장에 있습니다.

## 검색 벤치마크

`bench/search/`(로컬 전용, .gitignore)는 합성 말뭉치로 `search_skills`·`search_tools` 의 recall@k·MRR·지연을 잰다. 의존성은 `uv sync --group bench`(sentence-transformers·rank_bm25·kiwipiepy). 검색을 바꾸는 PR 의 게이트는 서버 모듈을 그대로 꽂는 다음 명령이고, 그 표를 `plans/search.md` §2 에 적는다(DESIGN §11 2026-10-19; 기대 app-hybrid R@3 ≈ 0.98, app-bm25 ≈ 0.94):

```sh
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock uv run --group bench python -m bench.search --n 720 --app --expanded --good-only --alphas 0.85
```

모델·리랭커·토크나이저 변형은 `--models`·`--rerank`·`--jev`·`--kiwi`·`--late`·`--ollama`. 방법과 한계는 `bench/search/README.md`.
