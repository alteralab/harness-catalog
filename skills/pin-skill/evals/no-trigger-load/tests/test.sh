#!/bin/sh
set -eu
mkdir -p /logs/verifier
# 내려받지 않았어야 1 (디렉토리·PINNED 없음)
if [ ! -e /work/.agents/skills/yt-subs ] && [ ! -e /work/.claude/skills/yt-subs ] && [ ! -e "$HOME/.agents/skills/yt-subs" ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
