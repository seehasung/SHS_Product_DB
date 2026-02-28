# routers/ai_automation.py
"""
AI 자동화 마케팅 시스템 라우터
- 상품 세팅 페이지
- 프롬프트 관리
- 스케줄 관리
- 신규 발행 관리
- 연동 관리
"""

from fastapi import APIRouter, Request, Form, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, and_
from datetime import date, datetime, timedelta
from typing import Optional, List
import json
import math

from database import (
    SessionLocal, User, Product, MarketingProduct,
    AIMarketingProduct, AIProductKeyword, AIProductReference,
    AIPromptTemplate, AIPrompt, AIMarketingSchedule, AIGeneratedPost,
    AutomationAccount, AutomationCafe, CafeAccountLink, Reference,
    DraftCreationSchedule, AutomationWorkerPC, AutomationTask, DraftPost,
    get_kst_now
)

router = APIRouter(prefix="/ai-automation")
templates = Jinja2Templates(directory="templates")

# ============================================================
# ⭐ 어그로용 한국 음식 이미지 프롬프트 풀 (FLUX 1.1 Pro 최적화)
# ============================================================
KOREAN_FOOD_ATTRACT_POOL = [
    # 삼겹살
    "Thick slices of Korean samgyeopsal pork belly sizzling aggressively on a cast iron grill, extreme close-up, rendered fat dripping, charcoal smoke filling the frame, tongs mid-flip, glistening caramelized surface, banchan dishes blurred in background, shot on Canon EOS R5 85mm f1.4, warm amber restaurant lighting, grain visible, authentic Korean BBQ atmosphere",
    # 소갈비
    "Korean galbi short ribs marinated in soy and pear sauce, caramelizing on a table grill, close-up macro shot with sauce bubbling and charring at edges, sesame seeds glistening, scissors resting beside the grill, slight smoke haze, shot on Nikon Z6 50mm f1.8, tungsten restaurant lighting, food-blogger style, hyper realistic",
    # 부대찌개
    "Bubbling Korean budae-jjigae in a wide aluminum pot on a portable gas burner, ramyeon noodles half-submerged, spam cubes and melted American cheese visible, steam rising aggressively, red broth boiling at edges, ladle resting on pot rim, taken from slightly above at a low-end Korean restaurant table with disposable chopsticks, shot on Samsung Galaxy S24 Ultra, realistic mobile photo, overexposed highlights, authentic look",
    # 치킨맥주
    "A half-eaten plate of Korean yangnyeom fried chicken, dark sticky glaze with sesame seeds, next to a frosted glass of golden draft beer with condensation dripping down, crumpled napkins on table, casual Korean chimaek restaurant booth, neon signs blurred in background, shot on iPhone 15 Pro max portrait mode, evening warm light, candid casual vibe, hyper realistic",
    # 곱창전골
    "Korean gopchang gui beef small intestine sizzling on a round charcoal grill, dark caramelized exterior, glistening with fat, green onion pieces scattered, doenjang dipping sauce bowl beside it, shot on Sony A7IV 35mm f1.8, low angle close-up, warm izakaya lighting, realistic texture detail, slight motion blur from tongs",
    # 떡볶이
    "Steaming Korean tteokbokki in a wide shallow pan at a street pojangmacha stall, glossy red gochujang sauce clinging to rice cakes, fish cakes and boiled eggs visible, fried mandu on a separate tray beside it, fluorescent overhead lighting casting sharp shadows, taken on a worn plastic tray, candid mobile snapshot style, Samsung A54 quality, slight overexposure, authentic street food grit",
    # 순대국밥
    "A deep earthenware bowl of Korean sundae-gukbap, milky white bone broth with sliced blood sausage and pork intestines, green onion and doenjang on the side, steaming heavily, small dish of sea salt and shrimp paste beside it, worn wooden table at a traditional Korean restaurant, harsh fluorescent light, realistic candid mobile photo, grainy texture",
    # 냉면
    "A stainless steel bowl of Korean mul-naengmyeon, thin buckwheat noodles in cold clear beef broth with floating ice chips, half a boiled egg, sliced pear and cucumber, mustard and vinegar bottles nearby, bright overhead cafeteria-style lighting, top-down flat lay shot, metal chopsticks resting on bowl rim, shot on iPhone 14, realistic and cold-feeling",
    # 해물파전
    "Korean haemul pajeon seafood pancake fresh off a cast iron pan, golden crispy edges, green onion stalks and squid pieces visible, served on a dark plate with soy dipping sauce in a small bowl, steam still rising, shot from 45-degree angle on a wooden table, shot on Fujifilm X-T5 with 35mm lens, warm soft kitchen light, appetizing hyper-realistic texture",
    # 된장찌개
    "A clay pot of Korean doenjang-jjigae fermented soybean paste stew bubbling on a portable gas stove, tofu cubes and zucchini floating, dark brown broth with white foam at edges, served with rice in a metal bowl beside it, small banchan dishes of kimchi and spinach, worn restaurant plastic table, harsh fluorescent lighting, mobile phone snapshot, authentic everyday Korean meal",
    # 비빔밥
    "A stone pot dolsot bibimbap sizzling at the edges, colorful namul vegetables arranged in sections around a raw egg yolk center, gochujang dollop on top, sesame oil gleaming, served on a wooden tray at a Korean restaurant, customer's hand reaching in with a spoon about to mix, shot on Sony A6700 55mm, warm window light, realistic lifestyle food photo",
    # 칼국수
    "A wide bowl of Korean kalguksu knife-cut noodle soup, thick handmade noodles in a milky anchovy broth, zucchini and clams visible, light steam rising, chopsticks mid-lift pulling noodles, taken at a busy Korean noodle restaurant, bright fluorescent light, slight motion blur on noodles, shot on Samsung Galaxy S23, authentic lunch vibe",
    # 보쌈
    "Korean bossam platter, sliced pork belly cooked soft and tender, arranged next to a fresh head of napa cabbage leaf, fermented kimchi, salted shrimp, and thinly sliced raw garlic, all on a large black plate, customer wrapping a piece into a ssam, close-up shot on Canon EOS M50 50mm f1.8, warm izakaya lighting, hyper realistic texture",
    # 라면
    "A single-serving pot of Korean ramyeon on a portable gas stove, bright orange broth boiling vigorously, noodles just placed and starting to soften, an egg cracked in still mostly raw, green onion slices on surface, eaten alone at a small table with a window view at night, soft lamp light, shot on iPhone 13 mini, cozy late-night vibe, realistic mobile photo quality",
    # 카페 디저트
    "A freshly baked Korean-style soufflé castella slice and an iced dirty coffee on a white ceramic plate at a minimalist Korean dessert cafe, natural window light creating soft shadows, condensation on the glass, small spoon resting beside, marble tabletop, blurred cafe interior bokeh, shot on iPhone 15 Pro portrait mode, bright airy morning atmosphere, Instagram lifestyle aesthetic",
]

# Imagen 3 이미지 생성 함수
async def generate_images_with_imagen(prompt: str, num_images: int = 3) -> List[str]:
    """Imagen 3로 이미지 생성"""
    try:
        from google.cloud import aiplatform
        from vertexai.preview.vision_models import ImageGenerationModel
        import os
        import json
        import tempfile
        
        project_id = os.environ.get('GOOGLE_PROJECT_ID')
        location = os.environ.get('GOOGLE_LOCATION', 'us-central1')
        credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
        
        if not project_id or not credentials_json:
            print("⚠️ Google Cloud 환경 변수가 설정되지 않았습니다")
            return []
        
        # JSON 문자열을 임시 파일로 저장
        credentials = json.loads(credentials_json)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(credentials, f)
            credentials_path = f.name
        
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        aiplatform.init(project=project_id, location=location)
        
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        
        images = model.generate_images(
            prompt=prompt,
            number_of_images=num_images,
            aspect_ratio="1:1",
            safety_filter_level="block_some",
            person_generation="allow_adult"
        )
        
        # 이미지 URL 리스트 반환
        image_urls = []
        for image in images:
            # 실제 구현 시: Cloud Storage에 업로드하고 URL 반환
            image_urls.append(f"https://storage.googleapis.com/bucket/image_{len(image_urls)}.png")
        
        return image_urls
        
    except Exception as e:
        print(f"Imagen 이미지 생성 오류: {e}")
        return []


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session) -> User:
    """현재 로그인한 사용자 조회"""
    username = request.session.get("user")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


# ============================================
# 1. 상품 세팅 페이지
# ============================================

@router.get("/product-setup", response_class=HTMLResponse)
async def product_setup_page(request: Request, db: Session = Depends(get_db)):
    """상품 세팅 페이지"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # AI 자동화 상품 목록 조회 (순서대로)
    ai_products = db.query(AIMarketingProduct).options(
        joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
    ).all()
    
    # 추가 가능한 상품 목록 (상품관리에 있지만 AI 자동화에 없는 것들)
    existing_ids = [ap.marketing_product_id for ap in ai_products]
    available_products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).filter(MarketingProduct.id.notin_(existing_ids)).all()
    
    return templates.TemplateResponse("ai_automation/product_setup.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "can_manage_marketing": current_user.can_manage_marketing or current_user.is_admin,
        "ai_products": ai_products,
        "available_products": available_products
    })


@router.post("/product-setup/add/{marketing_product_id}")
async def add_ai_product(
    marketing_product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """마케팅 상품을 AI 자동화 상품으로 추가"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    # 이미 존재하는지 확인
    existing = db.query(AIMarketingProduct).filter(
        AIMarketingProduct.marketing_product_id == marketing_product_id
    ).first()
    
    if existing:
        return JSONResponse({"success": False, "error": "이미 추가된 상품입니다"}, status_code=400)
    
    # 마케팅 상품 정보 조회
    mp = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).filter(MarketingProduct.id == marketing_product_id).first()
    
    if not mp or not mp.product:
        return JSONResponse({"success": False, "error": "상품을 찾을 수 없습니다"}, status_code=404)
    
    # AI 상품 생성 (기본값으로)
    ai_product = AIMarketingProduct(
        marketing_product_id=marketing_product_id,
        use_for_blog=False,
        use_for_cafe=True,  # 기본값: 카페만 체크
        product_name=mp.product.name,
        core_value="",
        sub_core_value="",
        size_weight="",
        difference="",
        famous_brands="",
        market_problem="",
        our_price="",
        market_avg_price="",
        target_age="",
        target_gender="",
        marketing_link=""
    )
    
    db.add(ai_product)
    db.commit()
    db.refresh(ai_product)
    
    return JSONResponse({"success": True, "ai_product_id": ai_product.id})


@router.post("/product-setup/update/{ai_product_id}")
async def update_ai_product(
    ai_product_id: int,
    request: Request,
    use_for_blog: bool = Form(False),
    use_for_cafe: bool = Form(False),
    product_name: str = Form(...),
    core_value: str = Form(...),
    sub_core_value: str = Form(...),
    size_weight: str = Form(...),
    difference: str = Form(...),
    famous_brands: str = Form(...),
    market_problem: str = Form(...),
    our_price: str = Form(...),
    market_avg_price: str = Form(...),
    target_age: str = Form(...),
    target_gender: str = Form(...),
    marketing_link: str = Form(...),
    additional_info: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """AI 상품 정보 업데이트"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    ai_product = db.query(AIMarketingProduct).filter(
        AIMarketingProduct.id == ai_product_id
    ).first()
    
    if not ai_product:
        return RedirectResponse("/ai-automation/product-setup?error=not_found", status_code=303)
    
    # 업데이트
    ai_product.use_for_blog = use_for_blog
    ai_product.use_for_cafe = use_for_cafe
    ai_product.product_name = product_name
    ai_product.core_value = core_value
    ai_product.sub_core_value = sub_core_value
    ai_product.size_weight = size_weight
    ai_product.difference = difference
    ai_product.famous_brands = famous_brands
    ai_product.market_problem = market_problem
    ai_product.our_price = our_price
    ai_product.market_avg_price = market_avg_price
    ai_product.target_age = target_age
    ai_product.target_gender = target_gender
    ai_product.marketing_link = marketing_link
    ai_product.additional_info = additional_info
    
    db.commit()
    
    return RedirectResponse("/ai-automation/product-setup", status_code=303)


# ============================================
# 2. 키워드 관리
# ============================================

@router.get("/keywords/{ai_product_id}", response_class=HTMLResponse)
async def manage_keywords(
    ai_product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """키워드 관리 페이지"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # AI 상품 조회
    ai_product = db.query(AIMarketingProduct).options(
        joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
    ).filter(AIMarketingProduct.id == ai_product_id).first()
    
    if not ai_product:
        return RedirectResponse("/ai-automation/product-setup?error=not_found", status_code=303)
    
    # 키워드 목록 조회
    keywords = db.query(AIProductKeyword).filter(
        AIProductKeyword.ai_product_id == ai_product_id
    ).all()
    
    return templates.TemplateResponse("ai_automation/keywords.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "ai_product": ai_product,
        "keywords": keywords
    })


@router.post("/keywords/sync/{ai_product_id}")
async def sync_keywords_from_marketing(
    ai_product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """마케팅 - 카페의 키워드를 동기화"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    ai_product = db.query(AIMarketingProduct).filter(
        AIMarketingProduct.id == ai_product_id
    ).first()
    
    if not ai_product:
        return JSONResponse({"success": False, "error": "상품을 찾을 수 없습니다"}, status_code=404)
    
    # 마케팅 상품의 키워드 가져오기
    mp = db.query(MarketingProduct).filter(
        MarketingProduct.id == ai_product.marketing_product_id
    ).first()
    
    if not mp or not mp.keywords:
        return JSONResponse({"success": False, "error": "키워드가 없습니다"}, status_code=400)
    
    try:
        keywords_data = json.loads(mp.keywords)
    except:
        return JSONResponse({"success": False, "error": "키워드 형식 오류"}, status_code=400)
    
    # 기존 AI 키워드 확인
    existing_keywords = {kw.keyword_text for kw in db.query(AIProductKeyword).filter(
        AIProductKeyword.ai_product_id == ai_product_id
    ).all()}
    
    added_count = 0
    for kw_item in keywords_data:
        if not kw_item.get('active', True):
            continue
        
        keyword_text = kw_item['keyword']
        if keyword_text not in existing_keywords:
            # 신규 키워드 추가 (미분류로)
            new_kw = AIProductKeyword(
                ai_product_id=ai_product_id,
                keyword_text=keyword_text,
                keyword_type='unclassified',
                is_active=True
            )
            db.add(new_kw)
            added_count += 1
    
    db.commit()
    
    return JSONResponse({"success": True, "added_count": added_count})


@router.post("/keywords/update/{keyword_id}")
async def update_keyword_classification(
    keyword_id: int,
    keyword_type: str = Form(...),
    db: Session = Depends(get_db)
):
    """키워드 분류 업데이트"""
    keyword = db.query(AIProductKeyword).filter(AIProductKeyword.id == keyword_id).first()
    
    if not keyword:
        return JSONResponse({"success": False, "error": "키워드를 찾을 수 없습니다"}, status_code=404)
    
    if keyword_type not in ['alternative', 'informational', 'unclassified']:
        return JSONResponse({"success": False, "error": "잘못된 분류입니다"}, status_code=400)
    
    keyword.keyword_type = keyword_type
    db.commit()
    
    return JSONResponse({"success": True})


@router.post("/keywords/add/{ai_product_id}")
async def add_keyword(
    ai_product_id: int,
    keyword_text: str = Form(...),
    keyword_type: str = Form('unclassified'),
    db: Session = Depends(get_db)
):
    """신규 키워드 추가"""
    # 중복 체크
    existing = db.query(AIProductKeyword).filter(
        AIProductKeyword.ai_product_id == ai_product_id,
        AIProductKeyword.keyword_text == keyword_text
    ).first()
    
    if existing:
        return JSONResponse({"success": False, "error": "이미 존재하는 키워드입니다"}, status_code=400)
    
    new_keyword = AIProductKeyword(
        ai_product_id=ai_product_id,
        keyword_text=keyword_text,
        keyword_type=keyword_type,
        is_active=True
    )
    
    db.add(new_keyword)
    db.commit()
    
    return JSONResponse({"success": True})


@router.post("/keywords/delete/{keyword_id}")
async def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """키워드 삭제"""
    keyword = db.query(AIProductKeyword).filter(AIProductKeyword.id == keyword_id).first()
    
    if keyword:
        db.delete(keyword)
        db.commit()
    
    return JSONResponse({"success": True})


@router.get("/api/products/list")
async def get_ai_products_list(
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 상품 목록 (필터용) - 반드시 /api/products/{product_id} 라우트보다 먼저 정의"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    try:
        products = db.query(AIMarketingProduct).order_by(AIMarketingProduct.id.desc()).all()
        return JSONResponse({
            'success': True,
            'products': [{'id': p.id, 'product_name': p.product_name} for p in products]
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/products/{product_id}/keywords")
async def get_product_keywords(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 상품의 키워드 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        keywords = db.query(AIProductKeyword).filter(
            AIProductKeyword.ai_product_id == product_id
        ).order_by(AIProductKeyword.keyword_text).all()

        # 키워드별 수정발행 완료 횟수 계산 (keyword 컬럼 기준)
        publish_counts = {}
        for kw in keywords:
            cnt = db.query(AutomationTask).filter(
                AutomationTask.task_type == 'post',
                AutomationTask.keyword == kw.keyword_text,
                AutomationTask.status == 'completed'
            ).count()
            publish_counts[kw.id] = cnt

        keywords_data = [{
            'id': kw.id,
            'keyword_text': kw.keyword_text,
            'keyword_type': kw.keyword_type,
            'is_active': kw.is_active,
            'publish_count': publish_counts.get(kw.id, 0),
            'max_publish': 6,
        } for kw in keywords]

        active_count = sum(1 for kw in keywords if kw.is_active)

        return JSONResponse({
            'success': True,
            'keywords': keywords_data,
            'count': active_count,
            'total': len(keywords_data)
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/keywords/{keyword_id}/publish-history")
async def get_keyword_publish_history(
    keyword_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """키워드별 수정발행 내역 조회"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)

    try:
        kw = db.query(AIProductKeyword).filter(AIProductKeyword.id == keyword_id).first()
        if not kw:
            return JSONResponse({"success": False, "error": "키워드를 찾을 수 없습니다"}, status_code=404)

        tasks = db.query(AutomationTask).filter(
            AutomationTask.task_type == 'post',
            AutomationTask.keyword == kw.keyword_text,
            AutomationTask.status == 'completed'
        ).order_by(AutomationTask.completed_at.desc()).all()

        history = []
        for t in tasks:
            acc = db.query(AutomationAccount).filter(AutomationAccount.id == t.assigned_account_id).first()
            cafe = db.query(AutomationCafe).filter(AutomationCafe.id == t.cafe_id).first()
            draft_url = None
            if t.error_message and 'MODIFY_URL:' in t.error_message:
                draft_url = t.error_message.split('MODIFY_URL:')[1].strip()
            history.append({
                'task_id': t.id,
                'account_id': acc.account_id if acc else '',
                'cafe_name': cafe.name if cafe else '',
                'cafe_url': cafe.url if cafe else '',
                'post_url': t.post_url or '',
                'draft_url': draft_url or '',
                'completed_at': (t.completed_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if t.completed_at else None,
            })

        return JSONResponse({
            'success': True,
            'keyword_text': kw.keyword_text,
            'publish_count': len(history),
            'max_publish': 6,
            'history': history,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 3. 레퍼런스 관리
# ============================================

@router.get("/references/{ai_product_id}", response_class=HTMLResponse)
async def manage_references(
    ai_product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """레퍼런스 관리 페이지"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # AI 상품 조회
    ai_product = db.query(AIMarketingProduct).options(
        joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
    ).filter(AIMarketingProduct.id == ai_product_id).first()
    
    if not ai_product:
        return RedirectResponse("/ai-automation/product-setup?error=not_found", status_code=303)
    
    # 레퍼런스 목록 조회
    ai_references = db.query(AIProductReference).options(
        joinedload(AIProductReference.reference).joinedload(Reference.comments)
    ).filter(AIProductReference.ai_product_id == ai_product_id).all()
    
    return templates.TemplateResponse("ai_automation/references.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "ai_product": ai_product,
        "ai_references": ai_references
    })


@router.post("/references/sync/{ai_product_id}")
async def sync_references_from_marketing(
    ai_product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """마케팅 - 카페의 레퍼런스를 동기화"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    # 모든 레퍼런스 가져오기
    all_references = db.query(Reference).all()
    
    # 기존 AI 레퍼런스 확인
    existing_ref_ids = {ref.reference_id for ref in db.query(AIProductReference).filter(
        AIProductReference.ai_product_id == ai_product_id
    ).all()}
    
    added_count = 0
    for ref in all_references:
        if ref.id not in existing_ref_ids:
            # 신규 레퍼런스 추가 (미분류로)
            new_ref = AIProductReference(
                ai_product_id=ai_product_id,
                reference_id=ref.id,
                reference_type='unclassified'
            )
            db.add(new_ref)
            added_count += 1
    
    db.commit()
    
    return JSONResponse({"success": True, "added_count": added_count})


@router.post("/references/update/{ai_ref_id}")
async def update_reference_classification(
    ai_ref_id: int,
    reference_type: str = Form(...),
    db: Session = Depends(get_db)
):
    """레퍼런스 분류 업데이트"""
    ai_ref = db.query(AIProductReference).filter(AIProductReference.id == ai_ref_id).first()
    
    if not ai_ref:
        return JSONResponse({"success": False, "error": "레퍼런스를 찾을 수 없습니다"}, status_code=404)
    
    if reference_type not in ['alternative', 'informational', 'unclassified']:
        return JSONResponse({"success": False, "error": "잘못된 분류입니다"}, status_code=400)
    
    ai_ref.reference_type = reference_type
    db.commit()
    
    return JSONResponse({"success": True})


@router.post("/references/add/{ai_product_id}")
async def add_ai_reference(
    ai_product_id: int,
    reference_id: int = Form(...),
    reference_type: str = Form('unclassified'),
    db: Session = Depends(get_db)
):
    """AI 레퍼런스 추가 (기존 Reference 연결)"""
    # 중복 체크
    existing = db.query(AIProductReference).filter(
        AIProductReference.ai_product_id == ai_product_id,
        AIProductReference.reference_id == reference_id
    ).first()
    
    if existing:
        return JSONResponse({"success": False, "error": "이미 추가된 레퍼런스입니다"}, status_code=400)
    
    ai_ref = AIProductReference(
        ai_product_id=ai_product_id,
        reference_id=reference_id,
        reference_type=reference_type
    )
    
    db.add(ai_ref)
    db.commit()
    
    return JSONResponse({"success": True})


@router.post("/references/delete/{ai_ref_id}")
async def delete_ai_reference(ai_ref_id: int, db: Session = Depends(get_db)):
    """AI 레퍼런스 삭제 (연결만 끊기, 원본은 유지)"""
    ai_ref = db.query(AIProductReference).filter(AIProductReference.id == ai_ref_id).first()
    
    if ai_ref:
        db.delete(ai_ref)
        db.commit()
    
    return JSONResponse({"success": True})


@router.get("/api/products/{product_id}/references")
async def get_product_references(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 상품의 레퍼런스 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        ai_refs = db.query(AIProductReference).options(
            joinedload(AIProductReference.reference)
        ).filter(
            AIProductReference.ai_product_id == product_id
        ).all()
        
        refs_data = []
        for ai_ref in ai_refs:
            if ai_ref.reference:
                refs_data.append({
                    'id': ai_ref.id,
                    'reference_id': ai_ref.reference_id,
                    'title': ai_ref.reference.title,
                    'ref_type': ai_ref.reference.ref_type,
                    'content': ai_ref.reference.content,
                    'reference_type': ai_ref.reference_type
                })
        
        return JSONResponse({'success': True, 'references': refs_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 4. 프롬프트 템플릿 관리
# ============================================

@router.get("/prompt-templates", response_class=HTMLResponse)
async def prompt_templates_page(request: Request, db: Session = Depends(get_db)):
    """프롬프트 템플릿 관리 페이지"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # 템플릿만 조회
    templates_list = db.query(AIPromptTemplate).filter(
        AIPromptTemplate.is_template == True
    ).all()
    
    return templates.TemplateResponse("ai_automation/prompt_templates.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "templates_list": templates_list
    })


@router.post("/prompt-templates/add")
async def add_prompt_template(
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 추가"""
    if template_type not in ['alternative', 'informational']:
        return JSONResponse({"success": False, "error": "잘못된 분류입니다"}, status_code=400)
    
    new_template = AIPromptTemplate(
        template_name=template_name,
        template_type=template_type,
        user_prompt_template=user_prompt_template,
        is_template=True
    )
    
    db.add(new_template)
    db.commit()
    
    return JSONResponse({"success": True})


@router.post("/prompt-templates/update/{template_id}")
async def update_prompt_template(
    template_id: int,
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 수정"""
    template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
    
    if not template:
        return JSONResponse({"success": False, "error": "템플릿을 찾을 수 없습니다"}, status_code=404)
    
    template.template_name = template_name
    template.template_type = template_type
    template.user_prompt_template = user_prompt_template
    
    db.commit()
    
    return JSONResponse({"success": True})


@router.post("/prompt-templates/delete/{template_id}")
async def delete_prompt_template(template_id: int, db: Session = Depends(get_db)):
    """프롬프트 템플릿 삭제"""
    template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
    
    if template:
        db.delete(template)
        db.commit()
    
    return JSONResponse({"success": True})


@router.post("/api/prompt-templates/duplicate/{template_id}")
async def duplicate_prompt_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 복제 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        original = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if not original:
            return JSONResponse({'success': False, 'error': '템플릿을 찾을 수 없습니다'}, status_code=404)
        
        # 복제 생성
        duplicate = AIPromptTemplate(
            template_name=f"{original.template_name} (복사본)",
            template_type=original.template_type,
            user_prompt_template=original.user_prompt_template,
            is_template=True
        )
        
        db.add(duplicate)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/prompt-templates/update/{template_id}")
async def update_prompt_template_json(
    template_id: int,
    request: Request,
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 수정 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if not template:
            return JSONResponse({'success': False, 'error': '템플릿을 찾을 수 없습니다'}, status_code=404)
        
        template.template_name = template_name
        template.template_type = template_type
        template.user_prompt_template = user_prompt_template
        
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/prompt-templates/delete/{template_id}")
async def delete_prompt_template_json(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 삭제 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if template:
            db.delete(template)
            db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/prompt-templates/add")
async def api_add_prompt_template(
    request: Request,
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        if template_type not in ['alternative', 'informational']:
            return JSONResponse({'success': False, 'error': '잘못된 분류입니다'}, status_code=400)
        
        template = AIPromptTemplate(
            template_name=template_name,
            template_type=template_type,
            user_prompt_template=user_prompt_template,
            is_template=True
        )
        
        db.add(template)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 5. 프롬프트 관리 (상품별)
# ============================================

@router.get("/prompts", response_class=HTMLResponse)
async def prompts_page(
    request: Request,
    product_filter: Optional[int] = Query(None),
    type_filter: Optional[str] = Query('all'),
    db: Session = Depends(get_db)
):
    """프롬프트 관리 페이지"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # AI 상품 목록
    ai_products = db.query(AIMarketingProduct).options(
        joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
    ).all()
    
    # 프롬프트 목록 조회
    prompts_query = db.query(AIPrompt).options(
        joinedload(AIPrompt.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
    )
    
    if product_filter:
        prompts_query = prompts_query.filter(AIPrompt.ai_product_id == product_filter)
    
    if type_filter != 'all':
        prompts_query = prompts_query.filter(AIPrompt.keyword_classification == type_filter)
    
    prompts = prompts_query.all()
    
    # 템플릿 목록
    templates_list = db.query(AIPromptTemplate).filter(
        AIPromptTemplate.is_template == True
    ).all()
    
    return templates.TemplateResponse("ai_automation/prompts.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "ai_products": ai_products,
        "prompts": prompts,
        "templates_list": templates_list,
        "product_filter": product_filter,
        "type_filter": type_filter
    })


@router.post("/prompts/add")
async def add_prompt(
    ai_product_id: int = Form(...),
    keyword_classification: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt: str = Form(...),
    temperature: float = Form(0.7),
    max_tokens: int = Form(2000),
    generate_images: bool = Form(False),
    db: Session = Depends(get_db)
):
    """프롬프트 추가 (HTML Redirect)"""
    if keyword_classification not in ['alternative', 'informational']:
        return JSONResponse({"success": False, "error": "잘못된 분류입니다"}, status_code=400)
    
    new_prompt = AIPrompt(
        ai_product_id=ai_product_id,
        keyword_classification=keyword_classification,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        generate_images=generate_images
    )
    
    db.add(new_prompt)
    db.commit()
    
    return RedirectResponse("/ai-automation/prompts", status_code=303)


@router.post("/api/prompts/add")
async def add_prompt_json(
    request: Request,
    ai_product_id: int = Form(...),
    keyword_classification: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt: str = Form(...),
    temperature: float = Form(0.7),
    max_tokens: int = Form(2000),
    generate_images: bool = Form(False),
    num_product_images: int = Form(1),
    num_attract_images: int = Form(2),
    product_image_style: str = Form(''),
    attract_image_prompts: str = Form(''),
    db: Session = Depends(get_db)
):
    """프롬프트 추가 (JSON Response)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        if keyword_classification not in ['alternative', 'informational']:
            return JSONResponse({"success": False, "error": "잘못된 분류입니다"}, status_code=400)
        
        new_prompt = AIPrompt(
            ai_product_id=ai_product_id,
            keyword_classification=keyword_classification,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            generate_images=generate_images,
            num_product_images=num_product_images,
            num_attract_images=num_attract_images,
            product_image_style=product_image_style or None,
            attract_image_prompts=attract_image_prompts or None
        )
        
        db.add(new_prompt)
        db.commit()
        db.refresh(new_prompt)
        
        return JSONResponse({"success": True, "id": new_prompt.id})
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/api/prompts/{prompt_id}")
async def get_prompt_detail(
    prompt_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """프롬프트 상세 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        prompt = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
        ).filter(AIPrompt.id == prompt_id).first()
        
        if not prompt:
            return JSONResponse({'success': False, 'error': '프롬프트를 찾을 수 없습니다'}, status_code=404)
        
        return JSONResponse({
            'success': True,
            'prompt': {
                'id': prompt.id,
                'ai_product_id': prompt.ai_product_id,
                'product_name': prompt.ai_product.product_name if prompt.ai_product else '',
                'keyword_classification': prompt.keyword_classification,
                'system_prompt': prompt.system_prompt,
                'user_prompt': prompt.user_prompt,
                'temperature': prompt.temperature,
                'max_tokens': prompt.max_tokens,
                'generate_images': prompt.generate_images,
                'apply_cafe_context': prompt.apply_cafe_context,
                'num_product_images': prompt.num_product_images or 1,
                'num_attract_images': prompt.num_attract_images or 2,
                'product_image_style': prompt.product_image_style or '',
                'attract_image_prompts': prompt.attract_image_prompts or ''
            }
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/prompts/update/{prompt_id}")
async def update_prompt_json(
    prompt_id: int,
    request: Request,
    ai_product_id: int = Form(...),
    keyword_classification: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt: str = Form(...),
    temperature: float = Form(...),
    max_tokens: int = Form(...),
    generate_images: bool = Form(False),
    apply_cafe_context: bool = Form(False),
    num_product_images: int = Form(1),
    num_attract_images: int = Form(2),
    product_image_style: str = Form(''),
    attract_image_prompts: str = Form(''),
    db: Session = Depends(get_db)
):
    """프롬프트 수정 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        prompt = db.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()
        
        if not prompt:
            return JSONResponse({'success': False, 'error': '프롬프트를 찾을 수 없습니다'}, status_code=404)
        
        if keyword_classification not in ['alternative', 'informational']:
            return JSONResponse({'success': False, 'error': '잘못된 분류입니다'}, status_code=400)
        
        # 수정
        prompt.ai_product_id = ai_product_id
        prompt.keyword_classification = keyword_classification
        prompt.system_prompt = system_prompt
        prompt.user_prompt = user_prompt
        prompt.temperature = temperature
        prompt.max_tokens = max_tokens
        prompt.generate_images = generate_images
        prompt.apply_cafe_context = apply_cafe_context
        prompt.num_product_images = num_product_images
        prompt.num_attract_images = num_attract_images
        prompt.product_image_style = product_image_style or None
        prompt.attract_image_prompts = attract_image_prompts or None
        
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/prompts/update/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    keyword_classification: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt: str = Form(...),
    temperature: float = Form(0.7),
    max_tokens: int = Form(2000),
    generate_images: bool = Form(False),
    db: Session = Depends(get_db)
):
    """프롬프트 수정"""
    prompt = db.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()
    
    if not prompt:
        return JSONResponse({"success": False, "error": "프롬프트를 찾을 수 없습니다"}, status_code=404)
    
    prompt.keyword_classification = keyword_classification
    prompt.system_prompt = system_prompt
    prompt.user_prompt = user_prompt
    prompt.temperature = temperature
    prompt.max_tokens = max_tokens
    prompt.generate_images = generate_images
    
    db.commit()
    
    return RedirectResponse("/ai-automation/prompts", status_code=303)


@router.post("/prompts/delete/{prompt_id}")
async def delete_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """프롬프트 삭제"""
    prompt = db.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()
    
    if prompt:
        db.delete(prompt)
        db.commit()
    
    return JSONResponse({"success": True})


@router.post("/api/prompts/delete/{prompt_id}")
async def delete_prompt_json(
    prompt_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """프롬프트 삭제 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        # 해당 프롬프트를 사용하는 스케줄 확인
        schedules = db.query(AIMarketingSchedule).filter(
            AIMarketingSchedule.prompt_id == prompt_id
        ).count()
        
        if schedules > 0:
            return JSONResponse({
                "success": False, 
                "error": f"이 프롬프트를 사용하는 스케줄이 {schedules}개 있습니다. 스케줄을 먼저 삭제해주세요."
            }, status_code=400)
        
        prompt = db.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()
        
        if prompt:
            db.delete(prompt)
            db.commit()
        
        return JSONResponse({"success": True})
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ============================================
# 6. 스케줄 관리
# ============================================

@router.get("/schedules", response_class=HTMLResponse)
async def schedules_page(
    request: Request,
    page: int = Query(1, ge=1),
    product_search: str = Query(""),
    status_filter: str = Query('all'),
    db: Session = Depends(get_db)
):
    """스케줄 관리 페이지 (페이지네이션 + 검색)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    PAGE_SIZE = 20
    
    # 스케줄 쿼리
    schedules_query = db.query(AIMarketingSchedule).options(
        joinedload(AIMarketingSchedule.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product),
        joinedload(AIMarketingSchedule.prompt)
    )
    
    # 검색 필터
    if product_search:
        schedules_query = schedules_query.join(
            AIMarketingProduct,
            AIMarketingSchedule.ai_product_id == AIMarketingProduct.id
        ).join(
            MarketingProduct,
            AIMarketingProduct.marketing_product_id == MarketingProduct.id
        ).join(
            Product,
            MarketingProduct.product_id == Product.id
        ).filter(Product.name.like(f"%{product_search}%"))
    
    # 상태 필터
    if status_filter != 'all':
        schedules_query = schedules_query.filter(AIMarketingSchedule.status == status_filter)
    
    # 전체 개수
    total_schedules = schedules_query.count()
    total_pages = math.ceil(total_schedules / PAGE_SIZE)
    
    # 페이지네이션
    offset = (page - 1) * PAGE_SIZE
    schedules = schedules_query.order_by(AIMarketingSchedule.created_at.desc()).offset(offset).limit(PAGE_SIZE).all()
    
    # AI 상품 목록 (스케줄 생성용)
    ai_products = db.query(AIMarketingProduct).options(
        joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product),
        joinedload(AIMarketingProduct.keywords)
    ).all()
    
    # 각 상품별 키워드 수 계산
    for ap in ai_products:
        ap.keyword_count = db.query(AIProductKeyword).filter(
            AIProductKeyword.ai_product_id == ap.id,
            AIProductKeyword.is_active == True
        ).count()
    
    return templates.TemplateResponse("ai_automation/schedules.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "schedules": schedules,
        "ai_products": ai_products,
        "current_page": page,
        "total_pages": total_pages,
        "product_search": product_search,
        "status_filter": status_filter
    })


@router.post("/schedules/add")
async def add_schedule(
    ai_product_id: int = Form(...),
    prompt_id: int = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    daily_post_count: int = Form(...),
    db: Session = Depends(get_db)
):
    """스케줄 추가"""
    # 예상 총 글 발행 수 계산 (주말 제외)
    current = start_date
    work_days = 0
    while current <= end_date:
        if current.weekday() < 5:  # 월~금
            work_days += 1
        current += timedelta(days=1)
    
    expected_total = work_days * daily_post_count
    
    new_schedule = AIMarketingSchedule(
        ai_product_id=ai_product_id,
        prompt_id=prompt_id,
        start_date=start_date,
        end_date=end_date,
        daily_post_count=daily_post_count,
        expected_total_posts=expected_total,
        status='scheduled'
    )
    
    db.add(new_schedule)
    db.commit()
    
    return RedirectResponse("/ai-automation/schedules", status_code=303)


@router.post("/api/schedules/add")
async def add_schedule_json(
    request: Request,
    ai_product_id: int = Form(...),
    prompt_id: int = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    daily_post_count: int = Form(...),
    scheduled_hour: int = Form(9),
    scheduled_minute: int = Form(0),
    repeat_type: str = Form('daily'),
    repeat_days: str = Form(None),
    posts_per_account: int = Form(1),
    db: Session = Depends(get_db)
):
    """스케줄 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)

    try:
        # 예상 총 글 발행 수 계산 (주말 제외)
        current_d = start_date
        work_days = 0
        while current_d <= end_date:
            if current_d.weekday() < 5:
                work_days += 1
            current_d += timedelta(days=1)

        expected_total = work_days * daily_post_count

        # next_run_at 계산
        next_run = _calc_next_run(scheduled_hour, scheduled_minute, repeat_type, repeat_days)

        new_schedule = AIMarketingSchedule(
            ai_product_id=ai_product_id,
            prompt_id=prompt_id,
            start_date=start_date,
            end_date=end_date,
            daily_post_count=daily_post_count,
            expected_total_posts=expected_total,
            scheduled_hour=scheduled_hour,
            scheduled_minute=scheduled_minute,
            repeat_type=repeat_type,
            repeat_days=repeat_days,
            posts_per_account=posts_per_account,
            next_run_at=next_run,
            is_active=True,
            status='scheduled'
        )

        db.add(new_schedule)
        db.commit()
        db.refresh(new_schedule)

        return JSONResponse({"success": True, "id": new_schedule.id})
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/schedules/delete/{schedule_id}")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """스케줄 삭제"""
    schedule = db.query(AIMarketingSchedule).filter(AIMarketingSchedule.id == schedule_id).first()
    
    if schedule:
        db.delete(schedule)
        db.commit()
    
    return JSONResponse({"success": True})


@router.post("/api/schedules/delete/{schedule_id}")
async def delete_schedule_json(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """스케줄 삭제 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        schedule = db.query(AIMarketingSchedule).filter(AIMarketingSchedule.id == schedule_id).first()
        
        if schedule:
            db.delete(schedule)
            db.commit()
        
        return JSONResponse({"success": True})
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/api/schedules/{schedule_id}/toggle")
async def toggle_ai_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 스케줄 활성/비활성 토글"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    try:
        s = db.query(AIMarketingSchedule).filter(AIMarketingSchedule.id == schedule_id).first()
        if not s:
            return JSONResponse({"success": False, "error": "스케줄을 찾을 수 없습니다"}, status_code=404)
        s.is_active = not s.is_active
        # 활성화 시 next_run_at 재계산
        if s.is_active and (not s.next_run_at or s.next_run_at < get_kst_now()):
            s.next_run_at = _calc_next_run(s.scheduled_hour, s.scheduled_minute, s.repeat_type, s.repeat_days)
        db.commit()
        return JSONResponse({"success": True, "is_active": s.is_active})
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.put("/api/schedules/{schedule_id}")
async def update_ai_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scheduled_hour: int = Form(9),
    scheduled_minute: int = Form(0),
    repeat_type: str = Form('daily'),
    repeat_days: str = Form(None),
    posts_per_account: int = Form(1),
):
    """AI 스케줄 수정"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    try:
        s = db.query(AIMarketingSchedule).filter(AIMarketingSchedule.id == schedule_id).first()
        if not s:
            return JSONResponse({"success": False, "error": "스케줄을 찾을 수 없습니다"}, status_code=404)
        s.scheduled_hour = scheduled_hour
        s.scheduled_minute = scheduled_minute
        s.repeat_type = repeat_type
        s.repeat_days = repeat_days
        s.posts_per_account = posts_per_account
        s.next_run_at = _calc_next_run(scheduled_hour, scheduled_minute, repeat_type, repeat_days)
        db.commit()
        return JSONResponse({"success": True})
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/api/schedule-logs/detail/{log_id}")
async def get_schedule_log_detail(
    log_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """스케줄 로그 상세 조회 - 작업별 계정/카페/URL/상태"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    try:
        from database import ScheduleLog, AutomationTask, AutomationAccount, AutomationCafe, DraftPost
        import json as _json_detail

        log = db.query(ScheduleLog).filter(ScheduleLog.id == log_id).first()
        if not log:
            return JSONResponse({"success": False, "error": "로그를 찾을 수 없습니다"}, status_code=404)

        # message에서 task_ids 파싱
        task_ids = []
        skipped = []
        try:
            msg_data = _json_detail.loads(log.message) if log.message else {}
            task_ids = msg_data.get('task_ids', [])
            skipped = msg_data.get('skipped', [])
        except Exception:
            pass

        # 각 task의 상세 정보 조회
        tasks_detail = []
        for tid in task_ids:
            task = db.query(AutomationTask).get(tid)
            if not task:
                tasks_detail.append({'task_id': tid, 'status': 'unknown', 'account': '-', 'cafe': '-', 'url': None})
                continue

            account = db.query(AutomationAccount).get(task.assigned_account_id) if task.assigned_account_id else None
            cafe = db.query(AutomationCafe).get(task.cafe_id) if task.cafe_id else None

            # DraftPost URL (create_draft → DraftPost 저장된 경우)
            draft_url = task.post_url  # 완료 시 post_url에 저장됨

            # AI 수정발행의 경우 error_message에 원본 MODIFY_URL이 있고, post_url이 발행된 URL
            original_draft_url = None
            if task.task_type == 'post' and task.error_message and 'MODIFY_URL:' in task.error_message:
                try:
                    original_draft_url = task.error_message.split('MODIFY_URL:')[1].strip()
                except Exception:
                    pass

            tasks_detail.append({
                'task_id': tid,
                'task_type': task.task_type,
                'status': task.status,
                'account': account.account_id if account else '-',
                'cafe': cafe.name if cafe else f'cafe#{task.cafe_id}',
                'cafe_url': cafe.url if cafe else None,
                'url': draft_url,                      # 신규발행 or 수정발행 완료 URL
                'original_draft_url': original_draft_url,  # 수정발행 원본 URL
                'completed_at': (task.completed_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if task.completed_at else None,
            })

        return JSONResponse({
            "success": True,
            "log_id": log_id,
            "tasks": tasks_detail,
            "skipped": skipped,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/api/schedule-logs/{schedule_type}/{schedule_id}")
async def get_schedule_logs(
    schedule_type: str,
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    date_filter: str = Query(None)   # 'YYYY-MM-DD'
):
    """스케줄 실행 로그 조회"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    try:
        from database import ScheduleLog
        query = db.query(ScheduleLog).filter(
            ScheduleLog.schedule_type == schedule_type,
            ScheduleLog.schedule_id == schedule_id
        )
        if date_filter:
            from sqlalchemy import func as _func
            query = query.filter(
                _func.date(ScheduleLog.executed_at) == date_filter
            )
        logs = query.order_by(ScheduleLog.executed_at.desc()).limit(100).all()
        return JSONResponse({
            "success": True,
            "logs": [
                {
                    "id": l.id,
                    "status": l.status,
                    "tasks_created": l.tasks_created,
                    "message": l.message,
                    "executed_at": (l.executed_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if l.executed_at else None,
                }
                for l in logs
            ]
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ============================================
# 7. 연동 관리 (AI 전용 - 별개)
# ============================================

@router.get("/connections", response_class=HTMLResponse)
async def connections_page(request: Request, db: Session = Depends(get_db)):
    """연동 관리 페이지 (AI 자동화 전용)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # 계정 목록
    accounts = db.query(AutomationAccount).all()
    
    # 카페 목록
    cafes = db.query(AutomationCafe).all()
    
    # 연동 목록
    connections = db.query(CafeAccountLink).options(
        joinedload(CafeAccountLink.cafe),
        joinedload(CafeAccountLink.account)
    ).all()
    
    return templates.TemplateResponse("ai_automation/connections.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "accounts": accounts,
        "cafes": cafes,
        "connections": connections
    })


# ============================================
# 8. 신규 발행 관리
# ============================================

@router.get("/generated-posts", response_class=HTMLResponse)
async def generated_posts_page(
    request: Request,
    account_filter: Optional[int] = Query(None),
    cafe_filter: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """신규 발행 관리 페이지"""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    
    # 글 목록 쿼리
    posts_query = db.query(AIGeneratedPost).options(
        joinedload(AIGeneratedPost.ai_product),
        joinedload(AIGeneratedPost.account),
        joinedload(AIGeneratedPost.cafe)
    )
    
    # 필터
    if account_filter:
        posts_query = posts_query.filter(AIGeneratedPost.account_id == account_filter)
    
    if cafe_filter:
        posts_query = posts_query.filter(AIGeneratedPost.cafe_id == cafe_filter)
    
    posts = posts_query.order_by(AIGeneratedPost.created_at.desc()).all()
    
    # 계정 및 카페 목록
    accounts = db.query(AutomationAccount).all()
    cafes = db.query(AutomationCafe).all()
    
    return templates.TemplateResponse("ai_automation/generated_posts.html", {
        "request": request,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "posts": posts,
        "accounts": accounts,
        "cafes": cafes,
        "account_filter": account_filter,
        "cafe_filter": cafe_filter
    })


# ============================================
# JSON API 엔드포인트 (automation_cafe_full.html 용)
# ============================================

@router.get("/api/products")
async def api_get_products(
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 상품 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        products = db.query(AIMarketingProduct).options(
            joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
        ).all()
        
        products_data = []
        for p in products:
            if p.marketing_product and p.marketing_product.product:
                products_data.append({
                    'id': p.id,
                    'product_name': p.product_name,
                    'product_code': p.marketing_product.product.product_code,
                    'thumbnail': p.marketing_product.product.thumbnail,
                    'use_for_cafe': p.use_for_cafe,
                    'use_for_blog': p.use_for_blog,
                    'marketing_link': p.marketing_link
                })
        
        return JSONResponse({'success': True, 'products': products_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/products/{product_id}")
async def api_get_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 상품 상세 정보 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        product = db.query(AIMarketingProduct).filter(AIMarketingProduct.id == product_id).first()
        
        if not product:
            return JSONResponse({'success': False, 'error': '상품을 찾을 수 없습니다'}, status_code=404)
        
        return JSONResponse({
            'success': True,
            'product': {
                'id': product.id,
                'use_for_cafe': product.use_for_cafe,
                'use_for_blog': product.use_for_blog,
                'product_name': product.product_name,
                'core_value': product.core_value,
                'sub_core_value': product.sub_core_value,
                'size_weight': product.size_weight,
                'difference': product.difference,
                'famous_brands': product.famous_brands,
                'market_problem': product.market_problem,
                'our_price': product.our_price,
                'market_avg_price': product.market_avg_price,
                'target_age': product.target_age,
                'target_gender': product.target_gender,
                'additional_info': product.additional_info,
                'marketing_link': product.marketing_link
            }
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/products/update/{product_id}")
async def api_update_product(
    product_id: int,
    request: Request,
    use_for_cafe: bool = Form(False),
    use_for_blog: bool = Form(False),
    product_name: str = Form(...),
    core_value: str = Form(...),
    sub_core_value: str = Form(...),
    size_weight: str = Form(...),
    difference: str = Form(...),
    famous_brands: str = Form(...),
    market_problem: str = Form(...),
    our_price: str = Form(...),
    market_avg_price: str = Form(...),
    target_age: str = Form(...),
    target_gender: str = Form(...),
    marketing_link: str = Form(...),
    additional_info: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """AI 상품 정보 업데이트 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        product = db.query(AIMarketingProduct).filter(AIMarketingProduct.id == product_id).first()
        
        if not product:
            return JSONResponse({'success': False, 'error': '상품을 찾을 수 없습니다'}, status_code=404)
        
        # 업데이트
        product.use_for_cafe = use_for_cafe
        product.use_for_blog = use_for_blog
        product.product_name = product_name
        product.core_value = core_value
        product.sub_core_value = sub_core_value
        product.size_weight = size_weight
        product.difference = difference
        product.famous_brands = famous_brands
        product.market_problem = market_problem
        product.our_price = our_price
        product.market_avg_price = market_avg_price
        product.target_age = target_age
        product.target_gender = target_gender
        product.additional_info = additional_info
        product.marketing_link = marketing_link
        
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/available-products")
async def api_get_available_products(
    request: Request,
    db: Session = Depends(get_db)
):
    """추가 가능한 상품 목록 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        # 이미 AI 자동화에 추가된 상품 ID들
        existing_ids = [p.marketing_product_id for p in db.query(AIMarketingProduct).all()]
        
        # 추가 가능한 상품들
        available = db.query(MarketingProduct).options(
            joinedload(MarketingProduct.product)
        ).filter(MarketingProduct.id.notin_(existing_ids) if existing_ids else True).all()
        
        products_data = []
        for mp in available:
            if mp.product:
                products_data.append({
                    'id': mp.id,
                    'name': mp.product.name,
                    'product_code': mp.product.product_code,
                    'thumbnail': mp.product.thumbnail
                })
        
        return JSONResponse({'success': True, 'products': products_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/products/add/{marketing_product_id}")
async def api_add_product(
    marketing_product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 상품 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        # 중복 체크
        existing = db.query(AIMarketingProduct).filter(
            AIMarketingProduct.marketing_product_id == marketing_product_id
        ).first()
        
        if existing:
            return JSONResponse({'success': False, 'error': '이미 추가된 상품입니다'}, status_code=400)
        
        # 마케팅 상품 정보 조회
        mp = db.query(MarketingProduct).options(
            joinedload(MarketingProduct.product)
        ).filter(MarketingProduct.id == marketing_product_id).first()
        
        if not mp or not mp.product:
            return JSONResponse({'success': False, 'error': '상품을 찾을 수 없습니다'}, status_code=404)
        
        # AI 상품 생성 (초기값으로)
        ai_product = AIMarketingProduct(
            marketing_product_id=marketing_product_id,
            use_for_cafe=True,
            use_for_blog=False,
            product_name=mp.product.name,
            core_value='',
            sub_core_value='',
            size_weight='',
            difference='',
            famous_brands='',
            market_problem='',
            our_price='',
            market_avg_price='',
            target_age='',
            target_gender='',
            marketing_link=''
        )
        
        db.add(ai_product)
        db.commit()
        db.refresh(ai_product)
        
        return JSONResponse({'success': True, 'id': ai_product.id})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/prompt-templates")
async def api_get_prompt_templates(
    request: Request,
    type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        query = db.query(AIPromptTemplate).filter(
            AIPromptTemplate.is_template == True
        )
        
        # 타입 필터 적용
        if type and type in ['alternative', 'informational']:
            query = query.filter(AIPromptTemplate.template_type == type)
        
        templates = query.all()
        
        templates_data = [{
            'id': t.id,
            'template_name': t.template_name,
            'template_type': t.template_type,
            'user_prompt_template': t.user_prompt_template,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in templates]
        
        return JSONResponse({'success': True, 'templates': templates_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/prompt-templates/{template_id}")
async def get_prompt_template_detail(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 상세 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if not template:
            return JSONResponse({'success': False, 'error': '템플릿을 찾을 수 없습니다'}, status_code=404)
        
        return JSONResponse({
            'success': True,
            'template': {
                'id': template.id,
                'template_name': template.template_name,
                'template_type': template.template_type,
                'user_prompt_template': template.user_prompt_template
            }
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/prompt-templates/add")
async def api_add_prompt_template(
    request: Request,
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        if template_type not in ['alternative', 'informational']:
            return JSONResponse({'success': False, 'error': '잘못된 분류입니다'}, status_code=400)
        
        template = AIPromptTemplate(
            template_name=template_name,
            template_type=template_type,
            user_prompt_template=user_prompt_template,
            is_template=True
        )
        
        db.add(template)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/prompts")
async def get_prompts_for_product(
    request: Request,
    product: Optional[str] = Query(None),  # str로 받아서 처리
    db: Session = Depends(get_db)
):
    """상품별 프롬프트 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        query = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
        )
        
        # product가 있고 빈 문자열이 아닌 경우에만 필터
        if product and product.strip():
            try:
                product_id = int(product)
                query = query.filter(AIPrompt.ai_product_id == product_id)
            except ValueError:
                pass  # 숫자가 아니면 무시
        
        prompts = query.all()
        
        prompts_data = [{
            'id': p.id,
            'ai_product_id': p.ai_product_id,
            'product_name': p.ai_product.product_name if p.ai_product else '알 수 없음',
            'keyword_classification': p.keyword_classification,
            'temperature': p.temperature,
            'max_tokens': p.max_tokens,
            'generate_images': p.generate_images
        } for p in prompts]
        
        return JSONResponse({'success': True, 'prompts': prompts_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/generated-posts")
async def get_generated_posts_list(
    request: Request,
    account: Optional[int] = Query(None),
    cafe: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """신규 발행 글 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        query = db.query(AIGeneratedPost).options(
            joinedload(AIGeneratedPost.ai_product),
            joinedload(AIGeneratedPost.account),
            joinedload(AIGeneratedPost.cafe)
        )
        
        if account:
            query = query.filter(AIGeneratedPost.account_id == account)
        
        if cafe:
            query = query.filter(AIGeneratedPost.cafe_id == cafe)
        
        posts = query.order_by(AIGeneratedPost.created_at.desc()).limit(100).all()
        
        posts_data = [{
            'id': p.id,
            'product_name': p.ai_product.product_name if p.ai_product else '',
            'account_name': p.account.account_id if p.account else '',
            'cafe_name': p.cafe.name if p.cafe else '',
            'post_title': p.post_title,
            'post_url': p.post_url,
            'status': p.status,
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'published_at': p.published_at.isoformat() if p.published_at else None
        } for p in posts]
        
        return JSONResponse({'success': True, 'posts': posts_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/post-history")
async def get_post_history(
    request: Request,
    account: Optional[int] = Query(None),
    cafe: Optional[int] = Query(None),
    product: Optional[int] = Query(None),
    page: int = Query(1),
    page_size: int = Query(50),
    db: Session = Depends(get_db)
):
    """수정 발행 이력 조회 (AI 신규발행 탭용)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)

    try:
        from database import CafeAccountLink, DraftPost, AIMarketingProduct
        from sqlalchemy import desc as _desc

        query = db.query(AutomationTask).filter(
            AutomationTask.task_type == 'post',
            AutomationTask.status == 'completed',
        )

        if account:
            query = query.filter(AutomationTask.assigned_account_id == account)
        if cafe:
            query = query.filter(AutomationTask.cafe_id == cafe)
        if product:
            query = query.filter(AutomationTask.schedule_id.in_(
                db.query(AIMarketingSchedule.id).filter(AIMarketingSchedule.ai_product_id == product)
            ))

        total = query.count()
        tasks = query.order_by(_desc(AutomationTask.completed_at)).offset((page - 1) * page_size).limit(page_size).all()

        result = []
        for t in tasks:
            acc = db.query(AutomationAccount).get(t.assigned_account_id) if t.assigned_account_id else None
            cafe_obj = db.query(AutomationCafe).get(t.cafe_id) if t.cafe_id else None
            schedule = db.query(AIMarketingSchedule).get(t.schedule_id) if t.schedule_id else None
            product_obj = db.query(AIMarketingProduct).get(schedule.ai_product_id) if schedule else None

            # 상품명: schedule 링크가 없으면 task.title에서 폴백
            resolved_product_name = (
                product_obj.product_name if product_obj
                else (t.title or '')
            )

            # DraftPost 상태 조회
            draft_url = None
            draft_status = None
            if t.error_message and 'MODIFY_URL:' in t.error_message:
                draft_url = t.error_message.split('MODIFY_URL:')[1].strip()
                dp = db.query(DraftPost).filter(DraftPost.draft_url == draft_url).first()
                draft_status = dp.status if dp else None

            result.append({
                'task_id': t.id,
                'account_id': acc.account_id if acc else '',
                'cafe_name': cafe_obj.name if cafe_obj else '',
                'cafe_id': t.cafe_id,
                'product_name': resolved_product_name,
                'product_id': product_obj.id if product_obj else None,
                'keyword': t.keyword or '',
                'draft_url': draft_url or '',
                'post_url': t.post_url or '',
                'draft_status': draft_status or 'used',
                'completed_at': t.completed_at.isoformat() if t.completed_at else None,
            })

        return JSONResponse({
            'success': True,
            'posts': result,
            'total': total,
            'page': page,
            'page_size': page_size,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/connections")
async def get_cafe_connections(
    request: Request,
    db: Session = Depends(get_db)
):
    """카페-계정 연동 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import CafeAccountLink
        
        connections = db.query(CafeAccountLink).options(
            joinedload(CafeAccountLink.cafe),
            joinedload(CafeAccountLink.account)
        ).all()
        
        connections_data = [{
            'id': c.id,
            'cafe_id': c.cafe_id,
            'account_id': c.account_id,
            'cafe_name': c.cafe.name if c.cafe else '',
            'cafe_characteristics': c.cafe.characteristics if c.cafe else '',
            'account_name': c.account.account_id if c.account else '',
            'status': c.status,
            'draft_post_count': c.draft_post_count,
            'used_post_count': c.used_post_count,
            'is_member': c.is_member
        } for c in connections]
        
        return JSONResponse({'success': True, 'connections': connections_data})
    except ImportError:
        # CafeAccountLink 테이블이 없는 경우
        return JSONResponse({'success': True, 'connections': []})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/cafes/{cafe_id}")
async def get_cafe_info(
    cafe_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """특정 카페 정보 조회 (카페명, 특성)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    try:
        from database import AutomationCafe
        cafe = db.query(AutomationCafe).filter(AutomationCafe.id == cafe_id).first()
        if not cafe:
            return JSONResponse({"success": False, "error": "카페를 찾을 수 없습니다"}, status_code=404)
        return JSONResponse({
            "success": True,
            "cafe": {
                "id": cafe.id,
                "cafe_name": cafe.name,
                "characteristics": cafe.characteristics or ""
            }
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/api/connections/add")
async def add_connection(
    request: Request,
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    is_member: bool = Form(True),
    db: Session = Depends(get_db)
):
    """카페-계정 연동 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import CafeAccountLink
        
        # 중복 확인
        existing = db.query(CafeAccountLink).filter(
            CafeAccountLink.cafe_id == cafe_id,
            CafeAccountLink.account_id == account_id
        ).first()
        
        if existing:
            return JSONResponse({'success': False, 'error': '이미 연동된 카페-계정입니다'}, status_code=400)
        
        # 연동 추가
        connection = CafeAccountLink(
            cafe_id=cafe_id,
            account_id=account_id,
            is_member=is_member,
            status='active',
            draft_post_count=0,
            used_post_count=0
        )
        
        db.add(connection)
        db.commit()
        db.refresh(connection)
        
        return JSONResponse({'success': True, 'id': connection.id})
    except ImportError:
        return JSONResponse({'success': False, 'error': 'CafeAccountLink 테이블이 없습니다. 테이블을 먼저 생성하세요.'}, status_code=500)
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/connections/delete/{connection_id}")
async def delete_connection(
    connection_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """카페-계정 연동 삭제 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import CafeAccountLink
        
        connection = db.query(CafeAccountLink).filter(CafeAccountLink.id == connection_id).first()
        
        if connection:
            db.delete(connection)
            db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/draft-posts/list/{link_id}")
async def get_draft_posts(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """신규발행 글 URL 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import DraftPost
        
        draft_posts = db.query(DraftPost).filter(
            DraftPost.link_id == link_id
        ).order_by(DraftPost.created_at.desc()).all()
        
        posts_data = [{
            'id': dp.id,
            'draft_url': dp.draft_url,
            'article_id': dp.article_id,
            'status': dp.status,
            'modified_url': dp.modified_url,
            'used_at': (dp.used_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if dp.used_at else None,
            'created_at': (dp.created_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if dp.created_at else None,
        } for dp in draft_posts]
        
        return JSONResponse({'success': True, 'draft_posts': posts_data})
    except ImportError:
        return JSONResponse({'success': True, 'draft_posts': []})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/draft-posts/add")
async def add_draft_post(
    request: Request,
    link_id: int = Form(...),
    draft_url: str = Form(...),
    db: Session = Depends(get_db)
):
    """신규발행 글 URL 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import DraftPost, CafeAccountLink
        
        # URL에서 article_id 추출 (마지막 숫자 부분)
        article_id = draft_url.split('/')[-1] if '/' in draft_url else draft_url
        
        # 중복 확인
        existing = db.query(DraftPost).filter(
            DraftPost.draft_url == draft_url
        ).first()
        
        if existing:
            return JSONResponse({'success': False, 'error': '이미 등록된 URL입니다'}, status_code=400)
        
        # URL 추가
        draft_post = DraftPost(
            link_id=link_id,
            draft_url=draft_url,
            article_id=article_id,
            status='available'
        )
        
        db.add(draft_post)
        
        # 연동의 draft_post_count 증가
        link = db.query(CafeAccountLink).filter(CafeAccountLink.id == link_id).first()
        if link:
            link.draft_post_count += 1
        
        db.commit()
        
        return JSONResponse({'success': True})
    except ImportError:
        return JSONResponse({'success': False, 'error': 'DraftPost 테이블이 없습니다'}, status_code=500)
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/test-generate")
async def test_generate_content(
    request: Request,
    prompt_id: int = Form(...),
    keyword: str = Form(...),
    cafe_id: int = Form(...),  # 카페 선택 추가
    db: Session = Depends(get_db)
):
    """Claude API 테스트 - 실제 글 생성"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        # anthropic 모듈 확인
        try:
            import anthropic
        except ImportError:
            return JSONResponse({
                'success': False,
                'error': 'anthropic 모듈이 설치되지 않았습니다. pip install anthropic'
            }, status_code=500)
        
        # 프롬프트 정보 가져오기
        prompt = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product)
        ).filter(AIPrompt.id == prompt_id).first()
        
        if not prompt or not prompt.ai_product:
            return JSONResponse({'success': False, 'error': '프롬프트를 찾을 수 없습니다'}, status_code=404)
        
        product = prompt.ai_product
        
        # 카페 특성 가져오기 (컬럼이 없을 수도 있으므로 안전하게 처리)
        cafe = db.query(AutomationCafe).filter(AutomationCafe.id == cafe_id).first()
        cafe_name = cafe.name if cafe else "알 수 없음"
        
        try:
            cafe_characteristics = cafe.characteristics if cafe and hasattr(cafe, 'characteristics') and cafe.characteristics else "일반적인 톤, 자연스러운 대화체"
        except (AttributeError, Exception):
            cafe_characteristics = "일반적인 톤, 자연스러운 대화체"
        
        # 레퍼런스 가져오기 (같은 분류)
        ai_refs = db.query(AIProductReference).options(
            joinedload(AIProductReference.reference).joinedload(Reference.comments)
        ).filter(
            AIProductReference.ai_product_id == product.id,
            AIProductReference.reference_type == prompt.keyword_classification
        ).limit(3).all()
        
        # 레퍼런스 텍스트 조합
        reference_text = ""
        for idx, ai_ref in enumerate(ai_refs):
            if ai_ref.reference:
                ref = ai_ref.reference
                reference_text += f"\n\n【예시 {idx + 1}: {ref.title}】\n"
                reference_text += f"{ref.content}\n"
                
                # 댓글도 포함
                if ref.comments:
                    reference_text += "\n댓글:\n"
                    for comment in ref.comments[:5]:  # 최대 5개
                        reference_text += f"- 계정{comment.account_sequence}: {comment.text}\n"
        
        # 변수 치환 (테스트 시에는 사용자가 선택한 키워드 사용)
        user_prompt = prompt.user_prompt
        replacements = {
            '{타겟_키워드}': keyword,  # 테스트 시: 사용자 선택 키워드
            '{keyword}': keyword,  # 기존 호환성
            '{product_name}': product.product_name,
            '{core_value}': product.core_value,
            '{sub_core_value}': product.sub_core_value,
            '{size_weight}': product.size_weight,
            '{difference}': product.difference,
            '{famous_brands}': product.famous_brands,
            '{market_problem}': product.market_problem,
            '{our_price}': product.our_price,
            '{market_avg_price}': product.market_avg_price,
            '{target_age}': product.target_age,
            '{target_gender}': product.target_gender,
            '{additional_info}': product.additional_info or '',
            '{marketing_link}': product.marketing_link
        }
        
        # 사용자 프롬프트 변수 치환
        for var, value in replacements.items():
            user_prompt = user_prompt.replace(var, str(value))
        
        # 시스템 프롬프트도 변수 치환
        system_prompt = prompt.system_prompt
        for var, value in replacements.items():
            system_prompt = system_prompt.replace(var, str(value))
        
        # 레퍼런스 추가
        if reference_text:
            user_prompt += f"\n\n참고할 예시 글들:{reference_text}\n\n위 예시들의 톤과 스타일을 참고하여 자연스럽고 진정성 있는 글을 작성해주세요."
        
        # 카페 특성 가져오기
        cafe = db.query(AutomationCafe).filter(AutomationCafe.id == cafe_id).first()
        cafe_name = cafe.name if cafe else "알 수 없음"
        cafe_characteristics = cafe.characteristics if cafe and cafe.characteristics else "일반적인 톤, 자연스러운 대화체"
        
        # 카페 컨텍스트 추가 (프롬프트 설정에 따라!)
        
        # 카페 연동 계정 수 조회
        from database import CafeAccountLink
        cafe_links = db.query(CafeAccountLink).filter(
            CafeAccountLink.cafe_id == cafe_id
        ).count()
        
        comment_account_count = max(1, cafe_links - 1)  # 작성자 제외, 최소 1명
        
        # 프롬프트 설정: 카페 특성 반영 여부 확인
        if prompt.apply_cafe_context:
            user_prompt += f"""

[발행될 카페 정보]
- 카페명: {cafe_name}
- 카페 특성: {cafe_characteristics}

위 카페의 특성에 맞춰 자연스럽게 작성해주세요.
"""
        
        # 댓글 작성 지침 (항상 추가)
        user_prompt += f"""

[댓글 작성 지침 - 중요!]
- 이 카페에 가입된 계정은 총 {cafe_links}개입니다 (작성자 포함).
- 댓글 작성자는 정확히 {comment_account_count}명만 사용하세요.
- 작성자명: '계정1'부터 '계정{comment_account_count}'까지
- 대댓글에는 '작성자' 또는 기존 계정명을 재사용하세요.
- 같은 댓글에 여러 대댓글을 달 수 있습니다.
- 예시:
  **계정1:** 댓글
  > **작성자:** 대댓글
  > **계정1:** 대댓글
  **계정2:** 댓글"""
        
        # 치환된 시스템 프롬프트 사용
        enhanced_system_prompt = system_prompt
        
        # Claude API 호출
        import os
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return JSONResponse({
                'success': False,
                'error': 'ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다'
            }, status_code=500)
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # 🔍 프롬프트 로깅 (디버깅용)
        print("\n" + "="*80)
        print("🔍 Claude API 호출 - 프롬프트 확인")
        print("="*80)
        print(f"\n[Model]: claude-opus-4-5")
        print(f"[Temperature]: {prompt.temperature}")
        print(f"[Max Tokens]: {prompt.max_tokens}")
        print(f"[키워드]: {keyword}")
        print(f"[카페]: {cafe_name}")
        print("\n[System Prompt]")
        print(enhanced_system_prompt)
        print("\n" + "-"*80)
        print("\n[User Prompt]")
        print(user_prompt)
        print("\n" + "="*80 + "\n")
        
        response = client.messages.create(
            model="claude-opus-4-5",  # Claude Opus 4.5 (최강 성능!)
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
            system=enhanced_system_prompt,  # 카페 특성 포함!
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        generated_content_raw = response.content[0].text
        
        # 🔍 생성된 원본 결과 로깅
        print("\n" + "="*80)
        print("📝 Claude 생성 결과 (RAW)")
        print("="*80)
        print(generated_content_raw)
        print("\n" + "="*80 + "\n")
        
        # 생성된 텍스트를 제목/본문/댓글로 분리
        def split_content(text):
            """제목, 본문, 댓글을 각각 분리 (Claude 출력 형식 대응)"""
            title = ""
            body = ""
            comments = ""
            
            # ── 제목 정리 헬퍼: 첫 번째 유효한 줄만, 마크다운/불필요 텍스트 제거
            def _clean_t(raw: str) -> str:
                skip = {'Menu', '---', 'Title', '제목', 'menu', 'title'}
                for line in raw.split('\n'):
                    line = line.strip()
                    if line and line not in skip:
                        return line.strip('*').strip('#').strip()
                return raw.split('\n')[0].strip().strip('*').strip('#').strip()

            # 1. --- 구분자로 섹션 분리
            sections = text.split('---')
            
            if len(sections) >= 3:
                # 형식: # 제목\n내용\n---\n# 본문\n내용\n---\n# 댓글\n내용
                title_section = sections[0].strip()
                body_section = sections[1].strip()
                comments_section = sections[2].strip()
                
                # 제목 추출 (헤더 제거 후 첫 줄만)
                if title_section.startswith('# 제목'):
                    title = _clean_t(title_section.replace('# 제목', '', 1).strip())
                elif title_section.startswith('**제목:**'):
                    title = _clean_t(title_section.replace('**제목:**', '', 1).strip())
                elif title_section.startswith('**제목**'):
                    title = _clean_t(title_section.replace('**제목**', '', 1).strip())
                else:
                    lines = title_section.split('\n')
                    title = _clean_t(lines[0].replace('#', '').strip())
                
                # 본문 추출 (헤더 제거)
                if body_section.startswith('# 본문'):
                    body = body_section.replace('# 본문', '', 1).strip()
                elif body_section.startswith('## 본문'):
                    body = body_section.replace('## 본문', '', 1).strip()
                elif body_section.startswith('**본문:**'):
                    body = body_section.replace('**본문:**', '', 1).strip()
                elif body_section.startswith('**본문**'):
                    body = body_section.replace('**본문**', '', 1).strip()
                else:
                    body = body_section.strip()
                
                # 댓글 추출 (헤더 제거)
                if comments_section.startswith('# 댓글'):
                    comments = comments_section.replace('# 댓글', '', 1).strip()
                elif comments_section.startswith('**댓글:**'):
                    comments = comments_section.replace('**댓글:**', '', 1).strip()
                elif comments_section.startswith('**댓글**'):
                    comments = comments_section.replace('**댓글**', '', 1).strip()
                else:
                    comments = comments_section.strip()
                
            elif len(sections) == 2:
                # 제목 + 본문만 (댓글 없음)
                title_section = sections[0].strip()
                body_section = sections[1].strip()
                
                if title_section.startswith('# 제목'):
                    title = _clean_t(title_section.replace('# 제목', '', 1).strip())
                else:
                    lines = title_section.split('\n')
                    title = _clean_t(lines[0].replace('#', '').strip())
                
                if body_section.startswith('# 본문'):
                    body = body_section.replace('# 본문', '', 1).strip()
                else:
                    body = body_section.strip()
                
            else:
                # --- 없는 경우: 전체를 본문으로
                lines = text.strip().split('\n')
                if lines and lines[0].startswith('#'):
                    title = _clean_t(lines[0].replace('#', '').strip())
                    body = '\n'.join(lines[1:]).strip()
                else:
                    body = text.strip()
            
            return title, body, comments
        
        title, body, comments = split_content(generated_content_raw)
        
        # ─────────────────────────────────────────
        # 이미지 생성 (FLUX 1.1 Pro via fal.ai)
        # ─────────────────────────────────────────
        image_urls = []
        product_image_urls = []
        attract_image_urls = []
        
        if prompt.generate_images:
            try:
                import fal_client
                import random
                
                fal_key = os.environ.get('FAL_KEY')
                if not fal_key:
                    print("⚠️  FAL_KEY 없음 - 이미지 생성 건너뜀")
                else:
                    os.environ['FAL_KEY'] = fal_key
                    
                    # 실사감을 높이는 공통 suffix
                    REALISM_SUFFIX = ", slight lens distortion, minor motion blur, not perfectly composed, natural imperfections, no AI look"
                    
                    async def _generate_flux_image(img_prompt: str, portrait: bool = False) -> str | None:
                        """
                        FLUX 1.1 Pro 이미지 생성
                        - portrait=True: 세로형 1024×1536 (SNS/모바일용)
                        - portrait=False: 정방형 1024×1024 (기본)
                        """
                        try:
                            full_prompt = img_prompt + REALISM_SUFFIX
                            img_size = {"width": 1024, "height": 1536} if portrait else {"width": 1024, "height": 1024}
                            print(f"🎨 FLUX 생성 중 ({img_size['width']}×{img_size['height']}): {img_prompt[:70]}...")
                            result = await fal_client.run_async(
                                "fal-ai/flux-pro/v1.1",
                                arguments={
                                    "prompt": full_prompt,
                                    "image_size": img_size,
                                    "num_inference_steps": 28,
                                    "guidance_scale": 3.5,
                                    "num_images": 1,
                                    "safety_tolerance": "2",
                                    "output_format": "jpeg",
                                }
                            )
                            url = result['images'][0]['url']
                            print(f"   ✅ 완료: {url[:60]}...")
                            return url
                        except Exception as e:
                            print(f"   ❌ FLUX 이미지 생성 실패: {e}")
                            return None
                    
                    # ── 제품 이미지 생성 ──
                    num_product = prompt.num_product_images or 1
                    if num_product > 0:
                        style_hint = prompt.product_image_style or 'lifestyle, photorealistic, shot on Sony A7III 50mm f1.8, shallow depth of field'
                        product_img_prompt = None
                        try:
                            claude_resp = client.messages.create(
                                model="claude-opus-4-5",
                                max_tokens=400,
                                messages=[{
                                    "role": "user",
                                    "content": f"""다음 제품을 FLUX AI 이미지 생성기에 넣을 영어 프롬프트를 만들어줘.

제품명: {product.product_name}
핵심 특징: {product.core_value or ''}
서브 특징: {product.sub_core_value or ''}
사이즈/무게: {product.size_weight or ''}
타겟: {product.target_age or ''} {product.target_gender or ''}
스타일 힌트: {style_hint}

규칙:
- 영어로만 작성
- 실제 사진처럼 보이는 자연스러운 생활 장면
- 반드시 위 제품이 실제로 사용되는 모습을 묘사 (음식이나 관계없는 장면 절대 금지)
- 제품의 타겟 고객이 사용하는 장면
- 카메라 기종, 렌즈, 조명 정보 포함 (예: shot on Sony A7III 50mm f1.8)
- 200자 이내
- 프롬프트 텍스트만 출력 (설명, 번호, 따옴표 없이)"""
                                }]
                            )
                            product_img_prompt = claude_resp.content[0].text.strip()
                            print(f"🤖 제품 이미지 프롬프트 (Claude 생성): {product_img_prompt}")
                        except Exception as e:
                            print(f"⚠️  Claude 프롬프트 생성 실패: {e}")
                            product_img_prompt = f"photorealistic lifestyle photo of Korean person using {product.product_name}, natural lighting, shot on Sony A7III 50mm f1.8, shallow depth of field"
                        
                        for _ in range(num_product):
                            url = await _generate_flux_image(product_img_prompt, portrait=False)
                            if url:
                                product_image_urls.append(url)
                                image_urls.append(url)
                        print(f"✅ 제품 이미지 {len(product_image_urls)}장 생성 완료")
                    
                    # ── 어그로 이미지 생성 ──
                    num_attract = prompt.num_attract_images or 2
                    if num_attract > 0:
                        attract_prompts_raw = prompt.attract_image_prompts or ''
                        attract_pool = [p.strip() for p in attract_prompts_raw.strip().split('\n') if p.strip()]
                        
                        # 풀이 없으면 검증된 기본 풀 사용
                        if not attract_pool:
                            attract_pool = KOREAN_FOOD_ATTRACT_POOL
                        
                        for _ in range(num_attract):
                            attract_prompt = random.choice(attract_pool)
                            print(f"🎯 어그로 이미지 프롬프트: {attract_prompt[:60]}...")
                            url = await _generate_flux_image(attract_prompt, portrait=False)
                            if url:
                                attract_image_urls.append(url)
                                image_urls.append(url)
                        print(f"✅ 어그로 이미지 {len(attract_image_urls)}장 생성 완료")
            
            except ImportError:
                print("⚠️  fal_client 미설치 - pip install fal-client")
            except Exception as e:
                print(f"❌ 이미지 생성 오류: {e}")
        
        return JSONResponse({
            'success': True,
            'title': title,
            'body': body,
            'comments': comments,
            'keyword': keyword,
            'prompt_name': f"{product.product_name} - {prompt.keyword_classification}",
            'cafe_name': cafe_name,
            'cafe_characteristics': cafe_characteristics,
            'references_used': len(ai_refs),
            'image_urls': image_urls,
            'product_image_urls': product_image_urls,
            'attract_image_urls': attract_image_urls,
            'num_product_images': len(product_image_urls),
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/publish-test")
async def publish_test(
    request: Request,
    prompt_id: int = Form(...),
    keyword: str = Form(...),
    draft_url_id: int = Form(...),  # 필수!
    cafe_id: Optional[int] = Form(None),  # 선택 (자동 추출)
    comment_count: int = Form(3),
    db: Session = Depends(get_db)
):
    """글 발행 테스트 - 실제 카페에 즉시 발행 + 댓글"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import AutomationTask, DraftPost
        import anthropic
        import os
        import re
        
        # 1. URL 정보 가져오기 (수정 발행용) - 먼저!
        draft_post = db.query(DraftPost).options(
            joinedload(DraftPost.link)
        ).filter(DraftPost.id == draft_url_id).first()
        
        if not draft_post or not draft_post.link:
            return JSONResponse({"success": False, "error": "초안 URL을 찾을 수 없습니다"}, status_code=404)
        
        # 카페 자동 추출!
        cafe_id = draft_post.link.cafe_id
        assigned_account_id = draft_post.link.account_id
        
        print(f"📋 초안 URL에서 자동 추출: 카페 ID={cafe_id}, 계정 ID={assigned_account_id}")
        
        # 2. AI로 글 생성 (자동 추출된 cafe_id 사용!)
        test_result = await test_generate_content(request, prompt_id, keyword, cafe_id, db)
        test_data = json.loads(test_result.body) if hasattr(test_result, 'body') else test_result
        
        if not test_data.get('success'):
            return JSONResponse(test_data)
        
        # 3. 프롬프트 정보
        prompt = db.query(AIPrompt).get(prompt_id)
        
        # 4. 본문 Task 생성 (스케줄 없이)
        # 제목 추출 (AI가 생성한 제목 또는 키워드)
        post_title = test_data.get('title') or keyword
        
        # 계정의 PC 찾기
        assigned_pc_id = None
        if assigned_account_id:
            from database import AutomationAccount
            account = db.query(AutomationAccount).get(assigned_account_id)
            if account:
                assigned_pc_id = account.assigned_pc_id
        
        # 이미지 URLs JSON 직렬화
        import json as _json
        task_image_urls = test_data.get('image_urls', [])
        image_urls_json = _json.dumps(task_image_urls) if task_image_urls else None
        if task_image_urls:
            print(f"   📸 이미지 {len(task_image_urls)}장 Task에 포함")
        
        # product_name 조회 (대시보드 표시용)
        _product_name = None
        try:
            from database import AIMarketingProduct as _AMP
            _prompt_obj = db.query(AIPrompt).get(prompt_id)
            if _prompt_obj and _prompt_obj.ai_product_id:
                _ai_prod = db.query(_AMP).get(_prompt_obj.ai_product_id)
                if _ai_prod:
                    _product_name = _ai_prod.product_name
        except Exception:
            pass

        post_task = AutomationTask(
            task_type='post',
            mode='ai',
            schedule_id=None,
            scheduled_time=datetime.now(),
            title=post_title,
            content=test_data['body'],
            cafe_id=cafe_id,
            assigned_pc_id=assigned_pc_id,
            assigned_account_id=assigned_account_id,
            status='pending',
            priority=10,
            image_urls=image_urls_json,
            keyword=keyword,
            product_name=_product_name,
        )
        
        # 수정 발행 URL 추가 (간단하게)
        if draft_post:
            post_task.error_message = f"MODIFY_URL:{draft_post.draft_url}"
        else:
            post_task.error_message = None
        
        db.add(post_task)
        db.flush()
        
        # 5. 댓글 Task 생성 (이미 생성된 댓글 사용!)
        comment_tasks = []
        print(f"\n💬 댓글 Task 생성 시작...")
        
        # AI가 이미 생성한 댓글 사용
        comments_text = test_data.get('comments', '')
        print(f"   AI 생성 댓글:\n{comments_text[:500]}...")
        
        if comments_text:
                
                # 댓글 구조 파싱 (복잡한 구조 지원)
                def parse_comment_structure(text):
                    """댓글 + 대댓글 파싱"""
                    lines = text.strip().split('\n')
                    result = []
                    
                    for line in lines:
                        if not line.strip() or line.startswith('---') or line.startswith('#'):
                            continue
                        
                        # 대댓글 레벨 확인
                        level = 0
                        original_line = line
                        while line.startswith('>'):
                            level += 1
                            line = line[1:].strip()
                        
                        # 계정명 추출: **계정:** 형식
                        if '**' in line and ':**' in line:
                            try:
                                # **계정1:** 댓글 내용
                                parts = line.split('**')
                                if len(parts) >= 3:
                                    account_part = parts[1]
                                    if ':' in account_part:
                                        account = account_part.split(':')[0].strip()
                                        content = '**'.join(parts[2:]).strip()
                                        
                                        result.append({
                                            'level': level,
                                            'account': account,
                                            'content': content
                                        })
                            except:
                                continue
                    
                    return result
                
                parsed_comments = parse_comment_structure(comments_text)
                print(f"   파싱된 댓글 수: {len(parsed_comments)}")
                
                # PC/계정 순차 할당 준비
                from database import AutomationWorkerPC, AutomationAccount
                
                # 1. 작성자 PC 확인
                author_pc_id = post_task.assigned_pc_id
                print(f"\n📋 계정 할당 준비:")
                print(f"   작성자 PC: #{author_pc_id}")
                
                # 2. 사용 가능한 PC 목록 (작성자 제외, 번호 순)
                available_pcs = db.query(AutomationWorkerPC).filter(
                    AutomationWorkerPC.id != author_pc_id,
                    AutomationWorkerPC.status == 'online'
                ).order_by(
                    AutomationWorkerPC.pc_number.asc()
                ).all()
                
                print(f"   사용 가능한 PC: {', '.join([f'#{pc.pc_number}' for pc in available_pcs])} (총 {len(available_pcs)}대)")
                
                if not available_pcs:
                    print("   ⚠️  사용 가능한 PC가 없습니다!")
                
                # Task 생성
                task_map = {}  # idx별 Task ID 저장
                
                print(f"\n📝 댓글 Task 생성 시작...")
                for idx, comment_obj in enumerate(parsed_comments):
                    print(f"   댓글 {idx+1}: {comment_obj['account']} - {comment_obj['content'][:30]}...")
                    
                    # 레벨에 따라 부모 Task 결정
                    if comment_obj['level'] == 0:
                        # 최상위 댓글 → 본문에 댓글
                        parent_id = post_task.id
                        task_type = 'comment'
                    else:
                        # 대댓글 → 바로 위 level 0 댓글 찾기 (여러 대댓글 지원!)
                        parent_id = post_task.id  # 기본값
                        for i in range(idx - 1, -1, -1):
                            prev_comment = parsed_comments[i]
                            if prev_comment['level'] == 0:
                                # 가장 최근 level 0 댓글의 Task ID
                                parent_id = task_map.get(i, post_task.id)
                                print(f"      부모: {prev_comment['account']} (idx:{i})")
                                break
                        
                        task_type = 'reply'
                    
                    # PC/계정 할당 (AI 생성 계정명 기반!)
                    target_pc_id = None
                    target_account_id = None
                    ai_account_name = comment_obj['account']  # '작성자', '계정1', '계정2' 등
                    
                    if ai_account_name == '작성자':
                        # 작성자는 본문 작성 PC 사용
                        target_pc_id = author_pc_id
                        if author_pc_id:
                            target_account = db.query(AutomationAccount).get(assigned_account_id)
                            if target_account:
                                target_account_id = target_account.id
                                print(f"      → 작성자: PC #{author_pc_id} (계정: {target_account.account_id}) 할당")
                    
                    elif ai_account_name.startswith('계정'):
                        # 계정1, 계정2 등 → 숫자 추출
                        import re
                        match = re.search(r'\d+', ai_account_name)
                        if match and available_pcs:
                            account_num = int(match.group())
                            # 계정1 → PC #2 (index 0), 계정2 → PC #3 (index 1), ...
                            pc_index = (account_num - 1) % len(available_pcs)
                            target_pc = available_pcs[pc_index]
                            
                            # 해당 PC의 계정 찾기
                            target_account = db.query(AutomationAccount).filter(
                                AutomationAccount.assigned_pc_id == target_pc.id,
                                AutomationAccount.status == 'active'
                            ).first()
                            
                            if target_account:
                                target_pc_id = target_pc.id
                                target_account_id = target_account.id
                                print(f"      → {ai_account_name}: PC #{target_pc.pc_number} (계정: {target_account.account_id}) 할당")
                    
                    comment_task = AutomationTask(
                        task_type=task_type,
                        mode='ai',
                        schedule_id=None,
                        scheduled_time=datetime.now(),  # 즉시 실행 (순차는 parent_task_id로 제어)
                        content=comment_obj['content'],
                        parent_task_id=parent_id,
                        order_sequence=idx,
                        cafe_id=cafe_id,
                        assigned_pc_id=target_pc_id,  # 미리 할당!
                        assigned_account_id=target_account_id,  # 미리 할당!
                        status='pending',
                        priority=10
                    )
                    db.add(comment_task)
                    db.flush()
                    comment_tasks.append(comment_task)
                    
                    # idx별로 Task ID 저장 (부모 추적용)
                    task_map[idx] = comment_task.id
                    print(f"      ✅ Task #{comment_task.id} 생성 (타입: {task_type}, 순서: {idx}, 부모: #{parent_id})")
        
        print(f"✅ 댓글 Task 생성 완료: 총 {len(comment_tasks)}개")
        db.commit()
        
        # 6. Worker PC에 직접 전송
        # ⚠️  핵심 수정: account.assigned_pc_id = PC의 DB ID (FK)
        #               worker_connections 키 = pc_number (1,2,3...)
        #               → DB ID로 worker_connections 조회하면 항상 False → 90초 타임아웃
        from routers.automation import send_task_to_worker, worker_connections
        from database import AutomationWorkerPC

        # DB ID → pc_number 변환
        pc_number_to_use = None
        if assigned_pc_id:
            pc_record = db.query(AutomationWorkerPC).filter(
                AutomationWorkerPC.id == assigned_pc_id
            ).first()
            if pc_record:
                pc_number_to_use = pc_record.pc_number
                print(f"\n📤 본문 Task 전송 준비...")
                print(f"   assigned_account_id : {assigned_account_id}")
                print(f"   assigned_pc_id (DB) : {assigned_pc_id}")
                print(f"   pc_number           : {pc_number_to_use}")
                print(f"   현재 연결된 PC 목록 : {list(worker_connections.keys())}")

        task_sent = False
        if pc_number_to_use is not None:
            if pc_number_to_use in worker_connections:
                await send_task_to_worker(pc_number_to_use, post_task, db)
                post_task.status = 'assigned'
                db.commit()
                print(f"✅ Task #{post_task.id} 직접 전송 → PC #{pc_number_to_use}")
                task_sent = True
            else:
                print(f"   ℹ️  PC #{pc_number_to_use} 현재 미연결 → DB 저장 (재연결 시 자동 처리)")
                # 90초 대기 제거: Render.com 30초 HTTP 타임아웃에 걸려 요청 자체가 끊김
                # 대신 Worker 재연결 시 worker_websocket 핸들러가 pending task 자동 감지
        else:
            print(f"   ⚠️  PC 정보 없음 (assigned_pc_id={assigned_pc_id}) → DB 저장")
        
        # 댓글 Task는 본문 Task 완료 후 자동 할당됨 (task_completed → assign_next_task)
        
        return JSONResponse({
            'success': True,
            'message': f'글 + 댓글 {len(comment_tasks)}개 Task 생성 완료!',
            'task_id': post_task.id,
            'title': test_data.get('title'),
            'body': test_data.get('body'),
            'keyword': test_data.get('keyword', ''),
            'ai_comments': test_data.get('comments'),
            'task_comments': len(comment_tasks),
            'cafe_name': test_data.get('cafe_name'),
            'image_urls': test_data.get('image_urls', []),
            'num_product_images': test_data.get('num_product_images', 1),
            'task_sent': task_sent
        })
        
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/draft-posts/delete/{draft_id}")
async def delete_draft_post(
    draft_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """신규발행 글 URL 삭제 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        from database import DraftPost, CafeAccountLink
        
        draft_post = db.query(DraftPost).filter(DraftPost.id == draft_id).first()
        
        if draft_post:
            link_id = draft_post.link_id
            db.delete(draft_post)
            
            # 연동의 draft_post_count 감소
            link = db.query(CafeAccountLink).filter(CafeAccountLink.id == link_id).first()
            if link and link.draft_post_count > 0:
                link.draft_post_count -= 1
            
            db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/schedules")
async def get_ai_schedules(
    request: Request,
    page: int = Query(1, ge=1),
    search: str = Query(''),
    status: str = Query('all'),
    db: Session = Depends(get_db)
):
    """AI 스케줄 목록 조회 (페이지네이션, JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        PAGE_SIZE = 20
        
        query = db.query(AIMarketingSchedule).options(
            joinedload(AIMarketingSchedule.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product),
            joinedload(AIMarketingSchedule.prompt)
        )
        
        # 검색 필터 (상품명)
        if search:
            query = query.join(
                AIMarketingProduct,
                AIMarketingSchedule.ai_product_id == AIMarketingProduct.id
            ).filter(AIMarketingProduct.product_name.like(f'%{search}%'))
        
        # 상태 필터
        if status != 'all':
            query = query.filter(AIMarketingSchedule.status == status)
        
        # 전체 개수
        total_count = query.count()
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        
        # 페이지네이션
        offset = (page - 1) * PAGE_SIZE
        schedules = query.order_by(AIMarketingSchedule.created_at.desc()).offset(offset).limit(PAGE_SIZE).all()
        
        schedules_data = []
        for s in schedules:
            if s.ai_product and s.prompt:
                schedules_data.append({
                    'id': s.id,
                    'product_name': s.ai_product.product_name,
                    'keyword_classification': s.prompt.keyword_classification,
                    'start_date': s.start_date.isoformat() if s.start_date else None,
                    'end_date': s.end_date.isoformat() if s.end_date else None,
                    'daily_post_count': s.daily_post_count,
                    'expected_total_posts': s.expected_total_posts,
                    'status': s.status,
                    'is_active': s.is_active,
                    'scheduled_hour': s.scheduled_hour,
                    'scheduled_minute': s.scheduled_minute,
                    'repeat_type': s.repeat_type,
                    'repeat_days': s.repeat_days,
                    'posts_per_account': s.posts_per_account,
                    'last_run_at': (s.last_run_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if s.last_run_at else None,
                    'next_run_at': (s.next_run_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if s.next_run_at else None,
                })
        
        return JSONResponse({
            'success': True,
            'schedules': schedules_data,
            'total_pages': total_pages,
            'current_page': page,
            'total_count': total_count
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================================
# ⭐ FLUX 1.1 Pro 이미지 생성 API
# ============================================================

@router.post("/api/generate-images")
async def generate_images(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    FLUX 1.1 Pro로 이미지 2종 생성
    1. 제품 이미지: 제품 정보 기반 자동 생성
    2. 어그로 이미지: 시선을 끄는 음식/라이프스타일 이미지
    """
    try:
        import os
        import fal_client

        body = await request.json()
        product_id = body.get('product_id')
        prompt_id = body.get('prompt_id')
        custom_product_prompt = body.get('product_prompt', '')
        custom_attract_prompt = body.get('attract_prompt', '')
        image_count = body.get('image_count', 1)  # 각 유형당 생성 수

        # fal.ai API 키 확인
        fal_key = os.environ.get('FAL_KEY')
        if not fal_key:
            return JSONResponse({
                'success': False,
                'error': 'FAL_KEY 환경변수가 설정되지 않았습니다. Render 환경변수에 FAL_KEY를 추가해주세요.'
            }, status_code=400)

        os.environ['FAL_KEY'] = fal_key

        # 제품 정보 조회
        product = db.query(AIMarketingProduct).get(product_id) if product_id else None

        results = {
            'success': True,
            'product_images': [],
            'attract_images': [],
        }

        # ─────────────────────────────────────────
        # 1. 제품 이미지 프롬프트 - Claude가 자동 생성
        # ─────────────────────────────────────────
        if not custom_product_prompt and product:
            import anthropic
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                client = anthropic.Anthropic(api_key=api_key)
                claude_msg = client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=400,
                    messages=[{
                        "role": "user",
                        "content": f"""다음 제품을 FLUX AI 이미지 생성기에 넣을 영어 프롬프트를 만들어줘.

제품명: {product.product_name}
핵심 특징: {product.core_value or ''}
서브 특징: {product.sub_core_value or ''}
사이즈/무게: {product.size_weight or ''}
타겟: {product.target_age or ''} {product.target_gender or ''}

규칙:
- 영어로만 작성
- 실제 사진처럼 보이는 자연스러운 생활 장면
- 반드시 위 제품이 실제로 사용되는 모습을 묘사 (음식이나 관계없는 장면 절대 금지)
- 제품의 타겟 고객이 사용하는 장면
- 카메라 기종, 렌즈, 조명 정보 포함 (예: shot on Sony A7III 50mm f1.8)
- 200자 이내
- 프롬프트 텍스트만 출력 (설명, 번호, 따옴표 없이)"""
                    }]
                )
                custom_product_prompt = claude_msg.content[0].text.strip()
                print(f"🤖 Claude 생성 이미지 프롬프트: {custom_product_prompt}")

        # ─────────────────────────────────────────
        # 2. 어그로 이미지 프롬프트 (기본 풀)
        # ─────────────────────────────────────────
        if not custom_attract_prompt:
            import random
            custom_attract_prompt = random.choice(KOREAN_FOOD_ATTRACT_POOL)

        # 실사감을 높이는 공통 suffix
        REALISM_SUFFIX = ", slight lens distortion, minor motion blur, not perfectly composed, natural imperfections, no AI look"

        # ─────────────────────────────────────────
        # 3. FLUX 1.1 Pro로 이미지 생성
        # ─────────────────────────────────────────
        async def generate_single_image(img_prompt: str, portrait: bool = False) -> dict:
            """fal.ai FLUX 1.1 Pro 단일 이미지 생성 (1024×1024 또는 1024×1536)"""
            try:
                full_prompt = img_prompt + REALISM_SUFFIX
                img_size = {"width": 1024, "height": 1536} if portrait else {"width": 1024, "height": 1024}
                print(f"🎨 이미지 생성 중 ({img_size['width']}×{img_size['height']}): {img_prompt[:70]}...")
                result = await fal_client.run_async(
                    "fal-ai/flux-pro/v1.1",
                    arguments={
                        "prompt": full_prompt,
                        "image_size": img_size,
                        "num_inference_steps": 28,
                        "guidance_scale": 3.5,
                        "num_images": 1,
                        "safety_tolerance": "2",
                        "output_format": "jpeg",
                    }
                )
                image_url = result['images'][0]['url']
                print(f"   ✅ 생성 완료: {image_url[:60]}...")
                return {
                    'url': image_url,
                    'prompt': img_prompt,
                    'width': result['images'][0].get('width', 0),
                    'height': result['images'][0].get('height', 0),
                }
            except Exception as e:
                print(f"   ❌ 이미지 생성 실패: {e}")
                return {'url': None, 'prompt': img_prompt, 'error': str(e)}

        # 제품 이미지 생성
        if custom_product_prompt:
            for i in range(image_count):
                img_result = await generate_single_image(custom_product_prompt, portrait=False)
                if img_result.get('url'):
                    results['product_images'].append(img_result)

        # 어그로 이미지 생성
        if custom_attract_prompt:
            for i in range(image_count):
                img_result = await generate_single_image(custom_attract_prompt, portrait=False)
                if img_result.get('url'):
                    results['attract_images'].append(img_result)

        results['product_prompt_used'] = custom_product_prompt
        results['attract_prompt_used'] = custom_attract_prompt
        results['total_generated'] = len(results['product_images']) + len(results['attract_images'])

        print(f"✅ 이미지 생성 완료: 제품 {len(results['product_images'])}장, 어그로 {len(results['attract_images'])}장")
        return JSONResponse(results)

    except ImportError:
        return JSONResponse({
            'success': False,
            'error': 'fal-client 패키지가 설치되지 않았습니다.'
        }, status_code=500)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/generate-images/test")
async def test_fal_connection():
    """fal.ai 연결 상태 확인"""
    import os
    fal_key = os.environ.get('FAL_KEY')
    if not fal_key:
        return JSONResponse({
            'success': False,
            'message': 'FAL_KEY 환경변수 없음',
            'setup_guide': 'Render 대시보드 → Environment → FAL_KEY 추가'
        })
    return JSONResponse({
        'success': True,
        'message': 'FAL_KEY 설정됨',
        'key_preview': f"{fal_key[:8]}..."
    })


# ============================================================
# ⭐ 신규발행 자동 스케줄 관리 API
# ============================================================

def _get_db_draft():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _calc_next_run(hour: int, minute: int, repeat_type: str, repeat_days_json: str) -> Optional[datetime]:
    """다음 실행 시간 계산 (KST 기준)"""
    import json as _j
    now = get_kst_now()
    today_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if repeat_type == 'once':
        return today_run if today_run > now else None

    if repeat_type == 'daily':
        if today_run > now:
            return today_run
        return today_run + timedelta(days=1)

    if repeat_type == 'weekly':
        try:
            days = _j.loads(repeat_days_json) if repeat_days_json else []
        except Exception:
            days = []
        if not days:
            return None
        for delta in range(8):
            candidate = today_run + timedelta(days=delta)
            if candidate.weekday() in days and candidate > now:
                return candidate
        return None

    return None


@router.get("/api/draft-schedules")
async def list_draft_schedules(db: Session = Depends(_get_db_draft)):
    """신규발행 스케줄 목록 조회"""
    schedules = db.query(DraftCreationSchedule).order_by(DraftCreationSchedule.created_at.desc()).all()
    result = []
    for s in schedules:
        result.append({
            'id': s.id,
            'name': s.name,
            'post_title': s.post_title,
            'post_body': s.post_body,
            'cafes_per_account': s.cafes_per_account,
            'scheduled_hour': s.scheduled_hour,
            'scheduled_minute': s.scheduled_minute,
            'repeat_type': s.repeat_type,
            'repeat_days': s.repeat_days,
            'target_pcs': s.target_pcs,
            'is_active': s.is_active,
            'last_run_at': (s.last_run_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if s.last_run_at else None,
            'next_run_at': (s.next_run_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if s.next_run_at else None,
            'created_at': (s.created_at.strftime('%Y-%m-%dT%H:%M:%S') + '+09:00') if s.created_at else None,
        })
    return JSONResponse({'success': True, 'schedules': result})


@router.post("/api/draft-schedules")
async def create_draft_schedule(
    name: str = Form(...),
    post_title: str = Form("안녕하세요"),
    post_body: str = Form(...),
    cafes_per_account: int = Form(1),
    scheduled_hour: int = Form(9),
    scheduled_minute: int = Form(0),
    repeat_type: str = Form("daily"),
    repeat_days: str = Form("[]"),
    target_pcs: str = Form("[]"),
    is_active: bool = Form(True),
    db: Session = Depends(_get_db_draft)
):
    """신규발행 스케줄 생성"""
    next_run = _calc_next_run(scheduled_hour, scheduled_minute, repeat_type, repeat_days)
    schedule = DraftCreationSchedule(
        name=name,
        post_title=post_title,
        post_body=post_body,
        cafes_per_account=cafes_per_account,
        scheduled_hour=scheduled_hour,
        scheduled_minute=scheduled_minute,
        repeat_type=repeat_type,
        repeat_days=repeat_days if repeat_days != '[]' else None,
        target_pcs=target_pcs if target_pcs != '[]' else None,
        is_active=is_active,
        next_run_at=next_run,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return JSONResponse({'success': True, 'id': schedule.id, 'message': '스케줄이 생성되었습니다.'})


@router.put("/api/draft-schedules/{schedule_id}")
async def update_draft_schedule(
    schedule_id: int,
    name: str = Form(...),
    post_title: str = Form("안녕하세요"),
    post_body: str = Form(...),
    cafes_per_account: int = Form(1),
    scheduled_hour: int = Form(9),
    scheduled_minute: int = Form(0),
    repeat_type: str = Form("daily"),
    repeat_days: str = Form("[]"),
    target_pcs: str = Form("[]"),
    is_active: bool = Form(True),
    db: Session = Depends(_get_db_draft)
):
    """신규발행 스케줄 수정"""
    s = db.query(DraftCreationSchedule).get(schedule_id)
    if not s:
        return JSONResponse({'success': False, 'message': '스케줄을 찾을 수 없습니다.'}, status_code=404)
    s.name = name
    s.post_title = post_title
    s.post_body = post_body
    s.cafes_per_account = cafes_per_account
    s.scheduled_hour = scheduled_hour
    s.scheduled_minute = scheduled_minute
    s.repeat_type = repeat_type
    s.repeat_days = repeat_days if repeat_days != '[]' else None
    s.target_pcs = target_pcs if target_pcs != '[]' else None
    s.is_active = is_active
    s.next_run_at = _calc_next_run(scheduled_hour, scheduled_minute, repeat_type, repeat_days)
    db.commit()
    return JSONResponse({'success': True, 'message': '스케줄이 수정되었습니다.'})


@router.delete("/api/draft-schedules/{schedule_id}")
async def delete_draft_schedule(schedule_id: int, db: Session = Depends(_get_db_draft)):
    """신규발행 스케줄 삭제"""
    s = db.query(DraftCreationSchedule).get(schedule_id)
    if not s:
        return JSONResponse({'success': False, 'message': '스케줄을 찾을 수 없습니다.'}, status_code=404)
    db.delete(s)
    db.commit()
    return JSONResponse({'success': True, 'message': '스케줄이 삭제되었습니다.'})


@router.post("/api/draft-schedules/{schedule_id}/toggle")
async def toggle_draft_schedule(schedule_id: int, db: Session = Depends(_get_db_draft)):
    """스케줄 활성/비활성 토글"""
    s = db.query(DraftCreationSchedule).get(schedule_id)
    if not s:
        return JSONResponse({'success': False, 'message': '스케줄을 찾을 수 없습니다.'}, status_code=404)
    s.is_active = not s.is_active
    if s.is_active:
        s.next_run_at = _calc_next_run(s.scheduled_hour, s.scheduled_minute, s.repeat_type, s.repeat_days)
    db.commit()
    return JSONResponse({'success': True, 'is_active': s.is_active})


async def _execute_draft_schedule(schedule_id: int, db: Session) -> dict:
    """
    스케줄 실행 핵심 로직
    - PC별 할당 계정 → 활성 CafeAccountLink에서 N개 랜덤 선택
    - 오늘 이미 해당 (계정+카페)에 인사글 쓴 경우 제외
    - create_draft AutomationTask 생성 후 WebSocket으로 전송
    """
    import random as _random

    s = db.query(DraftCreationSchedule).get(schedule_id)
    if not s:
        return {'success': False, 'message': '스케줄을 찾을 수 없습니다.'}

    now = get_kst_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 대상 PC 결정
    target_pc_nums = []
    if s.target_pcs:
        try:
            target_pc_nums = json.loads(s.target_pcs)
        except Exception:
            target_pc_nums = []

    pc_query = db.query(AutomationWorkerPC)
    if target_pc_nums:
        pc_query = pc_query.filter(AutomationWorkerPC.pc_number.in_(target_pc_nums))
    pcs = pc_query.all()

    if not pcs:
        return {'success': False, 'message': '대상 PC가 없습니다.'}

    tasks_created = []
    skipped = []

    for pc in pcs:
        # 이 PC에 할당된 활성 계정
        accounts = db.query(AutomationAccount).filter(
            AutomationAccount.assigned_pc_id == pc.id,
            AutomationAccount.status == 'active'
        ).all()

        for account in accounts:
            # 이 계정이 가입된 활성 카페 링크
            links = db.query(CafeAccountLink).filter(
                CafeAccountLink.account_id == account.id,
                CafeAccountLink.status == 'active',
                CafeAccountLink.is_member == True
            ).all()

            if not links:
                skipped.append(f"PC#{pc.pc_number}/{account.account_id}: 가입 카페 없음")
                continue

            # 오늘 이미 create_draft 완료한 카페 제외
            done_today = db.query(AutomationTask).filter(
                AutomationTask.task_type == 'create_draft',
                AutomationTask.assigned_account_id == account.id,
                AutomationTask.status == 'completed',
                AutomationTask.completed_at >= today_start
            ).all()
            done_cafe_ids = {t.cafe_id for t in done_today}

            available_links = [lk for lk in links if lk.cafe_id not in done_cafe_ids]

            if not available_links:
                skipped.append(f"PC#{pc.pc_number}/{account.account_id}: 오늘 이미 모든 카페 완료")
                continue

            # N개 랜덤 선택
            n = min(s.cafes_per_account, len(available_links))
            selected = _random.sample(available_links, n)

            for link in selected:
                task = AutomationTask(
                    task_type='create_draft',
                    mode='ai',
                    status='pending',
                    assigned_pc_id=pc.id,
                    assigned_account_id=account.id,
                    cafe_id=link.cafe_id,
                    title=s.post_title,
                    content=s.post_body,
                    scheduled_time=now,
                    # draft_title/body를 error_message JSON에 저장 (기존 컬럼 재활용)
                    error_message=json.dumps({
                        'draft_title': s.post_title,
                        'draft_body': s.post_body
                    }, ensure_ascii=False)
                )
                db.add(task)
                db.flush()
                tasks_created.append({
                    'task_id': task.id,
                    'pc_number': pc.pc_number,
                    'account_id': account.account_id,
                    'cafe_id': link.cafe_id,
                })

    db.commit()

    # WebSocket으로 즉시 전송 시도
    from routers.automation import worker_connections, send_task_to_worker
    sent = []
    queued = []
    for t_info in tasks_created:
        task_obj = db.query(AutomationTask).get(t_info['task_id'])
        pc_num = t_info['pc_number']
        if pc_num in worker_connections:
            try:
                await send_task_to_worker(pc_num, task_obj, db)
                task_obj.status = 'assigned'
                db.commit()
                sent.append(t_info)
            except Exception as e:
                queued.append({**t_info, 'reason': str(e)})
        else:
            queued.append({**t_info, 'reason': '워커 오프라인 - DB 대기'})

    # 스케줄 last_run_at / next_run_at 업데이트
    s.last_run_at = now
    if s.repeat_type == 'once':
        s.is_active = False
        s.next_run_at = None
    else:
        s.next_run_at = _calc_next_run(s.scheduled_hour, s.scheduled_minute, s.repeat_type, s.repeat_days)

    # 실행 로그 저장 (task_ids JSON으로 상세 조회 가능하게)
    try:
        from database import ScheduleLog
        import json as _json_log
        log_data = {
            'task_ids': [t['task_id'] for t in tasks_created],
            'skipped': skipped[:10],
        }
        log_entry = ScheduleLog(
            schedule_type='draft',
            schedule_id=s.id,
            schedule_name=s.name,
            status='success' if tasks_created else 'partial',
            tasks_created=len(tasks_created),
            message=_json_log.dumps(log_data, ensure_ascii=False)
        )
        db.add(log_entry)
    except Exception as le:
        print(f"  ⚠️ 로그 저장 실패: {le}")

    db.commit()

    return {
        'success': True,
        'tasks_created': len(tasks_created),
        'sent': len(sent),
        'queued': len(queued),
        'details': tasks_created,
        'skipped': skipped,
    }


# ─────────────────────────────────────────────────────────────
# 내부용 AI 글 생성 헬퍼 (인증 불필요)
# ─────────────────────────────────────────────────────────────
async def _generate_ai_content_internal(
    prompt_id: int, keyword: str, cafe_id: int, db: Session
) -> dict:
    """
    스케줄 자동 실행용 AI 글 생성 함수.
    인증 없이 Claude API를 호출해 제목/본문/댓글을 반환한다.
    반환: {'success': bool, 'title': str, 'body': str, 'comments': str, 'image_urls': list, 'error': str}
    """
    try:
        import anthropic, os

        prompt = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product)
        ).filter(AIPrompt.id == prompt_id).first()
        if not prompt or not prompt.ai_product:
            return {'success': False, 'error': '프롬프트를 찾을 수 없습니다'}

        product = prompt.ai_product
        cafe = db.query(AutomationCafe).filter(AutomationCafe.id == cafe_id).first()
        cafe_name = cafe.name if cafe else '알 수 없음'
        cafe_characteristics = (
            cafe.characteristics if cafe and cafe.characteristics
            else '일반적인 톤, 자연스러운 대화체'
        )

        # 레퍼런스
        ai_refs = db.query(AIProductReference).options(
            joinedload(AIProductReference.reference).joinedload(Reference.comments)
        ).filter(
            AIProductReference.ai_product_id == product.id,
            AIProductReference.reference_type == prompt.keyword_classification
        ).limit(3).all()

        reference_text = ''
        for idx, ai_ref in enumerate(ai_refs):
            if ai_ref.reference:
                ref = ai_ref.reference
                reference_text += f'\n\n【예시 {idx + 1}: {ref.title}】\n{ref.content}\n'
                if ref.comments:
                    reference_text += '\n댓글:\n'
                    for c in ref.comments[:5]:
                        reference_text += f'- 계정{c.account_sequence}: {c.text}\n'

        # 변수 치환
        replacements = {
            '{타겟_키워드}': keyword, '{keyword}': keyword,
            '{product_name}': product.product_name,
            '{core_value}': product.core_value or '',
            '{sub_core_value}': product.sub_core_value or '',
            '{size_weight}': product.size_weight or '',
            '{difference}': product.difference or '',
            '{famous_brands}': product.famous_brands or '',
            '{market_problem}': product.market_problem or '',
            '{our_price}': product.our_price or '',
            '{market_avg_price}': product.market_avg_price or '',
            '{target_age}': product.target_age or '',
            '{target_gender}': product.target_gender or '',
            '{additional_info}': product.additional_info or '',
            '{marketing_link}': product.marketing_link or '',
        }
        user_prompt = prompt.user_prompt
        system_prompt = prompt.system_prompt
        for var, val in replacements.items():
            user_prompt = user_prompt.replace(var, str(val))
            system_prompt = system_prompt.replace(var, str(val))

        if reference_text:
            user_prompt += f'\n\n참고할 예시 글들:{reference_text}\n\n위 예시들의 톤과 스타일을 참고하여 자연스럽고 진정성 있는 글을 작성해주세요.'

        if prompt.apply_cafe_context:
            user_prompt += f'\n\n[발행될 카페 정보]\n- 카페명: {cafe_name}\n- 카페 특성: {cafe_characteristics}\n\n위 카페의 특성에 맞춰 자연스럽게 작성해주세요.'

        # 댓글 지침
        from database import CafeAccountLink as _Cal
        cafe_links_cnt = db.query(_Cal).filter(_Cal.cafe_id == cafe_id).count()
        comment_account_count = max(1, cafe_links_cnt - 1)
        user_prompt += f'''

[댓글 작성 지침 - 중요!]
- 이 카페에 가입된 계정은 총 {cafe_links_cnt}개입니다 (작성자 포함).
- 댓글 작성자는 정확히 {comment_account_count}명만 사용하세요.
- 작성자명: '계정1'부터 '계정{comment_account_count}'까지'''

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return {'success': False, 'error': 'ANTHROPIC_API_KEY 환경변수 없음'}

        # ── 상세 로그 (test_generate_content와 동일) ──────────────
        print("\n" + "="*80)
        print("🔍 [AI생성] Claude API 호출 - 프롬프트 확인")
        print("="*80)
        print(f"  [Model]       : claude-opus-4-5")
        print(f"  [Temperature] : {prompt.temperature}")
        print(f"  [Max Tokens]  : {prompt.max_tokens}")
        print(f"  [키워드]      : {keyword}")
        print(f"  [카페명]      : {cafe_name}")
        print(f"  [카페 특성]   : {cafe_characteristics}")
        print(f"  [상품명]      : {product.product_name}")
        print(f"  [이미지 생성] : {prompt.generate_images}")
        if prompt.generate_images:
            print(f"  [제품 이미지 수] : {getattr(prompt, 'product_image_count', 1)}")
            print(f"  [어그로 이미지 수]: {getattr(prompt, 'attract_image_count', 2)}")
        print("\n" + "-"*80)
        print("[System Prompt]")
        print(system_prompt)
        print("\n" + "-"*80)
        print("[User Prompt]")
        print(user_prompt)
        print("\n" + "="*80 + "\n")

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}]
        )
        raw = response.content[0].text

        print("\n" + "="*80)
        print("📝 [AI생성] Claude 응답 원문")
        print("="*80)
        print(raw)
        print("="*80)
        print(f"  → 총 {len(raw)}자 생성됨\n")

        # 제목/본문/댓글 분리 (test_generate_content와 동일 로직)
        def _clean_title(raw_title: str) -> str:
            """제목에서 첫 번째 유효한 줄만 추출하고 마크다운/불필요 텍스트 제거"""
            # 줄 단위로 분리 후 비어있지 않은 첫 줄만 사용
            # (Claude가 제목 섹션에 여러 줄 생성하는 경우 대응 - e.g. "Title\nMenu")
            skip_words = {'Menu', '---', 'Title', '제목', 'menu', 'title'}
            for line in raw_title.split('\n'):
                line = line.strip()
                if line and line not in skip_words:
                    # 남은 마크다운 기호 제거 (**bold**, ## heading)
                    line = line.strip('*').strip('#').strip()
                    if line:
                        return line
            return raw_title.split('\n')[0].strip().strip('*').strip('#').strip()

        def _split(text):
            title = body = comments = ''
            sections = text.split('---')
            if len(sections) >= 3:
                t, b, c = sections[0].strip(), sections[1].strip(), sections[2].strip()
                for prefix in ['# 제목', '**제목:**', '**제목**']:
                    if t.startswith(prefix):
                        title = _clean_title(t.replace(prefix, '', 1).strip()); break
                else:
                    lines = t.split('\n')
                    title = _clean_title(lines[0].replace('#', '').strip())
                for prefix in ['# 본문', '## 본문', '**본문:**', '**본문**']:
                    if b.startswith(prefix):
                        body = b.replace(prefix, '', 1).strip(); break
                else:
                    body = b
                for prefix in ['# 댓글', '**댓글:**', '**댓글**']:
                    if c.startswith(prefix):
                        comments = c.replace(prefix, '', 1).strip(); break
                else:
                    comments = c
            elif len(sections) == 2:
                t, b = sections[0].strip(), sections[1].strip()
                title = _clean_title(
                    t.replace('# 제목', '', 1).strip() if t.startswith('# 제목')
                    else t.split('\n')[0].replace('#', '').strip()
                )
                body = b.replace('# 본문', '', 1).strip() if b.startswith('# 본문') else b
            else:
                lines = text.strip().split('\n')
                if lines and lines[0].startswith('#'):
                    title = _clean_title(lines[0].replace('#', '').strip())
                    body = '\n'.join(lines[1:]).strip()
                else:
                    body = text.strip()
            return title, body, comments

        title, body, comments = _split(raw)

        # 분리 결과 로그
        print("\n" + "-"*80)
        print("✂️ [AI생성] 제목/본문/댓글 분리 결과")
        print(f"  [제목] {title}")
        print(f"  [본문] {len(body)}자")
        if body:
            print(f"  [본문 미리보기] {body[:200]}{'...' if len(body) > 200 else ''}")
        print(f"  [댓글] {len(comments)}자")
        if comments:
            print(f"  [댓글 미리보기] {comments[:300]}{'...' if len(comments) > 300 else ''}")
        print("-"*80 + "\n")

        # 이미지 생성 (prompt 설정에 따라)
        image_urls = []
        if prompt.generate_images:
            try:
                n_product = getattr(prompt, 'product_image_count', 1) or 1
                n_attract = getattr(prompt, 'attract_image_count', 2) or 2
                attract_pool_raw = getattr(prompt, 'attract_image_prompts', None)
                attract_pool = []
                if attract_pool_raw:
                    import json as _j
                    try:
                        attract_pool = _j.loads(attract_pool_raw)
                    except Exception:
                        attract_pool = [p.strip() for p in attract_pool_raw.split('\n') if p.strip()]

                print(f"\n🎨 [AI생성] 이미지 생성 시작")
                print(f"  제품 이미지: {n_product}장, 어그로 이미지: {n_attract}장")
                print(f"  어그로 풀: {len(attract_pool)}개 프롬프트")

                import random as _rnd
                # 제품 이미지 프롬프트
                for i in range(n_product):
                    prod_prompt_text = (
                        f"Professional product photography of {product.product_name}. "
                        f"{product.core_value}. High quality, clean background, "
                        f"natural lighting, 4K resolution."
                    )
                    print(f"\n  📦 제품이미지 {i+1}/{n_product} 프롬프트:")
                    print(f"     {prod_prompt_text}")
                    url = await generate_images_with_imagen(prod_prompt_text, 1)
                    if url:
                        image_urls.extend(url if isinstance(url, list) else [url])
                        print(f"     ✅ 생성 완료: {url if isinstance(url, list) else [url]}")
                    else:
                        print(f"     ❌ 생성 실패")

                # 어그로 이미지
                for i in range(n_attract):
                    if attract_pool:
                        ap = _rnd.choice(attract_pool)
                        tail = ", slight lens distortion, minor motion blur, not perfectly composed, natural imperfections, no AI look"
                        full_prompt = ap + tail
                        print(f"\n  🍖 어그로이미지 {i+1}/{n_attract} 프롬프트:")
                        print(f"     {full_prompt[:200]}...")
                        url = await generate_images_with_imagen(full_prompt, 1)
                        if url:
                            image_urls.extend(url if isinstance(url, list) else [url])
                            print(f"     ✅ 생성 완료: {url if isinstance(url, list) else [url]}")
                        else:
                            print(f"     ❌ 생성 실패")

                print(f"\n  🎨 이미지 생성 완료: 총 {len(image_urls)}장")
                for idx_img, img_url in enumerate(image_urls):
                    print(f"     [{idx_img+1}] {img_url}")
            except Exception as img_err:
                print(f'  ⚠️ 이미지 생성 오류 (무시): {img_err}')
                import traceback; traceback.print_exc()

        return {
            'success': True,
            'title': title,
            'body': body,
            'comments': comments,
            'image_urls': image_urls,
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return {'success': False, 'error': str(e)}


# ─────────────────────────────────────────────────────────────
# AI 순차 실행 큐 (메모리) - schedule_id → deque of group_info
# ─────────────────────────────────────────────────────────────
from collections import deque as _deque
_ai_schedule_queues: dict = {}       # schedule_id → deque[group_info]
_ai_task_schedule_map: dict = {}     # post_task_id → schedule_id


async def _run_ai_group(group_info: dict, schedule_id: int, db) -> int | None:
    """
    단일 그룹 실행: AI 생성 → post task + 댓글 task 생성 → 첫 task 전송
    반환: post_task.id (실패 시 None)
    """
    import random as _r
    import json as _j

    account_id  = group_info['account_id']
    pc_id       = group_info['pc_id']
    pc_number   = group_info['pc_number']
    link_id     = group_info['link_id']
    cafe_id     = group_info['cafe_id']
    draft_url   = group_info['draft_url']
    draft_id    = group_info['draft_id']
    keyword_str = group_info['keyword']
    prompt_id   = group_info['prompt_id']
    product_name= group_info['product_name']
    now         = group_info['now']

    # ── AI 글/댓글/이미지 생성 ─────────────────────────────────
    print(f"\n{'='*80}")
    print(f"🤖 [AI그룹] 실행 시작")
    print(f"{'='*80}")
    print(f"  PC번호      : #{pc_number}")
    print(f"  계정ID      : {account_id}")
    print(f"  카페ID      : {cafe_id}")
    print(f"  초안 URL    : {draft_url}")
    print(f"  타겟 키워드 : {keyword_str}")
    print(f"  상품명      : {product_name}")
    print(f"  프롬프트 ID : {prompt_id}")
    print(f"  스케줄 ID   : {schedule_id}")
    print(f"{'='*80}")

    ai_result = await _generate_ai_content_internal(prompt_id, keyword_str or product_name, cafe_id, db)
    if not ai_result.get('success'):
        print(f"  ❌ AI 생성 실패: {ai_result.get('error')}")
        return None

    _raw_title = ai_result['title'] or keyword_str or product_name
    # 네이버 제목 200byte(한글 100자) 제한 적용
    _title_encoded = _raw_title.encode('utf-8')
    if len(_title_encoded) > 190:
        _raw_title = _title_encoded[:190].decode('utf-8', errors='ignore')
        print(f"  ⚠️  제목 자동 축약 (byte초과): {_raw_title}")
    ai_title = _raw_title
    ai_body  = ai_result['body']
    ai_comments_text = ai_result.get('comments', '')
    ai_image_urls    = ai_result.get('image_urls', [])
    image_urls_json  = _j.dumps(ai_image_urls) if ai_image_urls else None

    print(f"\n  📊 [AI그룹] 생성 결과 요약")
    print(f"     제목     : {ai_title}")
    print(f"     본문 길이: {len(ai_body)}자")
    print(f"     댓글 길이: {len(ai_comments_text)}자")
    print(f"     이미지 수: {len(ai_image_urls)}장")

    # ── post task 생성 ─────────────────────────────────────────
    account = db.query(AutomationAccount).get(account_id)
    post_task = AutomationTask(
        task_type='post', mode='ai', status='pending',
        assigned_pc_id=pc_id, assigned_account_id=account_id,
        cafe_id=cafe_id, scheduled_time=now,
        title=ai_title, content=ai_body,
        error_message=f"MODIFY_URL:{draft_url}",
        keyword=keyword_str, image_urls=image_urls_json,
        product_name=product_name,  # 대시보드 표시용
    )
    db.add(post_task)
    db.flush()
    print(f"\n  ✅ post Task #{post_task.id} 생성 (제목: {ai_title[:50]})")

    # ── 댓글/대댓글 task 생성 ──────────────────────────────────
    from database import CafeAccountLink as _Cal
    other_accs = []
    for cl in db.query(_Cal).filter(_Cal.cafe_id == cafe_id, _Cal.status == 'active', _Cal.account_id != account_id).all():
        acc = db.query(AutomationAccount).filter(AutomationAccount.id == cl.account_id, AutomationAccount.status == 'active').first()
        if acc:
            other_accs.append(acc)

    comment_count = 0
    if ai_comments_text and other_accs:
        def _parse(text):
            res = []
            for line in text.strip().split('\n'):
                if not line.strip() or line.startswith('---') or line.startswith('#'): continue
                lvl = 0
                while line.startswith('>'): lvl += 1; line = line[1:].strip()
                if '**' in line and ':**' in line:
                    try:
                        parts = line.split('**')
                        if len(parts) >= 3:
                            acct = parts[1].split(':')[0].strip()
                            content = '**'.join(parts[2:]).strip()
                            res.append({'level': lvl, 'account': acct, 'content': content})
                    except: pass
            return res

        parsed = _parse(ai_comments_text)
        task_map = {}
        for idx, cm in enumerate(parsed):
            parent_id = post_task.id
            task_type_cm = 'comment' if cm['level'] == 0 else 'reply'
            if cm['level'] > 0:
                for i in range(idx - 1, -1, -1):
                    if parsed[i]['level'] == 0:
                        parent_id = task_map.get(i, post_task.id); break

            target_acc_id = target_pc_id = None
            aname = cm['account']
            if aname == '작성자':
                target_acc_id, target_pc_id = account_id, pc_id
            elif aname.startswith('계정'):
                import re as _re
                m = _re.search(r'\d+', aname)
                if m and other_accs:
                    oa = other_accs[(int(m.group()) - 1) % len(other_accs)]
                    target_acc_id, target_pc_id = oa.id, oa.assigned_pc_id

            ct = AutomationTask(
                task_type=task_type_cm, mode='ai', status='pending',
                scheduled_time=now, content=cm['content'],
                parent_task_id=parent_id, order_sequence=idx,
                cafe_id=cafe_id, assigned_pc_id=target_pc_id,
                assigned_account_id=target_acc_id, priority=10,
            )
            db.add(ct); db.flush()
            task_map[idx] = ct.id
            comment_count += 1

    db.commit()
    print(f"  💬 댓글 {comment_count}개 생성")

    # ── post task 워커에 전송 ──────────────────────────────────
    from routers.automation import worker_connections, send_task_to_worker
    if pc_number in worker_connections:
        await send_task_to_worker(pc_number, post_task, db)
        post_task.status = 'assigned'; db.commit()
        print(f"  📤 Task #{post_task.id} → PC #{pc_number} 전송")
    else:
        print(f"  ⏳ PC #{pc_number} 오프라인 - DB 대기")

    # ── DraftPost 예약 처리 ────────────────────────────────────
    draft = db.query(DraftPost).get(draft_id)
    if draft:
        draft.status = 'reserved'
        db.commit()

    return post_task.id


async def _execute_next_ai_group(schedule_id: int, db) -> bool:
    """큐에서 다음 그룹을 꺼내 실행. 큐가 비면 False 반환."""
    queue = _ai_schedule_queues.get(schedule_id)
    if not queue:
        print(f"  ✅ [AI스케줄#{schedule_id}] 모든 그룹 처리 완료")
        return False

    group_info = queue.popleft()
    post_task_id = await _run_ai_group(group_info, schedule_id, db)
    if post_task_id:
        _ai_task_schedule_map[post_task_id] = schedule_id
    return True


# ─────────────────────────────────────────────────────────────
# AI 수정발행 스케줄 실행 함수
# ─────────────────────────────────────────────────────────────
async def _execute_ai_schedule(schedule_id: int, db: Session) -> dict:
    """
    AI 수정발행 스케줄 실행 (완전 순차).
    1) 전체 실행 계획(그룹 목록)을 빌드하여 메모리 큐에 저장
    2) 첫 번째 그룹만 즉시 AI 생성 → task 생성 → 전송
    3) 이후 그룹들은 _dispatch_next_task_bg 가 마지막 댓글 완료 시 하나씩 꺼내 실행
    """
    import random as _random

    schedule = db.query(AIMarketingSchedule).get(schedule_id)
    if not schedule:
        return {'success': False, 'message': '스케줄을 찾을 수 없습니다.'}

    now = get_kst_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    pcs = db.query(AutomationWorkerPC).order_by(AutomationWorkerPC.pc_number).all()
    if not pcs:
        return {'success': False, 'message': '등록된 Worker PC가 없습니다.'}

    # ── 활성 키워드 한 번만 조회 ──────────────────────────────
    active_kws = []
    if schedule.ai_product:
        active_kws = db.query(AIProductKeyword).filter(
            AIProductKeyword.ai_product_id == schedule.ai_product_id,
            AIProductKeyword.is_active == True
        ).all()

    def _pick_keyword():
        if not active_kws:
            return None
        eligible = [k for k in active_kws if db.query(AutomationTask).filter(
            AutomationTask.task_type == 'post',
            AutomationTask.keyword == k.keyword_text,
            AutomationTask.status == 'completed'
        ).count() < 6]
        pool = eligible if eligible else active_kws
        return _random.choice(pool).keyword_text

    product_name = schedule.ai_product.product_name if schedule.ai_product else ''
    groups = []   # 실행 계획
    skipped = []

    from database import CafeAccountLink

    for pc in pcs:
        accounts = db.query(AutomationAccount).filter(
            AutomationAccount.assigned_pc_id == pc.id,
            AutomationAccount.status == 'active'
        ).all()

        for account in accounts:
            done_cafe_ids = {t.cafe_id for t in db.query(AutomationTask).filter(
                AutomationTask.task_type == 'post',
                AutomationTask.assigned_account_id == account.id,
                AutomationTask.status == 'completed',
                AutomationTask.completed_at >= today_start
            ).all()}

            eligible = []
            for link in db.query(CafeAccountLink).filter(
                CafeAccountLink.account_id == account.id,
                CafeAccountLink.status == 'active'
            ).all():
                if link.cafe_id in done_cafe_ids:
                    continue
                draft = db.query(DraftPost).filter(
                    DraftPost.link_id == link.id,
                    DraftPost.status == 'available'
                ).first()
                if draft:
                    eligible.append((link, draft))

            if not eligible:
                skipped.append(f"PC#{pc.pc_number}/{account.account_id}: DraftPost 없음")
                continue

            n = min(schedule.posts_per_account or 1, len(eligible))
            for link, draft in _random.sample(eligible, n):
                groups.append({
                    'account_id': account.id,
                    'pc_id': pc.id,
                    'pc_number': pc.pc_number,
                    'link_id': link.id,
                    'cafe_id': link.cafe_id,
                    'draft_url': draft.draft_url,
                    'draft_id': draft.id,
                    'keyword': _pick_keyword() or product_name,
                    'prompt_id': schedule.prompt_id,
                    'product_name': product_name,
                    'now': now,
                })

    if not groups:
        return {'success': False, 'message': '실행할 그룹 없음', 'skipped': skipped}

    # ── 큐에 저장 (그룹 1 제외한 나머지) ─────────────────────
    _ai_schedule_queues[schedule_id] = _deque(groups[1:])

    # ── 첫 번째 그룹 즉시 실행 ────────────────────────────────
    print(f"\n[AI스케줄#{schedule_id}] 총 {len(groups)}개 그룹 → 첫 그룹 즉시 실행")
    first_post_id = await _run_ai_group(groups[0], schedule_id, db)
    if first_post_id:
        _ai_task_schedule_map[first_post_id] = schedule_id

    # ── 스케줄 last_run_at / next_run_at 업데이트 ─────────────
    schedule.last_run_at = now
    if schedule.repeat_type == 'once':
        schedule.is_active = False
        schedule.next_run_at = None
    else:
        schedule.next_run_at = _calc_next_run(
            schedule.scheduled_hour, schedule.scheduled_minute,
            schedule.repeat_type, schedule.repeat_days
        )

    # ── 실행 로그 저장 ─────────────────────────────────────────
    try:
        from database import ScheduleLog
        import json as _jl
        log_entry = ScheduleLog(
            schedule_type='ai', schedule_id=schedule.id,
            schedule_name=product_name,
            status='success' if groups else 'partial',
            tasks_created=len(groups),
            message=_jl.dumps({'task_ids': [], 'skipped': skipped[:10]}, ensure_ascii=False)
        )
        db.add(log_entry)
    except Exception as le:
        print(f"  ⚠️ 로그 저장 실패: {le}")

    db.commit()

    return {
        'success': True,
        'total_groups': len(groups),
        'queued': len(groups) - 1,
        'skipped': skipped,
        'message': f'총 {len(groups)}개 그룹 순차 실행 예약 완료 (첫 그룹 즉시 시작)',
    }


@router.post("/api/ai-schedules/{schedule_id}/run")
async def run_ai_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI 수정발행 스케줄 즉시 실행"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    result = await _execute_ai_schedule(schedule_id, db)
    return JSONResponse(result)


@router.post("/api/draft-schedules/{schedule_id}/run")
async def run_draft_schedule(schedule_id: int, db: Session = Depends(_get_db_draft)):
    """스케줄 즉시 실행"""
    result = await _execute_draft_schedule(schedule_id, db)
    return JSONResponse(result)


@router.post("/api/draft-schedules/test-run")
async def test_run_draft_schedule(
    name: str = Form("테스트"),
    post_title: str = Form("안녕하세요"),
    post_body: str = Form(...),
    cafes_per_account: int = Form(1),
    scheduled_hour: int = Form(9),
    scheduled_minute: int = Form(0),
    repeat_type: str = Form("daily"),
    repeat_days: str = Form("[]"),
    target_pcs: str = Form("[]"),
    db: Session = Depends(_get_db_draft)
):
    """
    스케줄 저장 없이 즉시 테스트 실행
    - 임시 스케줄 객체를 DB에 저장 후 실행, 완료 후 삭제
    """
    next_run = _calc_next_run(scheduled_hour, scheduled_minute, repeat_type, repeat_days)
    temp = DraftCreationSchedule(
        name=f"[테스트] {name}",
        post_title=post_title,
        post_body=post_body,
        cafes_per_account=cafes_per_account,
        scheduled_hour=scheduled_hour,
        scheduled_minute=scheduled_minute,
        repeat_type=repeat_type,
        repeat_days=repeat_days if repeat_days != '[]' else None,
        target_pcs=target_pcs if target_pcs != '[]' else None,
        is_active=False,
        next_run_at=next_run,
    )
    db.add(temp)
    db.commit()
    db.refresh(temp)

    result = await _execute_draft_schedule(temp.id, db)

    # 임시 스케줄 삭제
    temp_obj = db.query(DraftCreationSchedule).get(temp.id)
    if temp_obj:
        db.delete(temp_obj)
        db.commit()

    return JSONResponse({**result, 'test_mode': True})


@router.get("/api/draft-schedules/worker-pcs")
async def list_worker_pcs_for_schedule(db: Session = Depends(_get_db_draft)):
    """스케줄 설정용 PC 목록"""
    from routers.automation import worker_connections
    pcs = db.query(AutomationWorkerPC).order_by(AutomationWorkerPC.pc_number).all()
    result = []
    for pc in pcs:
        accounts = db.query(AutomationAccount).filter(
            AutomationAccount.assigned_pc_id == pc.id,
            AutomationAccount.status == 'active'
        ).count()
        result.append({
            'pc_number': pc.pc_number,
            'pc_name': pc.pc_name,
            'status': pc.status,
            'is_connected': pc.pc_number in worker_connections,
            'account_count': accounts,
        })
    return JSONResponse({'success': True, 'pcs': result})