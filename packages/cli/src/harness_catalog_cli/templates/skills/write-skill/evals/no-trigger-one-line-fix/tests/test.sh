#!/bin/bash
# Harbor 공식 뼈대(harbor tasks init)의 검증기 진입점: /tests/test_outputs.py를 pytest로 돌려 종료 코드로 reward 0/1을 쓴다.
# pytest·pytest-json-ctrf는 environment/Dockerfile이 미리 넣는다(검증 때 네트워크 없음). CTRF 보고는 /logs/verifier/ctrf.json.
set -u
mkdir -p /logs/verifier
cd /work || exit 1
if python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
