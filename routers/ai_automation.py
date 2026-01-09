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
    """프롬프트 추가"""
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


@router.post("/schedules/delete/{schedule_id}")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """스케줄 삭제"""
    schedule = db.query(AIMarketingSchedule).filter(AIMarketingSchedule.id == schedule_id).first()
    
    if schedule:
        db.delete(schedule)
        db.commit()
    
    return JSONResponse({"success": True})


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
