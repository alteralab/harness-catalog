#!/bin/sh
# Oracle: write-tool 단계 3~4의 끝 상태 — 브랜치 tool/subs-fetch에 tool.json과 runtime.path의 스크립트. main은 건드리지 않는다.
# 참조 해답이라 스킬의 scaffold_tool.py를 부르지 않는다(Oracle 에이전트는 잡 스킬(--skill)을 받지 않는다). 스크립트 자체는 코드 저장소의 pytest가 검사한다.
set -eu
cd /work/catalog
git checkout -q -b tool/subs-fetch
d=tools/subs-fetch
mkdir -p "$d/scripts"
cat > "$d/tool.json" <<'EOF'
{
  "$schema": "../../schemas/tool.schema.json",
  "name": "subs-fetch",
  "description": "Fetch YouTube subtitles as text for a video URL. 유튜브 자막 텍스트. Not for other sites.",
  "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "description": "YouTube video URL"}}, "required": ["url"], "additionalProperties": false},
  "runtime": {"kind": "script", "path": "scripts/fetch.py", "command": ["uv", "run", "--script", "scripts/fetch.py"]},
  "metadata": {"requires-tools": "uv yt-dlp"}
}
EOF
printf '# /// script\n# requires-python = ">=3.12"\n# dependencies = []\n# ///\nimport json, sys\nargs = json.load(sys.stdin)\nprint(args["url"])\n' > "$d/scripts/fetch.py"
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "tool: subs-fetch"
