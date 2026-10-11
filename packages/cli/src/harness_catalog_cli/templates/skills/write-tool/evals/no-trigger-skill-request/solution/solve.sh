#!/bin/sh
# Oracle: 음성 케이스 — 절차는 스킬이다. skills/<name>/SKILL.md를 브랜치에 만들고 tools/는 만들지 않는다.
set -eu
cd /work/catalog
git checkout -q -b skill/yt-summary
mkdir -p skills/yt-summary
printf -- '---\nname: yt-summary\ndescription: 유튜브 영상을 자막으로 요약해 노트에 붙인다. "영상 요약해줘".\n---\n# yt-summary\n' > skills/yt-summary/SKILL.md
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "skill: yt-summary 뼈대"
