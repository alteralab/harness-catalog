#!/bin/sh
# SessionStart 훅 하나. 하는 일 둘:
#  1) trail build 를 매 세션 돈다(캐시 재생 0.2초, 처음은 약 1초). 질의용 그래프(.trail/cache/.graph/wiring.json)는
#     질의 전마다 스스로 새로 만들지만 사람이 grep 하는 카드(.trail/cache/**/*.md, INDEX.md)는 build 때만 다시 써진다.
#     경로 주의: 0.21(graft) 은 지도를 graft/ 에 두었고 0.23(trail-code) 은 .trail/cache/ 에 둔다. graft/ 는 이제
#     --deep(LLM 요약 층)에서만 생기므로, 옛 경로로 존재를 검사하면 **매 세션 거짓으로 참**이 된다(2026-10-20 실측).
#     node_modules 가 없으면 빌드 대신 안내 한 줄(trail 의 session-start 는 그래프가 없을 때 만들어 주지 않는다).
#  2) 판을 package.json 에 고정한다 — 전역 설치가 아니라 저장소의 node_modules/.bin/trail 을 부른다.
#     trail 의 session-start(.trail/hook.cjs, 다음 훅)는 저장소 node_modules 와 전역 설치 중 더 새 판을 고르므로 전역에는
#     같은 판의 @trailhq/trail-code 만 두거나 아예 두지 않는다(docs/development.md).
set -eu
root="${CLAUDE_PROJECT_DIR:-.}"
cd "$root"
if [ ! -x node_modules/.bin/trail ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[trail] node_modules/ is not installed — run make trail once (npm ci + trail build) to get code-graph context in this repo."}}\n'
  exit 0
fi
note=""
if [ ! -f .trail/cache/.graph/wiring.json ]; then
  note="[trail] .trail/cache/ (the code map) was missing — built it now (pinned version from package.json). "
fi
node_modules/.bin/trail build >/dev/null 2>&1 || true   # 카드·INDEX.md 를 HEAD 와 작업 트리에 맞춘다(캐시 재생, 0.2초)
if [ -n "$note" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$note"
fi
