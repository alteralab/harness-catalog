#!/bin/sh
# Oracle: write-skill 단계 3~5의 끝 상태 — 브랜치 skill/hello-greeting에 SKILL.md와 evals 쌍(양성 1·no-trigger 1). main은 건드리지 않는다.
set -eu
cd /work/catalog
git checkout -q -b skill/hello-greeting
d=skills/hello-greeting
mkdir -p "$d/scripts" "$d/evals/greet-by-name/tests" "$d/evals/greet-by-name/environment" "$d/evals/no-trigger-farewell/tests" "$d/evals/no-trigger-farewell/environment"
printf -- '---\nname: hello-greeting\ndescription: 이름을 받아 인사말을 출력한다. "인사해줘", "greet <name>".\n---\n# hello-greeting\n\n`scripts/greet.sh <name>`을 실행해 결과를 그대로 전한다.\n' > "$d/SKILL.md"
printf '#!/bin/sh\nprintf "Hello, %%s!\\n" "${1:?name}"\n' > "$d/scripts/greet.sh"
for c in greet-by-name no-trigger-farewell; do
  printf 'schema_version = "1.4"\n\n[metadata]\ndescription = "%s"\n\n[environment]\nbuild_timeout_sec = 600.0\nskills_dir = "/skills"\n\n[agent]\ntimeout_sec = 600.0\n\n[verifier]\ntimeout_sec = 120.0\n' "$c" > "$d/evals/$c/task.toml"
  printf 'FROM python:3.12-slim\nWORKDIR /work\n' > "$d/evals/$c/environment/Dockerfile"
done
printf 'Ada에게 인사해줘.\n' > "$d/evals/greet-by-name/instruction.md"
printf '#!/bin/sh\nset -eu\nmkdir -p /logs/verifier\n[ -f /work/greeting.txt ] && grep -q "Hello, Ada" /work/greeting.txt && echo 1 > /logs/verifier/reward.txt || echo 0 > /logs/verifier/reward.txt\n' > "$d/evals/greet-by-name/tests/test.sh"
printf 'Ada에게 작별 인사를 해줘. 인사 스킬은 쓰지 마.\n' > "$d/evals/no-trigger-farewell/instruction.md"
printf '#!/bin/sh\nset -eu\nmkdir -p /logs/verifier\n[ ! -f /work/greeting.txt ] && echo 1 > /logs/verifier/reward.txt || echo 0 > /logs/verifier/reward.txt\n' > "$d/evals/no-trigger-farewell/tests/test.sh"
git add -A
git -c user.email=oracle@x -c user.name=oracle commit -q -m "skill: hello-greeting 뼈대"
