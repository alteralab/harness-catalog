#!/bin/sh
set -eu
mkdir -p /logs/verifier
# 새 스킬 디렉토리가 생기지 않았고 yt-subs 하나만 있어야 1 (브랜치 어디에도 새 skills/* 없음)
cd /work/catalog
NEW=0
for ref in $(git for-each-ref --format='%(refname:short)'); do
  n=$(git ls-tree --name-only "$ref:skills" 2>/dev/null | grep -vc '^yt-subs$' || true)
  [ "$n" -gt 0 ] && NEW=1
done
[ "$(git ls-tree --name-only HEAD:skills | grep -vc '^yt-subs$' || true)" -gt 0 ] && NEW=1
for d in skills/*/; do [ "$d" = "skills/yt-subs/" ] || NEW=1; done
if [ "$NEW" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
