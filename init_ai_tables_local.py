#!/usr/bin/env python3
"""
AI 자동화 시스템 테이블 생성 (로컬 SQLite용)
로컬에서 실행: python init_ai_tables_local.py
"""

from database import Base, engine, SessionLocal
from database import (
    AIMarketingProduct, AIProductKeyword, AIProductReference,
    AIPromptTemplate, AIPrompt, AIMarketingSchedule, AIGeneratedPost
)
from sqlalchemy import inspect

def create_ai_tables_local():
    """로컬 SQLite에 AI 테이블 생성"""
    print("="*60)
    print("AI 자동화 시스템 테이블 생성 (로컬)")
    print("="*60)
    
    # 기존 테이블 확인
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    print(f"\n📊 기존 테이블: {len(existing_tables)}개")
    
    ai_tables = [
        'ai_marketing_products',
        'ai_product_keywords',
        'ai_product_references',
        'ai_prompt_templates',
        'ai_prompts',
        'ai_marketing_schedules',
        'ai_generated_posts'
    ]
    
    # AI 테이블 확인
    print("\n🔍 AI 테이블 확인:")
    missing = []
    for table in ai_tables:
        if table in existing_tables:
            print(f"  ✅ {table}")
        else:
            print(f"  ❌ {table} (생성 필요)")
            missing.append(table)
    
    if not missing:
        print("\n✅ 모든 테이블이 이미 존재합니다!")
        return True
    
    # 테이블 생성
    print(f"\n🔨 테이블 생성 중... ({len(missing)}개)")
    
    try:
        # 전체 테이블 생성 (없는 것만)
        Base.metadata.create_all(bind=engine, checkfirst=True)
        
        print("\n✅ 테이블 생성 완료!")
        
        # 확인
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        print("\n📊 생성 확인:")
        for table in ai_tables:
            if table in existing_tables:
                print(f"  ✅ {table}")
            else:
                print(f"  ❌ {table} (실패)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def insert_sample_data():
    """샘플 데이터 삽입 (선택사항)"""
    print("\n" + "="*60)
    print("샘플 데이터 삽입")
    print("="*60)
    
    db = SessionLocal()
    
    try:
        # 마케팅 상품이 있는지 확인
        from database import MarketingProduct
        
        mp = db.query(MarketingProduct).first()
        if not mp:
            print("\n⚠️  마케팅 상품이 없습니다. 먼저 상품을 추가하세요.")
            return
        
        # AI 상품이 이미 있는지 확인
        existing = db.query(AIMarketingProduct).filter(
            AIMarketingProduct.marketing_product_id == mp.id
        ).first()
        
        if existing:
            print(f"\n✅ AI 상품이 이미 존재합니다 (ID: {existing.id})")
            return
        
        # 샘플 AI 상품 생성
        print(f"\n🔨 샘플 AI 상품 생성 중...")
        
        ai_product = AIMarketingProduct(
            marketing_product_id=mp.id,
            use_for_cafe=True,
            use_for_blog=False,
            product_name="테스트 상품",
            core_value="고품질 소재 사용",
            sub_core_value="세련된 디자인, 합리적인 가격",
            size_weight="30cm x 20cm x 10cm, 500g",
            difference="타사 대비 30% 저렴하면서도 품질 우수",
            famous_brands="A브랜드, B브랜드, C브랜드",
            market_problem="가격이 비싸고 품질이 일정하지 않음",
            our_price="29,900원",
            market_avg_price="45,000원",
            target_age="20-40대",
            target_gender="남녀공용",
            additional_info="친환경 소재 사용",
            marketing_link="https://example.com/product"
        )
        
        db.add(ai_product)
        db.commit()
        db.refresh(ai_product)
        
        print(f"✅ 샘플 AI 상품 생성 완료 (ID: {ai_product.id})")
        
        # 샘플 프롬프트 템플릿 생성
        print(f"\n🔨 샘플 템플릿 생성 중...")
        
        template_alt = AIPromptTemplate(
            template_name="대안성 기본 템플릿",
            template_type="alternative",
            user_prompt_template="""안녕하세요!

{product_name}에 대해 소개하겠습니다.

제품 특징:
{core_value}

추가 장점:
{sub_core_value}

사이즈: {size_weight}

가격: {our_price} (시장 평균 {market_avg_price} 대비 저렴!)

타사 제품과의 차별점:
{difference}

추천 대상: {target_age}, {target_gender}

자세한 정보: {marketing_link}""",
            is_template=True
        )
        
        template_info = AIPromptTemplate(
            template_name="정보성 기본 템플릿",
            template_type="informational",
            user_prompt_template="""안녕하세요!

{product_name}에 대한 정보를 공유합니다.

이 제품은 {core_value}이 특징입니다.

시장 상황:
현재 시장에서는 {market_problem} 문제가 있습니다.

유명 브랜드: {famous_brands}

가격대: 평균 {market_avg_price} 정도입니다.

더 자세한 내용: {marketing_link}""",
            is_template=True
        )
        
        db.add(template_alt)
        db.add(template_info)
        db.commit()
        
        print(f"✅ 샘플 템플릿 2개 생성 완료")
        
        print("\n" + "="*60)
        print("✅ 샘플 데이터 삽입 완료!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    success = create_ai_tables_local()
    
    if success:
        print("\n" + "="*60)
        
        # 샘플 데이터 삽입 여부 확인
        choice = input("\n샘플 데이터를 삽입하시겠습니까? (y/n): ")
        if choice.lower() == 'y':
            insert_sample_data()
        
        print("\n" + "="*60)
        print("✅ 완료! 이제 서버를 시작하세요:")
        print("   python -m uvicorn main:app --reload --port 8000")
        print("="*60)
