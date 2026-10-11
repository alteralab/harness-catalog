-- toolbox(DESIGN §11 2026-10-11): 도구 인덱스 표. skill_index와 같은 생성 열·인덱스 식. main에서 파생한 것이라 언제든 다시 짓는다.
-- 생성 열·인덱스 DDL은 설계 문서(그림 3 아래)의 계약 문자열 그대로다.
CREATE TABLE tool_index (
  name          varchar(64)  PRIMARY KEY,
  description   text         NOT NULL CHECK (length(description) <= 1024),
  kind          varchar(16)  NOT NULL CHECK (kind IN ('script', 'mcp')),
  server        varchar(64),
  metadata      jsonb        NOT NULL DEFAULT '{}'::jsonb,
  tree_sha      char(40)     NOT NULL,
  commit_sha    char(40)     NOT NULL,
  indexed_at    timestamptz  NOT NULL
);

ALTER TABLE tool_index
  ADD COLUMN replaced_by varchar(64)
    GENERATED ALWAYS AS (metadata->>'replaced-by') STORED,
  ADD COLUMN requires_tools text[]
    GENERATED ALWAYS AS (string_to_array(nullif(metadata->>'requires-tools', ''), ' ')) STORED,
  ADD COLUMN search_text text
    GENERATED ALWAYS AS (name || ' ' || description || ' ' || coalesce(metadata_values(metadata), '')) STORED,
  ADD COLUMN search tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', name || ' ' || description || ' ' || coalesce(metadata_values(metadata), ''))) STORED;

CREATE INDEX tool_index_search ON tool_index USING gin (search);
CREATE INDEX tool_index_trgm   ON tool_index USING gin (search_text gin_trgm_ops);
