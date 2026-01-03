-- CommentScript 테이블 수동 생성
-- Render Shell에서 실행: psql $DATABASE_URL < create_comment_script_table.sql

CREATE TABLE IF NOT EXISTS comment_scripts (
    id SERIAL PRIMARY KEY,
    post_task_id INTEGER NOT NULL REFERENCES automation_tasks(id),
    group_number INTEGER NOT NULL,
    sequence_number INTEGER NOT NULL,
    pc_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    is_new_comment BOOLEAN DEFAULT TRUE,
    parent_group INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    completed_at TIMESTAMP,
    generated_task_id INTEGER REFERENCES automation_tasks(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_post_task_group_seq 
ON comment_scripts(post_task_id, group_number, sequence_number);

-- 확인
SELECT COUNT(*) as table_exists 
FROM information_schema.tables 
WHERE table_name = 'comment_scripts';

