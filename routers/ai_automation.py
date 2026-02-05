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
            generate_images=generate_images
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
                'generate_images': prompt.generate_images
            }
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/prompts/update/{prompt_id}")
async def update_prompt_json(
    prompt_id: int,
    request: Request,
    keyword_classification: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt: str = Form(...),
    temperature: float = Form(...),
    max_tokens: int = Form(...),
    generate_images: bool = Form(False),
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
        prompt.keyword_classification = keyword_classification
        prompt.system_prompt = system_prompt
        prompt.user_prompt = user_prompt
        prompt.temperature = temperature
        prompt.max_tokens = max_tokens
        prompt.generate_images = generate_images
        
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
    product: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """상품별 프롬프트 목록 조회 (JSON)"""
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"success": False, "error": "로그인이 필요합니다"}, status_code=401)
    
    try:
        query = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product)
        )
        
        if product:
            query = query.filter(AIPrompt.ai_product_id == product)
        
        prompts = query.all()
        
        prompts_data = [{
            'id': p.id,
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