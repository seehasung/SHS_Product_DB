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
    AutomationAccount, AutomationCafe, CafeAccountLink, Reference
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
        
        keywords_data = [{
            'id': kw.id,
            'keyword_text': kw.keyword_text,
            'keyword_type': kw.keyword_type,
            'is_active': kw.is_active
        } for kw in keywords]
        
        # 활성 키워드 수 계산
        active_count = sum(1 for kw in keywords if kw.is_active)
        
        return JSONResponse({
            'success': True, 
            'keywords': keywords_data,
            'count': active_count,
            'total': len(keywords_data)
        })
    except Exception as e:
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
    db: Session = Depends(get_db)
):
    """스케줄 추가 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
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
            'used_at': dp.used_at.isoformat() if dp.used_at else None,
            'created_at': dp.created_at.isoformat() if dp.created_at else None
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
            
            # 1. --- 구분자로 섹션 분리
            sections = text.split('---')
            
            if len(sections) >= 3:
                # 형식: # 제목\n내용\n---\n# 본문\n내용\n---\n# 댓글\n내용
                title_section = sections[0].strip()
                body_section = sections[1].strip()
                comments_section = sections[2].strip()
                
                # 제목 추출 (헤더 제거)
                if title_section.startswith('# 제목'):
                    title = title_section.replace('# 제목', '', 1).strip()
                elif title_section.startswith('**제목:**'):
                    title = title_section.replace('**제목:**', '', 1).strip()
                elif title_section.startswith('**제목**'):
                    title = title_section.replace('**제목**', '', 1).strip()
                else:
                    # 첫 줄만 제목
                    lines = title_section.split('\n')
                    if lines[0].startswith('#'):
                        title = lines[0].replace('#', '').strip()
                    else:
                        title = lines[0].strip()
                
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
                    title = title_section.replace('# 제목', '', 1).strip()
                else:
                    lines = title_section.split('\n')
                    title = lines[0].replace('#', '').strip() if lines[0].startswith('#') else lines[0].strip()
                
                if body_section.startswith('# 본문'):
                    body = body_section.replace('# 본문', '', 1).strip()
                else:
                    body = body_section.strip()
                
            else:
                # --- 없는 경우: 전체를 본문으로
                lines = text.strip().split('\n')
                if lines and lines[0].startswith('#'):
                    title = lines[0].replace('#', '').strip()
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
            image_urls=image_urls_json,  # ⭐ 이미지 URL 저장
            keyword=keyword  # ⭐ 타겟 키워드 (태그 자동 입력용)
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
        
        # 6. Worker PC에 직접 전송 (계정 유지)
        from routers.automation import send_task_to_worker, worker_connections
        
        # 본문 Task 전송
        print(f"\n📤 본문 Task 전송 준비...")
        print(f"   assigned_account_id: {assigned_account_id}")
        print(f"   assigned_pc_id: {assigned_pc_id}")
        
        if assigned_pc_id and assigned_pc_id in worker_connections:
            await send_task_to_worker(assigned_pc_id, post_task, db)
            print(f"✅ Task #{post_task.id} 직접 전송 → PC #{assigned_pc_id}")
        else:
            print(f"⚠️  본문 Task 전송 실패: PC #{assigned_pc_id} 연결 안 됨 (worker_connections: {list(worker_connections.keys())})")
        
        # 댓글 Task는 본문 Task 완료 후 자동 할당됨 (task_completed → assign_next_task)
        
        return JSONResponse({
            'success': True,
            'message': f'글 + 댓글 {len(comment_tasks)}개 Task 생성 완료!',
            'task_id': post_task.id,
            'title': test_data.get('title'),
            'body': test_data.get('body'),
            'ai_comments': test_data.get('comments'),  # AI가 생성한 댓글 (참고용)
            'task_comments': len(comment_tasks),  # Task로 생성된 댓글 수
            'cafe_name': test_data.get('cafe_name'),
            'image_urls': test_data.get('image_urls', [])
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
                    'status': s.status
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