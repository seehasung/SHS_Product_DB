-- apply_cafe_context 컬럼 추가
-- Render Shell에서 실행: psql $DATABASE_URL < add_apply_cafe_context.sql

ALTER TABLE ai_prompts 
ADD COLUMN IF NOT EXISTS apply_cafe_context BOOLEAN DEFAULT FALSE;

SELECT '✅ apply_cafe_context 컬럼 추가 완료!' as result;
