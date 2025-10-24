from fastapi import APIRouter, Request, Form
from sqlalchemy.exc import IntegrityError
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import math
from fastapi import Query
from database import SessionLocal, User, Product

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ✅ 사용자 목록 보기 (검색 포함)
@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, search: str = ""):
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)

    db: Session = SessionLocal()
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_admin:
        db.close()
        return RedirectResponse("/", status_code=302)

    users = db.query(User).filter(User.username.contains(search)).all() if search else db.query(User).all()
    db.close()
    return templates.TemplateResponse("admin_users_bootstrap.html", {
        "request": request,
        "users": users,
        "username": username,
        "search": search
    })

# ✅ 사용자 이름 수정
@router.post("/users/update")
def update_user(user_id: int = Form(...), new_username: str = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.username = new_username
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 관리자 권한 토글
@router.post("/users/toggle-admin")
def toggle_admin(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_admin = not user.is_admin
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 사용자 삭제
@router.post("/users/delete")
def delete_user(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'admin':
        db.delete(user)
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 상품 목록 보기 (JSON 직렬화 문제 해결)
@router.get("/products", response_class=HTMLResponse)
def product_list(request: Request):
    """
    상품 목록 페이지
    페이지네이션은 프론트엔드에서 처리
    """
    db = SessionLocal()
    
    try:
        # 모든 상품을 가져옴 (페이지네이션 없이)
        all_products = db.query(Product).all()
        
        # 정렬 (상품코드 기준)
        def custom_sort_key(product):
            try:
                if product.product_code:
                    parts = product.product_code.split('-')
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        return (int(parts[0]), int(parts[1]))
                return (float('inf'),)
            except:
                return (float('inf'),)
        
        # Python에서 정렬
        sorted_products = sorted(all_products, key=custom_sort_key)
        
        # 딕셔너리로 변환 (JSON 직렬화 가능)
        products_list = []
        for product in sorted_products:
            product_dict = {
                'id': product.id,
                'product_code': product.product_code or '',
                'name': product.name or '',
                'price': product.price or 0,
                'kd_paid': bool(product.kd_paid),
                'customs_paid': bool(product.customs_paid),
                'customs_cost': product.customs_cost or 0,
                'coupang_link': product.coupang_link or '',
                'taobao_link': product.taobao_link or '',
                'thumbnail': product.thumbnail or '',
                'details': product.details or '',
                'coupang_options': product.coupang_options or '[]',
                'taobao_options': product.taobao_options or '[]'
            }
            
            # 네이버 필드 (있는 경우만)
            if hasattr(product, 'naver_link'):
                product_dict['naver_link'] = product.naver_link or ''
            else:
                product_dict['naver_link'] = ''
                
            if hasattr(product, 'naver_options'):
                product_dict['naver_options'] = product.naver_options or '[]'
            else:
                product_dict['naver_options'] = '[]'
            
            products_list.append(product_dict)
        
        # 전체 상품 수 로그
        print(f"📊 전체 상품 수: {len(products_list)}개")
        
        db.close()
        
        return templates.TemplateResponse("admin_products.html", {
            "request": request,
            "products": products_list  # 전체 상품 리스트 전달
        })
        
    except Exception as e:
        print(f"❌ 상품 목록 오류: {e}")
        db.close()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"상품 목록을 불러올 수 없습니다: {str(e)}"
        })

# ✅ 상품 등록 폼 (/products/add 라우트 추가 - index.html에서 사용)
@router.get("/products/add", response_class=HTMLResponse)
def product_add_form(request: Request):
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": None,
        "coupang_options": [],
        "taobao_options": [],
        "naver_options": []  # 네이버 옵션 추가
    })

# ✅ 상품 등록 처리 (/products/add POST)
@router.post("/products/add")
def product_add(
    request: Request,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: Optional[str] = Form(None),
    customs_paid: Optional[str] = Form(None),
    customs_cost: int = Form(0),
    coupang_link: Optional[str] = Form(""),
    taobao_link: Optional[str] = Form(""),
    naver_link: Optional[str] = Form(""),  # 네이버 링크 추가
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    naver_option_names: Optional[List[str]] = Form([]),  # 네이버 옵션 추가
    naver_option_prices: Optional[List[int]] = Form([]),  # 네이버 옵션 추가
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
    ])
    naver_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(naver_option_names, naver_option_prices)
    ])

    db = SessionLocal()
    
    try:
        new_product = Product(
            product_code=product_code,
            name=name,
            price=price,
            kd_paid=(kd_paid == "on"),
            customs_paid=(customs_paid == "on"),
            customs_cost=customs_cost,
            coupang_link=coupang_link,
            taobao_link=taobao_link,
            coupang_options=coupang_options,
            taobao_options=taobao_options,
            thumbnail=thumbnail,
            details=details
        )
        
        # 네이버 필드 (컬럼이 있는 경우만)
        if hasattr(Product, 'naver_link'):
            new_product.naver_link = naver_link
        if hasattr(Product, 'naver_options'):
            new_product.naver_options = naver_options
        
        db.add(new_product)
        db.commit()
        db.close()
        return RedirectResponse("/products?success=create", status_code=302)
    except IntegrityError:
        db.rollback()
        db.close()
        form_data = {
            "product_code": product_code, "name": name, "price": price,
            "kd_paid": (kd_paid == "on"), "customs_paid": (customs_paid == "on"),
            "customs_cost": customs_cost,
            "coupang_link": coupang_link, "taobao_link": taobao_link,
            "naver_link": naver_link,
            "thumbnail": thumbnail, "details": details
        }
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]"),
            "naver_options": json.loads(naver_options or "[]")
        })

# ✅ 상품 등록 폼 (기존 /products/create 유지)
@router.get("/products/create", response_class=HTMLResponse)
def product_create_form(request: Request):
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": None,
        "coupang_options": [],
        "taobao_options": [],
        "naver_options": []  # 네이버 옵션 추가
    })
    
# ✅ 상품 등록 처리 (기존 /products/create 유지)
@router.post("/products/create")
def product_create(
    request: Request,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: Optional[str] = Form(None),
    customs_paid: Optional[str] = Form(None),
    customs_cost: int = Form(0),
    coupang_link: Optional[str] = Form(""),
    taobao_link: Optional[str] = Form(""),
    naver_link: Optional[str] = Form(""),  # 네이버 링크 추가
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    naver_option_names: Optional[List[str]] = Form([]),  # 네이버 옵션 추가
    naver_option_prices: Optional[List[int]] = Form([]),  # 네이버 옵션 추가
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
    ])
    naver_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(naver_option_names, naver_option_prices)
    ])

    db = SessionLocal()
    
    try:
        new_product = Product(
            product_code=product_code,
            name=name,
            price=price,
            kd_paid=(kd_paid == "on"),
            customs_paid=(customs_paid == "on"),
            customs_cost=customs_cost,
            coupang_link=coupang_link,
            taobao_link=taobao_link,
            coupang_options=coupang_options,
            taobao_options=taobao_options,
            thumbnail=thumbnail,
            details=details
        )
        
        # 네이버 필드 (컬럼이 있는 경우만)
        if hasattr(Product, 'naver_link'):
            new_product.naver_link = naver_link
        if hasattr(Product, 'naver_options'):
            new_product.naver_options = naver_options
        
        db.add(new_product)
        db.commit()
        db.close()
        return RedirectResponse("/products?success=create", status_code=302)
    except IntegrityError:
        db.rollback()
        db.close()
        form_data = {
            "product_code": product_code, "name": name, "price": price,
            "kd_paid": (kd_paid == "on"), "customs_paid": (customs_paid == "on"),
            "customs_cost": customs_cost,
            "coupang_link": coupang_link, "taobao_link": taobao_link,
            "naver_link": naver_link,
            "thumbnail": thumbnail, "details": details
        }
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]"),
            "naver_options": json.loads(naver_options or "[]")
        })

# ✅ 상품 상세 보기
@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    db.close()
    if not product:
        return RedirectResponse("/products", status_code=302)
    
    # 네이버 옵션 파싱
    naver_options = []
    if hasattr(product, 'naver_options') and product.naver_options:
        try:
            naver_options = json.loads(product.naver_options)
        except:
            naver_options = []
    
    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "product": product,
        "coupang_options": json.loads(product.coupang_options or "[]"),
        "taobao_options": json.loads(product.taobao_options or "[]"),
        "naver_options": naver_options  # 네이버 옵션 추가
    })

# ✅ 상품 수정 폼
@router.get("/products/edit/{product_id}", response_class=HTMLResponse)
def edit_product_form(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    db.close()
    
    # 네이버 옵션 파싱
    naver_options = []
    if hasattr(product, 'naver_options') and product.naver_options:
        try:
            naver_options = json.loads(product.naver_options)
        except:
            naver_options = []
    
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": product,
        "coupang_options": json.loads(product.coupang_options or "[]"),
        "taobao_options": json.loads(product.taobao_options or "[]"),
        "naver_options": naver_options  # 네이버 옵션 추가
    })

# ✅ 상품 수정 처리
@router.post("/products/edit/{product_id}")
def edit_product(
    request: Request,  # request 파라미터 추가
    product_id: int,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: Optional[str] = Form(None),
    customs_paid: Optional[str] = Form(None),
    customs_cost: int = Form(0),
    coupang_link: Optional[str] = Form(""),
    taobao_link: Optional[str] = Form(""),
    naver_link: Optional[str] = Form(""),  # 네이버 링크 추가
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    naver_option_names: Optional[List[str]] = Form([]),  # 네이버 옵션 추가
    naver_option_prices: Optional[List[int]] = Form([]),  # 네이버 옵션 추가
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
    ])
    naver_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(naver_option_names, naver_option_prices)
    ])

    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    
    try:
        if product:
            product.product_code = product_code
            product.name = name
            product.price = price
            product.kd_paid = (kd_paid == "on")
            product.customs_paid = (customs_paid == "on")
            product.customs_cost = customs_cost
            product.coupang_link = coupang_link
            product.taobao_link = taobao_link
            product.coupang_options = coupang_options
            product.taobao_options = taobao_options
            product.thumbnail = thumbnail
            product.details = details
            
            # 네이버 필드 (컬럼이 있는 경우만)
            if hasattr(product, 'naver_link'):
                product.naver_link = naver_link
            if hasattr(product, 'naver_options'):
                product.naver_options = naver_options
            
            db.commit()
        db.close()
        return RedirectResponse("/products?success=edit", status_code=302)
    except IntegrityError:
        db.rollback()
        db.close()
        # 에러 발생 시, 현재 product 객체에 입력된 값을 덮어써서 form에 전달
        form_data_from_product = product.__dict__
        form_data_from_product.update({
             "product_code": product_code, "name": name, "price": price,
            "kd_paid": (kd_paid == "on"), "customs_paid": (customs_paid == "on"),
            "customs_cost": customs_cost,
            "coupang_link": coupang_link, "taobao_link": taobao_link,
            "naver_link": naver_link,
            "thumbnail": thumbnail, "details": details
        })
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data_from_product,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]"),
            "naver_options": json.loads(naver_options or "[]")
        })
        
# ✅ 상품 삭제
@router.post("/products/delete")
def product_delete(product_id: int = Form(...)):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    db.close()
    return RedirectResponse("/products", status_code=302)

# ✅ 상품 검색 API (자동완성)
@router.get("/search")
def search_products(q: str = Query("", description="검색어")):
    """상품 검색 API - 자동완성에 사용"""
    
    if not q or len(q.strip()) < 1:
        return JSONResponse(content=[])
    
    db = SessionLocal()
    try:
        # 검색어를 소문자로 변환
        search_term = q.strip().lower()
        
        # 상품명 또는 상품코드로 검색
        # SQLite용 쿼리 (ILIKE 대신 LIKE 사용)
        products = db.query(Product).filter(
            db.or_(
                Product.name.contains(search_term),
                Product.product_code.contains(search_term)
            )
        ).limit(10).all()
        
        # 결과를 JSON 형식으로 변환
        results = []
        for product in products:
            results.append({
                'id': product.id,
                'name': product.name,
                'product_code': product.product_code,
                'price': product.price,
                'thumbnail': product.thumbnail
            })
        
        return JSONResponse(content=results)
        
    except Exception as e:
        print(f"검색 오류: {e}")
        return JSONResponse(content=[], status_code=500)
    finally:
        db.close()

# ✅ 상품 상세 페이지 라우트 (네이버 옵션 추가)
@router.get("/product/{product_id}")
def product_page(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        db.close()
        return RedirectResponse("/products", status_code=302)
    
    # JSON 옵션 파싱
    try:
        coupang_options = json.loads(product.coupang_options) if product.coupang_options else []
    except:
        coupang_options = []
    
    try:
        taobao_options = json.loads(product.taobao_options) if product.taobao_options else []
    except:
        taobao_options = []
    
    # 네이버 옵션 파싱
    naver_options = []
    if hasattr(product, 'naver_options') and product.naver_options:
        try:
            naver_options = json.loads(product.naver_options)
        except:
            naver_options = []
    
    db.close()
    
    return templates.TemplateResponse("product_page.html", {
        "request": request,
        "product": product,
        "coupang_options": coupang_options,
        "taobao_options": taobao_options,
        "naver_options": naver_options,  # 네이버 옵션 추가
    })

# ✅ 경동 상태 업데이트 API
@router.post("/products/update-kd/{product_id}")
def update_kd_status(product_id: int, kd_paid: bool = Form(...)):
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            product.kd_paid = kd_paid
            db.commit()
            return JSONResponse({"success": True})
        return JSONResponse({"success": False, "error": "Product not found"}, status_code=404)
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        db.close()

# ✅ 관세 상태 업데이트 API
@router.post("/products/update-customs/{product_id}")
def update_customs_status(product_id: int, customs_paid: bool = Form(...)):
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            product.customs_paid = customs_paid
            db.commit()
            return JSONResponse({"success": True})
        return JSONResponse({"success": False, "error": "Product not found"}, status_code=404)
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        db.close()