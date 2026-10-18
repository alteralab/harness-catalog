#!/bin/sh
# Oracle 참조 해답: 점검표 A1·B2·C4·D2를 고친 판을 브랜치에 둔다.
set -eu
cd /work/catalog
git checkout -q -b review/yt-subs
cat > skills/yt-subs/SKILL.md <<'EOF'
---
name: yt-subs
description: 유튜브 영상 URL에서 자막을 텍스트로 추출한다. 사용자가 "자막 뽑아줘", "유튜브 자막", "subtitles"라고 할 때 쓴다. 영상 요약이나 번역은 이 스킬이 아니다.
---

# yt-subs

## 언제 쓰는가

- 쓴다: "자막 뽑아줘", "유튜브 자막 추출해줘".
- 쓰지 않는다: 영상 요약, 자막 번역.

## 단계

1. URL을 확인한다.
2. `uv run --script scripts/subs.py <url>`을 돌린다. 세션 전용 보조 스크립트다 — 사람이 읽을 자막 파일을 찍는 것이라 결과가 JSON일 이유가 없다. 자세한 옵션은 [advanced.md](references/advanced.md).
3. 사람 승인 전까지는 되돌릴 수 있는 일만 한다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 자막이 없는 영상 | 멈추고 알린다 |
EOF
printf '# advanced\n\n## 옵션\n\n- `--lang ko`: 언어 선택.\n' > skills/yt-subs/references/advanced.md
git rm -q skills/yt-subs/references/details.md
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "yt-subs: 심사 반영 — description, 참조 한 단계, 시간 문장 제거, scripts 이유"
