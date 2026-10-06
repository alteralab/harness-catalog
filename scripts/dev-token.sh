#!/bin/sh
# 기계 계정 토큰(비밀번호 그랜트). 사용: scripts/dev-token.sh <issuer> <registry-public-url> <client-id> <client-secret> <user> <password>
# 레지스트리의 RFC 9728 문서가 광고하는 스코프(openid groups audience:server:client_id:<URL>)를 그대로 요청한다.
# 액세스 토큰만 표준 출력에 낸다. 비밀·토큰을 로그에 남기지 않는다. 사람 토큰(PKCE)은 tools/pilot/dex_grants.py의 흐름을 쓴다.
set -eu
issuer="${1:?issuer}"; registry="${2:?registry public url}"; client="${3:?client id}"; secret="${4:?client secret}"; user="${5:?user}"; password="${6:?password}"
token_endpoint=$(curl -fsS "${issuer%/}/.well-known/openid-configuration" | python3 -c 'import sys,json; print(json.load(sys.stdin)["token_endpoint"])')
scope="openid groups audience:server:client_id:${registry%/}"
curl -fsS -u "$client:$secret" -X POST "$token_endpoint" \
  --data-urlencode "grant_type=password" --data-urlencode "username=$user" --data-urlencode "password=$password" --data-urlencode "scope=$scope" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["access_token"])'
