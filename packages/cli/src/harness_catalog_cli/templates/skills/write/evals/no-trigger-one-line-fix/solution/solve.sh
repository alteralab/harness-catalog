#!/bin/sh
# Oracle: 음성 케이스 — 기존 스킬의 한 줄 수정은 갱신 경로다(브랜치 → 수정 → 커밋). 새 skills/* 디렉토리를 만들지 않는다.
set -eu
cd /work/catalog
git checkout -q -b fix/yt-subs-wording
sed -i 's/뽑아줘/추출해줘/' skills/yt-subs/SKILL.md
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "yt-subs: 발동 문구 '뽑아줘' → '추출해줘'"
