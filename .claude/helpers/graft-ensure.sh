#!/bin/sh
# SessionStart: 그래프가 없으면 만든다(구조 계층, 약 1초). node_modules가 없으면 빌드 대신 안내 한 줄을 세션에 넣는다.
# graft init이 쓴 훅(graft-hooks.cjs)은 그래프가 없어도 만들지 않는다(2026-10-10 실측) — 협업에서 `make graft`를 잊은 사람을 위한 보강.
set -eu
root="${CLAUDE_PROJECT_DIR:-.}"
cd "$root"
if [ -f graft/.graph/wiring.json ]; then
  exit 0
fi
if [ -x node_modules/.bin/graft ]; then
  node_modules/.bin/graft build >/dev/null 2>&1 || true
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[graft] graft/ was missing — built it now (structural layer, pinned version from package.json)."}}\n'
else
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[graft] graft/ is missing and node_modules/ is not installed — run make graft once (npm ci + graft build) to get code-graph context in this repo."}}\n'
fi
