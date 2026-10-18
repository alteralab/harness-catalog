#!/bin/sh
set -eu
cd /work/catalog
git checkout -q -b skill/yt-summary
mkdir -p skills/yt-summary
printf -- '---\nname: yt-summary\ndescription: 유튜브 영상을 자막으로 요약해 노트에 붙인다. "영상 요약해줘".\n---\n# yt-summary\n' > skills/yt-summary/SKILL.md
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "skill: yt-summary 뼈대"
