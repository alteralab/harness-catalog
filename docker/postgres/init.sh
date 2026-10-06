#!/bin/sh
# 첫 기동에만 실행된다(postgres 이미지 초기화 훅). 비밀은 환경 변수에서 psql 변수로 넘기고 SQL은 init.sql이 소유한다 (distribution D2).
set -eu
psql -v ON_ERROR_STOP=1 \
  -v hc_password="$HC_DB_PASSWORD" \
  -v dex_password="$DEX_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname postgres \
  -f /docker-entrypoint-initdb.d/init.sql
