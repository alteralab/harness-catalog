#!/bin/sh
# 운영 compose의 비밀 파일 여덟을 만든다(무작위 넷, deploy key, database_url, otlp_headers(LANGFUSE_* 환경이 있으면 Basic 헤더)·빈 ldap_bind_pw). 사용: [LANGFUSE_PUBLIC_KEY=… LANGFUSE_SECRET_KEY=…] scripts/make-secrets.sh <SECRETS_DIR> [deploy_key.pem]
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
# otlp_headers: LANGFUSE_PUBLIC_KEY·LANGFUSE_SECRET_KEY 가 환경에 있으면(예: gopass show -o nas/langfuse-public) Basic 헤더를 쓴다. 없으면 빈 파일(헤더 없이 내보냄). 이미 내용이 있으면 건드리지 않는다.
if [ ! -s "$dir/otlp_headers" ]; then
  umask 077
  if [ -n "${LANGFUSE_PUBLIC_KEY:-}" ] && [ -n "${LANGFUSE_SECRET_KEY:-}" ]; then
    printf 'Authorization=Basic %s' "$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64 | tr -d '\n')" > "$dir/otlp_headers"
    echo "made $dir/otlp_headers (Langfuse Basic auth)"
  else
    : > "$dir/otlp_headers"; echo "note: $dir/otlp_headers is empty — spans go out without headers; set LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY and rerun to fill it" >&2
  fi
fi
if [ ! -f "$dir/ldap_bind_pw" ]; then umask 077; : > "$dir/ldap_bind_pw"; echo "note: $dir/ldap_bind_pw is empty — put the LDAP bind password there (synology-ldap overlay)" >&2; fi
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
