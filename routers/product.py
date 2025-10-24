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

# ✅ 상품 목록 보기
@router.get("/products", response_class=HTMLResponse)
def product_list(
    request: Request,
    keyword: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1)
):
    db = SessionLocal()
    
    # 정렬 키 함수: '1-10' 같은 문자열을 (1, 10) 같은 숫자 튜플로 변환
    def custom_sort_key(product):
        try:
            parts = product.product_code.split('-')
            # 파트가 2개 이상이고 모두 숫자로 변환 가능할 때만 처리
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return (int(parts[0]), int(parts[1]))
            # 형식이 맞지 않는 경우, 맨 뒤로 보내기 위해 큰 값을 반환
            return (float('inf'),)
        except (ValueError, IndexError):
            # 그 외 예외 발생 시에도 맨 뒤로 보냄
            return (float('inf'),)

    # 검색 쿼리
    query = db.query(Product)
    if keyword:
        query = query.filter(Product.name.contains(keyword))
    
    # --- ▼▼▼ 정렬 로직 변경 ▼▼▼ ---
    # 1. DB에서 모든 검색 결과를 가져옴
    all_filtered_products = query.all()

    # 2. Python에서 직접 정렬
    sorted_products = sorted(all_filtered_products, key=custom_sort_key)
    
    # 3. 전체 아이템 수 및 페이지 수 계산
    total_products = len(sorted_products)
    total_pages = math.ceil(total_products / size)

    # 4. 현재 페이지에 해당하는 부분만 잘라내기
    offset = (page - 1) * size
    paginated_products = sorted_products[offset : offset + size]
    # --- ▲▲▲ 정렬 로직 변경 ▲▲▲ ---

    db.close()
    
    return templates.TemplateResponse("admin_products.html", {
        "request": request,
        "products": paginated_products, # 정렬 및 페이징된 최종 목록 전달
        "keyword": keyword,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": size,
        "total_products": total_products
    })
# ✅ 상품 등록 폼
@router.get("/products/create", response_class=HTMLResponse)
def product_create_form(request: Request):
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": None,
        "coupang_options": [],
        "taobao_options": []
    })
    
# ✅ 상품 등록 처리 (수정된 최종 버전)
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
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
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
            "thumbnail": thumbnail, "details": details
        }
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]")
        })


# ✅ 상품 상세 보기
@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    db.close()
    if not product:
        return RedirectResponse("/products", status_code=302)
    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "product": product,
        "coupang_options": json.loads(product.coupang_options or "[]"),
        "taobao_options": json.loads(product.taobao_options or "[]")
    })

# ✅ 상품 수정 폼
@router.get("/products/edit/{product_id}", response_class=HTMLResponse)
def edit_product_form(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    db.close()
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": product,
        "coupang_options": json.loads(product.coupang_options or "[]"),
        "taobao_options": json.loads(product.taobao_options or "[]")
    })



# ✅ 상품 수정 처리 (수정된 최종 버전)
@router.post("/products/edit/{product_id}")
def edit_product(
    request: Request, # request 파라미터 추가
    product_id: int,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: Optional[str] = Form(None),
    customs_paid: Optional[str] = Form(None),
    customs_cost: int = Form(0),
    coupang_link: Optional[str] = Form(""),
    taobao_link: Optional[str] = Form(""),
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
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
            db.commit()
        db.close()
        return RedirectResponse("/products?success=edit", status_code=302) # create -> edit 으로 수정
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
            "thumbnail": thumbnail, "details": details
        })
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data_from_product,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]")
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

# 상품 상세 페이지 라우트 (네이버 옵션 추가)
@router.get("/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int):
    """상품 상세 정보 페이지"""
    
    db = SessionLocal()
    try:
        # 상품 조회
        product = db.query(Product).filter(Product.id == product_id).first()
        
        if not product:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "상품을 찾을 수 없습니다."
            })
        
        # 옵션 파싱 함수
        def parse_options(options_str):
            if not options_str:
                return []
            
            options = []
            try:
                # JSON 형식이면 파싱
                import json
                options_data = json.loads(options_str)
                if isinstance(options_data, list):
                    return options_data
            except:
                # JSON이 아니면 텍스트로 파싱
                # 형식: "옵션1:가격1, 옵션2:가격2"
                for opt in options_str.split(','):
                    if ':' in opt:
                        name, price = opt.strip().split(':', 1)
                        try:
                            options.append({
                                'name': name.strip(),
                                'price': int(price.strip())
                            })
                        except:
                            pass
            
            return options
        
        # 각 플랫폼별 옵션 파싱
        coupang_options = parse_options(product.coupang_options)
        taobao_options = parse_options(product.taobao_options)
        
        # 네이버 옵션 파싱 (새로 추가)
        naver_options = []
        if hasattr(product, 'naver_options'):
            naver_options = parse_options(product.naver_options)
        
        return templates.TemplateResponse("product_detail.html", {
            "request": request,
            "product": product,
            "coupang_options": coupang_options,
            "taobao_options": taobao_options,
            "naver_options": naver_options  # 네이버 옵션 추가
        })
        
    finally:
        db.close()
        
@router.get("/add", response_class=HTMLResponse)
def add_product_page(request: Request):
    """새 상품 등록 페이지"""
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    
    # 빈 상품 객체로 템플릿 렌더링
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": None,  # 신규 등록이므로 None
        "coupang_options": [],
        "naver_options": [],
        "taobao_options": []
    })

# 상품 등록 처리 (POST) - /products/add
@router.post("/add", response_class=HTMLResponse)
def add_product(
    request: Request,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: bool = Form(False),
    customs_paid: bool = Form(False),
    customs_cost: int = Form(0),
    coupang_link: str = Form(None),
    naver_link: str = Form(None),
    taobao_link: str = Form(None),
    thumbnail: str = Form(None),
    details: str = Form(None),
    coupang_option_names: list = Form([]),
    coupang_option_prices: list = Form([]),
    naver_option_names: list = Form([]),
    naver_option_prices: list = Form([]),
    taobao_option_names: list = Form([]),
    taobao_option_prices: list = Form([])
):
    """새 상품 등록 처리"""
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    
    db = SessionLocal()
    
    try:
        # 상품 코드 중복 체크
        existing = db.query(Product).filter(Product.product_code == product_code).first()
        if existing:
            # 중복 에러 표시
            return templates.TemplateResponse("product_form.html", {
                "request": request,
                "error": "이미 존재하는 상품 코드입니다.",
                "product": None,
                "coupang_options": [],
                "naver_options": [],
                "taobao_options": []
            })
        
        # 옵션 데이터 JSON으로 변환
        coupang_options = []
        for i in range(len(coupang_option_names)):
            if i < len(coupang_option_prices):
                coupang_options.append({
                    "name": coupang_option_names[i],
                    "price": int(coupang_option_prices[i])
                })
        
        naver_options = []
        for i in range(len(naver_option_names)):
            if i < len(naver_option_prices):
                naver_options.append({
                    "name": naver_option_names[i],
                    "price": int(naver_option_prices[i])
                })
        
        taobao_options = []
        for i in range(len(taobao_option_names)):
            if i < len(taobao_option_prices):
                taobao_options.append({
                    "name": taobao_option_names[i],
                    "price": int(taobao_option_prices[i])
                })
        
        # 새 상품 생성
        new_product = Product(
            product_code=product_code,
            name=name,
            price=price,
            kd_paid=kd_paid,
            customs_paid=customs_paid,
            customs_cost=customs_cost,
            coupang_link=coupang_link,
            naver_link=naver_link,
            taobao_link=taobao_link,
            thumbnail=thumbnail,
            details=details,
            coupang_options=json.dumps(coupang_options) if coupang_options else None,
            naver_options=json.dumps(naver_options) if naver_options else None,
            taobao_options=json.dumps(taobao_options) if taobao_options else None
        )
        
        db.add(new_product)
        db.commit()
        
        # 등록 성공 후 상품 상세 페이지로 이동
        return RedirectResponse(f"/products/{new_product.id}", status_code=303)
        
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": f"상품 등록 중 오류가 발생했습니다: {str(e)}",
            "product": None,
            "coupang_options": [],
            "naver_options": [],
            "taobao_options": []
        })
    finally:
        db.close()