-- 네이버 카페 자동화 시스템 테이블 생성 SQL
-- 실행 방법: psql -U username -d database_name -f migration_automation_system.sql

-- ============================================
-- 1. 작업 PC 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_worker_pcs (
    id SERIAL PRIMARY KEY,
    pc_number INTEGER UNIQUE NOT NULL,
    pc_name VARCHAR(100) NOT NULL,
    ip_address VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'offline',
    current_task_id INTEGER,
    last_heartbeat TIMESTAMP,
    cpu_usage FLOAT,
    memory_usage FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_worker_pcs_pc_number ON automation_worker_pcs(pc_number);
CREATE INDEX idx_automation_worker_pcs_status ON automation_worker_pcs(status);

-- ============================================
-- 2. 자동화 계정 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_accounts (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(100) UNIQUE NOT NULL,
    account_pw VARCHAR(255) NOT NULL,
    assigned_pc_id INTEGER REFERENCES automation_worker_pcs(id),
    status VARCHAR(20) DEFAULT 'active',
    login_status VARCHAR(20) DEFAULT 'logged_out',
    total_posts INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_accounts_account_id ON automation_accounts(account_id);
CREATE INDEX idx_automation_accounts_status ON automation_accounts(status);

-- ============================================
-- 3. 자동화 카페 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_cafes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500) UNIQUE NOT NULL,
    cafe_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_cafes_url ON automation_cafes(url);

-- ============================================
-- 4. AI 프롬프트 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_prompts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    prompt_type VARCHAR(50) NOT NULL,
    system_prompt TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    temperature FLOAT DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 1000,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_prompts_type ON automation_prompts(prompt_type);

-- ============================================
-- 5. 자동화 스케줄 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_schedules (
    id SERIAL PRIMARY KEY,
    mode VARCHAR(20) NOT NULL,
    scheduled_date DATE NOT NULL,
    marketing_product_id INTEGER REFERENCES marketing_products(id),
    keyword_text VARCHAR(255) NOT NULL,
    marketing_post_id INTEGER REFERENCES marketing_posts(id),
    prompt_id INTEGER REFERENCES automation_prompts(id),
    status VARCHAR(20) DEFAULT 'pending',
    is_completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_schedules_date ON automation_schedules(scheduled_date);
CREATE INDEX idx_automation_schedules_mode ON automation_schedules(mode);
CREATE INDEX idx_automation_schedules_status ON automation_schedules(status);

-- ============================================
-- 6. 작업 큐 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_tasks (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(20) NOT NULL,
    mode VARCHAR(20) NOT NULL,
    schedule_id INTEGER REFERENCES automation_schedules(id),
    scheduled_time TIMESTAMP NOT NULL,
    title VARCHAR(500),
    content TEXT NOT NULL,
    parent_task_id INTEGER REFERENCES automation_tasks(id),
    order_sequence INTEGER DEFAULT 0,
    assigned_pc_id INTEGER REFERENCES automation_worker_pcs(id),
    assigned_account_id INTEGER REFERENCES automation_accounts(id),
    cafe_id INTEGER REFERENCES automation_cafes(id),
    status VARCHAR(20) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    post_url VARCHAR(500),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_tasks_status ON automation_tasks(status);
CREATE INDEX idx_automation_tasks_scheduled_time ON automation_tasks(scheduled_time);
CREATE INDEX idx_automation_tasks_priority ON automation_tasks(priority);

-- ============================================
-- 7. 작성된 글 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_posts (
    id SERIAL PRIMARY KEY,
    mode VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    post_url VARCHAR(500),
    account_id INTEGER REFERENCES automation_accounts(id),
    cafe_id INTEGER REFERENCES automation_cafes(id),
    marketing_product_id INTEGER REFERENCES marketing_products(id),
    keyword_text VARCHAR(255),
    view_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_posts_mode ON automation_posts(mode);
CREATE INDEX idx_automation_posts_created_at ON automation_posts(created_at);

-- ============================================
-- 8. 작성된 댓글 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS automation_comments (
    id SERIAL PRIMARY KEY,
    mode VARCHAR(20) NOT NULL,
    post_id INTEGER REFERENCES automation_posts(id),
    parent_comment_id INTEGER REFERENCES automation_comments(id),
    content TEXT NOT NULL,
    account_id INTEGER REFERENCES automation_accounts(id),
    order_sequence INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_automation_comments_post_id ON automation_comments(post_id);

-- ============================================
-- 외래 키 추가 (참조 무결성)
-- ============================================
ALTER TABLE automation_worker_pcs 
    ADD CONSTRAINT fk_worker_pcs_current_task 
    FOREIGN KEY (current_task_id) REFERENCES automation_tasks(id);

-- ============================================
-- 완료 메시지
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '✅ 자동화 시스템 테이블 생성 완료!';
    RAISE NOTICE '   - automation_worker_pcs';
    RAISE NOTICE '   - automation_accounts';
    RAISE NOTICE '   - automation_cafes';
    RAISE NOTICE '   - automation_prompts';
    RAISE NOTICE '   - automation_schedules';
    RAISE NOTICE '   - automation_tasks';
    RAISE NOTICE '   - automation_posts';
    RAISE NOTICE '   - automation_comments';
END $$;

