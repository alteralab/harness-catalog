---
title: Trail 과 OpenWiki
description: Trail 코드 지도와 세션 학습, OpenWiki.
audience: 개발자
---

# Trail 과 OpenWiki

이 저장소에 붙어 있는 보조 도구 둘을 세우고 쓰는 쪽입니다. Trail은 "어디 있고 누가 부르나"를, OpenWiki는 "왜 이렇게 만들었나"를 맡습니다.

## Trail — 코드 지도와 세션 학습

이 저장소는 [Trail Code](https://github.com/trailhq/Trail-Code)(npm `@trailhq/trail-code`, 2026-10 에 `@nanonets/graft`에서 이름이 바뀜 — `graft` 명령도 그대로 돈다)를 Claude Code에 연결해 둡니다. tree-sitter로 심볼·호출 그래프(코드 지도, `.trail/cache/`)를 만들어 세션 시작에 저장소 지도를, 프롬프트마다 관련 심볼을 넣고, 편집 뒤 영향 범위를 알리며, 질의 때마다 그래프를 작업 트리에 맞춥니다. 여기에 `.trail/learnings/`(세션이 알아낸 것을 짧은 마크다운으로 — `trail note`, 커밋 대상)가 더해졌습니다. **구조 계층만** 씁니다. 모델 호출이 없고 키가 필요 없습니다. "왜 이렇게 만들었나"는 DESIGN.md와 원장이 답하고, Trail은 "어디 있고 누가 부르나"와 "지난 세션이 무엇을 알아냈나"를 답합니다.

구조 계층만 쓴다는 것은 **질의할 때 느껴집니다.** 그래프의 노드가 들고 있는 것은 이름과 시그니처뿐이고 요약 자리(`summary`·`crux`)는 비어 있습니다 — 그것을 채우는 것이 `trail build --deep`(모델 호출)이고, 그 산출물이 `graft/`입니다. 우리는 그 층을 쓰지 않으므로 `graft/`는 생기지 않습니다. 그래서 **묻는 말에 따라 도구가 갈립니다.** `trail ask`는 그 노드 색인만 보므로 영어 식별자나 영어 평문에서 맞습니다(`authorize`, `how does the registry index the catalog`). 한국어 평문(`인가`)은 0건입니다 — 이름·시그니처가 영어라서이지 고장이 아닙니다. 한국어로 찾을 때는 **`trail grep`**을 씁니다. 이쪽은 색인된 파일의 원문을 훑어 주석·독스트링까지 심볼별로 묶어 냅니다(2026-10-20 실측: `trail grep "볼록 결합"` → 5개 파일 8건, 노드 1038개는 전부 `summary_state: pending`). 한국어로 "왜 이렇게 만들었나"를 묻는 자리는 여전히 OpenWiki와 DESIGN.md입니다.

판은 `package.json`에 정확히 고정됩니다(`"@trailhq/trail-code": "0.23.0"`, lockfile 포함). 저장소의 `node_modules`가 기준이고, `.mcp.json`의 MCP 서버(도구 이름 `trail_*`)도 `npx -y @trailhq/trail-code@0.23.0 mcp`로 같은 판을 가리킵니다. 올리는 것은 `package.json`의 판을 바꾸고 `npm install`로 lockfile을 갱신한 뒤 `make mcp-pin`을 돌리는 명시 행위입니다.

```sh
make trail            # npm ci + trail build — 처음 clone한 뒤 한 번(지도는 .trail/cache/ 에, git 무시)
make trail-init       # Trail 의 배선(.trail/hook.cjs, settings.json 의 session-start)을 다시 쓸 때. 뒤에 git diff 로 확인
npx trail ask "where is the token audience verified"   # CLI로 바로 물을 때
npx trail build --check                                # 지도가 코드와 어긋났는지(훅이 자동으로 맞추므로 보통 OK)
npx trail note                                         # 이번 세션이 알아낸 것을 .trail/learnings/ 에 남길 때
```

커밋되는 것은 배선과 학습뿐입니다: `.claude/settings.json`(훅 전부 — 저장소 수준에 둡니다, 아래)·`.claude/helpers/trail-ensure.sh`·`.claude/skills/trail/SKILL.md`·`.trail/{hook.cjs,README.md,.gitignore,learnings/}`·`.mcp.json`·`.ignore`·`package.json`·`package-lock.json`. `.trail/cache/`(지도)·`node_modules/`는 git에도 Docker 빌드 컨텍스트에도 들어가지 않습니다. 레지스트리 이미지는 python 기반이라 node 자체가 없습니다.

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
