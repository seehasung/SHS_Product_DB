#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
블로그 시스템 초기화 스크립트
실행 방법: python init_blog.py
"""

from database import (
    SessionLocal, Base, engine, User, BlogWorker, 
    BlogAccount, MarketingProduct, BlogProductKeyword
)
import json

def main():
    print("🚀 블로그 시스템 초기화 시작...\n")
    
    # 1. 테이블 생성
    print("1️⃣ 데이터베이스 테이블 생성...")
    Base.metadata.create_all(bind=engine)
    print("✅ 테이블 생성 완료!\n")
    
    db = SessionLocal()
    
    try:
        # 2. 전체 관리자를 블로그 관리자로 자동 등록
        print("2️⃣ 전체 관리자를 블로그 관리자로 등록...")
        admins = db.query(User).filter(User.is_admin == True).all()
        
        for admin in admins:
            # 이미 블로그 작업자인지 확인
            existing = db.query(BlogWorker).filter(
                BlogWorker.user_id == admin.id
            ).first()
            
            if not existing:
                worker = BlogWorker(
                    user_id=admin.id,
                    status='active',
                    daily_quota=0,  # 관리자는 작업 안 함
                    is_blog_manager=True
                )
                db.add(worker)
                print(f"✅ {admin.username}을(를) 블로그 관리자로 등록")
            else:
                # 블로그 관리자 권한 부여
                if not existing.is_blog_manager:
                    existing.is_blog_manager = True
                    db.add(existing)
                    print(f"✅ {admin.username}에게 블로그 관리자 권한 부여")
                else:
                    print(f"ℹ️  {admin.username}은(는) 이미 블로그 관리자")
        
        db.commit()
        print()
        
        # 3. 기존 상품의 키워드 동기화
        print("3️⃣ 상품 키워드 동기화...")
        products = db.query(MarketingProduct).all()
        
        synced_count = 0
        for product in products:
            # 이미 동기화된 상품인지 확인
            existing_keywords = db.query(BlogProductKeyword).filter(
                BlogProductKeyword.marketing_product_id == product.id
            ).first()
            
            if existing_keywords:
                continue
            
            # 키워드 동기화
            if product.keywords:
                keywords = product.keywords
                if isinstance(keywords, str):
                    try:
                        keywords = json.loads(keywords)
                    except:
                        keywords = []
                
                if isinstance(keywords, list) and len(keywords) > 0:
                    for i, keyword in enumerate(keywords):
                        blog_kw = BlogProductKeyword(
                            marketing_product_id=product.id,
                            keyword_text=keyword,
                            is_active=True,
                            order_index=i
                        )
                        db.add(blog_kw)
                    synced_count += 1
        
        db.commit()
        print(f"✅ {synced_count}개 상품의 키워드 동기화 완료!\n")
        
        # 4. 요약
        print("=" * 50)
        print("✨ 초기화 완료!")
        print("=" * 50)
        print(f"📊 통계:")
        print(f"   - 블로그 관리자: {db.query(BlogWorker).filter(BlogWorker.is_blog_manager == True).count()}명")
        print(f"   - 블로그 작업자: {db.query(BlogWorker).count()}명")
        print(f"   - 블로그 계정: {db.query(BlogAccount).count()}개")
        print(f"   - 동기화된 상품: {synced_count}개")
        print()
        print("🎉 이제 /blog 페이지에 접속해보세요!")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()