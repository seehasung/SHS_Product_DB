#!/usr/bin/env python3
"""
AI 자동화 시스템 테이블 생성 스크립트
Render Shell에서 실행: python create_ai_tables.py
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from database import Base, AIMarketingProduct, AIProductKeyword, AIProductReference, AIPromptTemplate, AIPrompt, AIMarketingSchedule, AIGeneratedPost

load_dotenv()

def create_ai_tables():
    """AI 자동화 테이블 생성"""
    print("="*60)
    print("AI 자동화 시스템 테이블 생성 시작")
    print("="*60)
    
    # 데이터베이스 연결
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL 환경 변수가 설정되지 않았습니다.")
        return False
    
    print(f"\n✅ 데이터베이스 연결: {database_url[:30]}...")
    
    engine = create_engine(database_url)
    inspector = inspect(engine)
    
    # 기존 테이블 확인
    existing_tables = inspector.get_table_names()
    print(f"\n📊 기존 테이블: {len(existing_tables)}개")
    
    ai_tables = [
        'ai_marketing_products',
        'ai_product_keywords',
        'ai_product_references',
        'ai_prompt_templates',
        'ai_prompts',
        'ai_marketing_schedules',
        'ai_generated_posts',
        'cafe_account_links',
        'draft_posts'
    ]
    
    # AI 테이블 존재 여부 확인
    print("\n🔍 AI 테이블 확인:")
    missing_tables = []
    for table in ai_tables:
        if table in existing_tables:
            print(f"  ✅ {table}")
        else:
            print(f"  ❌ {table} (없음)")
            missing_tables.append(table)
    
    if not missing_tables:
        print("\n✅ 모든 AI 테이블이 이미 존재합니다!")
        return True
    
    # 테이블 생성
    print(f"\n🔨 누락된 테이블 생성 중... ({len(missing_tables)}개)")
    
    try:
        # AI 테이블만 생성
        # Base.metadata.create_all()을 사용하면 모든 테이블을 생성하려고 하므로
        # 개별 테이블만 생성
        
        from sqlalchemy import Table, MetaData
        
        # AI 모델들의 테이블만 추출
        ai_models = [
            AIMarketingProduct,
            AIProductKeyword,
            AIProductReference,
            AIPromptTemplate,
            AIPrompt,
            AIMarketingSchedule,
            AIGeneratedPost
        ]
        
        for model in ai_models:
            table_name = model.__tablename__
            if table_name not in existing_tables:
                print(f"  🔨 {table_name} 생성 중...")
                model.__table__.create(engine, checkfirst=True)
                print(f"  ✅ {table_name} 생성 완료")
        
        print("\n✅ 모든 AI 테이블 생성 완료!")
        
        # 생성 확인
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        print("\n📊 생성 확인:")
        for table in ai_tables:
            if table in existing_tables:
                print(f"  ✅ {table}")
            else:
                print(f"  ❌ {table} (여전히 없음)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 테이블 생성 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_table_info():
    """테이블 정보 표시"""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return
    
    engine = create_engine(database_url)
    inspector = inspect(engine)
    
    ai_tables = [
        'ai_marketing_products',
        'ai_product_keywords',
        'ai_product_references',
        'ai_prompt_templates',
        'ai_prompts',
        'ai_marketing_schedules',
        'ai_generated_posts',
        'cafe_account_links',
        'draft_posts'
    ]
    
    print("\n" + "="*60)
    print("AI 테이블 상세 정보")
    print("="*60)
    
    for table_name in ai_tables:
        if table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            print(f"\n📋 {table_name}:")
            for col in columns:
                print(f"  - {col['name']}: {col['type']}")


if __name__ == "__main__":
    success = create_ai_tables()
    
    if success:
        show_table_info()
        print("\n" + "="*60)
        print("✅ AI 자동화 시스템 테이블 생성 완료!")
        print("="*60)
        print("\n🚀 이제 서버를 재시작하세요:")
        print("   Render Dashboard → Manual Deploy → Deploy latest commit")
    else:
        print("\n" + "="*60)
        print("❌ 테이블 생성 실패")
        print("="*60)
        print("\n💡 해결 방법:")
        print("   1. DATABASE_URL 환경변수 확인")
        print("   2. PostgreSQL 연결 확인")
        print("   3. 로그 확인")
