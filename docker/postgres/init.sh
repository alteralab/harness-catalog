#!/bin/sh
# 첫 기동에만 실행된다(postgres 이미지 초기화 훅, 빈 데이터 디렉토리일 때). 비밀은 환경 변수(개발) 또는 *_FILE(운영, docker secrets)에서 psql 변수로 넘기고 SQL은 init.sql이 소유한다.
# init.sql은 initdb.d 밖(/opt/harness-catalog)에 마운트한다 — 안에 있으면 entrypoint가 한 번 더 돌린다.
set -eu
read_secret() {
  # $1 = 변수 이름. <이름>_FILE이 있으면 그 파일, 아니면 환경 변수
  file_var="${1}_FILE"
  eval "file_path=\${$file_var:-}"
  if [ -n "$file_path" ]; then
    tr -d '\n' < "$file_path"
  else
    eval "printf '%s' \"\${$1:?\$1 or \$file_var must be set}\""
  fi
}
HC_PW=$(read_secret HC_DB_PASSWORD)
DEX_PW=$(read_secret DEX_DB_PASSWORD)
psql -v ON_ERROR_STOP=1 \
  -v hc_password="$HC_PW" \
  -v dex_password="$DEX_PW" \
  --username "$POSTGRES_USER" --dbname postgres \
  -f /opt/harness-catalog/init.sql
