-- 스키마 정리(DESIGN §11 2026-10-19 스키마 정리 판): 검색은 0.8.0 부터 앱 메모리의 하이브리드 색인이 한다.
-- SQL 어휘 검색의 생성 열 둘(search_text·search)과 GIN 인덱스 넷, IMMUTABLE 함수 metadata_values 를 지운다.
-- pg_trgm 확장은 슈퍼유저 소유라 여기서 지우지 않는다(쓰는 곳 없음 — 운영 문서의 선택 절차).
DROP INDEX IF EXISTS skill_index_search;
DROP INDEX IF EXISTS skill_index_trgm;
DROP INDEX IF EXISTS tool_index_search;
DROP INDEX IF EXISTS tool_index_trgm;
ALTER TABLE skill_index DROP COLUMN IF EXISTS search, DROP COLUMN IF EXISTS search_text;
ALTER TABLE tool_index  DROP COLUMN IF EXISTS search, DROP COLUMN IF EXISTS search_text;
DROP FUNCTION IF EXISTS metadata_values(jsonb);
