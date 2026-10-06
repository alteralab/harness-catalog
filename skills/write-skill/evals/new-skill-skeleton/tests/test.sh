#!/bin/sh
set -eu
mkdir -p /logs/verifier
# 브랜치 skill/hello-greeting에 SKILL.md와 evals 케이스 둘(그중 no-trigger-* 하나)이 있고 main은 그대로여야 1
cd /work/catalog
if git rev-parse --verify -q skill/hello-greeting >/dev/null \
   && git show skill/hello-greeting:skills/hello-greeting/SKILL.md 2>/dev/null | grep -q '^name: hello-greeting' \
   && [ "$(git ls-tree --name-only skill/hello-greeting:skills/hello-greeting/evals 2>/dev/null | wc -l)" -ge 2 ] \
   && git ls-tree --name-only skill/hello-greeting:skills/hello-greeting/evals | grep -q '^no-trigger-' \
   && [ "$(git rev-list --count main)" -eq 1 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
