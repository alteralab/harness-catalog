#!/bin/sh
# 빠른 시작의 카탈로그 저장소 심기. /seed/template(init 템플릿 — 기본 스킬 둘 포함)으로
# /catalog/catalog.git(bare, main)을 한 번 만든다. 이미 있으면 아무것도 하지 않는다(멱등 — compose 재기동에 안전).
# harness-catalog init과 같은 것을 쓴다: 표지·기본 스킬 둘(skills/)·README·pre-commit 설정·GitHub 워크플로(v<판> 치환).
set -eu
target=/catalog/catalog.git
if [ -d "$target" ]; then
  echo "catalog already seeded at $target ($(git -C "$target" rev-parse --short HEAD))"
  exit 0
fi
version=$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' /seed/cli-pyproject.toml | head -n 1)
version="${version#v}"
work=$(mktemp -d)
cp /seed/template/.harness-catalog "$work/.harness-catalog"
mkdir -p "$work/skills" "$work/.github/workflows" "$work/.github/actions/code-repo-credentials"
cp -R /seed/template/skills/. "$work/skills/"
for f in README.md .pre-commit-config.yaml; do
  sed "s/v<판>/v$version/g" "/seed/template/$f" > "$work/$f"
done
sed "s/v<판>/v$version/g" /seed/template/github/check.yml > "$work/.github/workflows/check.yml"
cp /seed/template/github/actions/code-repo-credentials/action.yml "$work/.github/actions/code-repo-credentials/action.yml"
git -C "$work" init -q -b main
git -C "$work" -c user.name=quickstart -c user.email=quickstart@harness-catalog.local add -A
git -C "$work" -c user.name=quickstart -c user.email=quickstart@harness-catalog.local commit -q -m "quickstart seed: $(ls "$work/skills" | tr '\n' ' ')"
git clone -q --bare "$work" "$target"
chmod -R a+rX "$target"
echo "seeded $target with skills: $(ls "$work/skills" | tr '\n' ' ')($(git -C "$target" rev-parse --short HEAD), templates pinned to v$version)"
