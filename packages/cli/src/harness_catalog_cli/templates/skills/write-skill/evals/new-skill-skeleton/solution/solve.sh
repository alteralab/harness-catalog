#!/bin/sh
# Oracle: write-skill 단계 3~5의 끝 상태 — 브랜치 skill/hello-greeting에 SKILL.md와 evals 쌍(양성 1·no-trigger 1). main은 건드리지 않는다.
# 참조 해답이라 스킬의 scaffold.py를 부르지 않는다(Oracle 에이전트는 잡 스킬(--skill)을 받지 않는다 — Harbor 0.24 실측). 스크립트 자체는 코드 저장소의 pytest가 검사한다.
set -eu
cd /work/catalog
git checkout -q -b skill/hello-greeting
d=skills/hello-greeting
mkdir -p "$d/evals/greet-by-name/tests" "$d/evals/no-trigger-farewell/tests"
printf -- '---\nname: hello-greeting\ndescription: 이름을 받아 인사말을 출력한다. "인사해줘", "greet <name>".\n---\n# hello-greeting\n' > "$d/SKILL.md"
for c in greet-by-name no-trigger-farewell; do
  printf 'schema_version = "1.4"\n\n[metadata]\ndescription = "%s"\n\n[environment]\nbuild_timeout_sec = 600.0\nskills_dir = "/skills"\n\n[agent]\ntimeout_sec = 600.0\n\n[verifier]\ntimeout_sec = 120.0\n' "$c" > "$d/evals/$c/task.toml"
  printf 'TODO\n' > "$d/evals/$c/instruction.md"
  printf '#!/bin/sh\nset -eu\nmkdir -p /logs/verifier\necho 0 > /logs/verifier/reward.txt\n' > "$d/evals/$c/tests/test.sh"
done
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "skill: hello-greeting 뼈대"
