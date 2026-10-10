#!/bin/sh
# SessionStart: OpenWiki가 주지 않는 신선도 신호를 만든다. 위키의 기준 커밋(openwiki/.last-update.json의 gitHead)과
# 현재 HEAD를 견줘 한 줄 찍는다. 위키가 없으면 조용히 끝난다. 판정 불가도 한 줄로 알린다.
set -eu
cd "${CLAUDE_PROJECT_DIR:-.}"
f=openwiki/.last-update.json
[ -f "$f" ] || exit 0
say() { printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$1"; }
last=$(sed -n 's/.*"gitHead": *"\([0-9a-f]\{7,40\}\)".*/\1/p' "$f" | head -n 1)
status=$(sed -n 's/.*"status": *"\([a-z]*\)".*/\1/p' "$f" | head -n 1)
msg=""
[ "$status" = "interrupted" ] && msg="openwiki: 마지막 update가 중단된 상태다 — update를 다시 돌릴 것. "
if [ -z "$last" ]; then say "${msg}openwiki: .last-update.json에 gitHead가 없다 — 위키 기준점을 알 수 없다."; exit 0; fi
if ! git cat-file -e "$last^{commit}" 2>/dev/null; then say "${msg}openwiki: 기준 커밋 $last 가 로컬에 없다(shallow clone 또는 history rewrite) — 위키 나이를 판정할 수 없다."; exit 0; fi
if ! git merge-base --is-ancestor "$last" HEAD; then say "${msg}openwiki: 기준 커밋 $last 가 HEAD의 조상이 아니다 — 위키가 다른 브랜치 기준이다."; exit 0; fi
n=$(git rev-list --count "$last..HEAD")
[ "$n" -gt 0 ] && msg="${msg}openwiki: 마지막 갱신 이후 커밋 ${n}개 — 위치와 시그니처는 graft나 소스로 확인할 것. "
[ -n "$(git status --porcelain)" ] && msg="${msg}openwiki: 작업 트리에 커밋되지 않은 변경이 있다 — 위키는 그것을 모른다. "
[ -n "$msg" ] && say "$msg"
exit 0
