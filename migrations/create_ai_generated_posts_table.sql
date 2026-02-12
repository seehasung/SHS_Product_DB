-- AI 신규발행 글 메타데이터 테이블 생성
-- 실행일: 2026-02-12

CREATE TABLE ai_generated_posts (
    id SERIAL PRIMARY KEY,
    cafe_name VARCHAR(200) NOT NULL,
    author_account VARCHAR(100) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    title VARCHAR(500) NOT NULL,
    post_url VARCHAR(1000) NOT NULL UNIQUE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_ai_posts_status ON ai_generated_posts(status);
CREATE INDEX idx_ai_posts_created_at ON ai_generated_posts(created_at);

-- 확인
SELECT * FROM ai_generated_posts LIMIT 10;
