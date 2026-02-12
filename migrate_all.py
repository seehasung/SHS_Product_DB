#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""전체 DB 마이그레이션"""

from sqlalchemy import text
from database import engine

print("=" * 60)
print("🔧 DB 마이그레이션 시작")
print("=" * 60)

with engine.connect() as conn:
    # 1. target_board 추가
    print("\n1️⃣ target_board 컬럼 추가...")
    try:
        conn.execute(text("ALTER TABLE automation_cafes ADD COLUMN target_board VARCHAR(255)"))
        conn.commit()
        print("   ✅ 완료")
    except Exception as e:
        print(f"   ℹ️  {e}")
    
    # 2. worker_versions 테이블
    print("\n2️⃣ worker_versions 테이블 생성...")
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS worker_versions (
        id SERIAL PRIMARY KEY,
        version VARCHAR(20) UNIQUE NOT NULL,
        changelog TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(100)
    )"""))
    conn.commit()
    print("   ✅ 완료")
    
    # 3. 초기 데이터
    print("\n3️⃣ 초기 데이터 삽입...")
    conn.execute(text("""
    INSERT INTO worker_versions (version, changelog, is_active, created_by)
    VALUES ('1.0.2', '초기 버전\n기본 글 작성 기능', TRUE, 'system')
    ON CONFLICT (version) DO NOTHING
    """))
    conn.commit()
    print("   ✅ 완료")
    
    # 4. 확인
    print("\n4️⃣ 확인...")
    result = conn.execute(text("SELECT * FROM worker_versions"))
    for row in result:
        print(f"   - v{row[1]}")
    
print("\n" + "=" * 60)
print("✅ 마이그레이션 완료!")
print("=" * 60)
