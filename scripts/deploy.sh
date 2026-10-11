#!/bin/sh
# 운영 호스트에 레지스트리 한 판을 배포한다 — 한 명령. (plans/distribution.md D25)
#   scripts/deploy.sh <ssh 호스트> <이미지 태그(짧은 SHA 또는 vX.Y.Z)> [저장소 경로] [compose 오버레이]
# 하는 일: 호스트에서 git pull → docker/.env의 REGISTRY_IMAGE 교체 → 이미지 확인(없으면 pull) → registry만 up -d →
#          /readyz가 ready이고 db_unavailable이 없을 때까지 대기 → 적용된 마이그레이션·commit 출력.
# 전제: 호스트에 ssh 키 로그인, 저장소 클론, docker/.env·SECRETS_DIR 준비(docs/operations.md §2). 비대화 PATH에 docker가 없을 수 있어 DOCKER로 절대 경로를 준다.
# 예: scripts/deploy.sh mini 1b076d1 /Users/altera/harness-catalog docker/synology-ldap/compose.override.yml
set -eu
host="${1:?usage: deploy.sh <host> <image-tag> [repo-path] [overlay]}"
tag="${2:?usage: deploy.sh <host> <image-tag> [repo-path] [overlay]}"
repo="${3:-/Users/altera/harness-catalog}"
overlay="${4:-docker/synology-ldap/compose.override.yml}"
docker_bin="${DOCKER:-/opt/homebrew/bin/docker}"
image="ghcr.io/alteralab/harness-catalog:$tag"

# shellcheck disable=SC2087  # 의도: 호스트 경로·이미지·오버레이는 이쪽에서 받은 인자라 클라이언트 쪽에서 치환해 보낸다. 서버 쪽 변수는 \$로 피했다
ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "sh -s" <<EOF
set -eu
cd "$repo"
git pull -q --ff-only
echo "repo: \$(git log --oneline -1)"
grep -q '^REGISTRY_IMAGE=' docker/.env || { echo "docker/.env has no REGISTRY_IMAGE" >&2; exit 2; }
sed -i '' "s|^REGISTRY_IMAGE=.*|REGISTRY_IMAGE=$image|" docker/.env
"$docker_bin" image inspect "$image" >/dev/null 2>&1 || "$docker_bin" pull -q "$image"
compose="$docker_bin compose -f docker/compose.yml"
[ -n "$overlay" ] && [ -f "$overlay" ] && compose="\$compose -f $overlay"
\$compose up -d registry
i=0
while [ \$i -lt 40 ]; do
  out=\$(curl -fsS --max-time 3 http://127.0.0.1:8000/readyz 2>/dev/null || true)
  case "\$out" in
    *'"ready":true'*) case "\$out" in *db_unavailable*) ;; *) break ;; esac ;;
  esac
  i=\$((i+1)); sleep 3
done
echo "readyz: \$out"
case "\$out" in *'"ready":true'*) ;; *) echo "deploy: registry did not become ready" >&2; exit 1 ;; esac
echo "migrations: \$(\$compose exec -T postgres psql -U postgres -d harness_catalog -tAc 'select string_agg(migration_id, \$\$, \$\$ order by migration_id) from _yoyo_migration')"
echo "image: \$("$docker_bin" inspect harness-catalog-registry-1 --format '{{.Config.Image}}')"
EOF
