#!/bin/sh
# Oracle: 검증기가 참으로 보는 끝 상태를 직접 만든다 — pin-skill 단계 11의 결과물(디렉토리·PINNED 한 줄·.claude/skills 링크).
# 실제 에이전트는 레지스트리 MCP(load_skill·get_skill_file)로 내용을 받지만, 이 환경에는 레지스트리가 없으므로 내용은 자리표시자다.
set -eu
cd /work
mkdir -p .agents/skills/yt-subs .claude/skills
printf -- '---\nname: yt-subs\ndescription: YouTube 자막을 추출한다.\n---\n# yt-subs\n' > .agents/skills/yt-subs/SKILL.md
sha=$(git hash-object .agents/skills/yt-subs/SKILL.md)   # 40자 hex. 실제로는 카탈로그의 tree SHA
printf 'yt-subs %s %s\n' "$sha" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .agents/skills/yt-subs/PINNED
ln -sfn ../../.agents/skills/yt-subs .claude/skills/yt-subs
