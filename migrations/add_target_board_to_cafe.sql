-- 카페 테이블에 변경할 게시판명 컬럼 추가
-- 실행일: 2026-02-12

ALTER TABLE automation_cafes 
ADD COLUMN target_board VARCHAR(255);

-- 기존 데이터에 대한 확인
SELECT id, name, url, target_board 
FROM automation_cafes 
LIMIT 10;
