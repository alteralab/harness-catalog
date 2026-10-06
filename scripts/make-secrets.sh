#!/bin/sh
# 운영 compose의 비밀 파일 여섯을 만든다. 사용: scripts/make-secrets.sh <SECRETS_DIR> [deploy_key.pem]
# 이미 있는 파일은 건드리지 않는다(멱등). database_url은 hc_db_password와 같은 값으로 조립한다.
set -eu
dir="${1:?usage: make-secrets.sh <SECRETS_DIR> [deploy_key.pem]}"
key="${2:-}"
mkdir -p "$dir"
chmod 700 "$dir"
gen() {
  # $1 = 파일 이름. 없을 때만 무작위 값
  if [ ! -f "$dir/$1" ]; then
    umask 077
    openssl rand -base64 32 | tr -d '\n' > "$dir/$1"
    echo "made $dir/$1"
  fi
}
gen postgres_password
gen hc_db_password
gen dex_db_password
gen dex_ci_runner_secret
if [ ! -f "$dir/git_deploy_key" ]; then
  umask 077
  if [ -n "$key" ]; then cp "$key" "$dir/git_deploy_key"; else : > "$dir/git_deploy_key"; echo "warning: empty git_deploy_key (fine for file:// repos only)" >&2; fi
  echo "made $dir/git_deploy_key"
fi
if [ ! -f "$dir/database_url" ]; then
  umask 077
  printf 'postgresql://harness_catalog:%s@postgres:5432/harness_catalog' "$(cat "$dir/hc_db_password")" > "$dir/database_url"
  echo "made $dir/database_url"
fi
chmod 600 "$dir"/*
echo "secrets ready in $dir"
