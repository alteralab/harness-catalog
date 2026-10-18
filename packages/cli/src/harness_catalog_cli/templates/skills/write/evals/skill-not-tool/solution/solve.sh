#!/bin/sh
# Oracle 참조 해답: 스킬 하나(절차 있음)와 evals 쌍을 브랜치에. 도구는 만들지 않는다.
set -eu
cd /work/catalog
git checkout -q -b skill/yt-summary
d=skills/yt-summary
mkdir -p "$d/evals/summarize-video/tests" "$d/evals/no-trigger-subs-only/tests"
cat > "$d/SKILL.md" <<'EOF'
---
name: yt-summary
description: 유튜브 영상을 자막으로 요약해 노트에 붙인다. "영상 요약해줘", "이 유튜브 정리해서 노트에 넣어줘".
---

# yt-summary

## 언제 쓰는가

- 쓴다: "영상 요약해줘", "이 유튜브 정리해서 노트에 넣어줘".
- 쓰지 않는다: 자막만 뽑는 것(yt-subs).

## 단계

1. 자막을 뽑는다 — yt-subs 스킬의 절차대로.
2. 자막을 읽고 핵심을 다섯 줄로 요약한다.
3. 요약을 노트 맨 아래에 붙인다. 사람 승인 전까지는 되돌릴 수 있는 일만 한다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 자막이 없다 | 멈추고 알린다 |
EOF
for c in summarize-video no-trigger-subs-only; do
  printf 'schema_version = "1.4"\n\n[metadata]\ndescription = "%s"\n\n[environment]\nbuild_timeout_sec = 600.0\nskills_dir = "/skills"\n\n[agent]\ntimeout_sec = 600.0\n\n[verifier]\ntimeout_sec = 120.0\n' "$c" > "$d/evals/$c/task.toml"
  printf 'TODO 과제 한 줄\n' > "$d/evals/$c/instruction.md"
  printf '#!/bin/sh\nset -eu\nmkdir -p /logs/verifier\necho 0 > /logs/verifier/reward.txt\n' > "$d/evals/$c/tests/test.sh"
done
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "skill: yt-summary"
