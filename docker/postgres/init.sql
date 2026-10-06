-- 데이터베이스 둘과 역할 둘. 표는 만들지 않는다 — 서비스 마이그레이션(yoyo)과 Dex가 각자 만든다.
-- 역할은 자기 데이터베이스만 소유하고 남의 데이터베이스를 만들 권한이 없다.
-- 멱등: 반쯤 실행된 뒤 다시 돌아도 된다. psql 변수(:'hc_password')는 DO 블록 안에서 치환되지 않으므로 \gexec로 만든다.
SELECT format('CREATE ROLE harness_catalog LOGIN PASSWORD %L', :'hc_password')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_catalog') \gexec
SELECT format('CREATE ROLE dex LOGIN PASSWORD %L', :'dex_password')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dex') \gexec
SELECT 'CREATE DATABASE harness_catalog OWNER harness_catalog'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'harness_catalog') \gexec
SELECT 'CREATE DATABASE dex OWNER dex'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dex') \gexec
-- pg_trgm 확장은 슈퍼유저만 만들 수 있으므로 여기서 만든다 (서비스 마이그레이션은 CREATE EXTENSION IF NOT EXISTS로 확인만).
\connect harness_catalog
CREATE EXTENSION IF NOT EXISTS pg_trgm;
