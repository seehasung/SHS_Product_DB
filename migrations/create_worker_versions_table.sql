-- Worker Agent 버전 관리 테이블 생성
-- 실행일: 2026-02-12

CREATE TABLE worker_versions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    version VARCHAR(20) NOT NULL UNIQUE,
    changelog TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    INDEX idx_is_active (is_active)
);

-- 초기 버전 삽입
INSERT INTO worker_versions (version, changelog, is_active, created_by)
VALUES ('1.0.2', '초기 버전\n기본 글 작성 기능', TRUE, 'system');

-- 확인
SELECT * FROM worker_versions;
