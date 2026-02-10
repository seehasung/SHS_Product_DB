-- 카페 특성 컬럼 추가
-- Render Shell에서 실행: psql $DATABASE_URL < add_cafe_characteristics.sql

ALTER TABLE automation_cafes 
ADD COLUMN IF NOT EXISTS characteristics TEXT;

-- 기본값 설정
UPDATE automation_cafes 
SET characteristics = '일반적인 톤, 자연스러운 대화체'
WHERE characteristics IS NULL;

SELECT '✅ 카페 특성 컬럼 추가 완료!' as result;
