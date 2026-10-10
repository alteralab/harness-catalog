#!/bin/sh
# SessionStart(이 훅 하나가 graft의 session-start를 감싼다). 하는 일 셋:
#  1) graft/ 가 없으면 만든다(구조 계층, 약 1초). node_modules가 없으면 빌드 대신 안내 한 줄.
#  2) 배선 스탬프(graft/.cache/wiring-stamp.json)를 우리 의도로 보장한다 — global:false(~/.claude·~/.claude.json에 쓰지 않음),
#     mcp:false(.mcp.json은 우리가 판을 고정해 관리), statusline:false, 판은 package.json. 스탬프가 없거나 다르면 graft의
#     session-start가 기본값(global:true)으로 배선을 다시 써서 모든 팀원의 ~/.claude에 훅·MCP를 심는다.
#     스탬프는 git 무시 캐시라 새로 clone하면 없다 — 그래서 매 세션 여기서 쓴다.
#  3) 그 뒤 graft의 session-start(레포 지도·지시문)를 그대로 돌려 출력을 넘긴다.
set -eu
root="${CLAUDE_PROJECT_DIR:-.}"
cd "$root"
note=""
if [ ! -x node_modules/.bin/graft ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[graft] node_modules/ is not installed — run make graft once (npm ci + graft build) to get code-graph context in this repo."}}\n'
  exit 0
fi
if [ ! -f graft/.graph/wiring.json ]; then
  node_modules/.bin/graft build >/dev/null 2>&1 || true
  note="[graft] graft/ was missing — built it now (structural layer, pinned version from package.json). "
fi
version=$(node -p "require('./package.json').devDependencies['@nanonets/graft']")
mkdir -p graft/.cache
printf '{"version":"%s","hosts":["claude"],"opts":{"global":false,"mcp":false,"hooks":true,"statusline":false},"at":"%s"}\n' \
  "$version" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > graft/.cache/wiring-stamp.json
NOTE="$note" node -e '
  const { execFileSync } = require("child_process");
  let out = "";
  try { out = execFileSync(process.execPath, [".claude/helpers/graft-hooks.cjs", "session-start"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 8000 }); } catch {}
  let obj = null; try { obj = JSON.parse(out); } catch {}
  const note = process.env.NOTE || "";
  if (obj && obj.hookSpecificOutput) { obj.hookSpecificOutput.additionalContext = note + (obj.hookSpecificOutput.additionalContext || ""); process.stdout.write(JSON.stringify(obj) + "\n"); }
  else if (note) { process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: note } }) + "\n"); }
'
