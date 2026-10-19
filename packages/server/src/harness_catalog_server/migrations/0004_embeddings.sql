-- §11 2026-10-19 검색 0.8.0: 메모리 사본 위의 BM25 + dense 볼록 결합. 벡터는 파생 데이터지만 재기동 때 다시 임베딩하지 않도록 행에 함께 둔다.
-- embedding_generation = "<모델>/<문서형식 판>". 세대가 다른 벡터는 앱이 읽지 않는다(섞지 않음). 검색 자체는 더 이상 SQL(tsvector·trgm)을 쓰지 않는다 —
-- 생성 열 search·search_text 와 GIN 인덱스는 이번 판에서 그대로 두고 다음 스키마 정리 판에서 지운다(이전 이미지로의 롤백 공존).
ALTER TABLE skill_index ADD COLUMN IF NOT EXISTS embedding real[], ADD COLUMN IF NOT EXISTS embedding_generation text;
ALTER TABLE tool_index  ADD COLUMN IF NOT EXISTS embedding real[], ADD COLUMN IF NOT EXISTS embedding_generation text;
