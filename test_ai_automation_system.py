# test_ai_automation_system.py
"""
AI 자동화 시스템 전체 테스트
- 상품 세팅
- 키워드 관리
- 레퍼런스 관리
- 프롬프트 템플릿
- 프롬프트 관리
- 스케줄 관리
"""

import requests
import json
from datetime import date, timedelta

BASE_URL = "http://localhost:8000"

def test_login():
    """로그인 테스트"""
    print("\n1. 로그인 테스트...")
    
    session = requests.Session()
    response = session.post(f"{BASE_URL}/login", data={
        "username": "admin",
        "password": "admin"
    }, allow_redirects=False)
    
    if response.status_code in [200, 302, 303]:
        print("✅ 로그인 성공")
        return session
    else:
        print(f"❌ 로그인 실패: {response.status_code}")
        return None


def test_ai_product_list(session):
    """AI 상품 목록 조회"""
    print("\n2. AI 상품 목록 조회...")
    
    response = session.get(f"{BASE_URL}/ai-automation/api/products")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 상품 목록 조회 성공: {len(data['products'])}개")
        return data['products']
    else:
        print(f"❌ 실패: {data.get('error')}")
        return []


def test_available_products(session):
    """추가 가능한 상품 목록"""
    print("\n3. 추가 가능한 상품 목록...")
    
    response = session.get(f"{BASE_URL}/ai-automation/api/available-products")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 추가 가능한 상품: {len(data['products'])}개")
        return data['products']
    else:
        print(f"❌ 실패: {data.get('error')}")
        return []


def test_add_ai_product(session, marketing_product_id):
    """AI 상품 추가"""
    print(f"\n4. AI 상품 추가 (마케팅 상품 ID: {marketing_product_id})...")
    
    response = session.post(f"{BASE_URL}/ai-automation/api/products/add/{marketing_product_id}")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 상품 추가 성공: AI 상품 ID = {data['id']}")
        return data['id']
    else:
        print(f"❌ 실패: {data.get('error')}")
        return None


def test_update_ai_product(session, ai_product_id):
    """AI 상품 정보 업데이트"""
    print(f"\n5. AI 상품 정보 업데이트 (ID: {ai_product_id})...")
    
    form_data = {
        'use_for_cafe': 'true',
        'use_for_blog': 'false',
        'product_name': '테스트 상품',
        'core_value': '고품질, 내구성',
        'sub_core_value': '가성비, 디자인',
        'size_weight': '30x20x10cm, 500g',
        'difference': '타사 대비 30% 저렴',
        'famous_brands': 'A브랜드, B브랜드',
        'market_problem': '고가격, 낮은 품질',
        'our_price': '29,900원',
        'market_avg_price': '45,000원',
        'target_age': '20-40대',
        'target_gender': '남녀공용',
        'additional_info': '특별한 기능 포함',
        'marketing_link': 'https://example.com/product'
    }
    
    response = session.post(f"{BASE_URL}/ai-automation/api/products/update/{ai_product_id}", data=form_data)
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 상품 정보 업데이트 성공")
        return True
    else:
        print(f"❌ 실패: {data.get('error')}")
        return False


def test_keywords(session, ai_product_id):
    """키워드 관리 테스트"""
    print(f"\n6. 키워드 관리 테스트 (상품 ID: {ai_product_id})...")
    
    # 키워드 목록 조회
    response = session.get(f"{BASE_URL}/ai-automation/api/products/{ai_product_id}/keywords")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 키워드 목록: {data['count']}개 활성, 총 {data['total']}개")
        
        # 첫 번째 키워드 분류 변경
        if data['keywords']:
            keyword_id = data['keywords'][0]['id']
            print(f"   - 첫 번째 키워드 분류 변경 테스트...")
            
            classify_response = session.post(
                f"{BASE_URL}/ai-automation/keywords/update/{keyword_id}",
                data={'keyword_type': 'alternative'}
            )
            classify_data = classify_response.json()
            
            if classify_data.get('success'):
                print(f"   ✅ 분류 변경 성공")
            else:
                print(f"   ❌ 분류 변경 실패: {classify_data.get('error')}")
        
        return True
    else:
        print(f"❌ 실패: {data.get('error')}")
        return False


def test_references(session, ai_product_id):
    """레퍼런스 관리 테스트"""
    print(f"\n7. 레퍼런스 관리 테스트 (상품 ID: {ai_product_id})...")
    
    # 레퍼런스 목록 조회
    response = session.get(f"{BASE_URL}/ai-automation/api/products/{ai_product_id}/references")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 레퍼런스 목록: {len(data['references'])}개")
        
        # 첫 번째 레퍼런스 분류 변경
        if data['references']:
            ref_id = data['references'][0]['id']
            print(f"   - 첫 번째 레퍼런스 분류 변경 테스트...")
            
            classify_response = session.post(
                f"{BASE_URL}/ai-automation/references/update/{ref_id}",
                data={'reference_type': 'informational'}
            )
            classify_data = classify_response.json()
            
            if classify_data.get('success'):
                print(f"   ✅ 분류 변경 성공")
            else:
                print(f"   ❌ 분류 변경 실패: {classify_data.get('error')}")
        
        return True
    else:
        print(f"❌ 실패: {data.get('error')}")
        return False


def test_prompt_templates(session):
    """프롬프트 템플릿 테스트"""
    print(f"\n8. 프롬프트 템플릿 테스트...")
    
    # 템플릿 목록 조회
    response = session.get(f"{BASE_URL}/ai-automation/api/prompt-templates")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 템플릿 목록: {len(data['templates'])}개")
        return True
    else:
        print(f"❌ 실패: {data.get('error')}")
        return False


def test_prompts(session, ai_product_id):
    """프롬프트 목록 테스트"""
    print(f"\n9. 프롬프트 목록 테스트...")
    
    # 프롬프트 목록 조회
    response = session.get(f"{BASE_URL}/ai-automation/api/prompts?product={ai_product_id}")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 프롬프트 목록: {len(data['prompts'])}개")
        return True
    else:
        print(f"❌ 실패: {data.get('error')}")
        return False


def test_schedules(session):
    """스케줄 목록 테스트"""
    print(f"\n10. 스케줄 목록 테스트...")
    
    # 스케줄 목록 조회
    response = session.get(f"{BASE_URL}/ai-automation/api/schedules?page=1")
    data = response.json()
    
    if data.get('success'):
        print(f"✅ 스케줄 목록: {len(data['schedules'])}개 (페이지 {data['current_page']}/{data['total_pages']})")
        return True
    else:
        print(f"❌ 실패: {data.get('error')}")
        return False


def run_all_tests():
    """전체 테스트 실행"""
    print("="*60)
    print("AI 자동화 시스템 전체 테스트 시작")
    print("="*60)
    
    # 로그인
    session = test_login()
    if not session:
        print("\n❌ 로그인 실패. 테스트 중단.")
        return
    
    # AI 상품 목록
    ai_products = test_ai_product_list(session)
    
    # 추가 가능한 상품
    available_products = test_available_products(session)
    
    # 테스트용 AI 상품 ID (기존 또는 신규)
    ai_product_id = None
    
    if ai_products:
        ai_product_id = ai_products[0]['id']
        print(f"\n   → 기존 AI 상품 사용: ID {ai_product_id}")
    elif available_products:
        # 신규 추가
        ai_product_id = test_add_ai_product(session, available_products[0]['id'])
    
    if not ai_product_id:
        print("\n⚠️  AI 상품이 없습니다. 마케팅 상품을 먼저 추가하세요.")
        return
    
    # 상품 정보 업데이트
    test_update_ai_product(session, ai_product_id)
    
    # 키워드 관리
    test_keywords(session, ai_product_id)
    
    # 레퍼런스 관리
    test_references(session, ai_product_id)
    
    # 프롬프트 템플릿
    test_prompt_templates(session)
    
    # 프롬프트
    test_prompts(session, ai_product_id)
    
    # 스케줄
    test_schedules(session)
    
    print("\n" + "="*60)
    print("✅ 전체 테스트 완료!")
    print("="*60)


if __name__ == "__main__":
    run_all_tests()
