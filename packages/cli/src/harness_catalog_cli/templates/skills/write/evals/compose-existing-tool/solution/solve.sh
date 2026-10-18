#!/bin/sh
# Oracle 참조 해답: 있는 도구를 이름으로 엮은 스킬을 손으로 만든다(scaffold에 기대지 않는다 — Oracle은 --skill을 받지 않는다).
set -eu
cd /work/catalog
git checkout -q -b skill/release-notes
d=skills/release-notes
mkdir -p "$d/evals/draft-from-tags/tests" "$d/evals/no-trigger-single-commit/tests"
cat > "$d/SKILL.md" <<'EOF'
---
name: release-notes
description: 직전 태그부터 지금까지의 커밋을 종류별로 묶어 CHANGELOG 초안을 쓴다. "릴리스 노트 뽑아줘", "변경 내역 정리해줘".
---

# release-notes

## 언제 쓰는가

- 쓴다: "릴리스 노트 뽑아줘", "변경 내역 정리해줘".
- 쓰지 않는다: 커밋 메시지 한 줄 수정.

## 단계

1. 직전 태그와 현재 태그를 정한다.
2. 도구 `changelog-diff`를 `{"from": …, "to": …}`로 부른다 — Group the commits between two git refs by kind. 결과: `groups`
3. 묶음마다 사용자에게 보일 항목을 고른다. 사람 승인 전까지는 되돌릴 수 있는 일만 한다.

## 실패 대응

| 상황 | 대응 |
|---|---|
| 태그가 둘 미만 | 멈추고 범위를 묻는다 |
EOF
for c in draft-from-tags no-trigger-single-commit; do
  printf 'schema_version = "1.4"\n\n[metadata]\ndescription = "%s"\n\n[environment]\nbuild_timeout_sec = 600.0\nskills_dir = "/skills"\n\n[agent]\ntimeout_sec = 600.0\n\n[verifier]\ntimeout_sec = 120.0\n' "$c" > "$d/evals/$c/task.toml"
  printf 'TODO\n' > "$d/evals/$c/instruction.md"
  printf '#!/bin/sh\nset -eu\nmkdir -p /logs/verifier\necho 0 > /logs/verifier/reward.txt\n' > "$d/evals/$c/tests/test.sh"
done
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "skill: release-notes — changelog-diff를 엮는다"
