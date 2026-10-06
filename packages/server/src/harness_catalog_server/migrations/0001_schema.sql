-- 인덱스 표 하나(skill_index) + 상태 행 하나(index_state). 전부 main에서 파생한 것이라 언제든 다시 짓는다.
-- 생성 열·인덱스 DDL은 설계 문서의 계약 문자열 그대로다.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE FUNCTION metadata_values(m jsonb) RETURNS text
  LANGUAGE sql IMMUTABLE AS
  $$ SELECT string_agg(v, ' ' ORDER BY k) FROM jsonb_each_text(m) AS t(k, v) $$;

CREATE TABLE skill_index (
  name          varchar(64)  PRIMARY KEY,
  description   text         NOT NULL,
  compatibility text         CHECK (compatibility IS NULL OR length(compatibility) <= 500),
  metadata      jsonb        NOT NULL DEFAULT '{}'::jsonb,
  tree_sha      char(40)     NOT NULL,
  commit_sha    char(40)     NOT NULL,
  indexed_at    timestamptz  NOT NULL
);

CREATE TABLE index_state (
  id          int          PRIMARY KEY CHECK (id = 1),
  commit_sha  char(40)     NOT NULL,
  indexed_at  timestamptz  NOT NULL
);

ALTER TABLE skill_index
  ADD COLUMN replaced_by varchar(64)
    GENERATED ALWAYS AS (metadata->>'replaced-by') STORED,
  ADD COLUMN requires_tools text[]
    GENERATED ALWAYS AS (string_to_array(nullif(metadata->>'requires-tools', ''), ' ')) STORED,
  ADD COLUMN search_text text
    GENERATED ALWAYS AS (name || ' ' || description || ' ' || coalesce(metadata_values(metadata), '')) STORED,
  ADD COLUMN search tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', name || ' ' || description || ' ' || coalesce(metadata_values(metadata), ''))) STORED;

CREATE INDEX skill_index_search ON skill_index USING gin (search);
CREATE INDEX skill_index_trgm   ON skill_index USING gin (search_text gin_trgm_ops);
CREATE INDEX skill_index_tools  ON skill_index USING gin (requires_tools);
