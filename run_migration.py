"""
DB 마이그레이션 실행 스크립트
Render Shell에서 실행: python run_migration.py
"""

from sqlalchemy import create_engine, text
from database import get_db, engine
import os

def run_migration():
    """worker_versions 테이블 생성"""
    
    print("=" * 60)
    print("🔧 Worker Versions 테이블 마이그레이션 시작")
    print("=" * 60)
    
    try:
        with engine.connect() as connection:
            # 1. 테이블 생성
            print("\n1️⃣ worker_versions 테이블 생성 중...")
            
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS worker_versions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                version VARCHAR(20) NOT NULL UNIQUE,
                changelog TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                INDEX idx_is_active (is_active)
            )
            """
            
            connection.execute(text(create_table_sql))
            connection.commit()
            print("   ✅ 테이블 생성 완료")
            
            # 2. 초기 데이터 삽입 (이미 있으면 무시)
            print("\n2️⃣ 초기 버전 데이터 삽입 중...")
            
            insert_sql = """
            INSERT IGNORE INTO worker_versions (version, changelog, is_active, created_by)
            VALUES ('1.0.2', '초기 버전\n기본 글 작성 기능', TRUE, 'system')
            """
            
            connection.execute(text(insert_sql))
            connection.commit()
            print("   ✅ 초기 데이터 삽입 완료")
            
            # 3. 확인
            print("\n3️⃣ 데이터 확인 중...")
            result = connection.execute(text("SELECT * FROM worker_versions"))
            rows = result.fetchall()
            
            if rows:
                print(f"   ✅ {len(rows)}개의 버전이 등록되었습니다:")
                for row in rows:
                    print(f"      - v{row[1]} ({row[5]})")
            else:
                print("   ⚠️  데이터가 없습니다")
            
        print("\n" + "=" * 60)
        print("✅ 마이그레이션 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 마이그레이션 실패: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)
