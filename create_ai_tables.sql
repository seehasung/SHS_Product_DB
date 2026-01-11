-- AI 자동화 시스템 테이블 생성
-- Render Shell에서 실행: psql $DATABASE_URL < create_ai_tables.sql

-- ============================================
-- 1. AI 마케팅 상품 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_marketing_products (
    id SERIAL PRIMARY KEY,
    marketing_product_id INTEGER UNIQUE NOT NULL REFERENCES marketing_products(id) ON DELETE CASCADE,
    
    -- 플랫폼 권한
    use_for_blog BOOLEAN DEFAULT FALSE,
    use_for_cafe BOOLEAN DEFAULT FALSE,
    
    -- 상품 상세 정보 (12개 필드)
    product_name VARCHAR(500) NOT NULL,
    core_value TEXT NOT NULL,
    sub_core_value TEXT NOT NULL,
    size_weight TEXT NOT NULL,
    difference TEXT NOT NULL,
    famous_brands TEXT NOT NULL,
    market_problem TEXT NOT NULL,
    our_price VARCHAR(100) NOT NULL,
    market_avg_price VARCHAR(100) NOT NULL,
    target_age VARCHAR(100) NOT NULL,
    target_gender VARCHAR(50) NOT NULL,
    additional_info TEXT,
    
    -- 마케팅 링크
    marketing_link VARCHAR(2083) NOT NULL,
    
    -- 타임스탬프
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_marketing_products_marketing_product 
ON ai_marketing_products(marketing_product_id);


-- ============================================
-- 2. AI 상품 키워드 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_product_keywords (
    id SERIAL PRIMARY KEY,
    ai_product_id INTEGER NOT NULL REFERENCES ai_marketing_products(id) ON DELETE CASCADE,
    
    keyword_text VARCHAR(255) NOT NULL,
    keyword_type VARCHAR(20) NOT NULL DEFAULT 'unclassified', -- alternative, informational, unclassified
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ai_product_id, keyword_text)
);

CREATE INDEX IF NOT EXISTS idx_ai_product_keywords_product 
ON ai_product_keywords(ai_product_id);

CREATE INDEX IF NOT EXISTS idx_ai_product_keywords_type 
ON ai_product_keywords(keyword_type);


-- ============================================
-- 3. AI 상품 레퍼런스 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_product_references (
    id SERIAL PRIMARY KEY,
    ai_product_id INTEGER NOT NULL REFERENCES ai_marketing_products(id) ON DELETE CASCADE,
    reference_id INTEGER NOT NULL REFERENCES references(id) ON DELETE CASCADE,
    
    reference_type VARCHAR(20) NOT NULL DEFAULT 'unclassified', -- alternative, informational, unclassified
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ai_product_id, reference_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_product_references_product 
ON ai_product_references(ai_product_id);

CREATE INDEX IF NOT EXISTS idx_ai_product_references_type 
ON ai_product_references(reference_type);


-- ============================================
-- 4. AI 프롬프트 템플릿 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_prompt_templates (
    id SERIAL PRIMARY KEY,
    
    template_name VARCHAR(255) NOT NULL,
    template_type VARCHAR(20) NOT NULL, -- alternative, informational
    user_prompt_template TEXT NOT NULL,
    
    is_template BOOLEAN DEFAULT TRUE,
    ai_product_id INTEGER REFERENCES ai_marketing_products(id) ON DELETE CASCADE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_prompt_templates_type 
ON ai_prompt_templates(template_type);

CREATE INDEX IF NOT EXISTS idx_ai_prompt_templates_is_template 
ON ai_prompt_templates(is_template);


-- ============================================
-- 5. AI 프롬프트 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_prompts (
    id SERIAL PRIMARY KEY,
    
    ai_product_id INTEGER NOT NULL REFERENCES ai_marketing_products(id) ON DELETE CASCADE,
    keyword_classification VARCHAR(20) NOT NULL, -- alternative, informational
    
    system_prompt TEXT NOT NULL,
    user_prompt TEXT NOT NULL,
    
    temperature REAL DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2000,
    generate_images BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_prompts_product 
ON ai_prompts(ai_product_id);

CREATE INDEX IF NOT EXISTS idx_ai_prompts_classification 
ON ai_prompts(keyword_classification);


-- ============================================
-- 6. AI 마케팅 스케줄 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_marketing_schedules (
    id SERIAL PRIMARY KEY,
    
    ai_product_id INTEGER NOT NULL REFERENCES ai_marketing_products(id) ON DELETE CASCADE,
    prompt_id INTEGER NOT NULL REFERENCES ai_prompts(id) ON DELETE CASCADE,
    
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    daily_post_count INTEGER NOT NULL,
    expected_total_posts INTEGER NOT NULL,
    
    status VARCHAR(20) DEFAULT 'scheduled', -- scheduled, in_progress, completed
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_marketing_schedules_product 
ON ai_marketing_schedules(ai_product_id);

CREATE INDEX IF NOT EXISTS idx_ai_marketing_schedules_dates 
ON ai_marketing_schedules(start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_ai_marketing_schedules_status 
ON ai_marketing_schedules(status);


-- ============================================
-- 7. AI 생성 글 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS ai_generated_posts (
    id SERIAL PRIMARY KEY,
    
    ai_product_id INTEGER NOT NULL REFERENCES ai_marketing_products(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES ai_marketing_schedules(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES automation_accounts(id) ON DELETE CASCADE,
    cafe_id INTEGER NOT NULL REFERENCES automation_cafes(id) ON DELETE CASCADE,
    
    post_title TEXT NOT NULL,
    post_body TEXT NOT NULL,
    post_url VARCHAR(500),
    
    image_urls JSON,
    
    status VARCHAR(20) DEFAULT 'draft', -- draft, published
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_generated_posts_product 
ON ai_generated_posts(ai_product_id);

CREATE INDEX IF NOT EXISTS idx_ai_generated_posts_schedule 
ON ai_generated_posts(schedule_id);

CREATE INDEX IF NOT EXISTS idx_ai_generated_posts_account 
ON ai_generated_posts(account_id);

CREATE INDEX IF NOT EXISTS idx_ai_generated_posts_cafe 
ON ai_generated_posts(cafe_id);

CREATE INDEX IF NOT EXISTS idx_ai_generated_posts_status 
ON ai_generated_posts(status);


-- ============================================
-- 완료 메시지
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '✅ AI 자동화 시스템 테이블 생성 완료!';
    RAISE NOTICE '   - ai_marketing_products';
    RAISE NOTICE '   - ai_product_keywords';
    RAISE NOTICE '   - ai_product_references';
    RAISE NOTICE '   - ai_prompt_templates';
    RAISE NOTICE '   - ai_prompts';
    RAISE NOTICE '   - ai_marketing_schedules';
    RAISE NOTICE '   - ai_generated_posts';
    RAISE NOTICE '';
    RAISE NOTICE '🚀 서버를 재시작하세요!';
END $$;
