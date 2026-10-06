-- 데이터베이스 둘과 역할 둘 (distribution D2). 표는 만들지 않는다 — 서비스 마이그레이션(yoyo)과 Dex가 각자 만든다.
-- 역할은 자기 데이터베이스만 소유하고 남의 데이터베이스를 만들 권한이 없다.
CREATE ROLE harness_catalog LOGIN PASSWORD :'hc_password';
CREATE ROLE dex LOGIN PASSWORD :'dex_password';
CREATE DATABASE harness_catalog OWNER harness_catalog;
CREATE DATABASE dex OWNER dex;
-- pg_trgm 확장은 슈퍼유저만 만들 수 있으므로 여기서 만든다 (서비스 마이그레이션은 CREATE EXTENSION IF NOT EXISTS로 확인만).
\connect harness_catalog
CREATE EXTENSION IF NOT EXISTS pg_trgm;
