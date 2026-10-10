#!/bin/sh
set -eu
mkdir -p /logs/verifier
# PINNED 한 줄(이름 sha40 시각)과 .claude/skills 링크가 있어야 1
P=/work/.agents/skills/yt-subs/PINNED
if [ -f "$P" ] && [ "$(wc -l < "$P")" -eq 1 ] && grep -Eq '^yt-subs [0-9a-f]{40} [0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z$' "$P" \
   && [ -f /work/.agents/skills/yt-subs/SKILL.md ] && [ -L /work/.claude/skills/yt-subs ] && [ ! -d /work/.agents/skills/.yt-subs.pin-tmp ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
