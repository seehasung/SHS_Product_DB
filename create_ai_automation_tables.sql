-- AI 자동화 시스템 테이블 생성

-- 1. AI 상품 세팅 테이블
CREATE TABLE IF NOT EXISTS ai_product_setup (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    
    -- 권한
    is_cafe_enabled BOOLEAN DEFAULT TRUE,
    is_blog_enabled BOOLEAN DEFAULT FALSE,
    
    -- 상품 상세 정보 (12개 필드)
    product_name VARCHAR(200) NOT NULL,
    core_value TEXT NOT NULL,                    -- 핵심 주장
    sub_core_value TEXT NOT NULL,                -- 서브 핵심
    size_weight VARCHAR(200) NOT NULL,           -- 사이즈 & 무게
    differentiation TEXT NOT NULL,               -- 타사 차별점
    famous_brands TEXT,                          -- 유명 브랜드들
    market_problems TEXT NOT NULL,               -- 시장 문제점
    our_price VARCHAR(100) NOT NULL,             -- 우리 가격
    market_avg_price VARCHAR(100) NOT NULL,      -- 시장 평균 가격
    target_age VARCHAR(100) NOT NULL,            -- 예상 연령대
    target_gender VARCHAR(50) NOT NULL,          -- 예상 성별
    additional_notes TEXT,                       -- 기타 특이사항
    
    -- 마케팅 링크
    marketing_link TEXT NOT NULL,
    
    -- 메타 정보
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. AI 키워드 관리 테이블
CREATE TABLE IF NOT EXISTS ai_keywords (
    id SERIAL PRIMARY KEY,
    ai_product_id INTEGER REFERENCES ai_product_setup(id),
    keyword_text VARCHAR(200) NOT NULL,
    keyword_type VARCHAR(50),  -- 'alternative', 'informative', 'unclassified'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. AI 레퍼런스 관리 테이블
CREATE TABLE IF NOT EXISTS ai_references (
    id SERIAL PRIMARY KEY,
    ai_product_id INTEGER REFERENCES ai_product_setup(id),
    title VARCHAR(500) NOT NULL,
    content TEXT,
    ref_type VARCHAR(50),  -- 'alternative', 'informative', 'unclassified'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. AI 프롬프트 템플릿 테이블
CREATE TABLE IF NOT EXISTS ai_prompt_templates (
    id SERIAL PRIMARY KEY,
    template_name VARCHAR(200) NOT NULL,
    template_type VARCHAR(50) NOT NULL,  -- 'alternative', 'informative'
    user_prompt_template TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_ai_product_setup_product_id ON ai_product_setup(product_id);
CREATE INDEX IF NOT EXISTS idx_ai_keywords_product ON ai_keywords(ai_product_id);
CREATE INDEX IF NOT EXISTS idx_ai_references_product ON ai_references(ai_product_id);
CREATE INDEX IF NOT EXISTS idx_ai_prompt_templates_type ON ai_prompt_templates(template_type);

-- 확인
SELECT 'AI 자동화 테이블 생성 완료!' as message;
