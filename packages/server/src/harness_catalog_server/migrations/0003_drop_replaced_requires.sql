-- §11 2026-10-18: replaced-by·requires-tools를 계약에서 뺐다(은퇴는 삭제뿐, 의존성은 스크립트 안에만).
-- 생성 열 둘과 그 인덱스를 두 표에서 지운다. metadata jsonb는 그대로다(자유 맵).
DROP INDEX IF EXISTS skill_index_tools;
ALTER TABLE skill_index DROP COLUMN IF EXISTS replaced_by, DROP COLUMN IF EXISTS requires_tools;
ALTER TABLE tool_index DROP COLUMN IF EXISTS replaced_by, DROP COLUMN IF EXISTS requires_tools;
